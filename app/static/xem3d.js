// Xem 3D kết cấu (v3): dựng khối (extrude) từ kết quả /api/tinh. Mặt bằng X,Y (m) -> three: x = X, z = -Y, cao = y.
// Tính năng: đổ bóng + ánh sáng hiện đại · chọn/ẩn/cô lập cấu kiện · mặt cắt theo cao độ · xuyên thấu · đo khoảng cách
//            · ống gió: KHOÉT LỖ xuyên dầm tự động + kiểm tra va chạm cột/vách + xuất danh sách lỗ · chụp ảnh · hướng dẫn.
(function () {
  const LOAI = {
    cot:    {ten: "Cột",      mau: 0xe8645a},
    dam:    {ten: "Dầm",      mau: 0xf0b341},
    san:    {ten: "Sàn",      mau: 0x7fb2e5},
    mong:   {ten: "Móng",     mau: 0x9aa3ad},
    vach:   {ten: "Vách/lõi", mau: 0xa982e0},
    ong_gio:{ten: "Ống gió",  mau: 0x2fd0c8},
  };
  const BE_TONG = ["cot", "dam", "san", "mong", "vach"];
  const MAU_HEX = k => "#" + LOAI[k].mau.toString(16).padStart(6, "0");
  const TRANG_THAI = {
    ok:   {ten: "Đạt",              mau: 0x3ecf8e, css: "#3ecf8e"},
    lon:  {ten: "Lỗ lớn > 1/3 h",   mau: 0xffb020, css: "#ffb020"},
    mep:  {ten: "Lẹm mép dầm",      mau: 0xff7a45, css: "#ff7a45"},
    dut:  {ten: "Cắt đứt dầm",      mau: 0xff4d4f, css: "#ff4d4f"},
  };
  let dang = null;
  const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const f2 = (x, n = 2) => Number(x).toFixed(n);

  // ---------- hình học 2D ----------
  function dienTich(poly) {
    const a = r => { let s = 0; for (let i = 0; i < r.length; i++) { const p = r[i], q = r[(i + 1) % r.length]; s += p[0] * q[1] - q[0] * p[1]; } return Math.abs(s) / 2; };
    return poly.reduce((t, r, i) => t + (i === 0 ? a(r) : -a(r)), 0);
  }
  // giữ phần đa giác nằm phía n·p <= c (Sutherland–Hodgman, đủ cho dầm dạng chữ nhật / lồi)
  function catNua(P, nx, ny, c) {
    const out = [], n = P.length;
    for (let i = 0; i < n; i++) {
      const a = P[i], b = P[(i + 1) % n], da = nx * a[0] + ny * a[1] - c, db = nx * b[0] + ny * b[1] - c;
      if (da <= 0) out.push(a);
      if ((da < 0 && db > 0) || (da > 0 && db < 0)) { const t = da / (da - db); out.push([a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])]); }
    }
    return out;
  }
  const dtRing = r => dienTich([r]);
  function lamSach(r) {
    const o = [];
    r.forEach(p => { const q = o[o.length - 1]; if (!q || Math.hypot(p[0] - q[0], p[1] - q[1]) > 1e-6) o.push(p); });
    if (o.length > 1 && Math.hypot(o[0][0] - o[o.length - 1][0], o[0][1] - o[o.length - 1][1]) < 1e-6) o.pop();
    return o;
  }
  // Dải ống gió = hình chữ nhật dọc đoạn a->b; w = nửa bề rộng, e0/e1 = kéo dài hai đầu
  function daiOng(a, b, w, e0, e1) {
    const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy); if (L < 1e-6) return null;
    const ux = dx / L, uy = dy / L, vx = -uy, vy = ux, ua = ux * a[0] + uy * a[1], ub = ux * b[0] + uy * b[1], va = vx * a[0] + vy * a[1];
    return {ux, uy, L, planes: [[-ux, -uy, -ua + e0], [ux, uy, ub + e1], [vx, vy, va + w], [-vx, -vy, -va + w]]};
  }
  // Tách một khối (đa giác P, cao độ y0..y1) quanh hộp ống (dải + cao độ d0..d1). Trả về null nếu không giao nhau.
  function tachKhoi(P, y0, y1, dai, d0, d1) {
    if (d1 <= y0 + 1e-6 || d0 >= y1 - 1e-6) return null;
    const parts = []; let rest = P;
    for (const h of dai.planes) {
      const ngoai = catNua(rest, -h[0], -h[1], -h[2]);
      if (ngoai.length >= 3 && dtRing(ngoai) > 1e-5) parts.push({P: ngoai, y0, y1});
      rest = catNua(rest, h[0], h[1], h[2]);
      if (rest.length < 3 || dtRing(rest) < 1e-5) return null;
    }
    if (y0 < d0 - 1e-6) parts.push({P: rest, y0, y1: d0});
    if (d1 < y1 - 1e-6) parts.push({P: rest, y0: d1, y1});
    return {parts, trong: rest};
  }

  // ---------- chiều đứng từng loại ----------
  function khoiDoc(ck, H) {
    const ts = ck.thong_so || {};
    if (ck.loai === "cot" || ck.loai === "vach") return [0, ts.cao || H];
    if (ck.loai === "dam") { const h = ts.h || 0.5, ht = ts.h_tinh != null ? ts.h_tinh : h; return [H - h, H - h + ht]; }
    if (ck.loai === "san") { const t = ts.t || 0.12; return [H - t, H]; }
    if (ck.loai === "mong") { const d = ts.day || 0.8; return [-d, 0]; }
    return null;
  }
  function hinhShape(THREE, poly) {
    const vong = poly.map(r => r.map(p => new THREE.Vector2(p[0], p[1])));
    const sh = new THREE.Shape(vong[0]);
    for (let i = 1; i < vong.length; i++) sh.holes.push(new THREE.Path(vong[i]));
    return sh;
  }

  window.xem3D = function (d) {
    if (typeof THREE === "undefined" || !THREE.OrbitControls) {
      alert("Không tải được thư viện three.js (cần mạng lần đầu). Kiểm tra kết nối rồi thử lại.");
      return;
    }
    if (dang) dang.dong();
    const ongGio = d.ong_gio || [];
    const coOng = ongGio.some(o => o.diem && o.diem.length > 1);
    const H = parseFloat((d.thong_so || {}).chieu_cao_tang) || 3.6;
    const st = {
      loc: {cot: true, dam: true, san: true, mong: true, vach: true, ong_gio: true},
      xray: false, bong: true, luoi: true, xoay: false, canhBao: false,
      khoet: true, offset: 0.2, hoMm: 25,
      cat: false, catY: 0, an: new Set(), co: null, chon: null, ruoi: null, cc: null,
      pn: innerWidth > 900, dem: [],
    };
    let objs = new Map(), holes = [], vaCham = [], nhomMain = null, nhomHo = null, tong = {};
    let hop = null, tam = null, bk = 10;

    // ---------- giao diện ----------
    const lop = document.createElement("div");
    lop.className = "x3";
    lop.innerHTML = `<style>
      .x3{position:fixed;inset:0;z-index:9999;background:#0b0e14;color:#e6ebf5;font:13px/1.45 Roboto,"Segoe UI",Arial,sans-serif;display:flex;flex-direction:column;--ac:#F47A20;--bl:#4c9aff;--pn:#121823;--ln:#222d42}
      .x3 *{box-sizing:border-box}
      .x3 button{font:inherit;color:inherit;background:#1a2336;border:1px solid #2a3957;border-radius:7px;padding:0 11px;height:30px;cursor:pointer;display:inline-flex;align-items:center;gap:6px;white-space:nowrap;transition:background .12s,border-color .12s}
      .x3 button:hover{background:#22304d;border-color:#4c6da8}
      .x3 button.on{background:var(--bl);border-color:var(--bl);color:#fff}
      .x3 button.cam{background:var(--ac);border-color:var(--ac);color:#fff}
      .x3 button:disabled{opacity:.4;cursor:default}
      .x3 input[type=number]{width:72px;height:28px;background:#0a0f19;color:#e6ebf5;border:1px solid #2a3957;border-radius:6px;padding:0 6px;font:inherit}
      .x3 input[type=range]{width:100%;accent-color:var(--ac)}
      .x3 input[type=checkbox]{accent-color:var(--bl);width:15px;height:15px;margin:0}
      .x3-top{display:flex;align-items:center;gap:10px;padding:8px 14px;background:linear-gradient(100deg,#070b14,#0e2347 70%);border-bottom:2px solid var(--ac);flex-wrap:wrap}
      .x3-top b{font-size:15px;letter-spacing:.4px} .x3-top b em{font-style:normal;color:var(--ac)}
      .x3-top .tt{opacity:.7;font-size:12px}
      .x3-main{flex:1;min-height:0;display:flex;position:relative}
      .x3-cv{flex:1;min-width:0;position:relative;overflow:hidden}
      .x3-cv canvas{display:block;outline:0}
      .x3-bar{position:absolute;left:50%;bottom:16px;transform:translateX(-50%);display:flex;gap:6px;padding:6px;background:rgba(14,20,33,.86);border:1px solid #26334f;border-radius:12px;backdrop-filter:blur(8px);box-shadow:0 10px 30px rgba(0,0,0,.5);max-width:calc(100% - 20px);flex-wrap:wrap;justify-content:center}
      .x3-bar .sep{width:1px;background:#2a3957;margin:2px 3px}
      .x3-tip{position:absolute;pointer-events:none;background:rgba(8,12,20,.92);border:1px solid #3a5078;border-radius:6px;padding:4px 9px;font-size:12px;display:none;white-space:nowrap;z-index:3}
      .x3-do{position:absolute;pointer-events:none;background:#f0b341;color:#1b1400;font-weight:600;font-size:12px;padding:2px 8px;border-radius:10px;transform:translate(-50%,-130%);white-space:nowrap;box-shadow:0 2px 8px rgba(0,0,0,.5)}
      .x3-pn{width:330px;flex:none;background:var(--pn);border-left:1px solid var(--ln);overflow:auto;display:flex;flex-direction:column}
      .x3-pn[hidden]{display:none}
      .x3-sec{border-bottom:1px solid var(--ln);padding:10px 14px 12px}
      .x3-sec h5{margin:0 0 8px;font-size:10.5px;letter-spacing:1px;text-transform:uppercase;color:#7FA6D8;display:flex;align-items:center;gap:7px}
      .x3-sec h5::before{content:"";width:3px;height:11px;background:var(--ac);border-radius:2px}
      .x3-row{display:flex;align-items:center;gap:8px;padding:3px 0}
      .x3-row label{display:flex;align-items:center;gap:8px;cursor:pointer;flex:1;min-width:0}
      .x3-row .n{margin-left:auto;color:#8b97ad;font-size:11.5px;white-space:nowrap;font-variant-numeric:tabular-nums}
      .x3-dot{width:11px;height:11px;border-radius:3px;flex:none}
      .x3-mut{color:#8b97ad;font-size:11.5px}
      .x3-chip{display:inline-block;padding:0 8px;border-radius:10px;font-size:11px;font-weight:600;color:#0b0e14}
      .x3-kv{display:grid;grid-template-columns:92px 1fr;gap:3px 8px;font-size:12.5px}
      .x3-kv span:nth-child(odd){color:#8b97ad}
      .x3-ho{display:grid;grid-template-columns:1fr auto;gap:2px 8px;padding:6px 8px;margin:4px 0;border:1px solid var(--ln);border-radius:8px;background:#0e1522;cursor:pointer;font-size:12px}
      .x3-ho:hover{border-color:#4c6da8;background:#142038}
      .x3-ho.sel{border-color:var(--ac)}
      .x3-cb{margin:4px 0;padding:5px 9px;border-left:3px solid #ff7a45;background:rgba(255,122,69,.08);border-radius:0 6px 6px 0;font-size:12px}
      .x3-ft{padding:5px 14px;background:#0e1420;border-top:1px solid var(--ln);color:#7d899f;font-size:11.5px}
      .x3-gd{position:absolute;inset:0;background:rgba(4,7,12,.72);backdrop-filter:blur(3px);display:flex;align-items:center;justify-content:center;z-index:10;padding:16px}
      .x3-gd[hidden]{display:none}
      .x3-gd>div{width:min(760px,100%);max-height:100%;overflow:auto;background:#101827;border:1px solid #2a3957;border-radius:14px;padding:20px 24px;box-shadow:0 24px 60px rgba(0,0,0,.6)}
      .x3-gd h3{margin:0 0 4px;font-size:18px} .x3-gd h4{margin:16px 0 4px;font-size:13.5px;color:#ffb27a}
      .x3-gd p,.x3-gd li{color:#c9d3e6;font-size:13px;margin:3px 0} .x3-gd ul{margin:2px 0;padding-left:20px}
      .x3-gd kbd{background:#1c2740;border:1px solid #33456b;border-bottom-width:2px;border-radius:4px;padding:0 5px;font:12px Consolas,monospace;color:#cfe0ff}
      .x3-gd .bt{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}
      @media(max-width:900px){.x3-pn{position:absolute;right:0;top:0;bottom:0;max-width:88vw;z-index:6;box-shadow:-10px 0 30px rgba(0,0,0,.5)}}
    </style>
    <div class="x3-top">
      <b>AZB <em>3D</em> · Xem kết cấu</b><span class="tt" id="x3-tt"></span><span style="flex:1"></span>
      <button id="x3-bg" title="Hiện / ẩn bảng điều khiển bên phải">☰ Bảng điều khiển</button>
      <button id="x3-hd" title="Hướng dẫn sử dụng (phím ?)">❔ Hướng dẫn</button>
      <button id="x3-dong" title="Đóng (Esc)">✕ Đóng</button>
    </div>
    <div class="x3-main">
      <div class="x3-cv" id="x3-cv">
        <div class="x3-bar" id="x3-bar">
          <button data-v="iso" title="Góc nhìn 3D (phím 1)">◇ 3D</button><button data-v="top" title="Nhìn từ trên xuống (phím 2)">▦ Trên</button>
          <button data-v="front" title="Nhìn chính diện (phím 3)">▭ Trước</button><button data-v="right" title="Nhìn bên phải (phím 4)">▯ Phải</button>
          <button data-v="fit" title="Vừa khung hình (phím F)">⤢ Vừa</button>
          <span class="sep"></span>
          <button id="x3-do" title="Đo khoảng cách: bấm 2 điểm trên mô hình (phím M)">📏 Đo</button>
          <button id="x3-xr" title="Xuyên thấu: thấy xuyên qua mọi khối (phím X)">◫ Xuyên thấu</button>
          <button id="x3-ct" title="Mặt cắt ngang theo cao độ (phím C)">✂ Mặt cắt</button>
          <button id="x3-xoay" title="Tự xoay quanh mô hình (phím R)">⟳ Tự xoay</button>
          <span class="sep"></span>
          <button id="x3-anh" title="Lưu ảnh PNG của khung nhìn hiện tại">📷 Chụp ảnh</button>
        </div>
      </div>
      <div class="x3-pn" id="x3-pn"></div>
      <div class="x3-gd" id="x3-gd" hidden></div>
    </div>
    <div class="x3-ft" id="x3-ft"></div>`;
    document.body.appendChild(lop);
    const $ = s => lop.querySelector(s);
    const kg = $("#x3-cv"), pn = $("#x3-pn");

    // ---------- three: cảnh, ánh sáng, nền ----------
    const nenCv = document.createElement("canvas"); nenCv.width = 2; nenCv.height = 256;
    { const g = nenCv.getContext("2d"), gr = g.createLinearGradient(0, 0, 0, 256); gr.addColorStop(0, "#263149"); gr.addColorStop(.55, "#141a28"); gr.addColorStop(1, "#0a0d14"); g.fillStyle = gr; g.fillRect(0, 0, 2, 256); }
    const scene = new THREE.Scene();
    scene.background = new THREE.CanvasTexture(nenCv);
    scene.fog = new THREE.Fog(0x121827, 50, 200);
    const hemi = new THREE.HemisphereLight(0xdbe7ff, 0x2b2f3a, 0.85); scene.add(hemi);
    const den = new THREE.DirectionalLight(0xfff4e0, 0.95); scene.add(den); scene.add(den.target);
    const bu = new THREE.DirectionalLight(0x9db8ff, 0.25); scene.add(bu);
    const r = new THREE.WebGLRenderer({antialias: true, powerPreference: "high-performance"});
    r.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFSoftShadowMap;
    kg.insertBefore(r.domElement, kg.firstChild);
    const cam = new THREE.PerspectiveCamera(40, 1, 0.1, 5000);
    const dk = new THREE.OrbitControls(cam, r.domElement);
    dk.enableDamping = true; dk.dampingFactor = 0.08; dk.rotateSpeed = 0.8; dk.maxPolarAngle = Math.PI / 2 - 0.02;
    const mpCat = new THREE.Plane(new THREE.Vector3(0, -1, 0), 0);
    let nenDat = null, luoi = null;

    // ---------- dựng mô hình ----------
    function xoaMo() {
      [nhomMain, nhomHo].forEach(g => { if (!g) return; scene.remove(g); g.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material && !o.userData.chung) o.material.dispose(); }); });
      objs.forEach(o => o.mat && o.mat.dispose());
    }
    function dung() {
      xoaMo();
      objs = new Map(); holes = []; vaCham = []; tong = {};
      nhomMain = new THREE.Group(); nhomHo = new THREE.Group();
      const marg = Math.max(st.hoMm, 0) / 1000;
      // 1) hộp ống gió
      const ong = [];
      ongGio.forEach((o, oi) => {
        const n = (o.diem || []).length;
        for (let i = 0; i + 1 < n; i++) {
          const a = o.diem[i], b = o.diem[i + 1], L = Math.hypot(b[0] - a[0], b[1] - a[1]); if (L < 1e-6) continue;
          const y0 = H - st.offset - o.cao, ext = o.rong / 2;
          ong.push({o, oi, a, b, y0, y1: y0 + o.cao, e0: i > 0 ? ext : 0, e1: i + 2 < n ? ext : 0, id: `og${oi}_${i}`,
            dai: daiOng(a, b, o.rong / 2 + marg, marg + (i > 0 ? ext : 0), marg + (i + 2 < n ? ext : 0)),
            daiTrue: daiOng(a, b, o.rong / 2, 0, 0)});
        }
      });
      // 2) cấu kiện bê tông
      const dsCK = (d.cau_kien || []);
      dsCK.forEach(ck => {
        const dz = khoiDoc(ck, H); if (!dz) return;
        const loai = ck.loai, bo = !!ck.loai_bo;
        const coLoi = (ck.canh_bao || []).some(c => c.muc === "loi" || c.muc === "canh_bao");
        let vol = 0; ck.hinh.forEach(p => vol += dienTich(p));
        vol *= Math.max(dz[1] - dz[0], 0);
        const o = {id: ck.id, loai, ck, dz, bo, coLoi, vol, meshes: [], edges: [], mat: null, ten: ck.ten};
        objs.set(ck.id, o);
        tong[loai] = tong[loai] || {n: 0, v: 0}; tong[loai].n++; if (!bo) tong[loai].v += vol;
        const mat = new THREE.MeshStandardMaterial({color: bo ? 0x555b66 : LOAI[loai].mau, roughness: 0.62, metalness: 0.05});
        o.mat = mat;
        const khoiTho = (poly, y0, y1) => {
          let geo;
          try { geo = new THREE.ExtrudeGeometry(poly.length > 1 || poly.holes ? hinhShape(THREE, poly) : new THREE.Shape(poly[0].map(p => new THREE.Vector2(p[0], p[1]))), {depth: Math.max(y1 - y0, 0.01), bevelEnabled: false}); }
          catch (e) { return; }
          geo.rotateX(-Math.PI / 2); geo.translate(0, y0, 0);
          themMesh(o, geo, mat, loai !== "san" && !bo);
        };
        ck.hinh.forEach(poly => {
          // Dầm: khoét lỗ cho ống gió (chỉ khi dầm là một vòng liền, không có lỗ sẵn)
          if (loai === "dam" && !bo && poly.length === 1 && ong.length) {
            let khoi = [{P: lamSach(poly[0]), y0: dz[0], y1: dz[1]}];
            ong.forEach(s => {
              const moi = [];
              khoi.forEach(k => {
                const rs = tachKhoi(k.P, k.y0, k.y1, s.dai, s.y0 - marg, s.y1 + marg);
                if (!rs) { moi.push(k); return; }
                rs.parts.forEach(x => moi.push(x));
                // ghi nhận lỗ (một lần cho mỗi khối giao nhau theo chiều đứng)
                const yb = Math.max(s.y0 - marg, k.y0), yt = Math.min(s.y1 + marg, k.y1);
                if (!holes.some(h => h.k === k && h.s === s)) {
                  const u = s.dai.ux, v = s.dai.uy, us = rs.trong.map(p => u * p[0] + v * p[1]);
                  const cx = rs.trong.reduce((t, p) => t + p[0], 0) / rs.trong.length, cy = rs.trong.reduce((t, p) => t + p[1], 0) / rs.trong.length;
                  const hD = dz[1] - dz[0], hh = yt - yb;
                  const bi = yb <= dz[0] + 1e-6, ti = yt >= dz[1] - 1e-6;
                  const tt = (bi && ti) ? "dut" : (bi || ti) ? "mep" : hh > hD / 3 + 1e-6 ? "lon" : "ok";
                  holes.push({k, s, o, ck, dam: ck.ten, rong: s.o.rong + 2 * marg, cao: hh, dai: Math.max(...us) - Math.min(...us), hD,
                    yb, yt, cx, cy, tt, ang: Math.atan2(s.b[1] - s.a[1], s.b[0] - s.a[0]), id: ck.id});
                }
              });
              khoi = st.khoet ? moi : khoi;
            });
            khoi.forEach(k => khoiTho([k.P], k.y0, k.y1));
          } else ck.hinh.length && khoiTho(poly, dz[0], dz[1]);
        });
      });

      // 3) ống gió (hộp) + va chạm với cột/vách
      ong.forEach(s => {
        const o = {id: s.id, loai: "ong_gio", ten: `Ống gió ${(s.o.rong * 1000).toFixed(0)}x${(s.o.cao * 1000).toFixed(0)}`, dz: [s.y0, s.y1], meshes: [], edges: [], bo: false, coLoi: false, vol: 0, ck: null, duct: s};
        const mat = new THREE.MeshStandardMaterial({color: LOAI.ong_gio.mau, roughness: 0.4, metalness: 0.25, transparent: true, opacity: 0.88});
        o.mat = mat; objs.set(s.id, o);
        const L = s.daiTrue.L + s.e0 + s.e1;
        const geo = new THREE.BoxGeometry(L, s.o.cao, s.o.rong);
        const ux = s.daiTrue.ux, uy = s.daiTrue.uy, off = (s.e1 - s.e0) / 2;
        const mesh = new THREE.Mesh(geo, mat);
        mesh.position.set((s.a[0] + s.b[0]) / 2 + ux * off, s.y0 + s.o.cao / 2, -((s.a[1] + s.b[1]) / 2 + uy * off));
        mesh.rotation.y = Math.atan2(s.b[1] - s.a[1], s.b[0] - s.a[0]);
        mesh.castShadow = true; mesh.receiveShadow = true;
        mesh.userData.id = s.id; o.meshes.push(mesh); nhomMain.add(mesh);
        const vien = new THREE.LineSegments(new THREE.EdgesGeometry(geo), new THREE.LineBasicMaterial({color: 0x04302e, transparent: true, opacity: 0.55}));
        vien.position.copy(mesh.position); vien.rotation.copy(mesh.rotation); o.edges.push(vien); nhomMain.add(vien);
        tong.ong_gio = tong.ong_gio || {n: 0, v: 0}; tong.ong_gio.n++;
        // va chạm cột / vách (không khoét được): chỉ cần giao nhau trên mặt bằng và chồng cao độ
        dsCK.forEach(ck => {
          if (ck.loai_bo || (ck.loai !== "cot" && ck.loai !== "vach")) return;
          const dz = khoiDoc(ck, H); if (!dz || s.y1 <= dz[0] + 1e-6 || s.y0 >= dz[1] - 1e-6) return;
          const hit = ck.hinh.some(p => tachKhoi(lamSach(p[0]), dz[0], dz[1], s.daiTrue, s.y0, s.y1));
          if (hit) { vaCham.push({ck, s, id: ck.id}); o.va = true; const oc = objs.get(ck.id); if (oc) oc.va = true; }
        });
      });
      scene.add(nhomMain);
      // 4) khung đánh dấu lỗ
      holes.forEach((h, i) => {
        const g = new THREE.BoxGeometry(Math.max(h.dai, 0.05) + 0.02, h.cao, h.rong);
        const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({color: TRANG_THAI[h.tt].mau, transparent: true, opacity: 0.28, depthWrite: false}));
        m.position.set(h.cx, (h.yb + h.yt) / 2, -h.cy); m.rotation.y = h.ang; m.userData.chung = false; m.userData.ho = i;
        const ln = new THREE.LineSegments(new THREE.EdgesGeometry(g), new THREE.LineBasicMaterial({color: TRANG_THAI[h.tt].mau}));
        ln.position.copy(m.position); ln.rotation.copy(m.rotation);
        nhomHo.add(m); nhomHo.add(ln); h.mesh = m; h.ln = ln;
      });
      scene.add(nhomHo);
    }
    function themMesh(o, geo, mat, bong) {
      const m = new THREE.Mesh(geo, mat);
      m.castShadow = bong; m.receiveShadow = true; m.userData.id = o.id;
      o.meshes.push(m); nhomMain.add(m);
      const v = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), new THREE.LineBasicMaterial({color: 0x07090e, transparent: true, opacity: 0.5}));
      o.edges.push(v); nhomMain.add(v);
    }

    // ---------- áp trạng thái hiển thị lên mô hình ----------
    function ganEmi(o, c, k) { if (o.mat && o.mat.emissive) { o.mat.emissive.setHex(c); o.mat.emissiveIntensity = k; } }
    function ap() {
      objs.forEach(o => {
        const hien = !!st.loc[o.loai] && !st.an.has(o.id) && (!st.co || st.co.has(o.id));
        o.hien = hien;
        o.meshes.forEach(m => m.visible = hien); o.edges.forEach(v => v.visible = hien);
        const mat = o.mat; if (!mat) return;
        const loiMau = o.loai === "ong_gio" ? o.va : (st.canhBao && o.coLoi) || o.va;
        mat.color.setHex(o.bo ? 0x555b66 : loiMau ? 0xff3b3b : LOAI[o.loai].mau);
        const tr0 = mat.transparent;
        if (st.xray) { mat.transparent = true; mat.opacity = 0.22; mat.depthWrite = false; }
        else if (o.loai === "san") { mat.transparent = true; mat.opacity = 0.42; mat.depthWrite = false; }
        else if (o.bo) { mat.transparent = true; mat.opacity = 0.25; mat.depthWrite = false; }
        else if (o.loai === "ong_gio") { mat.transparent = true; mat.opacity = 0.88; mat.depthWrite = true; }
        else { mat.transparent = false; mat.opacity = 1; mat.depthWrite = true; }
        if (st.chon === o.id) ganEmi(o, 0xffd166, 0.55); else if (st.ruoi === o.id) ganEmi(o, 0x4c9aff, 0.35); else ganEmi(o, 0x000000, 0);
        if (tr0 !== mat.transparent) mat.needsUpdate = true;
        o.meshes.forEach(m => m.castShadow = st.bong && !st.xray && o.loai !== "san" && !o.bo);
      });
      holes.forEach(h => { const ob = objs.get(h.id); const v = st.khoet && st.loc.dam && ob && ob.hien; h.mesh.visible = h.ln.visible = !!v; });
      r.shadowMap.enabled = st.bong; den.castShadow = st.bong;
      if (luoi) luoi.visible = st.luoi;
      r.clippingPlanes = st.cat ? [mpCat] : [];
      r.localClippingEnabled = false;
      mpCat.constant = st.catY;
    }
    function datMoiTruong() {
      hop = new THREE.Box3().setFromObject(nhomMain);
      if (hop.isEmpty()) hop.set(new THREE.Vector3(-5, 0, -5), new THREE.Vector3(5, H, 5));
      tam = hop.getCenter(new THREE.Vector3()); const kich = hop.getSize(new THREE.Vector3());
      bk = Math.max(kich.x, kich.z, kich.y, 1);
      if (nenDat) { scene.remove(nenDat); nenDat.geometry.dispose(); nenDat.material.dispose(); }
      if (luoi) { scene.remove(luoi); luoi.geometry.dispose(); luoi.material.dispose(); }
      nenDat = new THREE.Mesh(new THREE.PlaneGeometry(bk * 8, bk * 8), new THREE.ShadowMaterial({opacity: 0.38}));
      nenDat.rotation.x = -Math.PI / 2; nenDat.position.set(tam.x, hop.min.y - 0.012, tam.z); nenDat.receiveShadow = true; scene.add(nenDat);
      const n = Math.min(Math.ceil(bk * 3), 200);
      luoi = new THREE.GridHelper(Math.ceil(bk * 3), n, 0x4a5876, 0x2a3348);
      luoi.material.transparent = true; luoi.material.opacity = 0.55; luoi.position.set(tam.x, hop.min.y - 0.01, tam.z); scene.add(luoi);
      scene.fog.near = bk * 2.2; scene.fog.far = bk * 6;
      den.position.set(tam.x + bk * 0.7, hop.max.y + bk * 1.1, tam.z + bk * 0.5); den.target.position.copy(tam);
      bu.position.set(tam.x - bk, hop.max.y + bk * 0.4, tam.z - bk * 0.8);
      const sc = den.shadow.camera, e = bk * 1.1; sc.left = -e; sc.right = e; sc.top = e; sc.bottom = -e; sc.near = 0.5; sc.far = bk * 6; sc.updateProjectionMatrix();
      den.shadow.mapSize.set(2048, 2048); den.shadow.bias = -0.0006; den.shadow.normalBias = Math.min(0.03, bk * 0.0008);
      cam.near = Math.max(bk / 2000, 0.02); cam.far = bk * 40; cam.updateProjectionMatrix();
      dk.minDistance = bk * 0.02; dk.maxDistance = bk * 8;
      $("#x3-ct").dataset.min = hop.min.y; $("#x3-ct").dataset.max = hop.max.y;
      if (st.catY === 0 || st.catY > hop.max.y) st.catY = hop.max.y + 0.01;
    }

    // ---------- camera ----------
    let anim = null;
    function bay(p, t, ms = 600) { anim = {p0: cam.position.clone(), t0: dk.target.clone(), p1: p, t1: t, s: performance.now(), ms}; }
    function goc(ten) {
      const dd = bk * 1.5, c = tam.clone();
      if (ten === "top") return [new THREE.Vector3(c.x, hop.max.y + dd * 1.1, c.z + 0.001), c];
      if (ten === "front") return [new THREE.Vector3(c.x, c.y + bk * 0.08, c.z + dd * 1.2), c];
      if (ten === "right") return [new THREE.Vector3(c.x + dd * 1.2, c.y + bk * 0.08, c.z), c];
      return [new THREE.Vector3(c.x + bk * 0.9, c.y + bk * 0.8, c.z + bk * 1.1), c];
    }
    function nhin(ten) { const [p, t] = goc(ten === "fit" ? "iso" : ten); bay(p, t); }
    function bayToiVat(o) {
      const b = new THREE.Box3(); o.meshes.forEach(m => b.expandByObject(m)); if (b.isEmpty()) return;
      const c = b.getCenter(new THREE.Vector3()), s = b.getSize(new THREE.Vector3()), dist = Math.max(s.x, s.y, s.z, 0.5) * 2.4 + 1.2;
      const hu = cam.position.clone().sub(dk.target).normalize(); hu.y = Math.max(hu.y, 0.35); hu.normalize();
      bay(c.clone().add(hu.multiplyScalar(dist)), c);
    }

    function datLai() {
      const w = Math.max(kg.clientWidth, 10), h = Math.max(kg.clientHeight, 10);
      r.setSize(w, h); cam.aspect = w / h; cam.updateProjectionMatrix();
    }

    // ---------- chọn, rê chuột, đo ----------
    const ray = new THREE.Raycaster(), pt = new THREE.Vector2();
    const tip = document.createElement("div"); tip.className = "x3-tip"; kg.appendChild(tip);
    const soDo = []; let diemDo = null; const nhomDo = new THREE.Group(); scene.add(nhomDo);
    function hienDuoc() { const a = []; objs.forEach(o => { if (o.hien) o.meshes.forEach(m => a.push(m)); }); return a; }
    function ban(e) {
      const b = r.domElement.getBoundingClientRect();
      pt.set(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1);
      ray.setFromCamera(pt, cam);
      const hit = ray.intersectObjects(hienDuoc(), false).filter(h => !(st.cat && h.point.y > st.catY))[0];
      return hit || null;
    }
    function diemDoTai(e, hit) {
      const b = r.domElement.getBoundingClientRect(); let p = null;
      if (hit) {
        p = hit.point.clone();
        // hít vào đỉnh gần nhất của mặt trúng (trong 14 px)
        const g = hit.object.geometry, pos = g.attributes.position; if (hit.face && pos) {
          let tot = null, td = 1e9;
          [hit.face.a, hit.face.b, hit.face.c].forEach(i => {
            const w = new THREE.Vector3().fromBufferAttribute(pos, i); hit.object.localToWorld(w);
            const s = w.clone().project(cam), px = (s.x + 1) / 2 * b.width + b.left, py = (1 - s.y) / 2 * b.height + b.top, dd = Math.hypot(px - e.clientX, py - e.clientY);
            if (dd < td) { td = dd; tot = w; }
          });
          if (tot && td < 14) p = tot;
        }
      } else { const q = new THREE.Vector3(); ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), -(hop.min.y)), q) && (p = q); }
      return p;
    }
    function vaoDo(p) {
      const ban0 = Math.max(bk * 0.006, 0.03);
      const dot = new THREE.Mesh(new THREE.SphereGeometry(ban0, 14, 10), new THREE.MeshBasicMaterial({color: 0xf0b341, depthTest: false})); dot.position.copy(p); dot.renderOrder = 9; nhomDo.add(dot);
      if (!diemDo) { diemDo = p; return; }
      const a = diemDo, ln = new THREE.Line(new THREE.BufferGeometry().setFromPoints([a, p]), new THREE.LineBasicMaterial({color: 0xf0b341, depthTest: false})); ln.renderOrder = 9; nhomDo.add(ln);
      const el = document.createElement("div"); el.className = "x3-do"; kg.appendChild(el);
      const dist = a.distanceTo(p), ngang = Math.hypot(p.x - a.x, p.z - a.z), dung_ = Math.abs(p.y - a.y);
      el.textContent = `${f2(dist)} m  (ngang ${f2(ngang)} · đứng ${f2(dung_)})`;
      soDo.push({a, b: p, el}); diemDo = null; capNhatPn();
    }
    function xoaDo() { while (nhomDo.children.length) { const c = nhomDo.children.pop(); c.geometry && c.geometry.dispose(); c.material && c.material.dispose(); } soDo.forEach(s => s.el.remove()); soDo.length = 0; diemDo = null; capNhatPn(); }
    function datCC(on) { st.cc = on ? "do" : null; $("#x3-do").classList.toggle("on", on); r.domElement.style.cursor = on ? "crosshair" : ""; if (!on) diemDo = null; }

    let dnx = 0, dny = 0, keo = false;
    r.domElement.addEventListener("pointerdown", e => { dnx = e.clientX; dny = e.clientY; keo = false; });
    r.domElement.addEventListener("pointermove", e => {
      if (e.buttons) { if (Math.hypot(e.clientX - dnx, e.clientY - dny) > 4) keo = true; tip.style.display = "none"; return; }
      const hit = ban(e), o = hit && objs.get(hit.object.userData.id);
      const id = o ? o.id : null;
      if (id !== st.ruoi) { st.ruoi = id; ap(); }
      if (o && st.cc !== "do") {
        const b = r.domElement.getBoundingClientRect();
        tip.innerHTML = `<b>${esc(o.ten)}</b> · ${LOAI[o.loai].ten}<br><span class="x3-mut">đáy ${f2(o.dz[0])} → đỉnh ${f2(o.dz[1])} m` + (o.bo ? " · loại bỏ" : "") + (o.va ? " · <span style='color:#ff7a45'>va chạm ống gió</span>" : "") + `</span>`;
        tip.style.left = (e.clientX - b.left + 14) + "px"; tip.style.top = (e.clientY - b.top + 14) + "px"; tip.style.display = "block";
      } else tip.style.display = "none";
    });
    r.domElement.addEventListener("pointerleave", () => { tip.style.display = "none"; if (st.ruoi) { st.ruoi = null; ap(); } });
    r.domElement.addEventListener("click", e => {
      if (keo) return;
      const hit = ban(e);
      if (st.cc === "do") { const p = diemDoTai(e, hit); if (p) vaoDo(p); return; }
      st.chon = hit ? hit.object.userData.id : null; ap(); capNhatPn();
    });
    r.domElement.addEventListener("dblclick", e => { if (st.cc) return; const hit = ban(e); if (hit) { const o = objs.get(hit.object.userData.id); o && bayToiVat(o); } });

    // ---------- bảng điều khiển ----------
    function soHo() { const c = {ok: 0, lon: 0, mep: 0, dut: 0}; holes.forEach(h => c[h.tt]++); return c; }
    function capNhatPn() {
      pn.hidden = !st.pn;
      const bt = BE_TONG.reduce((t, k) => t + (tong[k] ? tong[k].v : 0), 0);
      const lopHtml = Object.keys(LOAI).filter(k => tong[k]).map(k => `<div class="x3-row"><label><input type="checkbox" data-l="${k}" ${st.loc[k] ? "checked" : ""}><span class="x3-dot" style="background:${MAU_HEX(k)}"></span>${LOAI[k].ten}</label><span class="n">${tong[k].n}${BE_TONG.includes(k) ? " · " + f2(tong[k].v, 1) + " m³" : ""}</span></div>`).join("");
      let s = `<div class="x3-sec"><h5>Lớp hiển thị</h5>${lopHtml || '<div class="x3-mut">Không có cấu kiện.</div>'}
        <div class="x3-mut" style="margin-top:6px">Bê tông ước tính theo hình học: <b style="color:#e6ebf5">${f2(bt, 1)} m³</b> (chưa trừ giao nhau; số chính thức xem bảng Khối lượng).</div>
        <div class="x3-row" style="margin-top:4px"><button data-a="hien-het" ${st.an.size || st.co ? "" : "disabled"}>Hiện tất cả (A)</button><span class="n">${st.an.size ? "đang ẩn " + st.an.size : ""}${st.co ? "đang cô lập" : ""}</span></div></div>`;
      // đối tượng đang chọn
      const o = st.chon && objs.get(st.chon);
      if (o) {
        const ck = o.ck, ts = (ck && ck.thong_so) || {};
        let kt = "";
        if (ck) { const xs = [], ys = []; ck.hinh.forEach(p => p[0].forEach(q => { xs.push(q[0]); ys.push(q[1]); })); kt = `${f2((Math.max(...xs) - Math.min(...xs)) * 1000, 0)} × ${f2((Math.max(...ys) - Math.min(...ys)) * 1000, 0)} mm (khung bao)`; }
        else if (o.duct) kt = `${f2(o.duct.o.rong * 1000, 0)} × ${f2(o.duct.o.cao * 1000, 0)} mm · dài ${f2(o.duct.daiTrue.L)} m`;
        s += `<div class="x3-sec"><h5>Đối tượng đang chọn</h5><div class="x3-kv">
          <span>Tên</span><span><b>${esc(o.ten)}</b></span><span>Loại</span><span>${LOAI[o.loai].ten}${o.bo ? " · <i>bị loại khỏi tính</i>" : ""}</span>
          ${ck ? `<span>Layer</span><span>${esc(ck.layer)}</span>` : ""}<span>Kích thước</span><span>${kt}</span>
          <span>Cao độ</span><span>${f2(o.dz[0])} → ${f2(o.dz[1])} m</span>${o.vol ? `<span>Thể tích</span><span>${f2(o.vol, 3)} m³</span>` : ""}</div>
          ${o.va ? '<div class="x3-cb">Va chạm giữa ống gió và cột/vách: không khoét được, cần dời ống hoặc hạ cao độ.</div>' : ""}
          ${ck ? (ck.canh_bao || []).map(c => `<div class="x3-cb">${esc(c.noi_dung)}</div>`).join("") : ""}
          <div class="x3-row" style="margin-top:6px;flex-wrap:wrap"><button data-a="zoom">⌖ Zoom tới</button><button data-a="an">Ẩn (H)</button><button data-a="co">Chỉ hiện nó (I)</button></div></div>`;
      } else s += `<div class="x3-sec"><h5>Đối tượng đang chọn</h5><div class="x3-mut">Bấm vào một khối để xem chi tiết. Nhấp đúp để bay tới khối đó.</div></div>`;
      // hiển thị
      s += `<div class="x3-sec"><h5>Hiển thị</h5>
        <div class="x3-row"><label><input type="checkbox" data-o="bong" ${st.bong ? "checked" : ""}>Đổ bóng</label></div>
        <div class="x3-row"><label><input type="checkbox" data-o="luoi" ${st.luoi ? "checked" : ""}>Lưới nền</label></div>
        <div class="x3-row"><label><input type="checkbox" data-o="canhBao" ${st.canhBao ? "checked" : ""}>Tô đỏ cấu kiện có cảnh báo</label></div></div>`;
      // mặt cắt
      s += `<div class="x3-sec"><h5>Mặt cắt ngang</h5>
        <div class="x3-row"><label><input type="checkbox" data-o="cat" ${st.cat ? "checked" : ""}>Bật mặt cắt (cắt bỏ phần phía trên cao độ)</label></div>
        <input type="range" id="x3-cr" min="${f2(hop.min.y)}" max="${f2(hop.max.y + 0.01)}" step="0.01" value="${st.catY}" ${st.cat ? "" : "disabled"}>
        <div class="x3-mut">Cao độ cắt: <b id="x3-cv2" style="color:#e6ebf5">${f2(st.catY)}</b> m · 0 = mặt sàn tầng. Kéo xuống để nhìn vào bên trong.</div></div>`;
      // ống gió + lỗ
      if (coOng) {
        const c = soHo(), nv = vaCham.length;
        s += `<div class="x3-sec"><h5>Ống gió &amp; khoét lỗ dầm</h5>
          <div class="x3-row"><label><input type="checkbox" data-o="khoet" ${st.khoet ? "checked" : ""}>Khoét lỗ dầm cho ống gió đi xuyên</label></div>
          <div class="x3-row"><span>Đỉnh ống thấp hơn đỉnh sàn</span><span class="n"><input type="number" id="x3-off" step="0.05" min="0" max="${H}" value="${st.offset}"> m</span></div>
          <div class="x3-row"><span>Khe hở quanh ống (mỗi phía)</span><span class="n"><input type="number" id="x3-hm" step="5" min="0" max="200" value="${st.hoMm}"> mm</span></div>
          <div class="x3-mut" style="margin:4px 0 6px">Hạ ống xuống dưới đáy dầm thì không còn lỗ. Kết quả tức thời khi đổi số.</div>
          ${holes.length ? `<div class="x3-row" style="flex-wrap:wrap;gap:6px">${["ok", "lon", "mep", "dut"].filter(k => c[k]).map(k => `<span class="x3-chip" style="background:${TRANG_THAI[k].css}">${TRANG_THAI[k].ten}: ${c[k]}</span>`).join("")}</div>` : '<div class="x3-mut">Không có ống gió nào giao với dầm.</div>'}
          ${nv ? `<div class="x3-cb">${nv} va chạm ống gió với cột/vách (tô đỏ).</div>` : ""}
          ${holes.length ? `<div style="margin-top:6px;max-height:240px;overflow:auto">${holes.map((h, i) => `<div class="x3-ho ${st.chon === h.id ? "sel" : ""}" data-h="${i}"><span><b>${esc(h.dam)}</b> · lỗ ${f2(h.rong * 1000, 0)}×${f2(h.cao * 1000, 0)}</span><span class="x3-chip" style="background:${TRANG_THAI[h.tt].css}">${TRANG_THAI[h.tt].ten}</span><span class="x3-mut">dầm cao ${f2(h.hD * 1000, 0)} mm · lỗ/dầm ${f2(h.cao / h.hD * 100, 0)}%</span><span></span></div>`).join("")}</div>
          <div class="x3-row" style="margin-top:6px"><button data-a="csv">⬇ Xuất danh sách lỗ (CSV)</button></div>` : ""}</div>`;
      }
      // số đo
      s += `<div class="x3-sec"><h5>Đo khoảng cách</h5>${soDo.length ? soDo.map((m, i) => `<div class="x3-row"><span>Số đo ${i + 1}</span><span class="n">${f2(m.a.distanceTo(m.b))} m</span></div>`).join("") : '<div class="x3-mut">Bấm nút 📏 Đo (hoặc phím M), rồi bấm 2 điểm trên mô hình.</div>'}
        ${soDo.length ? '<div class="x3-row"><button data-a="xoa-do">Xóa số đo</button></div>' : ""}</div>`;
      pn.innerHTML = s;
      $("#x3-bg").classList.toggle("on", st.pn);
    }
    pn.addEventListener("change", e => {
      const t = e.target;
      if (t.dataset.l) { st.loc[t.dataset.l] = t.checked; ap(); return; }
      if (t.dataset.o) { const k = t.dataset.o; st[k] = t.checked; if (k === "khoet" || k === "cat") { if (k === "khoet") { dung(); } ap(); } else ap(); capNhatPn(); return; }
      if (t.id === "x3-off") { st.offset = Math.max(0, parseFloat(t.value) || 0); dung(); ap(); capNhatPn(); return; }
      if (t.id === "x3-hm") { st.hoMm = Math.max(0, parseFloat(t.value) || 0); dung(); ap(); capNhatPn(); }
    });
    pn.addEventListener("input", e => { if (e.target.id === "x3-cr") { st.catY = parseFloat(e.target.value); $("#x3-cv2").textContent = f2(st.catY); ap(); } });
    pn.addEventListener("click", e => {
      const hb = e.target.closest("[data-h]"); if (hb) { const h = holes[+hb.dataset.h]; st.chon = h.id; ap(); capNhatPn();
        const c = new THREE.Vector3(h.cx, (h.yb + h.yt) / 2, -h.cy), hu = cam.position.clone().sub(dk.target).normalize(); hu.y = Math.max(hu.y, 0.4); bay(c.clone().add(hu.normalize().multiplyScalar(Math.max(h.hD, 0.6) * 5 + 2)), c); return; }
      const a = e.target.closest("[data-a]"); if (!a) return; hanhDong(a.dataset.a);
    });
    function hanhDong(k) {
      const o = st.chon && objs.get(st.chon);
      if (k === "hien-het") { st.an.clear(); st.co = null; ap(); capNhatPn(); }
      else if (k === "zoom" && o) bayToiVat(o);
      else if (k === "an" && o) { st.an.add(o.id); st.chon = null; ap(); capNhatPn(); }
      else if (k === "co" && o) { st.co = new Set([o.id]); ap(); capNhatPn(); }
      else if (k === "xoa-do") xoaDo();
      else if (k === "csv") xuatCSV();
    }
    function xuatCSV() {
      const dong = [["Dầm", "Chiều cao dầm (mm)", "Rộng lỗ (mm)", "Cao lỗ (mm)", "Dài xuyên (mm)", "Đáy lỗ (m)", "Đỉnh lỗ (m)", "Lỗ/dầm (%)", "Đánh giá", "Tọa độ X (m)", "Tọa độ Y (m)"]]
        .concat(holes.map(h => [h.dam, h.hD * 1000, h.rong * 1000, h.cao * 1000, h.dai * 1000, h.yb, h.yt, h.cao / h.hD * 100, TRANG_THAI[h.tt].ten, h.cx, h.cy].map(v => typeof v === "number" ? +v.toFixed(3) : v)));
      const csv = "﻿" + dong.map(r_ => r_.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\r\n");
      taiVe(new Blob([csv], {type: "text/csv;charset=utf-8"}), "danh_sach_lo_xuyen_dam.csv");
    }
    function taiVe(blob, ten) { const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = ten; document.body.appendChild(a); a.click(); setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 500); }
    function chupAnh() {
      r.render(scene, cam);
      const w = r.domElement.width, h = r.domElement.height, c = document.createElement("canvas"); c.width = w; c.height = h;
      const g = c.getContext("2d"); g.drawImage(r.domElement, 0, 0);
      g.font = `${Math.round(h / 48)}px Roboto, sans-serif`; g.fillStyle = "rgba(255,255,255,.65)"; g.fillText("AZB Take-off · " + (d.ten_file || ""), 14, h - 14);
      c.toBlob(b => taiVe(b, "AZB-3D-" + (d.ten_file || "mo-hinh").replace(/\.[^.]+$/, "") + ".png"));
    }

    // ---------- thanh nút ----------
    $("#x3-bar").addEventListener("click", e => { const b = e.target.closest("button"); if (b && b.dataset.v) nhin(b.dataset.v); });
    $("#x3-do").onclick = () => datCC(st.cc !== "do");
    $("#x3-xr").onclick = () => { st.xray = !st.xray; $("#x3-xr").classList.toggle("on", st.xray); ap(); };
    $("#x3-ct").onclick = () => { st.cat = !st.cat; $("#x3-ct").classList.toggle("on", st.cat); if (st.cat) { st.pn = true; if (st.catY >= hop.max.y) st.catY = hop.min.y + (hop.max.y - hop.min.y) * 0.55; } ap(); capNhatPn(); };
    $("#x3-xoay").onclick = () => { st.xoay = !st.xoay; dk.autoRotate = st.xoay; dk.autoRotateSpeed = 1.6; $("#x3-xoay").classList.toggle("on", st.xoay); };
    $("#x3-anh").onclick = chupAnh;
    $("#x3-bg").onclick = () => { st.pn = !st.pn; capNhatPn(); setTimeout(datLai, 0); };

    // ---------- hướng dẫn ----------
    const gd = $("#x3-gd");
    function moGD(m) {
      if (!m) { gd.hidden = true; return; }
      gd.innerHTML = `<div><h3>Hướng dẫn xem 3D</h3><p class="x3-mut">Mô hình dựng từ hình 2D và chiều cao đã tính, để kiểm tra nhanh và phát hiện sai sót; chưa phải mô hình BIM.</p>
        <h4>1. Di chuyển trong mô hình</h4><ul><li><b>Chuột trái</b> kéo: xoay · <b>Chuột phải</b> (hoặc <kbd>Shift</kbd> + trái): dịch · <b>Lăn chuột</b>: phóng / thu.</li>
        <li>Các nút dưới màn hình: <kbd>1</kbd> góc 3D · <kbd>2</kbd> nhìn từ trên · <kbd>3</kbd> chính diện · <kbd>4</kbd> bên phải · <kbd>F</kbd> vừa khung.</li></ul>
        <h4>2. Chọn, ẩn, cô lập cấu kiện</h4><ul><li>Bấm vào một khối để xem tên, layer, kích thước, thể tích và cảnh báo ở bảng bên phải. <b>Nhấp đúp</b> để bay tới khối đó.</li>
        <li><kbd>H</kbd> ẩn khối đang chọn · <kbd>I</kbd> chỉ hiện khối đó · <kbd>A</kbd> hiện lại tất cả. Tích / bỏ tích từng lớp (Cột, Dầm, Sàn...) ở mục <i>Lớp hiển thị</i>.</li></ul>
        <h4>3. Khoét lỗ dầm cho ống gió (tự động)</h4><ul><li>Khi bản vẽ có layer Ống gió, app tự tìm chỗ ống đi xuyên dầm và <b>khoét lỗ thật trên khối dầm</b>, có khung màu đánh dấu quanh lỗ.</li>
        <li>Chỉnh <b>Đỉnh ống thấp hơn đỉnh sàn</b> (m) và <b>Khe hở quanh ống</b> (mm) ở mục <i>Ống gió &amp; khoét lỗ dầm</i>; lỗ và danh sách cập nhật ngay. Hạ ống xuống dưới đáy dầm thì không còn lỗ.</li>
        <li>Màu đánh giá (ngưỡng tham khảo, kỹ sư kết cấu quyết định): <span class="x3-chip" style="background:${TRANG_THAI.ok.css}">Đạt</span> lỗ cao ≤ 1/3 chiều cao dầm · <span class="x3-chip" style="background:${TRANG_THAI.lon.css}">Lỗ lớn</span> cao hơn 1/3 · <span class="x3-chip" style="background:${TRANG_THAI.mep.css}">Lẹm mép</span> lỗ chạm đáy/đỉnh dầm · <span class="x3-chip" style="background:${TRANG_THAI.dut.css}">Cắt đứt</span> ống cao bằng dầm.</li>
        <li>Bấm một dòng trong danh sách lỗ để bay tới lỗ đó. Nút <b>Xuất danh sách lỗ (CSV)</b> mở được bằng Excel, dùng để gửi cho bên kết cấu duyệt.</li>
        <li>Ống đụng <b>cột / vách</b> không khoét được nên cả hai tô đỏ để bạn dời ống hoặc đổi cao độ.</li></ul>
        <h4>4. Mặt cắt, xuyên thấu</h4><ul><li><kbd>C</kbd> bật <b>Mặt cắt</b>, kéo thanh cao độ để cắt bỏ phần phía trên và nhìn vào trong (ví dụ cắt ngay dưới sàn để thấy hệ dầm cột).</li>
        <li><kbd>X</kbd> <b>Xuyên thấu</b>: mọi khối thành trong mờ, tiện soi ống gió nằm sau dầm.</li></ul>
        <h4>5. Đo khoảng cách</h4><ul><li><kbd>M</kbd> bật đo, bấm 2 điểm (tự hít vào góc gần nhất). Kết quả gồm khoảng cách thẳng, ngang và đứng. Bấm <b>Xóa số đo</b> để làm lại.</li></ul>
        <h4>6. Xuất ảnh &amp; trình bày</h4><ul><li><b>Chụp ảnh</b> lưu PNG khung nhìn hiện tại. <kbd>R</kbd> tự xoay để trình chiếu. Tắt <i>Đổ bóng</i> nếu máy yếu bị giật.</li></ul>
        <h4>Phím tắt</h4><p><kbd>Esc</kbd> bỏ chọn / thoát đo / đóng · <kbd>?</kbd> mở hướng dẫn này.</p>
        <div class="bt"><button class="cam" id="x3-gd-ok">Đã hiểu</button></div></div>`;
      gd.hidden = false; gd.querySelector("#x3-gd-ok").onclick = () => moGD(false);
      try { localStorage.setItem("azb-3d-gd", "1"); } catch (e) {}
    }
    $("#x3-hd").onclick = () => moGD(gd.hidden);
    gd.addEventListener("click", e => { if (e.target === gd) moGD(false); });

    // ---------- phím tắt ----------
    function phim(e) {
      if (e.target.tagName === "INPUT" && e.target.type !== "checkbox" && e.target.type !== "range") return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "escape") { if (!gd.hidden) moGD(false); else if (st.cc) datCC(false); else if (st.chon) { st.chon = null; ap(); capNhatPn(); } else dong(); return; }
      if (k === "?" || (k === "/" && e.shiftKey)) moGD(gd.hidden);
      else if (k === "1") nhin("iso"); else if (k === "2") nhin("top"); else if (k === "3") nhin("front"); else if (k === "4") nhin("right"); else if (k === "f") nhin("fit");
      else if (k === "x") $("#x3-xr").click(); else if (k === "c") $("#x3-ct").click(); else if (k === "m") $("#x3-do").click(); else if (k === "r") $("#x3-xoay").click();
      else if (k === "h") hanhDong("an"); else if (k === "i") hanhDong("co"); else if (k === "a") hanhDong("hien-het");
    }
    addEventListener("keydown", phim);
    $("#x3-dong").onclick = () => dong();

    // ---------- khởi động ----------
    dung(); datMoiTruong(); ap();
    { const [p, t] = goc("iso"); cam.position.copy(p); dk.target.copy(t); dk.update(); }
    datLai(); addEventListener("resize", datLai);
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(datLai) : null; ro && ro.observe(kg);
    capNhatPn();
    $("#x3-tt").textContent = `Cao tầng ${H} m · ${(d.cau_kien || []).filter(c => c.loai_bo).length} cấu kiện bị loại (xám mờ)` + (coOng ? ` · ${holes.length} lỗ xuyên dầm` : "");
    $("#x3-ft").textContent = "Chuột trái: xoay · Phải: dịch · Lăn: zoom · Bấm: chọn · Nhấp đúp: bay tới · Bấm ❔ Hướng dẫn hoặc phím ? để xem chi tiết. Khối dựng từ hình 2D và chiều cao đã tính, chưa phải mô hình BIM.";
    let chay = true;
    const bnd = new THREE.Vector3();
    (function vong() {
      if (!chay) return;
      if (anim) { const k = Math.min(1, (performance.now() - anim.s) / anim.ms), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; cam.position.lerpVectors(anim.p0, anim.p1, e); dk.target.lerpVectors(anim.t0, anim.t1, e); if (k >= 1) anim = null; }
      dk.update(); r.render(scene, cam);
      if (soDo.length) { const b = r.domElement.getBoundingClientRect(), kb = kg.getBoundingClientRect(); soDo.forEach(m => { bnd.copy(m.a).add(m.b).multiplyScalar(.5).project(cam); const vis = bnd.z < 1; m.el.style.display = vis ? "" : "none"; m.el.style.left = ((bnd.x + 1) / 2 * b.width + b.left - kb.left) + "px"; m.el.style.top = ((1 - bnd.y) / 2 * b.height + b.top - kb.top) + "px"; }); }
      requestAnimationFrame(vong);
    })();
    let daXem = false; try { daXem = !!localStorage.getItem("azb-3d-gd"); } catch (e) {}
    if (!daXem) moGD(true);

    function dong() {
      chay = false; removeEventListener("resize", datLai); removeEventListener("keydown", phim); ro && ro.disconnect();
      xoaMo(); xoaDo(); [nenDat, luoi].forEach(o => { if (o) { o.geometry.dispose(); o.material.dispose(); } });
      scene.background && scene.background.dispose && scene.background.dispose();
      dk.dispose(); r.dispose(); lop.remove(); dang = null;
    }
    dang = {dong};
  };
})();
