// Xem 3D kết cấu (v3): dựng khối (extrude) từ kết quả /api/tinh. Mặt bằng X,Y (m) -> three: x = X, z = -Y, cao = y.
// Tính năng: đổ bóng + ánh sáng hiện đại · chọn/ẩn/cô lập cấu kiện · mặt cắt theo cao độ · xuyên thấu · đo khoảng cách
//            · ống gió: KHOÉT LỖ xuyên dầm tự động + kiểm tra va chạm cột/vách + xuất danh sách lỗ · chụp ảnh · hướng dẫn.
(function () {
  const LOAI = {
    cot:    {ten: "Cột",      mau: 0xe8645a},
    dam:    {ten: "Dầm",      mau: 0xf0b341},
    san:    {ten: "Sàn",      mau: 0x7fb2e5},
    mong:   {ten: "Móng",     mau: 0x9aa3ad},
    coc:    {ten: "Cọc",      mau: 0xb08968},
    vach:   {ten: "Vách/lõi", mau: 0xa982e0},
    tuong:  {ten: "Tường",    mau: 0xe3d5b8},
    cua:    {ten: "Cửa",      mau: 0x7ec8e3},
    mai:    {ten: "Mái",      mau: 0xb5654a},
    ong_gio:{ten: "Ống gió",  mau: 0x2fd0c8},
    ong_nuoc:{ten: "Ống nước", mau: 0x3d8bff},
    ong_pccc:{ten: "Ống PCCC", mau: 0xd946a8},
    khay_cap:{ten: "Khay cáp",  mau: 0xc9a46a},
    truc:   {ten: "Tim trục", mau: 0xe14b4b},
    ve:     {ten: "Nét vẽ thêm", mau: 0xffd166},
    chu:    {ten: "Ghi chú",  mau: 0xffffff},
  };
  const THEM_LOAI = ["cot", "dam", "san", "vach", "tuong", "cua"];          // cấu kiện được nhân theo số tầng
  const NHAN_VAI = {cot: "Cột", dam: "Dầm", san: "Sàn", mong: "Móng", coc: "Cọc", vach: "Vách/lõi"};
  const MEPK = ["ong_gio", "ong_nuoc", "ong_pccc", "khay_cap"];
  const NHAT_XUONG = {ong_gio: 0.2, ong_nuoc: 0.3, ong_pccc: 0.3, khay_cap: 0.45};   // đỉnh ống thấp hơn đỉnh sàn (m), mặc định
  const CAT_DUOC = ["dam", "san", "vach"];                                           // cấu kiện có thể khoét lỗ
  const BE_TONG = ["cot", "dam", "san", "mong", "vach", "coc"];
  const MAU_HEX = k => "#" + LOAI[k].mau.toString(16).padStart(6, "0");
  const TRANG_THAI = {
    ok:   {ten: "Đạt",              mau: 0x3ecf8e, css: "#3ecf8e"},
    lon:  {ten: "Lỗ lớn",           mau: 0xffb020, css: "#ffb020"},
    mep:  {ten: "Lẹm mép",          mau: 0xff7a45, css: "#ff7a45"},
    dut:  {ten: "Cắt đứt",          mau: 0xff4d4f, css: "#ff4d4f"},
  };
  const TEN_TT = {   // tên đánh giá theo loại cấu kiện bị khoét
    dam:  {ok: "Đạt", lon: "Lỗ lớn > 1/3 h", mep: "Lẹm mép dầm", dut: "Cắt đứt dầm"},
    san:  {ok: "Đạt", lon: "Lỗ > 300 mm", mep: "Lỗ > 300 mm", dut: "Lỗ / rãnh > 600 mm"},
    vach: {ok: "Đạt", lon: "Lỗ > 300 mm", mep: "Lẹm mép vách", dut: "Cắt đứt vách"},
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

  // đa giác (gần như) lồi: dầm, vách dạng dải, mảng sàn chữ nhật. Chỉ loại này mới tách khối an toàn bằng cắt nửa mặt phẳng.
  function loiXuyen(P) {
    if (P.length < 3) return false;
    const pts = P.map(p => [p[0], p[1]]).sort((a, b) => a[0] - b[0] || a[1] - b[1]), cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
    const lo = [], up = [];
    pts.forEach(p => { while (lo.length > 1 && cr(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop(); lo.push(p); });
    for (let i = pts.length - 1; i >= 0; i--) { const p = pts[i]; while (up.length > 1 && cr(up[up.length - 2], up[up.length - 1], p) <= 0) up.pop(); up.push(p); }
    const hull = lo.slice(0, -1).concat(up.slice(0, -1));
    return hull.length >= 3 && dtRing(P) >= 0.985 * dtRing(hull);
  }


  // ---------- hình học phục vụ liên kết, tim trục, vẽ thêm ----------
  const bbVong = P => { let x0 = 1e18, y0 = 1e18, x1 = -1e18, y1 = -1e18; P.forEach(p => { if (p[0] < x0) x0 = p[0]; if (p[0] > x1) x1 = p[0]; if (p[1] < y0) y0 = p[1]; if (p[1] > y1) y1 = p[1]; }); return [x0, y0, x1, y1]; };
  function trongVong(pt, P) {
    let t = false;
    for (let i = 0, j = P.length - 1; i < P.length; j = i++) {
      const a = P[i], b = P[j];
      if ((a[1] > pt[1]) !== (b[1] > pt[1]) && pt[0] < (b[0] - a[0]) * (pt[1] - a[1]) / (b[1] - a[1]) + a[0]) t = !t;
    }
    return t;
  }
  function kcDoan(p, a, b) {
    const dx = b[0] - a[0], dy = b[1] - a[1], l2 = dx * dx + dy * dy;
    let t = l2 > 1e-12 ? ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / l2 : 0; t = Math.max(0, Math.min(1, t));
    return Math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy));
  }
  function cat2D(a, b, c, d_) {
    const o = (p, q, r) => (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]);
    return o(a, b, c) * o(a, b, d_) < 0 && o(c, d_, a) * o(c, d_, b) < 0;
  }
  // khoảng cách ngắn nhất giữa hai vòng đa giác (0 nếu chồng / chứa nhau)
  function kcVong(P, Q) {
    if (P.some(p => trongVong(p, Q)) || Q.some(p => trongVong(p, P))) return 0;
    let m = 1e18;
    for (let i = 0; i < P.length; i++) {
      const a = P[i], b = P[(i + 1) % P.length];
      for (let j = 0; j < Q.length; j++) {
        const c = Q[j], e = Q[(j + 1) % Q.length];
        if (cat2D(a, b, c, e)) return 0;
        m = Math.min(m, kcDoan(a, c, e), kcDoan(b, c, e), kcDoan(c, a, b), kcDoan(e, a, b));
      }
    }
    return m;
  }
  const vongHCN = (cx, cy, b, h) => [[cx - b / 2, cy - h / 2], [cx + b / 2, cy - h / 2], [cx + b / 2, cy + h / 2], [cx - b / 2, cy + h / 2]];
  function vongDam(a, b, w) {
    const dx = b[0] - a[0], dy = b[1] - a[1], L = Math.hypot(dx, dy) || 1, nx = -dy / L * w / 2, ny = dx / L * w / 2;
    return [[a[0] + nx, a[1] + ny], [b[0] + nx, b[1] + ny], [b[0] - nx, b[1] - ny], [a[0] - nx, a[1] - ny]];
  }
  const vongTron = (cx, cy, r, n = 14) => Array.from({length: n}, (_, i) => [cx + r * Math.cos(2 * Math.PI * i / n), cy + r * Math.sin(2 * Math.PI * i / n)]);
  function chuCai(i) { let s = ""; i++; while (i > 0) { const m = (i - 1) % 26; s = String.fromCharCode(65 + m) + s; i = Math.floor((i - 1) / 26); } return s; }
  const gom = (xs, tol) => {      // gộp các giá trị gần nhau (cột thẳng hàng) thành tim trục
    const a = xs.slice().sort((p, q) => p - q), nh = [];
    a.forEach(v => { const l = nh[nh.length - 1]; if (l && v - l.max <= tol) { l.max = v; l.s += v; l.n++; } else nh.push({max: v, s: v, n: 1}); });
    return nh.map(g => g.s / g.n);
  };
  // kích thước dài × rộng của hình gần chữ nhật (theo cạnh), dùng cho dầm / vách
  function dai_rong(P) {
    if (P.length < 3) return [0, 0];
    let u = null, Lm = 0;
    for (let i = 0; i < P.length; i++) { const a = P[i], b = P[(i + 1) % P.length], l = Math.hypot(b[0] - a[0], b[1] - a[1]); if (l > Lm) { Lm = l; u = [(b[0] - a[0]) / l, (b[1] - a[1]) / l]; } }
    if (!u) return [0, 0];
    const us = P.map(p => p[0] * u[0] + p[1] * u[1]), vs = P.map(p => -p[0] * u[1] + p[1] * u[0]);
    return [Math.max(...us) - Math.min(...us), Math.max(...vs) - Math.min(...vs)];
  }

  // ---------- chiều đứng từng loại ----------
  function khoiDoc(ck, H) {
    const ts = ck.thong_so || {}, Z = ck.Z != null ? ck.Z : H, Hc = ck.Hc != null ? ck.Hc : H;   // Z = cao độ mặt sàn của mặt bằng chứa cấu kiện, Hc = chiều cao tầng bên dưới
    if (ck.loai === "cot" || ck.loai === "vach") return [Z - Hc, Z - Hc + (ts.cao || Hc)];
    if (ck.loai === "dam") { const h = ts.h || 0.5, ht = ts.h_tinh != null ? ts.h_tinh : h; return [Z - h, Z - h + ht]; }
    if (ck.loai === "san") { const t = ts.t || 0.12; return [Z - t, Z]; }
    if (ck.loai === "tuong") { const z0 = ts.z0 || 0; return [Z - Hc + z0, Z - Hc + z0 + (ts.cao || Hc - z0)]; }
    if (ck.loai === "cua") return [Z - Hc, Z - Hc + (ts.cao || 2.1)];
    if (ck.loai === "mai") {   // z_thap / z_cao: cao độ mép thấp / mép cao của mái dốc (tính từ mặt nền); không có thì mái phẳng trên đỉnh tầng
      const b = Z - Hc + (ts.z_thap != null ? ts.z_thap : Hc), d = ts.day || 0.15;
      return [b, b + d + (ts.huong && ts.z_cao > ts.z_thap ? ts.z_cao - ts.z_thap : 0)];
    }
    if (ck.loai === "mong") { const d0 = ts.day || 0.8, z0 = ck.Z != null ? ck.Z : 0; return [z0 - d0, z0]; }
    return null;
  }
  function hinhShape(THREE, poly) {
    const vong = poly.map(r => r.map(p => new THREE.Vector2(p[0], p[1])));
    const sh = new THREE.Shape(vong[0]);
    for (let i = 1; i < vong.length; i++) sh.holes.push(new THREE.Path(vong[i]));
    return sh;
  }
  // Cụm khối chính: các khối nối nhau khi hộp mặt bằng cách nhau <= D (m). Trả về chỉ số khối trong cụm lớn nhất.
  // Dùng để khung nhìn đầu tiên ôm đúng chỗ có cấu kiện, không ôm cả bản vẽ khi cấu kiện rải rác.
  function cumChinh(boxes, D) {
    const n = boxes.length;
    if (n === 0) return [];
    if (n > 3000) return boxes.map((_, i) => i);   // quá nhiều: bỏ qua, coi như một cụm
    const cha = Array.from({length: n}, (_, i) => i);
    const goc = i => { while (cha[i] !== i) { cha[i] = cha[cha[i]]; i = cha[i]; } return i; };
    for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
      const a = boxes[i], b = boxes[j];
      const dx = Math.max(0, b[0] - a[2], a[0] - b[2]), dz = Math.max(0, b[1] - a[3], a[1] - b[3]);
      if (Math.hypot(dx, dz) <= D) cha[goc(i)] = goc(j);
    }
    const dem = new Map();
    for (let i = 0; i < n; i++) { const r = goc(i); dem.set(r, (dem.get(r) || 0) + 1); }
    let best = null, sl = -1;
    dem.forEach((c, r) => { if (c > sl) { sl = c; best = r; } });
    const kq = [];
    for (let i = 0; i < n; i++) if (goc(i) === best) kq.push(i);
    return kq;
  }

  window.xem3D = function (d) {
    if (typeof THREE === "undefined" || !THREE.OrbitControls) {
      alert("Không tải được thư viện three.js (cần mạng lần đầu). Kiểm tra kết nối rồi thử lại.");
      return;
    }
    if (dang) dang.dong();
    const nguonOng = [];
    (d.ong_gio || []).forEach((o, i) => (o.diem || []).length > 1 && nguonOng.push({loai: "ong_gio", tron: false, rong: o.rong, cao: o.cao, diem: o.diem, key: "g" + i}));
    (d.mep || []).forEach((o, i) => (o.diem || []).length > 1 && LOAI[o.loai] && nguonOng.push({loai: o.loai, tron: !!o.tron, rong: o.rong, cao: o.cao, diem: o.diem, key: "m" + i, layer: o.layer}));
    const coOng = nguonOng.length > 0;
    const macDinh = d.mep_mac_dinh || {};
    const H = parseFloat((d.thong_so || {}).chieu_cao_tang) || 3.6;
    const st = {
      loc: {cot: true, dam: true, san: true, mong: true, vach: true, tuong: true, cua: true, mai: true, ong_gio: true, ong_nuoc: true, ong_pccc: true, khay_cap: true},
      xray: false, bong: true, luoi: true, xoay: false, canhBao: false, ten: false,
      khoet: true, hoMm: 25, tt: 2.4, mep: {},
      cat: false, catY: 0, an: new Set(), co: null, chon: null, ruoi: null, cc: null,
      pn: innerWidth > 900, dem: [],
      // liên kết, làm việc từng phần, tim trục, cọc, vẽ thêm
      tab: "dt", lv: null, tang: 1, noi: true, noiMm: 300, dungSai: 50, mauKhoi: false, matBang: false,
      mb: {}, mbRef: null, sua: {}, truc: {x: [], y: []}, them: [], cocCfg: {head: null, cut: null, L: 15},
      ve: {tool: "cot", pts: [], b: 300, h: 300, w: 200, hd: 500, t: 120, d: 300, dir: "x", muc: null},
    };
    st.loc.coc = st.loc.truc = st.loc.ve = st.loc.chu = true;
    const KHOA = "azb-3d-" + (d.ten_file || "");
    const goiY = () => ({sua: st.sua, truc: st.truc, them: st.them, cocCfg: st.cocCfg, tang: st.tang, noi: st.noi, mb: st.mb, mbRef: st.mbRef});
    const dsMB = Array.isArray(d.mat_bang) && d.mat_bang.length ? d.mat_bang : null;   // nhiều mặt bằng (móng, các tầng) ghép thành một công trình
    let daLuuBV = JSON.stringify(goiY());      // bản đã lưu vào bản vẽ (so để biết còn thay đổi chưa lưu)
    function nap() {
      try {
        const j = d.ve3d || JSON.parse(localStorage.getItem(KHOA) || "null"); if (!j) return;
        ["sua", "truc", "them", "cocCfg", "mb"].forEach(k => { if (j[k]) st[k] = j[k]; });
        if (j.mbRef) st.mbRef = j.mbRef;
        if (j.tang) st.tang = j.tang;
        if (j.noi != null) st.noi = j.noi;
      } catch (e) {}
    }
    function luu() { try { localStorage.setItem(KHOA, JSON.stringify(goiY())); } catch (e) {} capLuu(); }
    const chuaLuuBV = () => JSON.stringify(goiY()) !== daLuuBV;
    function capLuu() {
      const b = lop.querySelector("#x3-luu"); if (!b) return;
      const dirty = chuaLuuBV();
      b.className = dirty ? "cam" : ""; b.textContent = dirty ? "💾 Lưu vào bản vẽ ●" : "✓ Đã lưu vào bản vẽ"; b.disabled = !d.luuVe3d;
    }
    function luuBanVe() {
      if (!d.luuVe3d) { alert("Không lưu được: 3D này không mở từ một bản vẽ trong dự án."); return; }
      d.luuVe3d(JSON.parse(JSON.stringify(goiY()))); daLuuBV = JSON.stringify(goiY()); capLuu();
    }

    // ---------- ghép nhiều mặt bằng thành một công trình (móng, tầng 1, tầng 2 ...) ----------
    const khongDau = t => String(t || "").normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/đ/gi, "d").toLowerCase();
    // Đoán loại mặt bằng: tên ghi rõ "tầng n" thì là tầng n; có móng / cọc / đà kiềng thì là mặt bằng móng; còn lại tính theo thứ tự
    function doanMB(p) {
      const t = khongDau((p.ten || "") + " " + (p.tang_goi_y || ""));
      const m = t.match(/(?:tang|floor|level|lvl|\bt)\s*[-_.:]?\s*(\d+)/);
      if (m) return {loai: "tang", tang: +m[1]};
      const coMong = p.ck.some(c => c.loai === "mong") || (p.coc || []).length > 0;
      if (coMong || /mong|foundation|\bfnd\b|dai coc|pile|da kieng|giang/.test(t)) return {loai: "mong", tang: 0};
      if (/\bmai\b|roof/.test(t)) return {loai: "mai", tang: null};
      return {loai: "tang", tang: null};
    }
    const tamCotMB = p => {   // điểm neo để căn: tâm cột, cọc (đã gộp trùng), móng
      const lay = lo => p.ck.filter(c => c.loai === lo && c.hinh.length && c.hinh[0][0].length > 2).map(c => tamVong(lamSach(c.hinh[0][0])));
      const coc = (p.coc || []).map(c => [c.x, c.y]), seen = new Set();
      const uniq = a => a.filter(q => { const k = Math.round(q[0] * 50) + "," + Math.round(q[1] * 50); if (seen.has(k)) return false; seen.add(k); return true; });
      return uniq(lay("cot").concat(coc, lay("mong"), lay("vach")));
    };
    // Căn mặt bằng p vào mặt bằng chuẩn theo vị trí cột: bỏ phiếu các độ dịch (a - b) và lấy độ dịch có nhiều cột trùng nhất
    function canTheoCot(pRef, p) {
      const A = tamCotMB(pRef).slice(0, 400), B = tamCotMB(p).slice(0, 400); if (A.length < 1 || B.length < 1) return null;
      const cell = 0.1, bin = new Map();
      A.forEach(a => B.forEach(b => { const kx = Math.round((a[0] - b[0]) / cell), ky = Math.round((a[1] - b[1]) / cell), k = kx + "," + ky; const e = bin.get(k) || {n: 0, sx: 0, sy: 0, kx, ky}; e.n++; e.sx += a[0] - b[0]; e.sy += a[1] - b[1]; bin.set(k, e); }));
      let best = null;
      bin.forEach(e => {
        let n = 0, sx = 0, sy = 0;
        for (let i = -1; i <= 1; i++) for (let j = -1; j <= 1; j++) { const q = bin.get((e.kx + i) + "," + (e.ky + j)); if (q) { n += q.n; sx += q.sx; sy += q.sy; } }
        if (!best || n > best.n) best = {n, dx: sx / n, dy: sy / n};
      });
      if (!best) return null;
      // đếm lại số cột thực sự khớp (trong 0.12 m) sau khi dịch
      let khop = 0; A.forEach(a => { if (B.some(b => Math.hypot(a[0] - (b[0] + best.dx), a[1] - (b[1] + best.dy)) < 0.12)) khop++; });
      return {dx: +best.dx.toFixed(3), dy: +best.dy.toFixed(3), n: khop};
    }
    function macDinhMB() {
      if (!dsMB) return;
      const dd = dsMB.map(doanMB), dung_ = new Set(dd.filter(x => x.loai === "tang" && x.tang != null).map(x => x.tang));
      let nx = 1; dd.forEach(x => { if (x.loai === "tang" && x.tang == null) { while (dung_.has(nx)) nx++; x.tang = nx; dung_.add(nx); } });
      const tMax = Math.max(0, ...dd.filter(x => x.loai === "tang").map(x => x.tang));
      dsMB.forEach((p, i) => {
        if (st.mb[p.key]) return;
        const x = dd[i], tg = x.loai === "mai" ? tMax + 1 : x.tang;
        st.mb[p.key] = {loai: x.loai, tang: tg, Z: x.loai === "mong" ? 0 : +(tg * H).toFixed(3), dx: 0, dy: 0, hien: true, canh: null};
      });
      if (!st.mbRef || !dsMB.some(p => p.key === st.mbRef)) {
        let b = null; dsMB.forEach(p => { const c = st.mb[p.key]; if (c.loai === "mong") return; const n = p.ck.filter(k => k.loai === "cot").length; if (!b || n > b.n) b = {n, key: p.key}; });
        st.mbRef = b ? b.key : dsMB[0].key;
      }
    }
    function tuCanMB(ep) {
      if (!dsMB) return;
      const ref = dsMB.find(p => p.key === st.mbRef); if (!ref) return;
      const bb = p => { const a = []; p.ck.forEach(c => c.hinh.forEach(h => h[0].forEach(q => a.push(q)))); return a.length ? bbVong(a) : [0, 0, 0, 0]; };
      const bR = bb(ref);
      dsMB.forEach(p => {
        const c = st.mb[p.key]; if (!c) return;
        if (p.key === st.mbRef) { c.dx = 0; c.dy = 0; c.canh = {n: -1}; return; }
        if (!ep && c.canh) return;
        const r = canTheoCot(ref, p);
        if (r && r.n >= 2) { c.dx = r.dx; c.dy = r.dy; c.canh = {n: r.n}; }
        else { const b2 = bb(p); c.dx = +(bR[0] - b2[0]).toFixed(3); c.dy = +(bR[1] - b2[1]).toFixed(3); c.canh = {n: 0}; }   // không khớp được cột: tạm căn theo góc dưới trái
      });
    }
    function ghepMB() {
      const ck = [], coc = [];
      const ds = dsMB.map((p, i) => ({p, i, c: st.mb[p.key]})).filter(x => x.c && x.c.hien && x.c.loai !== "bo");
      const Zs = [...new Set(ds.map(x => x.c.Z))].sort((a, b) => a - b);
      ds.forEach(x => {
        const k = Zs.indexOf(x.c.Z), Hc = k > 0 ? x.c.Z - Zs[k - 1] : (x.c.Z > 0 ? x.c.Z : H), dx = x.c.dx || 0, dy = x.c.dy || 0;
        const nhan = x.c.loai === "mong" ? "" : ` · T${x.c.tang}`;
        const tt = h => h.map(poly => poly.map(r => r.map(q => [q[0] + dx, q[1] + dy])));
        const coTang = ds.some(y => y.c.loai !== "mong" && y.p.ck.some(k => k.loai === "cot"));
        x.p.ck.forEach(c => {
          const cotMong = x.c.loai === "mong" && c.loai === "cot";
          if (cotMong && coTang) return;   // đã có mặt bằng tầng chứa cột thật: cột trong mặt bằng móng chỉ là cột chờ
          // chưa có mặt bằng tầng: giữ cột của mặt bằng móng, dựng từ cao độ 0 lên một tầng
          ck.push(Object.assign({}, c, {id: `${x.i}:${c.id}`, ten: c.ten + nhan, hinh: tt(c.hinh), Z: cotMong ? H : x.c.Z, Hc: cotMong ? H : Hc, mbi: x.i}));
        });
        (x.p.coc || []).forEach(c => coc.push(Object.assign({}, c, {id: `${x.i}:${c.id}`, x: c.x + dx, y: c.y + dy, mbi: x.i})));
      });
      return {ck, coc};
    }
    const lui = []; let seq = 0;
    function ghiLui() { lui.push(JSON.stringify({sua: st.sua, truc: st.truc, them: st.them, cocCfg: st.cocCfg, mb: st.mb, mbRef: st.mbRef})); if (lui.length > 60) lui.shift(); }
    nap();
    if (d.coc_bang && d.coc_bang.l_m && !(d.ve3d && d.ve3d.cocCfg) && st.cocCfg.L === 15) st.cocCfg.L = d.coc_bang.l_m;   // chiều dài cọc đọc từ bảng thống kê cọc
    macDinhMB(); tuCanMB(false);
    if (dsMB && !(d.ve3d && d.ve3d.mb)) daLuuBV = JSON.stringify(Object.assign(JSON.parse(daLuuBV), {mb: st.mb, mbRef: st.mbRef}));
    if (d.ve3d) daLuuBV = JSON.stringify(goiY());
    if (dsMB) st.tang = 1;
    st.them.forEach(m => { const n = parseInt(String(m.id).replace(/\D/g, ""), 10); if (n > seq) seq = n; });
    let objs = new Map(), holes = [], vaCham = [], vaMep = [], khongKhoet = [], thongThuy = null, nhomMain = null, nhomHo = null, nhomTruc = null, nhomMB = null, tong = {};
    let loiLK = [], soNoi = 0, soKhungLon = 0, khungMo = [0, 0, 1, 1], nhanPhu = [];
    MEPK.forEach(k => {   // mặc định cao độ + kích thước theo từng hệ thống
      const x = nguonOng.find(o => o.loai === k); if (!x) return;
      const md = macDinh[k] || {};
      st.mep[k] = {off: md.nhat_xuong != null ? md.nhat_xuong : NHAT_XUONG[k], kt: null, kt0: [Math.round(x.rong * 1000), Math.round(x.cao * 1000)], tron: x.tron};
    });
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
      .x3-cv canvas{display:block;outline:0;cursor:default}
      .x3-bar{position:absolute;left:50%;bottom:16px;transform:translateX(-50%);display:flex;gap:6px;padding:6px;background:rgba(14,20,33,.86);border:1px solid #26334f;border-radius:12px;backdrop-filter:blur(8px);box-shadow:0 10px 30px rgba(0,0,0,.5);max-width:calc(100% - 20px);flex-wrap:wrap;justify-content:center}
      .x3-bar .sep{width:1px;background:#2a3957;margin:2px 3px}
      .x3-nh{position:absolute;pointer-events:none;font-size:10.5px;font-weight:600;color:#fff;background:rgba(8,12,20,.72);border:1px solid rgba(255,255,255,.18);border-radius:4px;padding:0 5px;transform:translate(-50%,-100%);white-space:nowrap;z-index:2}
      .x3-mp{display:grid;grid-template-columns:1fr auto;gap:4px 8px;align-items:center;padding:6px 0;border-bottom:1px dashed var(--ln)}
      .x3-mp:last-of-type{border-bottom:0}
      .x3-mp .t{display:flex;align-items:center;gap:7px;font-weight:600}
      .x3-mp .f{grid-column:1/3;display:flex;gap:6px;align-items:center;flex-wrap:wrap;color:#8b97ad;font-size:12px}
      .x3-mp input[type=number]{width:62px}
      .x3-tr{position:absolute;pointer-events:none;width:24px;height:24px;border-radius:50%;border:2px solid #e14b4b;background:rgba(10,14,22,.8);color:#ffd2d2;font-size:12px;font-weight:700;display:flex;align-items:center;justify-content:center;transform:translate(-50%,-50%);z-index:2}
      .x3-tabs{display:flex;border-bottom:1px solid var(--ln);position:sticky;top:0;background:var(--pn);z-index:3}
      .x3-tabs button{flex:1;border:0;border-bottom:2px solid transparent;border-radius:0;background:none;height:36px;padding:0 4px;justify-content:center;font-size:12px}
      .x3-tabs button.on{background:#17233a;border-bottom-color:var(--ac);color:#fff}
      .x3-lv[hidden]{display:none}
      .x3-h6{margin:10px 0 4px;font-size:11px;color:#ffb27a;text-transform:uppercase;letter-spacing:.6px}
      .x3-lkrow{padding:2px 0;font-size:12.5px;line-height:1.7}
      .x3-lkrow a,.x3 a[data-go]{color:#7fb7ff;cursor:pointer;text-decoration:underline dotted;margin-right:6px}
      .x3-lv{position:absolute;left:50%;top:10px;transform:translateX(-50%);background:rgba(244,122,32,.94);color:#fff;font-weight:600;padding:5px 8px 5px 14px;border-radius:20px;display:flex;align-items:center;gap:10px;z-index:4;box-shadow:0 4px 14px rgba(0,0,0,.45)}
      .x3-lv button{height:24px;background:rgba(0,0,0,.28);border:0;border-radius:12px}
      .x3-kv input[type=number]{width:74px}
      .x3-kv input[type=text]{width:100%;height:28px;background:#0a0f19;color:#e6ebf5;border:1px solid #2a3957;border-radius:6px;padding:0 6px;font:inherit}
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
      <button id="x3-luu" title="Lưu phần vẽ thêm, tim trục, cao độ đã chỉnh vào bản vẽ (Ctrl+S). Bản vẽ 2D sẽ hiện lại các phần này.">💾 Lưu vào bản vẽ</button>
      <button id="x3-bg" title="Hiện / ẩn bảng điều khiển bên phải">☰ Bảng điều khiển</button>
      <button id="x3-hd" title="Hướng dẫn sử dụng (phím ?)">❔ Hướng dẫn</button>
      <button id="x3-dong" title="Đóng (Esc)">✕ Đóng</button>
    </div>
    <div class="x3-main">
      <div class="x3-cv" id="x3-cv">
        <div class="x3-lv" id="x3-lv" hidden></div>
        <div class="x3-bar" id="x3-bar">
          <button data-v="iso" title="Góc nhìn 3D (phím 1)">◇ 3D</button><button data-v="top" title="Nhìn từ trên xuống (phím 2)">▦ Trên</button>
          <button data-v="front" title="Nhìn chính diện (phím 3)">▭ Trước</button><button data-v="right" title="Nhìn bên phải (phím 4)">▯ Phải</button>
          <button data-v="fit" title="Vừa khung hình (phím F)">⤢ Vừa</button>
          <span class="sep"></span>
          <button id="x3-mb" title="Xem mặt bằng: nhìn từ trên, cắt ngang qua dầm, hiện nét 2D">▦ Mặt bằng</button>
          <button id="x3-ve" title="Vẽ thêm cột, dầm, sàn, cọc, trục, đường, ghi chú (phím V)">✏ Vẽ</button>
          <button id="x3-do" title="Đo khoảng cách: bấm 2 điểm trên mô hình (phím M)">📏 Đo</button>
          <button id="x3-xr" title="Xuyên thấu: thấy xuyên qua mọi khối (phím X)">◫ Xuyên thấu</button>
          <button id="x3-ct" title="Mặt cắt ngang theo cao độ (phím C)">✂ Mặt cắt</button>
          <button id="x3-xoay" title="Tự xoay quanh mô hình (phím R)">⟳ Tự xoay</button>
          <button id="x3-ten" title="Hiện tên cột, dầm, vách, sàn, móng trên mô hình (phím L)">🏷 Tên</button>
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
      [nhomMain, nhomHo, nhomMB].forEach(g => { if (!g) return; scene.remove(g); g.traverse(o => { if (o.geometry) o.geometry.dispose(); if (o.material && !o.userData.chung) o.material.dispose(); }); });
      objs.forEach(o => { o.mat && o.mat.dispose(); o.matCat && o.matCat.dispose(); });
    }
    function dung() {
      xoaMo();
      objs = new Map(); holes = []; vaCham = []; vaMep = []; khongKhoet = []; tong = {};
      nhanPhu.forEach(n => n.el.remove()); nhanPhu = [];
      nhomMain = new THREE.Group(); nhomHo = new THREE.Group();
      const marg = Math.max(st.hoMm, 0) / 1000;
      // 1) các đoạn ống (gió, nước, PCCC, khay cáp) với kích thước và cao độ đang chọn
      const ong = [];
      nguonOng.forEach(o0 => {
        const cf = st.mep[o0.loai] || {};
        const o = {loai: o0.loai, tron: o0.tron, rong: o0.rong, cao: o0.cao};
        if (o0.loai !== "ong_gio" && cf.kt) { o.rong = cf.kt[0] / 1000; o.cao = cf.kt[1] / 1000; }
        const off = cf.off != null ? cf.off : NHAT_XUONG[o0.loai], n = o0.diem.length;
        for (let i = 0; i + 1 < n; i++) {
          const a = o0.diem[i], b = o0.diem[i + 1]; if (Math.hypot(b[0] - a[0], b[1] - a[1]) < 1e-6) continue;
          const y0 = H - off - o.cao, ext = o.tron ? 0 : o.rong / 2, e0 = i > 0 ? ext : 0, e1 = i + 2 < n ? ext : 0, w = o.rong / 2 + marg + ext;
          ong.push({o, loai: o0.loai, run: o0.key, i, a, b, y0, y1: y0 + o.cao, e0, e1, id: `${o0.key}_${i}`, nut: i > 0,
            bb: [Math.min(a[0], b[0]) - w, Math.min(a[1], b[1]) - w, Math.max(a[0], b[0]) + w, Math.max(a[1], b[1]) + w],
            dai: daiOng(a, b, o.rong / 2 + marg, marg + e0, marg + e1), daiTrue: daiOng(a, b, o.rong / 2, 0, 0)});
        }
      });
      const giaoBB = (p, q) => p[0] <= q[2] && p[2] >= q[0] && p[1] <= q[3] && p[3] >= q[1];
      const bbP = P => { let x0 = 1e18, y0 = 1e18, x1 = -1e18, y1 = -1e18; P.forEach(p => { x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]); y0 = Math.min(y0, p[1]); y1 = Math.max(y1, p[1]); }); return [x0, y0, x1, y1]; };
      // 2) cấu kiện bê tông (dầm, sàn, vách được khoét lỗ cho ống đi xuyên)
      const gh = dsMB ? ghepMB() : null;
      const dsCK = dsCauKien(gh);
      const dsCoc = (gh ? gh.coc : (d.coc || []).map(c => Object.assign({}, c))).concat(st.them.filter(m => m.k === "coc").map(m => ({id: m.id, ten: m.ten, x: m.x, y: m.y, d: m.d, moi: true})));
      {
        let x0 = 1e18, y0 = 1e18, x1 = -1e18, y1 = -1e18;
        dsCK.forEach(ck => ck.hinh.forEach(p => p[0].forEach(q => { x0 = Math.min(x0, q[0]); x1 = Math.max(x1, q[0]); y0 = Math.min(y0, q[1]); y1 = Math.max(y1, q[1]); })));
        dsCoc.forEach(c => { x0 = Math.min(x0, c.x); x1 = Math.max(x1, c.x); y0 = Math.min(y0, c.y); y1 = Math.max(y1, c.y); });
        khungMo = x0 > x1 ? [-5, -5, 5, 5] : [x0, y0, x1, y1];
      }
      dsCK.forEach(ck => {
        const dz = dzCua(ck); if (!dz) return;
        const loai = ck.loai, bo = !!ck.loai_bo;
        const coLoi = (ck.canh_bao || []).some(c => c.muc === "loi" || c.muc === "canh_bao");
        let vol = 0; ck.hinh.forEach(p => vol += dienTich(p));
        vol *= Math.max(dz[1] - dz[0], 0);
        const o = {id: ck.id, loai, ck, dz, bo, coLoi, vol, meshes: [], edges: [], mat: null, ten: ck.ten, vongs: ck.hinh.map(p => lamSach(p[0])), lk: new Set(), mbi: ck.mbi};
        objs.set(ck.id, o);
        tong[loai] = tong[loai] || {n: 0, v: 0}; tong[loai].n++; if (!bo) tong[loai].v += vol;
        const mat = new THREE.MeshStandardMaterial({color: bo ? 0x555b66 : LOAI[loai].mau, roughness: 0.62, metalness: 0.05});
        o.mat = mat;
        const khoiTho = (poly, y0, y1) => {
          let geo;
          const tsm = ck.thong_so || {}, doc = loai === "mai" && tsm.huong && tsm.z_cao > tsm.z_thap;   // mái dốc: dày = day, nghiêng theo hướng huong
          try { geo = new THREE.ExtrudeGeometry(poly.length > 1 ? hinhShape(THREE, poly) : new THREE.Shape(poly[0].map(p => new THREE.Vector2(p[0], p[1]))), {depth: Math.max(doc ? (tsm.day || 0.15) : y1 - y0, 0.01), bevelEnabled: false}); }
          catch (e) { return; }
          geo.rotateX(-Math.PI / 2);
          if (doc) {
            const pos = geo.attributes.position, u = tsm.huong, pr = i => pos.getX(i) * u[0] + (-pos.getZ(i)) * u[1];
            let pmin = 1e18, pmax = -1e18;
            for (let i = 0; i < pos.count; i++) { const v = pr(i); if (v < pmin) pmin = v; if (v > pmax) pmax = v; }
            const dd = (tsm.z_cao - tsm.z_thap) / Math.max(pmax - pmin, 1e-6);
            for (let i = 0; i < pos.count; i++) pos.setY(i, pos.getY(i) + (pr(i) - pmin) * dd);
            pos.needsUpdate = true; geo.computeVertexNormals();
          }
          geo.translate(0, y0, 0);
          themMesh(o, geo, mat, loai !== "san" && !bo);
        };
        const catDuoc = CAT_DUOC.includes(loai) && !bo && ong.length > 0;
        let phucTap = false;
        ck.hinh.forEach(poly => {
          if (catDuoc && poly.length === 1 && loiXuyen(poly[0])) {
            let khoi = [{P: lamSach(poly[0]), y0: dz[0], y1: dz[1]}];
            for (const s of ong) {
              if (khoi.length > 300) { khongKhoet.push(`${ck.ten} (quá nhiều lỗ, dừng khoét)`); break; }
              const moi = [];
              khoi.forEach(k => {
                if (!giaoBB(bbP(k.P), s.bb)) { moi.push(k); return; }
                const rs = tachKhoi(k.P, k.y0, k.y1, s.dai, s.y0 - marg, s.y1 + marg);
                if (!rs) { moi.push(k); return; }
                rs.parts.forEach(x => moi.push(x));
                const yb = Math.max(s.y0 - marg, k.y0), yt = Math.min(s.y1 + marg, k.y1);
                if (!holes.some(h => h.k === k && h.s === s)) {
                  const u = s.dai.ux, v = s.dai.uy, us = rs.trong.map(p => u * p[0] + v * p[1]);
                  const cx = rs.trong.reduce((t, p) => t + p[0], 0) / rs.trong.length, cy = rs.trong.reduce((t, p) => t + p[1], 0) / rs.trong.length;
                  const hh = yt - yb, rongLo = s.o.rong + 2 * marg, dai = Math.max(...us) - Math.min(...us);
                  holes.push({k, s, host: ck, hLoai: loai, dam: ck.ten, rong: rongLo, cao: hh, dai, hD: dz[1] - dz[0], yb, yt, cx, cy,
                    tt: danhGia(loai, hh, rongLo, dai, yb, yt, dz), ang: Math.atan2(s.b[1] - s.a[1], s.b[0] - s.a[0]), id: ck.id});
                }
              });
              if (st.khoet) khoi = moi;
            }
            khoi.forEach(k => khoiTho([k.P], k.y0, k.y1));
          } else {
            if (catDuoc && poly[0]) { const bp = bbP(poly[0]); if (ong.some(s => giaoBB(bp, s.bb) && s.y1 > dz[0] + 1e-6 && s.y0 < dz[1] - 1e-6)) phucTap = true; }
            khoiTho(poly, dz[0], dz[1]);
          }
        });
        if (phucTap) khongKhoet.push(`${ck.ten} (${LOAI[loai].ten} hình phức tạp)`);
      });
      dungCoc(dsCoc);
      nhanTang();
      const nang = {dut: 0, mep: 1, lon: 2, ok: 3};
      holes.sort((p, q) => nang[p.tt] - nang[q.tt]);

      // 3) ống: dựng khối + va chạm với cột + giao cắt giữa các hệ thống MEP
      ong.forEach(s => {
        const kt = s.o.tron ? `Ø${f2(s.o.rong * 1000, 0)}` : `${f2(s.o.rong * 1000, 0)}×${f2(s.o.cao * 1000, 0)}`;
        const o = {id: s.id, loai: s.loai, ten: `${LOAI[s.loai].ten} ${kt}`, dz: [s.y0, s.y1], meshes: [], edges: [], bo: false, coLoi: false, vol: 0, ck: null, duct: s, kt};
        const mat = new THREE.MeshStandardMaterial({color: LOAI[s.loai].mau, roughness: 0.4, metalness: 0.25, transparent: true, opacity: 0.88});
        o.mat = mat; objs.set(s.id, o);
        const L = s.daiTrue.L + s.e0 + s.e1, ux = s.daiTrue.ux, uy = s.daiTrue.uy, off = (s.e1 - s.e0) / 2;
        const geo = s.o.tron ? new THREE.CylinderGeometry(s.o.rong / 2, s.o.rong / 2, L, 20) : new THREE.BoxGeometry(L, s.o.cao, s.o.rong);
        if (s.o.tron) geo.rotateZ(Math.PI / 2);
        const dat = (g, x, y, z, ry) => {
          const mesh = new THREE.Mesh(g, mat); mesh.position.set(x, y, z); mesh.rotation.y = ry || 0;
          mesh.castShadow = true; mesh.receiveShadow = true; mesh.userData.id = s.id; o.meshes.push(mesh); nhomMain.add(mesh);
          const vien = new THREE.LineSegments(new THREE.EdgesGeometry(g, 30), new THREE.LineBasicMaterial({color: 0x06121a, transparent: true, opacity: 0.55}));
          vien.position.copy(mesh.position); vien.rotation.copy(mesh.rotation); o.edges.push(vien); nhomMain.add(vien);
        };
        dat(geo, (s.a[0] + s.b[0]) / 2 + ux * off, s.y0 + s.o.cao / 2, -((s.a[1] + s.b[1]) / 2 + uy * off), Math.atan2(s.b[1] - s.a[1], s.b[0] - s.a[0]));
        if (s.o.tron && s.nut) dat(new THREE.SphereGeometry(s.o.rong / 2, 16, 12), s.a[0], s.y0 + s.o.cao / 2, -s.a[1], 0);
        tong[s.loai] = tong[s.loai] || {n: 0, v: 0}; tong[s.loai].n++;
        dsCK.forEach(ck => {
          if (ck.loai_bo || ck.loai !== "cot") return;
          const dz = dzCua(ck); if (!dz || s.y1 <= dz[0] + 1e-6 || s.y0 >= dz[1] - 1e-6) return;
          const hit = ck.hinh.some(p => giaoBB(bbP(p[0]), s.bb) && tachKhoi(lamSach(p[0]), dz[0], dz[1], s.daiTrue, s.y0, s.y1));
          if (hit) { const oc = objs.get(ck.id); vaCham.push({ck, s, id: ck.id}); o.va = true; o.vaGhi = "Ống đụng cột"; if (oc) { oc.va = true; oc.vaGhi = "Va chạm ống"; } }
        });
      });
      // giao cắt giữa hai tuyến MEP khác nhau (cắt ngang hoàn toàn nhau, chồng cao độ)
      const hcn = s => { const w = s.o.rong / 2, ux = s.daiTrue.ux, uy = s.daiTrue.uy, vx = -uy, vy = ux; return [[s.a[0] + vx * w, s.a[1] + vy * w], [s.b[0] + vx * w, s.b[1] + vy * w], [s.b[0] - vx * w, s.b[1] - vy * w], [s.a[0] - vx * w, s.a[1] - vy * w]]; };
      for (let i = 0; i < ong.length && vaMep.length < 200; i++) for (let j = i + 1; j < ong.length; j++) {
        const A = ong[i], B = ong[j];
        if (A.run === B.run || !giaoBB(A.bb, B.bb) || A.y1 <= B.y0 + 1e-3 || B.y1 <= A.y0 + 1e-3) continue;
        let P = hcn(A); for (const h of B.daiTrue.planes) { P = catNua(P, h[0], h[1], h[2]); if (P.length < 3) break; }
        if (P.length < 3) continue;
        if (dtRing(P) >= 0.85 * A.o.rong * B.o.rong) {
          vaMep.push({a: A, b: B}); [A, B].forEach(x => { const ob = objs.get(x.id); ob.va = true; ob.vaGhi = "Giao cắt với tuyến MEP khác"; });
        }
      }
      scene.add(nhomMain);
      thongThuy = ong.length ? Math.min(...ong.map(s => s.y0)) : null;
      // 4) khung đánh dấu lỗ
      holes.forEach((h, i) => {
        const g = new THREE.BoxGeometry(Math.max(h.dai, 0.05) + 0.02, h.cao, h.rong);
        const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({color: TRANG_THAI[h.tt].mau, transparent: true, opacity: 0.28, depthWrite: false}));
        m.position.set(h.cx, (h.yb + h.yt) / 2, -h.cy); m.rotation.y = h.ang; m.userData.ho = i;
        const ln = new THREE.LineSegments(new THREE.EdgesGeometry(g), new THREE.LineBasicMaterial({color: TRANG_THAI[h.tt].mau}));
        ln.position.copy(m.position); ln.rotation.copy(m.rotation);
        nhomHo.add(m); nhomHo.add(ln); h.mesh = m; h.ln = ln;
      });
      scene.add(nhomHo);
      dungVeThem();
      tinhLienKet();
      dungTruc();
      dungMatBang();
      if (st.chon && !objs.has(st.chon)) st.chon = null;
      if (st.lv && !objs.has(st.lv)) st.lv = null;
      dungNhan();
    }

    // ---------- dữ liệu cấu kiện: gộp cấu kiện từ bản vẽ + phần vẽ thêm, nối dầm vào cột, chỉnh cao độ ----------
    function itemCK(m) {
      const b0 = {id: m.id, ten: m.ten || m.id, nhan: "", layer: "Vẽ thêm trong 3D", nguon: "3D", canh_bao: [], loai_bo: false, moi: true, item: m};
      if (m.Z != null) { b0.Z = m.Z; b0.Hc = H; }
      if (m.k === "cot") return Object.assign(b0, {loai: "cot", thong_so: {}, hinh: [[vongHCN(m.x, m.y, m.b, m.h)]]});
      if (m.k === "dam") return Object.assign(b0, {loai: "dam", thong_so: {h: m.h, b: m.w}, hinh: [[vongDam(m.a, m.b, m.w)]]});
      if (m.k === "san") return Object.assign(b0, {loai: "san", thong_so: {t: m.t}, hinh: [[[[m.x0, m.y0], [m.x1, m.y0], [m.x1, m.y1], [m.x0, m.y1]]]]});
      return null;
    }
    function dsCauKien(gh) {
      const ds = (gh ? gh.ck : d.cau_kien || []).slice();
      st.them.forEach(m => { const c = itemCK(m); if (c) ds.push(c); });
      soNoi = 0;
      // Hình "dầm" rộng hơn 1,2 m không phải một dầm mà là đường bao khung dầm / ô dầm: dựng thành khối đặc sẽ thành một tấm lớn, nên bỏ khỏi 3D
      const ra = ds.filter(c => { if (c.loai !== "dam" || c.hinh.length < 1 || !c.hinh[0][0] || c.hinh[0][0].length < 3) return true; const r = dai_rong(lamSach(c.hinh[0][0])); return Math.min(r[0], r[1]) <= 1.2; });
      soKhungLon = ds.length - ra.length; ds.length = 0; ra.forEach(c => ds.push(c));
      return st.noi ? noiDam(ds) : ds;
    }
    // Dầm vẽ rời khỏi cột / vách một khe nhỏ thì kéo dài đầu dầm cho chạm mặt cột, như thi công thực tế.
    function noiDam(ds) {
      const tol = st.noiMm / 1000;
      const gan = ds.filter(c => !c.loai_bo && (c.loai === "cot" || c.loai === "vach") && c.hinh.length).map(c => c.hinh.map(p => ({R: lamSach(p[0]), mbi: c.mbi}))).flat();
      if (!gan.length) return ds;
      return ds.map(ck => {
        if (ck.loai !== "dam" || ck.loai_bo || ck.hinh.length !== 1) return ck;
        const P = lamSach(ck.hinh[0][0]); if (P.length !== 4) return ck;
        let u = null, Lm = 0;
        for (let i = 0; i < 4; i++) { const a = P[i], b = P[(i + 1) % 4], l = Math.hypot(b[0] - a[0], b[1] - a[1]); if (l > Lm) { Lm = l; u = [(b[0] - a[0]) / l, (b[1] - a[1]) / l]; } }
        if (!u) return ck;
        const v = [-u[1], u[0]], us = P.map(p => p[0] * u[0] + p[1] * u[1]), vs = P.map(p => p[0] * v[0] + p[1] * v[1]);
        const u0 = Math.min(...us), u1 = Math.max(...us), v0 = Math.min(...vs), v1 = Math.max(...vs);
        let n0 = u0, n1 = u1, best0 = tol + 1e-9, best1 = tol + 1e-9;
        gan.forEach(({R, mbi: cm}) => {
          if (cm !== ck.mbi) return;
          const cu = R.map(p => p[0] * u[0] + p[1] * u[1]), cv = R.map(p => p[0] * v[0] + p[1] * v[1]);
          if (Math.min(Math.max(...cv), v1) - Math.max(Math.min(...cv), v0) < 0.02) return;
          const cmin = Math.min(...cu), cmax = Math.max(...cu), g0 = u0 - cmax, g1 = cmin - u1;
          if (g0 > 0.003 && g0 < best0) { best0 = g0; n0 = cmax; }
          if (g1 > 0.003 && g1 < best1) { best1 = g1; n1 = cmin; }
        });
        if (n0 === u0 && n1 === u1) return ck;
        soNoi++;
        const pt = (a, b) => [a * u[0] + b * v[0], a * u[1] + b * v[1]];
        return Object.assign({}, ck, {hinh: [[[pt(n0, v0), pt(n1, v0), pt(n1, v1), pt(n0, v1)]]], noiThem: [u0 - n0, n1 - u1]});
      });
    }
    function dzCua(ck) {
      const dz = khoiDoc(ck, H); if (!dz) return null;
      const sc = st.sua[ck.id]; if (!sc) return dz;
      const y0 = sc.y0 != null ? sc.y0 : dz[0], y1 = sc.y1 != null ? sc.y1 : dz[1];
      return y1 > y0 + 0.01 ? [y0, y1] : dz;
    }
    function thongSoCoc(c, dayMax) {
      const sc = st.sua[c.id] || {}, cf = st.cocCfg;
      const cut = sc.cut != null ? sc.cut : cf.cut != null ? cf.cut : -dayMax + 0.1;
      const head = sc.head != null ? sc.head : cf.head != null ? cf.head : cut + 0.5;
      const L = Math.max(0.1, sc.L != null ? sc.L : cf.L), D = Math.max(0.05, sc.d != null ? sc.d : c.d);
      return {cut, head, L, D, tip: head - L};
    }
    // Cọc: thân cọc từ mũi đến cao độ cắt (màu cọc), phần đầu cọc bị cắt bỏ từ cao độ cắt đến cao độ đầu cọc (đỏ mờ)
    function dungCoc(dsCoc) {
      let dayMax = 0; objs.forEach(o => { if (o.loai === "mong" && !o.bo) dayMax = Math.max(dayMax, -o.dz[0]); });
      if (!dayMax) dayMax = 0.8;
      dsCoc.forEach(c => {
        const t = thongSoCoc(c, dayMax), r = t.D / 2, tren = Math.min(t.cut, t.head), hThan = Math.max(tren - t.tip, 0.05), dCat = Math.max(t.head - t.cut, 0);
        const mat = new THREE.MeshStandardMaterial({color: LOAI.coc.mau, roughness: 0.7, metalness: 0.05});
        const o = {id: c.id, loai: "coc", ten: c.ten, dz: [t.tip, Math.max(t.head, t.cut)], meshes: [], edges: [], bo: false, coLoi: t.cut > t.head + 1e-6, vol: Math.PI * r * r * hThan, ck: null, mat, matCat: null,
          coc: Object.assign({x: c.x, y: c.y, moi: !!c.moi, layer: c.layer, dCat}, t), vongs: [vongTron(c.x, c.y, r)], lk: new Set(), moi: !!c.moi, mbi: c.mbi};
        objs.set(c.id, o);
        const them = (geo, m, cat) => {
          const mesh = new THREE.Mesh(geo, m); mesh.userData.id = c.id; mesh.userData.cat = !!cat; mesh.castShadow = !cat; mesh.receiveShadow = true; o.meshes.push(mesh); nhomMain.add(mesh);
          return mesh;
        };
        const m1 = them(new THREE.CylinderGeometry(r, r, hThan, 24), mat, false); m1.position.set(c.x, t.tip + hThan / 2, -c.y);
        const v = new THREE.LineSegments(new THREE.EdgesGeometry(m1.geometry, 30), new THREE.LineBasicMaterial({color: 0x07090e, transparent: true, opacity: 0.45}));
        v.position.copy(m1.position); o.edges.push(v); nhomMain.add(v);
        if (dCat > 1e-3) {
          o.matCat = new THREE.MeshStandardMaterial({color: 0xff4d4f, roughness: 0.6, transparent: true, opacity: 0.55, depthWrite: false});
          const m2 = them(new THREE.CylinderGeometry(r, r, dCat, 24), o.matCat, true); m2.position.set(c.x, t.cut + dCat / 2, -c.y);
        }
        const tg = tong.coc = tong.coc || {n: 0, v: 0, cat: 0}; tg.n++; tg.v += o.vol; tg.cat += Math.PI * r * r * dCat;
      });
    }
    function nhanTang() {
      if (st.tang <= 1 || dsMB) return;
      const goc = [...objs.values()].filter(o => THEM_LOAI.includes(o.loai) && o.ck);
      for (let k = 1; k < st.tang; k++) goc.forEach(b => {
        const o = Object.assign({}, b, {id: `${b.id}@${k}`, ten: `${b.ten} · T${k + 1}`, dz: [b.dz[0] + k * H, b.dz[1] + k * H], meshes: [], edges: [], base: b.id, tang: k, mat: b.mat.clone(), va: false, lk: new Set()});
        b.meshes.forEach(m => { const c = new THREE.Mesh(m.geometry, o.mat); c.position.copy(m.position); c.position.y += k * H; c.castShadow = m.castShadow; c.receiveShadow = true; c.userData.id = o.id; o.meshes.push(c); nhomMain.add(c); });
        b.edges.forEach(v => { const c = new THREE.LineSegments(v.geometry, v.material); c.position.copy(v.position); c.position.y += k * H; o.edges.push(c); nhomMain.add(c); });
        objs.set(o.id, o);
        const tg = tong[o.loai]; tg.n++; if (!o.bo) tg.v += o.vol;
      });
    }
    // Liên kết: hai cấu kiện liên kết khi hình chiếu mặt bằng chạm / chồng nhau (trong dung sai) và khoảng cao độ chạm nhau
    function tinhLienKet() {
      loiLK = [];
      const tol = st.dungSai / 1000;
      const ds = [...objs.values()].filter(o => o.vongs && !o.base && !o.bo && o.vongs.length);
      ds.forEach(o => { o.lk = new Set(); const bs = o.vongs.map(bbVong); o.bbx = [Math.min(...bs.map(b => b[0])), Math.min(...bs.map(b => b[1])), Math.max(...bs.map(b => b[2])), Math.max(...bs.map(b => b[3]))]; });
      const khongNoi = (a, b) => a.loai === b.loai && a.mbi === b.mbi && (a.loai === "cot" || a.loai === "san" || a.loai === "coc");
      for (let i = 0; i < ds.length; i++) for (let j = i + 1; j < ds.length; j++) {
        const a = ds[i], b = ds[j];
        if (khongNoi(a, b) || a.bbx[0] > b.bbx[2] + tol || b.bbx[0] > a.bbx[2] + tol || a.bbx[1] > b.bbx[3] + tol || b.bbx[1] > a.bbx[3] + tol) continue;
        if (a.dz[0] > b.dz[1] + tol || b.dz[0] > a.dz[1] + tol) continue;
        if (a.vongs.some(P => b.vongs.some(Q => kcVong(P, Q) <= tol))) { a.lk.add(b.id); b.lk.add(a.id); }
      }
      if (st.tang > 1) objs.forEach(o => {
        if (!o.base) return;
        const b = objs.get(o.base); if (!b) return;
        b.lk.forEach(n => { const on = objs.get(n); if (on && THEM_LOAI.includes(on.loai)) o.lk.add(`${n}@${o.tang}`); });
        if (o.loai === "cot" || o.loai === "vach") {
          const duoi = o.tang === 1 ? b.id : `${b.id}@${o.tang - 1}`, od = objs.get(duoi);
          if (od) { o.lk.add(duoi); od.lk.add(o.id); }
        }
      });
      const dem = (o, ks) => [...o.lk].filter(id => { const x = objs.get(id); return x && ks.includes(x.loai); }).length;
      const coMong = ds.some(o => o.loai === "mong"), coCoc = ds.some(o => o.loai === "coc");
      const bao = (o, nd) => loiLK.push({id: o.id, nd});
      ds.forEach(o => {
        if (!o.lk.size) bao(o, "Rời rạc: chưa chạm cấu kiện nào");
        else if (o.loai === "cot" && coMong && !dem(o, ["mong", "coc"]) && !(o.dz[0] > 0.05 && dem(o, ["cot", "vach"]))) bao(o, "Cột chưa đặt trên móng / chưa nối với cột tầng dưới");
        else if (o.loai === "dam" && dem(o, ["cot", "vach", "dam"]) < 2) bao(o, "Dầm chưa tựa đủ 2 đầu (cột / vách / dầm)");
        else if (o.loai === "mong" && coCoc && !dem(o, ["coc"])) bao(o, "Móng chưa có cọc");
        else if (o.loai === "coc" && coMong && !dem(o, ["mong"])) bao(o, "Cọc không nằm dưới móng");
        else if (o.loai === "san" && !dem(o, ["dam", "vach", "cot"])) bao(o, "Sàn chưa chạm dầm / vách / cột");
      });
    }
    const vaiTro = o => {
      if (!st.lv) return 2;
      if (o.id === st.lv) return 2;
      const f = objs.get(st.lv);
      return f && f.lk && f.lk.has(o.id) ? 1 : 0;
    };
    const nhanHTML = (cls, txt) => { const el = document.createElement("div"); el.className = cls; el.textContent = txt; kg.appendChild(el); return el; };
    function xoaNhanPhu(k) { nhanPhu = nhanPhu.filter(n => { if (n.k === k) { n.el.remove(); return false; } return true; }); }
    // Tim trục: đường đứng (trục số, x = const) và đường ngang (trục chữ, y = const); chọn được, sửa tên / vị trí được
    function dungTruc() {
      [...objs.keys()].filter(k => k.startsWith("truc:")).forEach(k => objs.delete(k));
      if (nhomTruc) { scene.remove(nhomTruc); nhomTruc.traverse(o => { o.geometry && o.geometry.dispose(); o.material && o.material.dispose(); }); }
      xoaNhanPhu("truc");
      nhomTruc = new THREE.Group();
      const [x0, y0, x1, y1] = khungMo, kich = Math.max(x1 - x0, y1 - y0, 1), m = 1.2 + kich * 0.04, w = Math.max(0.06, kich * 0.0025);
      let n = 0;
      ["x", "y"].forEach(hx => st.truc[hx].forEach((a, i) => {
        const id = `truc:${hx}:${i}`, mat = new THREE.MeshStandardMaterial({color: LOAI.truc.mau, roughness: 0.5, emissive: 0x000000});
        const dai = (hx === "x" ? y1 - y0 : x1 - x0) + 2 * m;
        const geo = hx === "x" ? new THREE.BoxGeometry(w, 0.05, dai) : new THREE.BoxGeometry(dai, 0.05, w);
        const mesh = new THREE.Mesh(geo, mat); mesh.userData.id = id;
        if (hx === "x") mesh.position.set(a.v, 0.03, -(y0 + y1) / 2); else mesh.position.set((x0 + x1) / 2, 0.03, -a.v);
        nhomTruc.add(mesh);
        const o = {id, loai: "truc", ten: `Trục ${a.ten}`, dz: [0, 0.05], meshes: [mesh], edges: [], bo: false, coLoi: false, vol: 0, ck: null, mat, truc: {hx, i}, lk: new Set()};
        objs.set(id, o); n++;
        const ends = hx === "x" ? [[a.v, -(y0 - m)], [a.v, -(y1 + m)]] : [[x0 - m, -a.v], [x1 + m, -a.v]];
        ends.forEach(e => nhanPhu.push({k: "truc", o, el: nhanHTML("x3-tr", a.ten), p: new THREE.Vector3(e[0], 0.03, e[1])}));
      }));
      if (n) tong.truc = {n, v: 0}; else delete tong.truc;
      scene.add(nhomTruc);
    }
    // Mặt bằng: nét 2D (đường bao) của mọi cấu kiện đặt sát mặt trên từng cấu kiện, để xem như bản vẽ mặt bằng
    function dungMatBang() {
      if (nhomMB) { scene.remove(nhomMB); nhomMB.traverse(o => { o.geometry && o.geometry.dispose(); o.material && o.material.dispose(); }); }
      nhomMB = new THREE.Group();
      const theo = {};
      objs.forEach(o => {
        if (!o.vongs || o.bo) return;
        const y = (o.loai === "coc" ? Math.max(o.coc.cut, o.coc.head) : o.dz[1]) + 0.006, a = theo[o.loai] = theo[o.loai] || [];
        o.vongs.forEach(P => P.forEach((p, i) => { const q = P[(i + 1) % P.length]; a.push(p[0], y, -p[1], q[0], y, -q[1]); }));
      });
      Object.keys(theo).forEach(k => {
        const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(theo[k], 3));
        nhomMB.add(new THREE.LineSegments(g, new THREE.LineBasicMaterial({color: k === "coc" ? 0xd9b38c : LOAI[k].mau})));
      });
      nhomMB.visible = st.matBang;
      scene.add(nhomMB);
    }
    // Nét vẽ thêm (đường, ghi chú) trong 3D
    function dungVeThem() {
      let nv = 0, nc = 0;
      st.them.forEach(m => {
        const y = m.muc != null ? m.muc : H;
        if (m.k === "duong") {
          const mat = new THREE.MeshStandardMaterial({color: LOAI.ve.mau, roughness: 0.5, emissive: 0x000000});
          const o = {id: m.id, loai: "ve", ten: m.ten || m.id, dz: [y, y], meshes: [], edges: [], bo: false, coLoi: false, vol: 0, ck: null, mat, moi: true, item: m, lk: new Set()};
          for (let i = 0; i + 1 < m.pts.length; i++) {
            const a = m.pts[i], b = m.pts[i + 1], L = Math.hypot(b[0] - a[0], b[1] - a[1]); if (L < 1e-6) continue;
            const mesh = new THREE.Mesh(new THREE.BoxGeometry(L, 0.04, 0.04), mat);
            mesh.position.set((a[0] + b[0]) / 2, y + 0.02, -(a[1] + b[1]) / 2); mesh.rotation.y = Math.atan2(b[1] - a[1], b[0] - a[0]); mesh.userData.id = m.id;
            o.meshes.push(mesh); nhomMain.add(mesh);
          }
          objs.set(m.id, o); nv++;
        } else if (m.k === "chu") {
          const mat = new THREE.MeshStandardMaterial({color: LOAI.ve.mau, roughness: 0.5, emissive: 0x000000});
          const mesh = new THREE.Mesh(new THREE.SphereGeometry(0.09, 12, 8), mat); mesh.position.set(m.x, y + 0.1, -m.y); mesh.userData.id = m.id;
          const o = {id: m.id, loai: "chu", ten: m.text, dz: [y, y], meshes: [mesh], edges: [], bo: false, coLoi: false, vol: 0, ck: null, mat, moi: true, item: m, lk: new Set()};
          nhomMain.add(mesh); objs.set(m.id, o); nc++;
          nhanPhu.push({k: "ve", o, el: nhanHTML("x3-nh", m.text), p: new THREE.Vector3(m.x, y + 0.2, -m.y)});
        }
      });
      if (nv) tong.ve = {n: nv, v: 0};
      if (nc) tong.chu = {n: nc, v: 0};
    }

    function danhGia(loai, hh, rongLo, dai, yb, yt, dz) {
      const hD = dz[1] - dz[0], bi = yb <= dz[0] + 1e-6, ti = yt >= dz[1] - 1e-6;
      if (loai === "dam") return (bi && ti) ? "dut" : (bi || ti) ? "mep" : hh > hD / 3 + 1e-6 ? "lon" : "ok";
      if (loai === "vach") { if (bi && ti) return "dut"; if (bi || ti) return "mep"; return Math.max(rongLo, hh) > 0.3 + 1e-6 ? "lon" : "ok"; }
      const m = Math.max(rongLo, dai);
      return m > 0.6 + 1e-6 ? "dut" : m > 0.3 + 1e-6 ? "lon" : "ok";
    }
    const tenTT = h => (TEN_TT[h.hLoai] || TEN_TT.dam)[h.tt];
    // nhãn tên cấu kiện (bật bằng nút Tên / phím L)
    let nhan = [];
    function dungNhan() {
      nhan.forEach(n => n.el.remove()); nhan = [];
      if (!st.ten) return;
      let dem = 0;
      ["cot", "dam", "vach", "san", "mong", "coc"].forEach(k => objs.forEach(o => {
        if (o.loai !== k || dem >= 250 || !o.meshes.length) return;
        const b = new THREE.Box3(); o.meshes.forEach(m => b.expandByObject(m));
        const c = b.getCenter(new THREE.Vector3()); c.y = b.max.y + 0.05;
        const el = document.createElement("div"); el.className = "x3-nh"; el.textContent = o.ten; kg.appendChild(el);
        nhan.push({o, el, p: c}); dem++;
      }));
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
        const hien = !!st.loc[o.loai] && !st.an.has(o.base || o.id) && !st.an.has(o.id) && (!st.co || st.co.has(o.id));
        o.hien = hien;
        const vt = vaiTro(o), sel0 = st.chon && objs.get(st.chon);
        o.meshes.forEach(m => m.visible = hien); o.edges.forEach(v => v.visible = hien && vt > 0);
        const mat = o.mat; if (!mat) return;
        const loiMau = MEPK.includes(o.loai) ? o.va : (st.canhBao && o.coLoi) || o.va;
        const mauBT = st.mauKhoi && BE_TONG.includes(o.loai) && o.loai !== "coc" ? 0xaeb4bd : LOAI[o.loai].mau;
        mat.color.setHex(o.bo ? 0x555b66 : loiMau ? 0xff3b3b : mauBT);
        const tr0 = mat.transparent;
        if (st.xray) { mat.transparent = true; mat.opacity = 0.22; mat.depthWrite = false; }
        else if (o.loai === "san") { mat.transparent = true; mat.opacity = 0.42; mat.depthWrite = false; }
        else if (o.loai === "cua") { mat.transparent = true; mat.opacity = 0.45; mat.depthWrite = false; }
        else if (o.bo) { mat.transparent = true; mat.opacity = 0.25; mat.depthWrite = false; }
        else if (MEPK.includes(o.loai)) { mat.transparent = true; mat.opacity = 0.88; mat.depthWrite = true; }
        else { mat.transparent = false; mat.opacity = 1; mat.depthWrite = true; }
        if (vt === 1) { mat.transparent = true; mat.opacity = Math.min(mat.opacity, 0.6); mat.depthWrite = false; }
        else if (vt === 0) { mat.transparent = true; mat.opacity = 0.06; mat.depthWrite = false; }
        if (o.matCat) o.matCat.opacity = vt === 0 ? 0.05 : 0.55;
        if (st.chon === o.id) ganEmi(o, 0xffd166, 0.55); else if (st.ruoi === o.id) ganEmi(o, 0x4c9aff, 0.35);
        else if (sel0 && sel0.lk && sel0.lk.has(o.id)) ganEmi(o, 0x4c9aff, 0.22); else ganEmi(o, 0x000000, 0);
        if (tr0 !== mat.transparent) mat.needsUpdate = true;
        o.meshes.forEach(m => m.castShadow = st.bong && !st.xray && o.loai !== "san" && !o.bo);
      });
      holes.forEach(h => { const ob = objs.get(h.id); const v = st.khoet && st.loc.dam && ob && ob.hien; h.mesh.visible = h.ln.visible = !!v; });
      r.shadowMap.enabled = st.bong; den.castShadow = st.bong;
      if (luoi) luoi.visible = st.luoi;
      if (nhomMB) nhomMB.visible = st.matBang;
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
    function hienDuoc() { const a = []; objs.forEach(o => { if (o.hien && vaiTro(o) > 0) o.meshes.forEach(m => a.push(m)); }); return a; }
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
    // ---------- vẽ thêm trong 3D: bắt điểm (giao trục, góc cấu kiện, tâm cọc, lưới 50 mm) ----------
    const mucY = () => st.ve.muc != null ? st.ve.muc : H;
    const nhomVe = new THREE.Group(); scene.add(nhomVe);
    function xoaNhomVe() { while (nhomVe.children.length) { const c = nhomVe.children.pop(); c.geometry && c.geometry.dispose(); c.material && c.material.dispose(); } }
    function huyVe() { st.ve.pts = []; xoaNhomVe(); }
    function diemVe(e) {
      const b = r.domElement.getBoundingClientRect();
      pt.set(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1);
      ray.setFromCamera(pt, cam);
      const q = new THREE.Vector3(); if (!ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), -mucY()), q)) return null;
      let best = null, bd = 12;
      const xet = (x, y, nd) => {
        const s = new THREE.Vector3(x, mucY(), -y).project(cam); if (s.z > 1) return;
        const px = (s.x + 1) / 2 * b.width + b.left, py = (1 - s.y) / 2 * b.height + b.top, dd = Math.hypot(px - e.clientX, py - e.clientY);
        if (dd < bd) { bd = dd; best = {x, y, nd}; }
      };
      st.truc.x.forEach(a => st.truc.y.forEach(c => xet(a.v, c.v, `giao trục ${c.ten}/${a.ten}`)));
      objs.forEach(o => {
        if (!o.vongs || o.base || !o.hien) return;
        if (o.coc) xet(o.coc.x, o.coc.y, "tâm cọc " + o.ten); else o.vongs.forEach(P => P.forEach(p => xet(p[0], p[1], "góc " + o.ten)));
      });
      if (best) return best;
      const g = 0.05;
      return {x: Math.round(q.x / g) * g, y: Math.round(-q.z / g) * g, nd: ""};
    }
    function veGhost(p) {
      xoaNhomVe();
      const y = mucY() + 0.03, v = st.ve, t = v.tool, pts = v.pts;
      const mk = new THREE.Mesh(new THREE.SphereGeometry(Math.max(bk * 0.006, 0.05), 12, 8), new THREE.MeshBasicMaterial({color: 0x4cffb0, depthTest: false}));
      mk.position.set(p.x, y, -p.y); mk.renderOrder = 10; nhomVe.add(mk);
      let ring = null, open = null;
      if (t === "cot") ring = vongHCN(p.x, p.y, v.b / 1000, v.h / 1000);
      else if (t === "coc") ring = vongTron(p.x, p.y, v.d / 2000, 20);
      else if (t === "dam" && pts.length === 1) ring = vongDam(pts[0], [p.x, p.y], v.w / 1000);
      else if (t === "san" && pts.length === 1) ring = [[pts[0][0], pts[0][1]], [p.x, pts[0][1]], [p.x, p.y], [pts[0][0], p.y]];
      else if (t === "duong" && pts.length) open = pts.concat([[p.x, p.y]]);
      else if (t === "truc") open = v.dir === "x" ? [[p.x, khungMo[1] - 2], [p.x, khungMo[3] + 2]] : [[khungMo[0] - 2, p.y], [khungMo[2] + 2, p.y]];
      const lin = (P, dong) => {
        const arr = P.map(q => new THREE.Vector3(q[0], y, -q[1])); if (dong) arr.push(arr[0].clone());
        const l = new THREE.Line(new THREE.BufferGeometry().setFromPoints(arr), new THREE.LineBasicMaterial({color: 0x4cffb0, depthTest: false})); l.renderOrder = 10; nhomVe.add(l);
      };
      if (ring) lin(ring, true);
      if (open) lin(open, false);
    }
    const TIEN_TO = {cot: "CM", dam: "DM", san: "SM", coc: "PM", duong: "Nét ", chu: "GC"};
    function themMoi(m) {
      ghiLui(); m.id = "moi" + (++seq);
      if (m.k === "cot" || m.k === "dam" || m.k === "san") m.Z = mucY();
      m.ten = TIEN_TO[m.k] + (st.them.filter(x => x.k === m.k).length + 1);
      st.them.push(m); luu(); dung(); ap(); st.chon = m.id; ap(); capNhatPn();
    }
    function xongDuong() {
      const v = st.ve;
      if (v.tool === "duong" && v.pts.length >= 2) themMoi({k: "duong", pts: v.pts.slice(), muc: mucY()});
      huyVe();
    }
    function veBam(p) {
      const v = st.ve, t = v.tool, mm = x => x / 1000;
      if (t === "cot") themMoi({k: "cot", x: p.x, y: p.y, b: mm(v.b), h: mm(v.h)});
      else if (t === "coc") themMoi({k: "coc", x: p.x, y: p.y, d: mm(v.d)});
      else if (t === "dam" || t === "san") {
        if (!v.pts.length) { v.pts = [[p.x, p.y]]; veGhost(p); return; }
        const a = v.pts[0]; v.pts = []; xoaNhomVe();
        if (Math.hypot(p.x - a[0], p.y - a[1]) < 0.02) return;
        if (t === "dam") themMoi({k: "dam", a, b: [p.x, p.y], w: mm(v.w), h: mm(v.hd)});
        else themMoi({k: "san", x0: a[0], y0: a[1], x1: p.x, y1: p.y, t: mm(v.t)});
      } else if (t === "truc") {
        const arr = st.truc[v.dir]; ghiLui();
        arr.push({ten: v.dir === "x" ? String(arr.length + 1) : chuCai(arr.length), v: +(v.dir === "x" ? p.x : p.y).toFixed(3)});
        luu(); dungTruc(); ap(); capNhatPn();
      } else if (t === "duong") {
        const l = v.pts[v.pts.length - 1]; if (l && Math.hypot(l[0] - p.x, l[1] - p.y) < 0.01) return;
        v.pts.push([p.x, p.y]); veGhost(p);
      } else if (t === "chu") {
        const tx = prompt("Nội dung ghi chú:"); if (tx && tx.trim()) themMoi({k: "chu", x: p.x, y: p.y, text: tx.trim(), muc: mucY()});
      }
    }
    function hoanTac() {
      if (!lui.length) return;
      const j = JSON.parse(lui.pop());
      st.sua = j.sua; st.truc = j.truc; st.them = j.them; st.cocCfg = j.cocCfg; if (j.mb) st.mb = j.mb; st.mbRef = j.mbRef || st.mbRef;
      luu(); huyVe(); dung(); ap(); capNhatPn();
    }
    const HUONG_DAN_VE = {
      cot: "Bấm 1 điểm để đặt cột (kích thước nhập bên dưới).", dam: "Bấm điểm đầu rồi điểm cuối của dầm.", san: "Bấm 2 góc đối diện của mảng sàn.",
      coc: "Bấm vị trí đặt cọc (tự bắt tâm cọc / giao trục).", truc: "Bấm một điểm: dựng tim trục đi qua điểm đó.", duong: "Bấm các điểm của đường; nhấp đúp hoặc Enter để kết thúc.",
      chu: "Bấm vị trí rồi gõ nội dung ghi chú.",
    };

    function datCC(on, k = "do") {
      st.cc = on ? k : null;
      $("#x3-do").classList.toggle("on", on && k === "do"); $("#x3-ve").classList.toggle("on", on && k === "ve");
      r.domElement.style.cursor = on ? "crosshair" : "";
      diemDo = null; huyVe();
      if (on && k === "ve") { st.tab = "ve"; st.pn = true; }
      capNhatPn();
    }

    let dnx = 0, dny = 0, keo = false;
    r.domElement.addEventListener("pointerdown", e => { dnx = e.clientX; dny = e.clientY; keo = false; });
    r.domElement.addEventListener("pointermove", e => {
      if (e.buttons) { if (Math.hypot(e.clientX - dnx, e.clientY - dny) > 4) keo = true; tip.style.display = "none"; return; }
      const bb = r.domElement.getBoundingClientRect();
      if (st.cc === "ve") {
        const p = diemVe(e); if (!p) return;
        veGhost(p);
        tip.innerHTML = `X ${f2(p.x, 3)} · Y ${f2(p.y, 3)} · Z ${f2(mucY())} m` + (p.nd ? `<br><span class="x3-mut">${esc(p.nd)}</span>` : "");
        tip.style.left = (e.clientX - bb.left + 14) + "px"; tip.style.top = (e.clientY - bb.top + 14) + "px"; tip.style.display = "block";
        return;
      }
      const hit = ban(e), o = hit && objs.get(hit.object.userData.id);
      const id = o ? o.id : null;
      if (id !== st.ruoi) { st.ruoi = id; ap(); }
      if (!st.cc) r.domElement.style.cursor = timTruc(e, hit) ? "grab" : "";
      if (o && st.cc !== "do") {
        const nl = o.lk ? o.lk.size : 0;
        tip.innerHTML = `<b>${esc(o.ten)}</b> · ${LOAI[o.loai].ten}<br><span class="x3-mut">đáy ${f2(o.dz[0])} → đỉnh ${f2(o.dz[1])} m` + (nl ? ` · ${nl} liên kết` : "") + (o.bo ? " · loại bỏ" : "") + (o.va ? ` · <span style='color:#ff7a45'>${o.vaGhi || "va chạm"}</span>` : "") + `</span>`;
        tip.style.left = (e.clientX - bb.left + 14) + "px"; tip.style.top = (e.clientY - bb.top + 14) + "px"; tip.style.display = "block";
      } else tip.style.display = "none";
    });
    // Kéo tim trục bằng chuột: bấm giữ vào trục rồi kéo, tự bắt vào mép / tâm cột, dầm, vách gần nhất
    let keoTruc = null;
    function giaTriBat(hx, v) {
      const tol = Math.max(0.04, cam.position.distanceTo(dk.target) * 0.012), k = hx === "x" ? 0 : 1;
      let best = null, bd = tol;
      objs.forEach(o => {
        if (!o.vongs || o.base || !o.hien) return;
        o.vongs.forEach(P => {
          let lo = 1e18, hi = -1e18;
          P.forEach(p => { lo = Math.min(lo, p[k]); hi = Math.max(hi, p[k]); });
          [lo, hi, (lo + hi) / 2].forEach(c => { const dd = Math.abs(c - v); if (dd < bd) { bd = dd; best = c; } });
        });
      });
      return best != null ? best : Math.round(v / 0.01) * 0.01;
    }
    // Tìm trục gần con trỏ (trong 7 px màn hình) kể cả khi bị sàn / móng che phía trên
    function timTruc(e, hit) {
      const ho = hit && objs.get(hit.object.userData.id);
      if (ho && ho.truc) return ho;
      if (ho && !e.altKey && !["san", "mong", "coc"].includes(ho.loai)) return null;
      const b = r.domElement.getBoundingClientRect(); let best = null, bd = 7;
      objs.forEach(o => {
        if (!o.truc || !o.hien) return;
        const m = o.meshes[0], g = m.geometry.parameters, dai = o.truc.hx === "x" ? g.depth : g.width, c = m.position;
        const e0 = o.truc.hx === "x" ? [c.x, c.y, c.z - dai / 2] : [c.x - dai / 2, c.y, c.z], e1 = o.truc.hx === "x" ? [c.x, c.y, c.z + dai / 2] : [c.x + dai / 2, c.y, c.z];
        const pr = v => { const q = new THREE.Vector3(v[0], v[1], v[2]).project(cam); return [(q.x + 1) / 2 * b.width + b.left, (1 - q.y) / 2 * b.height + b.top, q.z]; };
        const A = pr(e0), B = pr(e1); if (A[2] > 1 || B[2] > 1) return;
        const dd = kcDoan([e.clientX, e.clientY], A, B); if (dd < bd) { bd = dd; best = o; }
      });
      return best;
    }
    function diemNen(e, y) {
      const b = r.domElement.getBoundingClientRect();
      pt.set(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1); ray.setFromCamera(pt, cam);
      const q = new THREE.Vector3(); return ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), -y), q) ? q : null;
    }
    function datTruc(o, v) {
      const a = st.truc[o.truc.hx][o.truc.i]; a.v = +v.toFixed(3);
      const m = o.meshes[0]; if (o.truc.hx === "x") m.position.x = a.v; else m.position.z = -a.v;
      nhanPhu.forEach(n => { if (n.o === o) { if (o.truc.hx === "x") n.p.x = a.v; else n.p.z = -a.v; } });
    }
    r.domElement.addEventListener("pointerdown", e => {
      if (e.button !== 0 || st.cc) return;
      const o = timTruc(e, ban(e)); if (!o) return;
      const id = o.id;
      e.stopImmediatePropagation(); dk.enabled = false; keo = false; dnx = e.clientX; dny = e.clientY;
      ghiLui(); keoTruc = {o, x0: e.clientX, y0: e.clientY, moved: false}; st.chon = id; ap();
      try { r.domElement.setPointerCapture(e.pointerId); } catch (x) {}
    }, true);
    r.domElement.addEventListener("pointermove", e => {
      if (!keoTruc) return;
      e.stopImmediatePropagation();
      if (Math.hypot(e.clientX - keoTruc.x0, e.clientY - keoTruc.y0) > 3) keoTruc.moved = true;
      if (!keoTruc.moved) return;
      const q = diemNen(e, 0.03); if (!q) return;
      const hx = keoTruc.o.truc.hx; datTruc(keoTruc.o, giaTriBat(hx, hx === "x" ? q.x : -q.z));
      const bb = r.domElement.getBoundingClientRect();
      tip.innerHTML = `<b>Trục ${esc(st.truc[hx][keoTruc.o.truc.i].ten)}</b> = ${f2(st.truc[hx][keoTruc.o.truc.i].v, 3)} m`;
      tip.style.left = (e.clientX - bb.left + 14) + "px"; tip.style.top = (e.clientY - bb.top + 14) + "px"; tip.style.display = "block";
    }, true);
    addEventListener("pointerup", () => {
      if (!keoTruc) return;
      const k = keoTruc; keoTruc = null; dk.enabled = true; tip.style.display = "none";
      if (k.moved) { luu(); keo = true; } else lui.pop();
      capNhatPn();
    });
    r.domElement.addEventListener("pointerleave", () => { tip.style.display = "none"; if (st.ruoi) { st.ruoi = null; ap(); } });
    r.domElement.addEventListener("click", e => {
      if (keo) return;
      if (st.cc === "ve") { const p = diemVe(e); if (p) veBam(p); return; }
      const hit = ban(e);
      if (st.cc === "do") { const p = diemDoTai(e, hit); if (p) vaoDo(p); return; }
      const id = hit ? hit.object.userData.id : null;
      st.chon = id;
      if (st.lv && id) st.lv = id;     // đang làm việc từng phần: bấm sang cấu kiện liên kết thì chuyển sang làm việc với nó
      ap(); capNhatPn();
    });
    r.domElement.addEventListener("dblclick", e => {
      if (st.cc === "ve") { xongDuong(); return; }
      if (st.cc) return;
      const hit = ban(e); if (hit) { const o = objs.get(hit.object.userData.id); if (o) { st.chon = o.id; vaoLamViec(o.id); } }
    });
    r.domElement.addEventListener("contextmenu", e => { if (st.cc === "ve" && st.ve.pts.length) { e.preventDefault(); huyVe(); } });

    // ---------- làm việc từng phần ----------
    function vaoLamViec(id) {
      const o = objs.get(id); if (!o) return;
      st.lv = id; st.chon = id; st.tab = "dt"; st.pn = true;
      ap(); capNhatPn(); bayToiVat(o);
    }
    function thoatLamViec() { st.lv = null; ap(); capNhatPn(); }

    // ---------- tim trục gần nhất, vị trí cấu kiện so với trục ----------
    function gannhat(arr, c) { let b = null; arr.forEach(a => { const dd = Math.abs(a.v - c); if (!b || dd < b.dd) b = {a, dd}; }); return b; }
    function tamVong(P) { const b = bbVong(P); return [(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]; }
    function dauDam(P) {   // trung điểm hai cạnh ngắn của dầm
      const e = P.map((a, i) => { const b = P[(i + 1) % P.length]; return {l: Math.hypot(b[0] - a[0], b[1] - a[1]), m: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2]}; }).sort((p, q) => p.l - q.l);
      return [e[0].m, e[1].m];
    }
    function viTriTruc(o) {
      if (!st.truc.x.length && !st.truc.y.length) return '<span class="x3-mut">Chưa khai báo tim trục (tab Trục &amp; cọc).</span>';
      const P = o.vongs && o.vongs[0]; if (!P) return "";
      const mm = v => f2(v * 1000, 0) + " mm";
      if (o.loai === "dam" && P.length >= 3) {
        const [p, q] = dauDam(P), kq = [];
        [["x", 0, "Trục"], ["y", 1, "Trục"]].forEach(([hx, k]) => {
          const a = gannhat(st.truc[hx], p[k]), b = gannhat(st.truc[hx], q[k]);
          if (a && b && a.a === b.a && a.dd < 0.05 && b.dd < 0.05) kq.push(`nằm trên trục <b>${esc(a.a.ten)}</b>`);
        });
        const nhan = (pp) => { const gx = gannhat(st.truc.x, pp[0]), gy = gannhat(st.truc.y, pp[1]); return (gy ? esc(gy.a.ten) : "?") + "/" + (gx ? esc(gx.a.ten) : "?"); };
        return (kq.length ? kq.join(", ") + " · " : "") + `từ ${nhan(p)} đến ${nhan(q)}`;
      }
      const c = tamVong(P), gx = gannhat(st.truc.x, c[0]), gy = gannhat(st.truc.y, c[1]);
      if (!gx && !gy) return "";
      return `giao trục <b>${gy ? esc(gy.a.ten) : "?"}/${gx ? esc(gx.a.ten) : "?"}</b>` + ` <span class="x3-mut">(lệch ${gx ? mm(gx.dd) : "-"} · ${gy ? mm(gy.dd) : "-"})</span>`;
    }
    const dtOb = o => o.ck ? o.ck.hinh.reduce((t, p) => t + dienTich(p), 0) : 0;

    // ---------- bảng điều khiển ----------
    function soHo() { const c = {ok: 0, lon: 0, mep: 0, dut: 0}; holes.forEach(h => c[h.tt]++); return c; }
    const fN = (attr, key, val, o = {}) => `<input type="number" data-${attr}="${key}" ${o.mm ? 'data-mm="1"' : ""} step="${o.step || (o.mm ? 10 : 0.05)}" ${o.min != null ? `min="${o.min}"` : ""} ${o.ph ? `placeholder="${o.ph}"` : ""} value="${val == null || val === "" ? "" : (o.mm ? f2(val * 1000, 0) : f2(val, o.nd || 3))}">`;
    const fT = (attr, key, val) => `<input type="text" data-${attr}="${key}" value="${esc(val)}">`;
    const kvr = (a, b) => `<span>${a}</span><span>${b}</span>`;
    const dem = (o, ks) => [...o.lk].filter(id => { const x = objs.get(id); return x && ks.includes(x.loai); }).length;

    // Giao diện theo loại: mỗi loại cấu kiện có thông số và ô chỉnh riêng
    function loaiHTML(o) {
      const bid = o.base || o.id, ob = objs.get(bid) || o, P = o.vongs && o.vongs[0], ts = (o.ck && o.ck.thong_so) || {};
      const mauTieuDe = (t) => `<h6 class="x3-h6">${t}</h6>`;
      const muc = (k, v) => ob.moi ? "" : "";
      let s = "";
      const capDo = () => kvr("Cao độ đáy", fN("su", "y0", ob.dz[0]) + " m") + kvr("Cao độ đỉnh", fN("su", "y1", ob.dz[1]) + " m");
      const tang = o.tang ? `<div class="x3-mut" style="margin:4px 0">Đây là bản sao tầng ${o.tang + 1}; chỉnh sửa áp dụng cho mọi tầng (theo ${esc(ob.ten)}).</div>` : "";
      if (o.loai === "cot") {
        const [bx0, by0, bx1, by1] = bbVong(P);
        s = `<div class="x3-kv">${kvr("Tiết diện", `${f2((bx1 - bx0) * 1000, 0)} × ${f2((by1 - by0) * 1000, 0)} mm`)}${capDo()}${kvr("Vị trí", viTriTruc(o))}${kvr("Đặt trên", dem(o, ["mong", "coc"]) ? "móng / đài" : '<span style="color:#ff7a45">chưa chạm móng</span>')}${kvr("Dầm liên kết", dem(o, ["dam"]))}</div>`;
      } else if (o.loai === "dam") {
        const [L, W] = dai_rong(P), noi = o.ck && o.ck.noiThem;
        s = `<div class="x3-kv">${kvr("Dài × rộng", `${f2(L * 1000, 0)} × ${f2(W * 1000, 0)} mm`)}${kvr("Cao h", f2((ob.dz[1] - ob.dz[0]) * 1000, 0) + " mm")}${capDo()}${kvr("Vị trí", viTriTruc(o))}${kvr("Tựa lên", `${dem(o, ["cot"])} cột · ${dem(o, ["vach"])} vách · ${dem(o, ["dam"])} dầm khác`)}${noi ? kvr("Nối thêm", `${f2(noi[0] * 1000, 0)} mm đầu 1 · ${f2(noi[1] * 1000, 0)} mm đầu 2 (kéo dài chạm cột)`) : ""}</div>`;
      } else if (o.loai === "san") {
        s = `<div class="x3-kv">${kvr("Dày", f2((ob.dz[1] - ob.dz[0]) * 1000, 0) + " mm")}${kvr("Diện tích", f2(dtOb(o), 2) + " m²")}${capDo()}${kvr("Liên kết", `${dem(o, ["dam"])} dầm · ${dem(o, ["cot"])} cột · ${dem(o, ["vach"])} vách`)}</div>`;
      } else if (o.loai === "mong") {
        s = `<div class="x3-kv">${kvr("Dày", f2((ob.dz[1] - ob.dz[0]) * 1000, 0) + " mm")}${kvr("Diện tích", f2(dtOb(o), 2) + " m²")}${capDo()}${kvr("Cọc dưới móng", dem(o, ["coc"]) ? dem(o, ["coc"]) + " cọc" : '<span class="x3-mut">chưa có</span>')}${kvr("Cột trên móng", dem(o, ["cot", "vach"]))}</div>`;
      } else if (o.loai === "vach") {
        const [L, W] = dai_rong(P);
        s = `<div class="x3-kv">${kvr("Dài × dày", `${f2(Math.max(L, W) * 1000, 0)} × ${f2(Math.min(L, W) * 1000, 0)} mm`)}${capDo()}${kvr("Liên kết", `${dem(o, ["dam"])} dầm · ${dem(o, ["san"])} sàn · ${dem(o, ["mong"])} móng`)}</div>`;
      } else if (o.loai === "coc") {
        const c = o.coc, sc = st.sua[o.id] || {}, ph = (k, v) => ({ph: f2(v)});
        s = `<div class="x3-kv">${kvr("Đường kính D", fN("su", "d", c.D, {mm: true, step: 10}) + " mm")}
          ${kvr("Chiều dài L", fN("su", "L", c.L, {step: 0.5, nd: 2}) + " m")}
          ${kvr("Cao độ đầu cọc", fN("su", "head", c.head, {nd: 3}) + " m")}
          ${kvr("Cao độ cắt cọc", fN("su", "cut", c.cut, {nd: 3}) + " m")}
          ${kvr("Mũi cọc", `<b>${f2(c.tip, 3)}</b> m`)}
          ${kvr("Đoạn cắt bỏ", c.cut > c.head + 1e-6 ? '<span style="color:#ff7a45">cao độ cắt cao hơn đầu cọc</span>' : `<b>${f2(c.dCat * 1000, 0)}</b> mm (đỏ mờ)`)}
          ${kvr("Cọc còn lại", `${f2(Math.max(Math.min(c.cut, c.head) - c.tip, 0), 2)} m · ${f2(o.vol, 3)} m³`)}
          ${kvr("Vị trí", `X ${f2(c.x, 3)} · Y ${f2(c.y, 3)}` + (viTriTruc({loai: "coc", vongs: o.vongs}) ? "<br>" + viTriTruc({loai: "coc", vongs: o.vongs}) : ""))}
          ${kvr("Dưới móng", dem(o, ["mong"]) ? "có" : '<span style="color:#ff7a45">chưa chạm móng</span>')}</div>
          <div class="x3-mut" style="margin:4px 0">Đầu cọc = cao độ cọc sau khi ép / đóng; cắt cọc = cao độ cắt bỏ phần thừa (đầu cọc thiết kế ngàm vào đài). Mũi cọc = đầu cọc - L.</div>
          <div class="x3-row" style="flex-wrap:wrap"><button data-a="coc-all">Áp cho mọi cọc</button>${st.sua[o.id] ? '<button data-a="reset-sua">Về mặc định</button>' : ""}</div>`;
      } else if (o.loai === "truc") {
        const a = st.truc[o.truc.hx][o.truc.i];
        s = `<div class="x3-kv">${kvr("Tên trục", fT("tr", "ten", a.ten))}${kvr("Vị trí", fN("tr", "v", a.v, {step: 0.05}) + (o.truc.hx === "x" ? " m (x = const, đường đứng)" : " m (y = const, đường ngang)"))}</div>
          <div class="x3-row"><button data-a="xoa-truc">Xóa trục này</button></div>`;
      } else if (o.loai === "chu") {
        const m = o.item;
        s = `<div class="x3-kv">${kvr("Nội dung", fT("mi", "text", m.text))}${kvr("X / Y", fN("mi", "x", m.x) + fN("mi", "y", m.y))}${kvr("Cao độ", fN("mi", "muc", m.muc != null ? m.muc : H) + " m")}</div>
          <div class="x3-row"><button data-a="xoa-moi">Xóa ghi chú</button></div>`;
      } else if (o.loai === "ve") {
        const m = o.item, L = m.pts.reduce((t, p, i) => i ? t + Math.hypot(p[0] - m.pts[i - 1][0], p[1] - m.pts[i - 1][1]) : 0, 0);
        s = `<div class="x3-kv">${kvr("Số điểm", m.pts.length)}${kvr("Tổng dài", f2(L, 3) + " m")}${kvr("Cao độ", fN("mi", "muc", m.muc != null ? m.muc : H) + " m")}</div>
          <div class="x3-row"><button data-a="xoa-moi">Xóa nét vẽ</button></div>`;
      } else if (o.duct) {
        s = `<div class="x3-kv">${kvr("Kích thước", `${f2(o.duct.o.rong * 1000, 0)} × ${f2(o.duct.o.cao * 1000, 0)} mm`)}${kvr("Dài", f2(o.duct.daiTrue.L) + " m")}${kvr("Cao độ", `${f2(o.dz[0])} → ${f2(o.dz[1])} m`)}</div>`;
      }
      // hình học của phần vẽ thêm: sửa được
      const m = o.ck && o.ck.moi ? o.ck.item : (o.loai === "coc" && o.moi ? st.them.find(x => x.id === o.id) : null);
      if (m && m.k) {
        let f = "";
        if (m.k === "cot") f = kvr("Tâm X / Y", fN("mi", "x", m.x) + fN("mi", "y", m.y)) + kvr("b × h (mm)", fN("mi", "b", m.b, {mm: true}) + fN("mi", "h", m.h, {mm: true}));
        else if (m.k === "coc") f = kvr("Tâm X / Y", fN("mi", "x", m.x) + fN("mi", "y", m.y));
        else if (m.k === "dam") f = kvr("Đầu 1 X / Y", fN("mi", "ax", m.a[0]) + fN("mi", "ay", m.a[1])) + kvr("Đầu 2 X / Y", fN("mi", "bx", m.b[0]) + fN("mi", "by", m.b[1])) + kvr("Rộng b (mm)", fN("mi", "w", m.w, {mm: true})) + kvr("Cao h (mm)", fN("mi", "h", m.h, {mm: true}));
        else if (m.k === "san") f = kvr("Góc 1 X / Y", fN("mi", "x0", m.x0) + fN("mi", "y0", m.y0)) + kvr("Góc 2 X / Y", fN("mi", "x1", m.x1) + fN("mi", "y1", m.y1)) + kvr("Dày (mm)", fN("mi", "t", m.t, {mm: true}));
        s += mauTieuDe("Phần vẽ thêm") + `<div class="x3-kv">${f}</div><div class="x3-row"><button data-a="xoa-moi">Xóa phần vẽ thêm này</button></div>`;
      }
      return tang + s;
    }

    function chonHTML() {
      const o = st.chon && objs.get(st.chon);
      if (!o) return `<div class="x3-sec"><h5>Đối tượng đang chọn</h5><div class="x3-mut">Bấm vào một khối để xem và chỉnh theo loại của nó. <b>Nhấp đúp</b> hoặc phím <kbd>W</kbd> để làm việc riêng với cấu kiện đó (các phần khác mờ đi, chỉ giữ phần liên kết).</div></div>`;
      const ck = o.ck;
      const lk = o.lk ? [...o.lk].map(id => objs.get(id)).filter(Boolean) : [];
      const nhom = {};
      lk.forEach(x => (nhom[x.loai] = nhom[x.loai] || []).push(x));
      const lkHtml = lk.length ? Object.keys(nhom).map(k => `<div class="x3-lkrow"><span class="x3-dot" style="background:${MAU_HEX(k)}"></span><b>${LOAI[k].ten}</b> <span class="x3-mut">${nhom[k].length}:</span> ${nhom[k].slice(0, 12).map(x => `<a data-go="${esc(x.id)}">${esc(x.ten)}</a>`).join(" ")}${nhom[k].length > 12 ? " …" : ""}</div>`).join("") : '<div class="x3-mut">Chưa liên kết với cấu kiện nào.</div>';
      const loi = loiLK.filter(x => x.id === o.id).map(x => `<div class="x3-cb">${esc(x.nd)}</div>`).join("");
      return `<div class="x3-sec"><h5>Đối tượng đang chọn · ${LOAI[o.loai].ten}</h5>
        <div class="x3-kv">${kvr("Tên", `<b>${esc(o.ten)}</b>${o.bo ? " · <i>bị loại khỏi tính</i>" : ""}`)}${ck ? kvr("Layer", esc(ck.layer)) : ""}${o.vol ? kvr("Thể tích", f2(o.vol, 3) + " m³") : ""}</div>
        ${loaiHTML(o)}
        ${o.va ? '<div class="x3-cb">Va chạm giữa ống và cột/vách: không khoét được, cần dời ống hoặc hạ cao độ.</div>' : ""}
        ${ck ? (ck.canh_bao || []).map(c => `<div class="x3-cb">${esc(c.noi_dung)}</div>`).join("") : ""}
        ${loi}
        <div class="x3-row" style="margin-top:8px;flex-wrap:wrap"><button class="cam" data-a="lv" ${st.lv === o.id ? "disabled" : ""}>◎ Làm việc với phần này (W)</button><button data-a="zoom">⌖ Zoom</button><button data-a="an">Ẩn (H)</button><button data-a="co">Chỉ hiện nó (I)</button></div>
        <h5 style="margin-top:10px">Liên kết (${lk.length})</h5>${lkHtml}
        ${lk.length ? '<div class="x3-row" style="flex-wrap:wrap"><button data-a="cum">Chỉ hiện cụm liên kết</button></div>' : ""}</div>`;
    }

    function lopHTML() {
      const lopHtml = Object.keys(LOAI).filter(k => tong[k]).map(k => `<div class="x3-row"><label><input type="checkbox" data-l="${k}" ${st.loc[k] ? "checked" : ""}><span class="x3-dot" style="background:${MAU_HEX(k)}"></span>${LOAI[k].ten}</label><span class="n">${tong[k].n}${BE_TONG.includes(k) ? " · " + f2(tong[k].v, 1) + " m³" : ""}</span></div>`).join("");
      const bt = BE_TONG.reduce((t, k) => t + (tong[k] ? tong[k].v : 0), 0);
      return `<div class="x3-sec"><h5>Lớp hiển thị</h5>${lopHtml || '<div class="x3-mut">Không có cấu kiện.</div>'}
        <div class="x3-row"><label><input type="checkbox" data-o="matBang" ${st.matBang ? "checked" : ""}><span class="x3-dot" style="background:#e6ebf5"></span>Mặt bằng (nét 2D đường bao)</label><button data-a="mb" style="height:24px">▦ Xem</button></div>
        <div class="x3-mut" style="margin-top:6px">Bê tông ước tính theo hình học: <b style="color:#e6ebf5">${f2(bt, 1)} m³</b> (chưa trừ giao nhau; số chính thức xem bảng Khối lượng).</div>
        <div class="x3-row" style="margin-top:4px"><button data-a="hien-het" ${st.an.size || st.co ? "" : "disabled"}>Hiện tất cả (A)</button><span class="n">${st.an.size ? "đang ẩn " + st.an.size : ""}${st.co ? "đang cô lập" : ""}</span></div></div>`;
    }

    function lienKetHTML() {
      let n = 0, nl = 0;
      objs.forEach(o => { if (o.vongs && !o.base && !o.bo) { n++; nl += o.lk.size; } });
      nl /= 2;
      return `<div class="x3-sec"><h5>Liên kết toàn công trình</h5>
        <div class="x3-mut">Hai cấu kiện liên kết khi chạm / chồng nhau trên mặt bằng và trùng khoảng cao độ. <b style="color:#e6ebf5">${n}</b> cấu kiện · <b style="color:#e6ebf5">${f2(nl, 0)}</b> liên kết · <b style="color:${loiLK.length ? "#ff7a45" : "#3ecf8e"}">${loiLK.length}</b> chỗ cần kiểm tra.</div>
        <div class="x3-kv" style="margin-top:6px">${dsMB ? kvr("Tầng", `<a data-tab="mb" style="cursor:pointer">${dsMB.length} mặt bằng ghép → tab Tầng</a>`) : kvr("Số tầng dựng", `<input type="number" data-g="tang" min="1" max="30" step="1" value="${st.tang}">`)}${kvr("Dung sai chạm", `<input type="number" data-g="dungSai" min="0" max="500" step="10" value="${st.dungSai}"> mm`)}</div>
        <div class="x3-row"><label><input type="checkbox" data-o="noi" ${st.noi ? "checked" : ""}>Nối dầm vào cột / vách khi hở ≤</label><span class="n"><input type="number" data-g="noiMm" min="0" max="1000" step="50" value="${st.noiMm}"> mm</span></div>
        ${soKhungLon ? `<div class="x3-cb">${soKhungLon} hình "dầm" rộng hơn 1,2 m (đường bao khung dầm hoặc ô dầm, không phải dầm) đã bỏ khỏi 3D. Nếu là dầm thật thì kiểm tra lại cách gán layer.</div>` : ""}
        ${soNoi ? `<div class="x3-mut">Đã kéo dài đầu của ${soNoi} dầm cho chạm cột / vách (chỉ để dựng 3D, không đổi khối lượng chính thức).</div>` : ""}
        <div class="x3-row"><label><input type="checkbox" data-o="mauKhoi" ${st.mauKhoi ? "checked" : ""}>Bê tông liền khối (một màu, như công trình thật)</label></div>
        ${loiLK.length ? `<div style="max-height:200px;overflow:auto;margin-top:6px">${loiLK.slice(0, 80).map(x => { const o = objs.get(x.id); return `<div class="x3-ho" data-go="${esc(x.id)}"><span><b>${esc(o.ten)}</b> · ${LOAI[o.loai].ten}</span><span></span><span class="x3-mut" style="grid-column:1/3">${esc(x.nd)}</span></div>`; }).join("")}${loiLK.length > 80 ? `<div class="x3-mut">… và ${loiLK.length - 80} chỗ khác</div>` : ""}</div>` : ""}</div>`;
    }


    // Tab Tầng: mỗi mặt bằng được khai báo loại (móng / tầng), cao độ sàn và độ dịch để căn thẳng trục với mặt bằng chuẩn
    function mbHTML() {
      const hang = dsMB.map((p, i) => {
        const c = st.mb[p.key], chuan = p.key === st.mbRef, nOb = p.ck.length, nc = (p.coc || []).length;
        const kq = chuan ? '<span class="x3-chip" style="background:#3ecf8e">Mặt bằng chuẩn</span>' : c.canh ? (c.canh.n >= 4 ? `<span class="x3-chip" style="background:#3ecf8e">Khớp ${c.canh.n} điểm (cột / cọc / móng)</span>` : c.canh.n >= 2 ? `<span class="x3-chip" style="background:#ffb020">Chỉ khớp ${c.canh.n} điểm: kiểm tra lại độ dịch</span>` : '<span class="x3-chip" style="background:#ffb020">Chưa khớp cột: căn tạm theo góc</span>') : "";
        return `<div class="x3-sec" style="${c.hien ? "" : "opacity:.55"}"><div class="x3-row"><label><input type="checkbox" data-mbh="${i}" ${c.hien ? "checked" : ""}><b>${esc(p.ten)}</b></label></div>
          <div class="x3-mut" style="margin-bottom:4px">${nOb} cấu kiện${nc ? ` · ${nc} cọc` : ""} ${kq}</div>
          <div class="x3-kv">${kvr("Loại", `<select data-mb="loai" data-i="${i}"><option value="mong" ${c.loai === "mong" ? "selected" : ""}>Móng / cọc</option><option value="tang" ${c.loai === "tang" || c.loai === "mai" ? "selected" : ""}>Tầng</option><option value="bo" ${c.loai === "bo" ? "selected" : ""}>Bỏ qua</option></select>`)}
            ${c.loai !== "mong" ? kvr("Tầng số", `<input type="number" data-mb="tang" data-i="${i}" min="1" max="60" step="1" value="${c.tang}">`) : ""}
            ${kvr("Cao độ sàn", `<input type="number" data-mb="Z" data-i="${i}" step="0.1" value="${f2(c.Z, 2)}"> m`)}
            ${kvr("Dịch X / Y", `<input type="number" data-mb="dx" data-i="${i}" step="0.05" value="${f2(c.dx, 3)}"><input type="number" data-mb="dy" data-i="${i}" step="0.05" value="${f2(c.dy, 3)}">`)}</div>
          <div class="x3-row" style="flex-wrap:wrap;margin-top:6px"><button data-a="mb-can" data-i="${i}" ${chuan ? "disabled" : ""}>⚙ Căn theo cột</button><button data-a="mb-chuan" data-i="${i}" ${chuan ? "disabled" : ""}>Đặt làm chuẩn</button><button data-a="mb-chi" data-i="${i}">Chỉ hiện tầng này</button></div></div>`;
      }).join("");
      return `<div class="x3-sec"><h5>Ghép các mặt bằng thành công trình</h5>
        <div class="x3-mut">Mỗi mặt bằng (móng, tầng 1, tầng 2...) đã được dựng riêng rồi <b>dịch cho thẳng trục</b> với mặt bằng chuẩn và <b>xếp lên đúng cao độ sàn</b>. Cột tầng trên nối cột tầng dưới; cột tầng 1 đứng trên móng. Tầng n mặc định có cao độ sàn = n × cao tầng (${f2(H, 2)} m): sửa nếu khác. Mặt bằng có móng / cọc / đà kiềng được xếp ở cao độ ±0,00; nếu đã có mặt bằng tầng thì cột trong mặt bằng móng chỉ là cột chờ nên không dựng.</div>
        <div class="x3-row" style="flex-wrap:wrap;margin-top:6px"><button class="cam" data-a="mb-can-het">⚙ Căn lại tất cả theo cột</button><button data-a="mb-hien-het">Hiện mọi mặt bằng</button></div></div>${hang}`;
    }
    function trucHTML() {
      const hang = (hx, tieuDe, ghiChu) => `<div class="x3-sec"><h5>${tieuDe}</h5><div class="x3-mut" style="margin-bottom:4px">${ghiChu}</div>
        ${st.truc[hx].map((a, i) => `<div class="x3-row"><input type="text" class="tt" data-tr="ten" data-hx="${hx}" data-i="${i}" value="${esc(a.ten)}" style="width:62px;height:28px;background:#0a0f19;color:#e6ebf5;border:1px solid #2a3957;border-radius:6px;padding:0 6px"><input type="number" data-tr="v" data-hx="${hx}" data-i="${i}" step="0.05" value="${f2(a.v, 3)}"><span class="x3-mut">m</span><button data-a="chon-truc" data-hx="${hx}" data-i="${i}" style="height:24px" title="Bay tới trục">⌖</button><button data-a="truc-tam" data-hx="${hx}" data-i="${i}" style="height:24px" title="Đặt trục vào tâm cấu kiện đang chọn">◎</button><button data-a="xoa-truc" data-hx="${hx}" data-i="${i}" style="height:24px">✕</button></div>`).join("") || '<div class="x3-mut">Chưa có.</div>'}
        <div class="x3-row"><button data-a="them-truc" data-hx="${hx}">+ Thêm trục</button></div>
        <div class="x3-row" style="flex-wrap:wrap;gap:6px"><span class="x3-mut">Lưới nhanh: từ</span><input type="number" data-lbd="${hx}" step="0.5" value="${f2(hx === "x" ? khungMo[0] : khungMo[1], 3)}" style="width:70px"><span class="x3-mut">m, cách (mm)</span><input type="text" data-lk="${hx}" placeholder="vd 3x6000 7200" style="width:120px;height:28px;background:#0a0f19;color:#e6ebf5;border:1px solid #2a3957;border-radius:6px;padding:0 6px"><button data-a="luoi-nhanh" data-hx="${hx}" style="height:26px">Tạo</button></div></div>`;
      const tg = tong.coc || {n: 0, v: 0, cat: 0}, cf = st.cocCfg;
      return `<div class="x3-sec"><h5>Khai báo tim trục</h5><div class="x3-mut"><b>Chỉnh nhanh:</b> kéo trục trực tiếp trên mô hình (bấm giữ vào phần đầu trục nhô ra ngoài công trình, hoặc giữ <kbd>Alt</kbd> rồi kéo ở bất kỳ đâu; tự bắt mép / tâm cột, dầm); bấm ◎ để đặt trục vào tâm cấu kiện đang chọn; hoặc gõ dãy khoảng cách ở <i>Lưới nhanh</i> (vd <kbd>3x6000 7200</kbd> = 3 nhịp 6 m rồi 1 nhịp 7,2 m).</div><div class="x3-mut" style="margin-top:4px">Trục hiển thị trên mô hình (nét đỏ + bong bóng tên), chọn được, bắt điểm khi vẽ. Lưu theo bản vẽ trong trình duyệt.</div>
        <div class="x3-row" style="flex-wrap:wrap;margin-top:6px"><button class="cam" data-a="do-truc">⚙ Dò từ vị trí cột</button><button data-a="xoa-het-truc" ${st.truc.x.length + st.truc.y.length ? "" : "disabled"}>Xóa hết trục</button></div></div>
        ${hang("x", "Trục số (đường đứng, x = const)", "Ví dụ 1, 2, 3 ... chạy theo phương X.")}${hang("y", "Trục chữ (đường ngang, y = const)", "Ví dụ A, B, C ... chạy theo phương Y.")}
        <div class="x3-sec"><h5>Cọc · cao độ đầu cọc &amp; cắt cọc</h5>
        <div class="x3-mut">${tg.n ? `Có <b style="color:#e6ebf5">${tg.n}</b> cọc (${f2(tg.v, 2)} m³ còn lại; cắt bỏ ${f2(tg.cat, 2)} m³). Thông số dưới đây áp cho mọi cọc, bỏ trống = tự tính theo đáy móng. Mỗi cọc sửa riêng khi chọn nó.` : 'Chưa có cọc: gán layer "Cọc" (hình tròn) ở cột trái rồi mở lại 3D, hoặc vẽ thêm cọc ở tab Vẽ thêm.'}</div>
        <div class="x3-kv" style="margin-top:6px">${kvr("Cao độ đầu cọc", `<input type="number" data-cc="head" step="0.05" placeholder="tự động" value="${cf.head != null ? f2(cf.head, 3) : ""}"> m`)}${kvr("Cao độ cắt cọc", `<input type="number" data-cc="cut" step="0.05" placeholder="tự động" value="${cf.cut != null ? f2(cf.cut, 3) : ""}"> m`)}${kvr("Chiều dài cọc L", `<input type="number" data-cc="L" step="0.5" min="0.5" value="${f2(cf.L, 2)}"> m`)}</div>
        <div class="x3-mut" style="margin-top:4px">Tự động: cao độ cắt = đáy móng + 0,1 m; đầu cọc = cắt + 0,5 m. Phần cọc từ cao độ cắt lên đầu cọc tô đỏ mờ (đoạn phải đập bỏ).</div></div>`;
    }

    function veHTML() {
      const v = st.ve, T = (k, ten) => `<button data-a="ve-${k}" class="${v.tool === k ? "on" : ""}">${ten}</button>`;
      const tsl = {
        cot: `Cột b × h <input type="number" data-ve="b" value="${v.b}" step="50" min="50"> × <input type="number" data-ve="h" value="${v.h}" step="50" min="50"> mm`,
        dam: `Dầm b <input type="number" data-ve="w" value="${v.w}" step="50" min="50"> × h <input type="number" data-ve="hd" value="${v.hd}" step="50" min="50"> mm`,
        san: `Sàn dày <input type="number" data-ve="t" value="${v.t}" step="10" min="40"> mm`,
        coc: `Cọc D <input type="number" data-ve="d" value="${v.d}" step="50" min="50"> mm`,
        truc: `Hướng <select data-ve="dir"><option value="x" ${v.dir === "x" ? "selected" : ""}>Trục số (đường đứng)</option><option value="y" ${v.dir === "y" ? "selected" : ""}>Trục chữ (đường ngang)</option></select>`,
        duong: v.pts.length >= 2 ? '<button data-a="xong-duong">Kết thúc đường (Enter)</button>' : "", chu: "",
      };
      const n = st.them.length;
      return `<div class="x3-sec x3-ve"><h5>Vẽ thêm vào bản vẽ 3D</h5>
        <div class="x3-mut">Vẽ trực tiếp trên mặt phẳng ngang ở cao độ chọn dưới đây. Điểm tự bắt vào giao trục, góc cấu kiện, tâm cọc, lưới 50 mm. Phần vẽ thêm là cấu kiện thật: liên kết, khoét lỗ, chọn và sửa được như cấu kiện từ bản vẽ.</div>
        <div class="x3-row" style="flex-wrap:wrap;margin-top:6px">${T("cot", "Cột")}${T("dam", "Dầm")}${T("san", "Sàn")}${T("coc", "Cọc")}${T("truc", "Trục")}${T("duong", "Đường")}${T("chu", "Ghi chú")}</div>
        <div class="x3-row" style="flex-wrap:wrap;gap:6px;margin-top:6px">${tsl[v.tool] || ""}</div>
        <div class="x3-row">Mức vẽ (cao độ) <input type="number" data-ve="muc" step="0.1" value="${f2(mucY())}"> m <button data-a="muc-chon" style="height:24px" title="Lấy cao độ đỉnh cấu kiện đang chọn">⌖ Từ đối tượng chọn</button></div>
        <div class="x3-row" style="margin-top:6px"><button class="${st.cc === "ve" ? "cam" : ""}" data-a="bat-ve">${st.cc === "ve" ? "■ Dừng vẽ (Esc)" : "✏ Bắt đầu vẽ (V)"}</button><button data-a="hoan-tac" ${lui.length ? "" : "disabled"}>↶ Hoàn tác (Ctrl+Z)</button></div>
        ${st.cc === "ve" ? `<div class="x3-cb" style="border-color:#4cffb0;background:rgba(76,255,176,.08)">${HUONG_DAN_VE[v.tool]}</div>` : ""}</div>
        <div class="x3-sec"><h5>Đã vẽ thêm (${n})</h5>
        ${n ? `<div style="max-height:200px;overflow:auto">${st.them.map(m => `<div class="x3-ho ${st.chon === m.id ? "sel" : ""}" data-go="${esc(m.id)}"><span><b>${esc(m.k === "chu" ? m.text : m.ten)}</b></span><span class="x3-chip" style="background:${m.k === "duong" || m.k === "chu" ? "#ffd166" : MAU_HEX(m.k === "dam" ? "dam" : m.k)}">${{cot: "Cột", dam: "Dầm", san: "Sàn", coc: "Cọc", duong: "Đường", chu: "Ghi chú"}[m.k]}</span></div>`).join("")}</div>` : '<div class="x3-mut">Chưa có.</div>'}
        <div class="x3-row" style="flex-wrap:wrap;margin-top:6px"><button class="cam" data-a="luu-bv" ${d.luuVe3d ? "" : "disabled"}>💾 Lưu vào bản vẽ (Ctrl+S)</button><button data-a="dxf" ${n || st.truc.x.length + st.truc.y.length ? "" : "disabled"}>⬇ Xuất DXF phần vẽ thêm &amp; trục</button><button data-a="xoa-het-moi" ${n ? "" : "disabled"}>Xóa hết phần vẽ thêm</button></div>
        <div class="x3-mut" style="margin-top:4px">DXF dùng đúng đơn vị bản vẽ (${esc(d.don_vi || "mm")}), mở được trong AutoCAD để ghép vào bản vẽ gốc. Bản vẽ gốc không bị sửa.</div>
        <div class="x3-mut" style="margin-top:4px"><b>Lưu vào bản vẽ</b>: ghi vào dự án và hiện lại trên bản vẽ 2D (cột, dầm, sàn, cọc, trục, đường, ghi chú), lần sau mở 3D vẫn còn.</div></div>`;
    }

    function mepHTML() {
      let s = "";
      const cdH = (d.chan_doan || []).map(c => `<div class="x3-cb">${esc(c)}</div>`).join("");
      if (!coOng) s += `<div class="x3-sec"><h5>Hệ thống MEP &amp; khoét lỗ</h5>${cdH || '<div class="x3-mut">Chưa có ống nào để khoét lỗ.</div>'}<div class="x3-mut" style="margin-top:6px">Khi bản vẽ có ống (gió, nước, PCCC, khay cáp) đã gán layer, mục này hiện bảng chỉnh cao độ, danh sách lỗ và va chạm.</div></div>`;
      if (coOng) {
        const c = soHo(), nv = vaCham.length + vaMep.length, loaiO = MEPK.filter(k => st.mep[k]);
        const ngMau = k => `<span class="x3-dot" style="background:${MAU_HEX(k)}"></span>`;
        s += `<div class="x3-sec"><h5>Hệ thống MEP &amp; khoét lỗ</h5>${cdH}
          <div class="x3-row"><label><input type="checkbox" data-o="khoet" ${st.khoet ? "checked" : ""}>Khoét lỗ dầm, sàn, vách cho ống đi xuyên</label></div>
          <div class="x3-row"><span>Khe hở quanh ống (mỗi phía)</span><span class="n"><input type="number" id="x3-hm" step="5" min="0" max="200" value="${st.hoMm}"> mm</span></div>
          ${loaiO.map(k => { const m = st.mep[k], kt = m.kt || m.kt0;
            return `<div class="x3-mp"><span class="t">${ngMau(k)}${LOAI[k].ten}</span><span class="x3-mut">${tong[k] ? tong[k].n : 0} đoạn</span>
              <div class="f">Đỉnh ống thấp hơn đỉnh sàn <input type="number" data-mo="${k}" step="0.05" min="0" max="${H}" value="${f2(m.off)}"> m
              ${k === "ong_gio" ? "" : m.tron ? `· Ø <input type="number" data-md="${k}" step="10" min="10" max="2000" value="${kt[0]}"> mm` : `· Rộng <input type="number" data-mw="${k}" step="10" min="10" max="3000" value="${kt[0]}"> × cao <input type="number" data-mh="${k}" step="10" min="10" max="3000" value="${kt[1]}"> mm`}</div></div>`; }).join("")}
          <div class="x3-mut" style="margin:6px 0">Hạ ống xuống dưới đáy dầm thì không còn lỗ. Kích thước ống nước / PCCC / khay cáp lấy từ tên layer (vd D100, 300x100), sửa được ở đây. Lỗ cho ống tròn tính theo hình vuông bao quanh ống.</div>
          <div class="x3-row"><span>Cao thông thủy tối thiểu cần</span><span class="n"><input type="number" id="x3-tmin" step="0.1" min="0" max="${H}" value="${st.tt}"> m</span></div>
          ${thongThuy != null ? `<div class="${thongThuy < st.tt ? "x3-cb" : "x3-mut"}" style="${thongThuy < st.tt ? "" : "padding:2px 0"}">Đáy MEP thấp nhất cách sàn <b style="color:#e6ebf5">${f2(thongThuy)} m</b>${thongThuy < st.tt ? ` (thấp hơn ${f2(st.tt)} m cần có)` : " (đạt)"}.</div>` : ""}
          ${holes.length ? `<div class="x3-row" style="flex-wrap:wrap;gap:6px;margin-top:4px">${["ok", "lon", "mep", "dut"].filter(k => c[k]).map(k => `<span class="x3-chip" style="background:${TRANG_THAI[k].css}">${TRANG_THAI[k].ten}: ${c[k]}</span>`).join("")}</div>` : '<div class="x3-mut">Không có ống nào giao với dầm, sàn, vách.</div>'}
          ${nv ? `<div class="x3-cb">${vaCham.length} ống đụng cột (không khoét được) · ${vaMep.length} chỗ giao cắt giữa các tuyến MEP. Tất cả tô đỏ.</div>` : ""}
          ${khongKhoet.length ? `<div class="x3-cb">Chưa khoét được ${khongKhoet.length} cấu kiện: ${khongKhoet.slice(0, 4).map(esc).join(", ")}${khongKhoet.length > 4 ? "…" : ""}.</div>` : ""}
          ${holes.length ? `<div style="margin-top:6px;max-height:260px;overflow:auto">${holes.map((h, i) => `<div class="x3-ho ${st.chon === h.id ? "sel" : ""}" data-h="${i}"><span><b>${esc(h.dam)}</b> · ${LOAI[h.hLoai].ten}</span><span class="x3-chip" style="background:${TRANG_THAI[h.tt].css}">${tenTT(h)}</span><span class="x3-mut">${LOAI[h.s.loai].ten} · lỗ ${f2(h.rong * 1000, 0)}×${f2(h.cao * 1000, 0)} mm${h.hLoai === "dam" ? ` · ${f2(h.cao / h.hD * 100, 0)}% chiều cao dầm` : ""}</span><span></span></div>`).join("")}</div>` : ""}
          ${vaCham.length + vaMep.length ? `<div style="margin-top:6px;max-height:160px;overflow:auto">${vaCham.map((v, i) => `<div class="x3-ho" data-vc="c${i}"><span><b>${esc(v.ck.ten)}</b> · Cột</span><span class="x3-chip" style="background:#ff4d4f">Va chạm</span><span class="x3-mut">${esc(objs.get(v.s.id).ten)}</span><span></span></div>`).join("")}${vaMep.map((v, i) => `<div class="x3-ho" data-vc="m${i}"><span><b>${esc(objs.get(v.a.id).ten)}</b></span><span class="x3-chip" style="background:#ff4d4f">Giao cắt</span><span class="x3-mut">với ${esc(objs.get(v.b.id).ten)}</span><span></span></div>`).join("")}</div>` : ""}
          <div class="x3-row" style="margin-top:6px;flex-wrap:wrap"><button data-a="csv" ${holes.length || nv ? "" : "disabled"}>⬇ Xuất lỗ &amp; va chạm (CSV)</button></div></div>`;
      }
      return s;
    }

    function moHinhHTML() {
      let s = `<div class="x3-sec"><h5>Hiển thị</h5>
        <div class="x3-row"><label><input type="checkbox" data-o="bong" ${st.bong ? "checked" : ""}>Đổ bóng</label></div>
        <div class="x3-row"><label><input type="checkbox" data-o="luoi" ${st.luoi ? "checked" : ""}>Lưới nền</label></div>
        <div class="x3-row"><label><input type="checkbox" data-o="canhBao" ${st.canhBao ? "checked" : ""}>Tô đỏ cấu kiện có cảnh báo</label></div></div>`;
      s += `<div class="x3-sec"><h5>Mặt cắt ngang</h5>
        <div class="x3-row"><label><input type="checkbox" data-o="cat" ${st.cat ? "checked" : ""}>Bật mặt cắt (cắt bỏ phần phía trên cao độ)</label></div>
        <input type="range" id="x3-cr" min="${f2(hop.min.y)}" max="${f2(hop.max.y + 0.01)}" step="0.01" value="${st.catY}" ${st.cat ? "" : "disabled"}>
        <div class="x3-mut">Cao độ cắt: <b id="x3-cv2" style="color:#e6ebf5">${f2(st.catY)}</b> m · 0 = mặt sàn tầng. Kéo xuống để nhìn vào bên trong.</div></div>`;
      s += mepHTML();
      s += `<div class="x3-sec"><h5>Xuất mô hình</h5><div class="x3-row" style="flex-wrap:wrap"><button data-a="glb">⬇ Xuất .glb (SketchUp, Blender, Revit...)</button></div>
        <div class="x3-mut">Giữ màu và các lỗ đã khoét. Đơn vị mét.</div></div>`;
      s += `<div class="x3-sec"><h5>Đo khoảng cách</h5>${soDo.length ? soDo.map((m, i) => `<div class="x3-row"><span>Số đo ${i + 1}</span><span class="n">${f2(m.a.distanceTo(m.b))} m</span></div>`).join("") : '<div class="x3-mut">Bấm nút 📏 Đo (hoặc phím M), rồi bấm 2 điểm trên mô hình.</div>'}
        ${soDo.length ? '<div class="x3-row"><button data-a="xoa-do">Xóa số đo</button></div>' : ""}</div>`;
      return s;
    }

    function capNhatPn() {
      pn.hidden = !st.pn;
      const cuon = pn.scrollTop;
      const TABS = [["dt", "Đối tượng"]].concat(dsMB ? [["mb", "Tầng"]] : [], [["tc", "Trục &amp; cọc"], ["ve", "Vẽ thêm"], ["mh", "Mô hình"]]);
      let s = `<div class="x3-tabs">${TABS.map(([k, t]) => `<button data-tab="${k}" class="${st.tab === k ? "on" : ""}">${t}</button>`).join("")}</div>`;
      if (st.tab === "dt") s += lopHTML() + chonHTML() + lienKetHTML();
      else if (st.tab === "mb" && dsMB) s += mbHTML();
      else if (st.tab === "tc") s += trucHTML();
      else if (st.tab === "ve") s += veHTML();
      else s += moHinhHTML();
      pn.innerHTML = s;
      pn.scrollTop = cuon;
      $("#x3-bg").classList.toggle("on", st.pn);
      const lvEl = $("#x3-lv"), olv = st.lv && objs.get(st.lv);
      lvEl.hidden = !olv;
      if (olv) lvEl.innerHTML = `◎ Đang làm việc: <b>${esc(olv.ten)}</b> · ${LOAI[olv.loai].ten} · ${olv.lk.size} liên kết <button id="x3-lv-ra">Thoát (Esc)</button>`;
      const lr = $("#x3-lv-ra"); if (lr) lr.onclick = thoatLamViec;
    }

    // ---------- sự kiện bảng điều khiển ----------
    function ganSua(bid, k, v) {
      ghiLui();
      const sc = st.sua[bid] = st.sua[bid] || {};
      if (v == null) delete sc[k]; else sc[k] = v;
      if (!Object.keys(sc).length) delete st.sua[bid];
      luu(); dung(); ap(); capNhatPn();
    }
    pn.addEventListener("change", e => {
      const t = e.target, dd = t.dataset;
      if (dd.l) { st.loc[dd.l] = t.checked; ap(); return; }
      if (dd.o) {
        const k = dd.o; st[k] = t.checked;
        if (k === "noi") { luu(); dung(); ap(); } else if (k === "khoet") { dung(); ap(); } else ap();
        capNhatPn(); return;
      }
      if (dd.mbh != null) { const c = st.mb[dsMB[+dd.mbh].key]; ghiLui(); c.hien = t.checked; luu(); dung(); ap(); capNhatPn(); return; }
      if (dd.mb) {
        const i = +dd.i, c = st.mb[dsMB[i].key]; ghiLui();
        if (dd.mb === "loai") { c.loai = t.value; if (c.loai === "mong") { c.Z = 0; c.tang = 0; } else if (c.loai === "tang") { if (!c.tang) c.tang = 1; c.Z = +(c.tang * H).toFixed(3); } }
        else { const v = parseFloat(t.value); if (!isFinite(v)) return; c[dd.mb] = dd.mb === "tang" ? Math.max(1, Math.round(v)) : v; if (dd.mb === "tang") c.Z = +(c.tang * H).toFixed(3); if (dd.mb === "dx" || dd.mb === "dy") c.canh = {n: 0, tay: true}; }
        luu(); dung(); ap(); capNhatPn(); return;
      }
      if (dd.g) {
        let v = parseFloat(t.value); if (!isFinite(v)) return;
        if (dd.g === "tang") { st.tang = Math.max(1, Math.min(30, Math.round(v))); luu(); dung(); datMoiTruong(); ap(); capNhatPn(); return; }
        st[dd.g] = Math.max(0, v); luu(); dung(); ap(); capNhatPn(); return;
      }
      if (dd.su) {
        const o = st.chon && objs.get(st.chon); if (!o) return;
        let v = parseFloat(t.value); v = isFinite(v) ? (dd.mm ? v / 1000 : v) : null;
        ganSua(o.base || o.id, dd.su, v); return;
      }
      if (dd.mi) {
        const m = st.them.find(x => x.id === st.chon); if (!m) return;
        ghiLui();
        if (dd.mi === "text") m.text = t.value;
        else {
          let v = parseFloat(t.value); if (!isFinite(v)) return; if (dd.mm) v /= 1000;
          if (dd.mi === "ax") m.a[0] = v; else if (dd.mi === "ay") m.a[1] = v; else if (dd.mi === "bx") m.b[0] = v; else if (dd.mi === "by") m.b[1] = v; else m[dd.mi] = v;
        }
        luu(); dung(); ap(); capNhatPn(); return;
      }
      if (dd.tr) {
        const so_ = st.chon && objs.get(st.chon), tt_ = so_ && so_.truc;
        const hx_ = dd.hx || (tt_ && tt_.hx), i_ = dd.i != null ? +dd.i : (tt_ && tt_.i);
        const a = hx_ && st.truc[hx_] && st.truc[hx_][i_]; if (!a) return;
        ghiLui();
        if (dd.tr === "ten") a.ten = t.value || a.ten; else { const v = parseFloat(t.value); if (!isFinite(v)) return; a.v = v; }
        luu(); dungTruc(); ap(); capNhatPn(); return;
      }
      if (dd.cc) {
        ghiLui(); const v = parseFloat(t.value);
        if (dd.cc === "L") st.cocCfg.L = isFinite(v) ? Math.max(0.5, v) : 15; else st.cocCfg[dd.cc] = isFinite(v) ? v : null;
        luu(); dung(); ap(); capNhatPn(); return;
      }
      if (dd.ve) {
        if (dd.ve === "dir") st.ve.dir = t.value;
        else { const v = parseFloat(t.value); if (!isFinite(v)) return; st.ve[dd.ve] = dd.ve === "muc" ? v : Math.max(10, v); }
        capNhatPn(); return;
      }
      if (dd.mo) { st.mep[dd.mo].off = Math.max(0, parseFloat(t.value) || 0); dung(); ap(); capNhatPn(); return; }
      if (dd.md || dd.mw || dd.mh) {
        const k = dd.md || dd.mw || dd.mh, m = st.mep[k], kt = (m.kt || m.kt0).slice(), v = Math.max(10, parseFloat(t.value) || 10);
        if (dd.md) { kt[0] = v; kt[1] = v; } else if (dd.mw) kt[0] = v; else kt[1] = v;
        m.kt = kt; dung(); ap(); capNhatPn(); return;
      }
      if (t.id === "x3-tmin") { st.tt = Math.max(0, parseFloat(t.value) || 0); capNhatPn(); return; }
      if (t.id === "x3-hm") { st.hoMm = Math.max(0, parseFloat(t.value) || 0); dung(); ap(); capNhatPn(); }
    });
    pn.addEventListener("input", e => { if (e.target.id === "x3-cr") { st.catY = parseFloat(e.target.value); $("#x3-cv2").textContent = f2(st.catY); ap(); } });
    pn.addEventListener("click", e => {
      const tb = e.target.closest("[data-tab]"); if (tb) { st.tab = tb.dataset.tab; capNhatPn(); return; }
      const go = e.target.closest("[data-go]"); if (go) { const o = objs.get(go.dataset.go); if (o) { st.chon = o.id; if (st.lv) st.lv = o.id; ap(); capNhatPn(); bayToiVat(o); } return; }
      const hb = e.target.closest("[data-h]"); if (hb) { const h = holes[+hb.dataset.h]; st.chon = h.id; ap(); capNhatPn();
        const c = new THREE.Vector3(h.cx, (h.yb + h.yt) / 2, -h.cy), hu = cam.position.clone().sub(dk.target).normalize(); hu.y = Math.max(hu.y, 0.4); bay(c.clone().add(hu.normalize().multiplyScalar(Math.max(h.hD, 0.6) * 5 + 2)), c); return; }
      const vc = e.target.closest("[data-vc]");
      if (vc) {
        const [k, i] = [vc.dataset.vc[0], +vc.dataset.vc.slice(1)], v = k === "c" ? vaCham[i] : vaMep[i], o = k === "c" ? objs.get(v.id) : objs.get(v.a.id), oo = objs.get(k === "c" ? v.s.id : v.b.id);
        st.chon = o.id; ap(); capNhatPn();
        const b = new THREE.Box3(); [o, oo].forEach(x => x.meshes.forEach(m => b.expandByObject(m)));
        const c = b.getCenter(new THREE.Vector3()), hu = cam.position.clone().sub(dk.target).normalize(); hu.y = Math.max(hu.y, 0.4); hu.normalize();
        bay(c.clone().add(hu.multiplyScalar(Math.max(b.getSize(new THREE.Vector3()).length(), 1) * 1.8 + 1.5)), c); return;
      }
      const a = e.target.closest("[data-a]"); if (!a) return; hanhDong(a.dataset.a, a.dataset);
    });
    function chonTruc(hx, i) { const o = objs.get(`truc:${hx}:${i}`); if (o) { st.chon = o.id; st.tab = "tc"; ap(); capNhatPn(); bayToiVat(o); } }
    function hanhDong(k, dd = {}) {
      const o = st.chon && objs.get(st.chon);
      if (k === "hien-het") { st.an.clear(); st.co = null; ap(); capNhatPn(); }
      else if (k === "zoom" && o) bayToiVat(o);
      else if (k === "an" && o) { st.an.add(o.id); st.chon = null; ap(); capNhatPn(); }
      else if (k === "co" && o) { st.co = new Set([o.id]); ap(); capNhatPn(); }
      else if (k === "cum" && o) { st.co = new Set([o.id, ...o.lk]); ap(); capNhatPn(); }
      else if (k === "lv" && o) vaoLamViec(o.id);
      else if (k === "xoa-do") xoaDo();
      else if (k === "csv") xuatCSV();
      else if (k === "glb") xuatGLB();
      else if (k === "mb") matBangXem();
      else if (k === "reset-sua" && o) { ghiLui(); delete st.sua[o.base || o.id]; luu(); dung(); ap(); capNhatPn(); }
      else if (k === "coc-all" && o && o.coc) {
        ghiLui(); st.cocCfg.head = o.coc.head; st.cocCfg.cut = o.coc.cut; st.cocCfg.L = o.coc.L;
        Object.keys(st.sua).forEach(id => { const s = st.sua[id]; delete s.head; delete s.cut; delete s.L; if (!Object.keys(s).length) delete st.sua[id]; });
        luu(); dung(); ap(); capNhatPn();
      }
      else if (k === "xoa-moi" && o) xoaChon();
      else if (k === "xoa-truc") {
        if (dd.hx != null) { ghiLui(); st.truc[dd.hx].splice(+dd.i, 1); luu(); dungTruc(); st.chon = null; ap(); capNhatPn(); } else xoaChon();
      }
      else if (k === "chon-truc") chonTruc(dd.hx, +dd.i);
      else if (k === "them-truc") {
        ghiLui(); const arr = st.truc[dd.hx], l = arr[arr.length - 1], l2 = arr[arr.length - 2];
        const buoc = l && l2 ? l.v - l2.v : 3, v0 = l ? l.v + buoc : (dd.hx === "x" ? khungMo[0] : khungMo[1]);
        arr.push({ten: dd.hx === "x" ? String(arr.length + 1) : chuCai(arr.length), v: +v0.toFixed(3)});
        luu(); dungTruc(); ap(); capNhatPn();
      }
      else if (k === "mb-can" && dsMB) { const c = st.mb[dsMB[+dd.i].key]; ghiLui(); c.canh = null; tuCanMB(false); luu(); dung(); ap(); capNhatPn(); }
      else if (k === "mb-can-het" && dsMB) { ghiLui(); tuCanMB(true); luu(); dung(); ap(); capNhatPn(); }
      else if (k === "mb-chuan" && dsMB) { ghiLui(); st.mbRef = dsMB[+dd.i].key; tuCanMB(true); luu(); dung(); ap(); capNhatPn(); }
      else if (k === "mb-chi" && dsMB) { ghiLui(); dsMB.forEach((p, j) => { st.mb[p.key].hien = j === +dd.i; }); luu(); dung(); ap(); capNhatPn(); }
      else if (k === "mb-hien-het" && dsMB) { ghiLui(); dsMB.forEach(p => { st.mb[p.key].hien = true; }); luu(); dung(); ap(); capNhatPn(); }
      else if (k === "do-truc") doTruc();
      else if (k === "truc-tam") {
        const c = st.chon && objs.get(st.chon);
        if (!c || !c.vongs || !c.vongs[0]) { alert("Chọn một cấu kiện (cột, dầm, cọc...) trước rồi bấm ◎."); return; }
        const t = tamVong(c.vongs[0]), a = st.truc[dd.hx][+dd.i]; if (!a) return;
        ghiLui(); a.v = +t[dd.hx === "x" ? 0 : 1].toFixed(3); luu(); dungTruc(); ap(); capNhatPn();
      }
      else if (k === "luoi-nhanh") {
        const hx = dd.hx, gt = pn.querySelector(`[data-lk="${hx}"]`).value, bd = parseFloat(pn.querySelector(`[data-lbd="${hx}"]`).value);
        const bc = []; gt.split(/[\s,;]+/).filter(Boolean).forEach(tk => { const m = tk.match(/^(\d+)[x*×](\d+(?:\.\d+)?)$/i); if (m) for (let i = 0; i < Math.min(+m[1], 60); i++) bc.push(+m[2]); else if (isFinite(+tk)) bc.push(+tk); });
        if (!bc.length || !isFinite(bd)) { alert("Gõ khoảng cách (mm), ví dụ: 3x6000 7200"); return; }
        if (st.truc[hx].length && !confirm("Thay các trục hiện có của hướng này bằng lưới mới?")) return;
        ghiLui(); let v = bd; const arr = [{ten: hx === "x" ? "1" : "A", v: +v.toFixed(3)}];
        bc.forEach((b, i) => { v += b / 1000; arr.push({ten: hx === "x" ? String(i + 2) : chuCai(i + 1), v: +v.toFixed(3)}); });
        st.truc[hx] = arr; luu(); dungTruc(); ap(); capNhatPn();
      }
      else if (k === "xoa-het-truc") { if (confirm("Xóa toàn bộ tim trục đã khai báo?")) { ghiLui(); st.truc = {x: [], y: []}; luu(); dungTruc(); ap(); capNhatPn(); } }
      else if (k.startsWith("ve-")) { st.ve.tool = k.slice(3); huyVe(); capNhatPn(); }
      else if (k === "bat-ve") datCC(st.cc !== "ve", "ve");
      else if (k === "xong-duong") { xongDuong(); }
      else if (k === "hoan-tac") hoanTac();
      else if (k === "muc-chon") { if (o) { st.ve.muc = +o.dz[1].toFixed(3); capNhatPn(); } }
      else if (k === "dxf") xuatDXF();
      else if (k === "luu-bv") luuBanVe();
      else if (k === "xoa-het-moi") { if (confirm("Xóa hết cấu kiện và nét đã vẽ thêm?")) { ghiLui(); st.them = []; st.chon = null; luu(); dung(); ap(); capNhatPn(); } }
    }
    function xoaChon() {
      const o = st.chon && objs.get(st.chon); if (!o) return;
      if (o.truc) { ghiLui(); st.truc[o.truc.hx].splice(o.truc.i, 1); luu(); st.chon = null; dungTruc(); ap(); capNhatPn(); return; }
      const i = st.them.findIndex(x => x.id === o.id);
      if (i < 0) return;
      ghiLui(); st.them.splice(i, 1); delete st.sua[o.id]; luu(); st.chon = null; dung(); ap(); capNhatPn();
    }
    // Dò tim trục từ tâm các cột (gom các cột thẳng hàng trong 150 mm)
    function doTruc() {
      const tam = []; objs.forEach(o => { if (o.loai === "cot" && !o.base && !o.bo && o.hien && o.vongs && o.vongs[0]) tam.push(tamVong(o.vongs[0])); });
      if (tam.length < 2) { alert("Cần ít nhất 2 cột để dò tim trục."); return; }
      if ((st.truc.x.length || st.truc.y.length) && !confirm("Thay các tim trục hiện có bằng kết quả dò từ cột?")) return;
      ghiLui();
      const xs = gom(tam.map(p => p[0]), 0.15), ys = gom(tam.map(p => p[1]), 0.15);
      st.truc = {x: xs.map((v, i) => ({ten: String(i + 1), v: +v.toFixed(3)})), y: ys.map((v, i) => ({ten: chuCai(i), v: +v.toFixed(3)}))};
      luu(); dungTruc(); ap(); capNhatPn();
    }
    // Mặt bằng tầng: nhìn từ trên, cắt ngang qua dầm, hiện nét 2D
    let mbDang = false;
    function matBangXem() {
      mbDang = !mbDang;
      if (mbDang) {
        let hMax = 0; objs.forEach(o => { if (o.loai === "dam" && !o.base) hMax = Math.max(hMax, o.dz[1] - o.dz[0]); });
        st.matBang = true; st.cat = true; st.catY = H - Math.max(hMax, 0.3) / 2; $("#x3-ct").classList.add("on"); nhin("top");
      } else { st.cat = false; $("#x3-ct").classList.remove("on"); nhin("iso"); }
      $("#x3-mb").classList.toggle("on", mbDang); ap(); capNhatPn();
    }
    // Xuất DXF phần vẽ thêm + tim trục (đơn vị theo bản vẽ gốc)
    function xuatDXF() {
      const k = {mm: 1000, cm: 100, m: 1}[d.don_vi] || 1000, E = [], layers = {};
      const L = (layer, mau) => { layers[layer] = mau; return layer; };
      const so = v => (+(v * k).toFixed(4)).toString();
      const dong = (ly, a, b) => E.push(`0\nLINE\n8\n${ly}\n10\n${so(a[0])}\n20\n${so(a[1])}\n30\n0\n11\n${so(b[0])}\n21\n${so(b[1])}\n31\n0\n`);
      const chu = (ly, p, h, tx) => E.push(`0\nTEXT\n8\n${ly}\n10\n${so(p[0])}\n20\n${so(p[1])}\n30\n0\n40\n${so(h)}\n1\n${String(tx).replace(/[\r\n]/g, " ")}\n`);
      const vong = (ly, P) => P.forEach((p, i) => dong(ly, p, P[(i + 1) % P.length]));
      st.them.forEach(m => {
        if (m.k === "cot") { vong(L("AZB-COT", 1), vongHCN(m.x, m.y, m.b, m.h)); chu("AZB-COT", [m.x, m.y], 0.15, m.ten); }
        else if (m.k === "dam") { const P = vongDam(m.a, m.b, m.w); vong(L("AZB-DAM", 2), P); chu("AZB-DAM", [(m.a[0] + m.b[0]) / 2, (m.a[1] + m.b[1]) / 2], 0.15, `${m.ten} ${f2(m.w * 1000, 0)}x${f2(m.h * 1000, 0)}`); }
        else if (m.k === "san") { vong(L("AZB-SAN", 5), [[m.x0, m.y0], [m.x1, m.y0], [m.x1, m.y1], [m.x0, m.y1]]); chu("AZB-SAN", [(m.x0 + m.x1) / 2, (m.y0 + m.y1) / 2], 0.15, `${m.ten} dày ${f2(m.t * 1000, 0)}`); }
        else if (m.k === "coc") { L("AZB-COC", 30); E.push(`0\nCIRCLE\n8\nAZB-COC\n10\n${so(m.x)}\n20\n${so(m.y)}\n30\n0\n40\n${so(m.d / 2)}\n`); chu("AZB-COC", [m.x + m.d / 2, m.y], 0.15, m.ten); }
        else if (m.k === "duong") { L("AZB-NET", 2); for (let i = 0; i + 1 < m.pts.length; i++) dong("AZB-NET", m.pts[i], m.pts[i + 1]); }
        else if (m.k === "chu") { L("AZB-CHU", 7); chu("AZB-CHU", [m.x, m.y], 0.2, m.text); }
      });
      const [x0, y0, x1, y1] = khungMo, mg = 1.5;
      st.truc.x.forEach(a => { dong(L("AZB-TRUC", 1), [a.v, y0 - mg], [a.v, y1 + mg]); chu("AZB-TRUC", [a.v, y1 + mg + 0.1], 0.25, a.ten); });
      st.truc.y.forEach(a => { dong(L("AZB-TRUC", 1), [x0 - mg, a.v], [x1 + mg, a.v]); chu("AZB-TRUC", [x0 - mg - 0.4, a.v], 0.25, a.ten); });
      const bang = Object.keys(layers).map(n => `0\nLAYER\n2\n${n}\n70\n0\n62\n${layers[n]}\n6\nCONTINUOUS\n`).join("");
      const txt = `0\nSECTION\n2\nTABLES\n0\nTABLE\n2\nLAYER\n70\n${Object.keys(layers).length}\n${bang}0\nENDTAB\n0\nENDSEC\n0\nSECTION\n2\nENTITIES\n${E.join("")}0\nENDSEC\n0\nEOF\n`;
      taiVe(new Blob([txt], {type: "application/dxf"}), "AZB-3D-ve-them-" + (d.ten_file || "mo-hinh").replace(/\.[^.]+$/, "") + ".dxf");
    }
    function xuatCSV() {
      const so = v => typeof v === "number" ? +v.toFixed(3) : v;
      const dong = [["Cấu kiện bị khoét", "Loại", "Hệ thống ống", "Kích thước ống", "Rộng lỗ (mm)", "Cao lỗ (mm)", "Dài xuyên (mm)", "Đáy lỗ (m)", "Đỉnh lỗ (m)", "Lỗ / chiều cao dầm (%)", "Đánh giá", "Tọa độ X (m)", "Tọa độ Y (m)"]]
        .concat(holes.map(h => [h.dam, LOAI[h.hLoai].ten, LOAI[h.s.loai].ten, objs.get(h.s.id).kt, h.rong * 1000, h.cao * 1000, h.dai * 1000, h.yb, h.yt, h.hLoai === "dam" ? h.cao / h.hD * 100 : "", tenTT(h), h.cx, h.cy].map(so)));
      if (vaCham.length + vaMep.length) {
        dong.push([], ["VA CHẠM / GIAO CẮT", "Đối tượng 1", "Đối tượng 2", "Ghi chú"]);
        vaCham.forEach(v => dong.push(["Ống đụng cột", "Cột " + v.ck.ten, objs.get(v.s.id).ten, "Không khoét được, cần dời ống hoặc đổi cao độ"]));
        vaMep.forEach(v => dong.push(["Giao cắt MEP", objs.get(v.a.id).ten, objs.get(v.b.id).ten, "Hai tuyến cắt ngang nhau ở cùng cao độ"]));
      }
      const csv = "\ufeff" + dong.map(r_ => r_.map(v => `"${String(v).replace(/"/g, '""')}"`).join(",")).join("\r\n");
      taiVe(new Blob([csv], {type: "text/csv;charset=utf-8"}), "lo_xuyen_va_va_cham.csv");
    }
    function napScript(url) {
      return new Promise((ok, loi) => { const s = document.createElement("script"); s.src = url; s.onload = ok; s.onerror = () => loi(new Error("Không tải được bộ xuất .glb (cần mạng).")); document.head.appendChild(s); });
    }
    async function xuatGLB() {
      try {
        if (!THREE.GLTFExporter) await napScript("https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/exporters/GLTFExporter.js");
        const vien = []; nhomMain.traverse(o => { if (o.isLineSegments && o.visible) { o.visible = false; vien.push(o); } });
        new THREE.GLTFExporter().parse(nhomMain, res => {
          vien.forEach(o => o.visible = true);
          taiVe(new Blob([res], {type: "model/gltf-binary"}), "AZB-3D-" + (d.ten_file || "mo-hinh").replace(/\.[^.]+$/, "") + ".glb");
        }, {binary: true, onlyVisible: true});
      } catch (e) { alert(e.message); }
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
    $("#x3-ve").onclick = () => datCC(st.cc !== "ve", "ve");
    $("#x3-mb").onclick = matBangXem;
    $("#x3-xr").onclick = () => { st.xray = !st.xray; $("#x3-xr").classList.toggle("on", st.xray); ap(); };
    $("#x3-ct").onclick = () => { st.cat = !st.cat; $("#x3-ct").classList.toggle("on", st.cat); if (st.cat) { st.pn = true; if (st.catY >= hop.max.y) st.catY = hop.min.y + (hop.max.y - hop.min.y) * 0.55; } ap(); capNhatPn(); };
    $("#x3-xoay").onclick = () => { st.xoay = !st.xoay; dk.autoRotate = st.xoay; dk.autoRotateSpeed = 1.6; $("#x3-xoay").classList.toggle("on", st.xoay); };
    $("#x3-anh").onclick = chupAnh;
    $("#x3-ten").onclick = () => { st.ten = !st.ten; $("#x3-ten").classList.toggle("on", st.ten); dungNhan(); };
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
        <h4>2b. Liên kết, làm việc từng phần (tab Đối tượng)</h4><ul>
        <li>Cột, dầm, sàn, móng, vách, cọc được <b>liên kết</b> khi chạm nhau trên mặt bằng và trùng khoảng cao độ. Chọn một cấu kiện: các phần liên kết sáng nhẹ, danh sách liên kết hiện bên dưới (bấm tên để đi tới). Mục <i>Liên kết toàn công trình</i> báo chỗ rời rạc: dầm chưa tựa đủ 2 đầu, cột chưa đặt trên móng, cọc không nằm dưới móng...</li>
        <li><b>Nối dầm vào cột / vách</b> khi hở nhỏ (mặc định ≤ 300 mm), <b>số tầng dựng</b> (nhân cột, dầm, sàn, vách theo chiều cao tầng), <b>bê tông liền khối</b> (một màu như công trình thật).</li>
        <li><b>Nhấp đúp</b> hoặc phím <kbd>W</kbd>: làm việc riêng với cấu kiện đó, các phần khác mờ đi, chỉ giữ phần liên kết; bấm sang cấu kiện liên kết để đổi sang nó; <kbd>Esc</kbd> thoát. Bảng bên phải hiện thông số và ô chỉnh theo loại (cột, dầm, sàn, móng, vách, cọc, trục): cao độ đáy / đỉnh, kích thước, vị trí so với tim trục.</li></ul>
        <h4>2c. Tim trục và cọc (tab Trục &amp; cọc)</h4><ul>
        <li>Khai báo trục số (đường đứng) và trục chữ (đường ngang) bằng tay hoặc bấm <b>Dò từ vị trí cột</b>. Trục hiện nét đỏ có bong bóng tên, chọn được, sửa tên / vị trí được; cấu kiện cho biết nó nằm ở giao trục nào.</li>
        <li><b>Cọc</b> (layer gán loại Cọc, hình tròn): đặt <b>cao độ đầu cọc</b>, <b>cao độ cắt cọc</b>, chiều dài L chung cho mọi cọc hoặc riêng từng cọc. Đoạn từ cao độ cắt lên đầu cọc tô đỏ mờ (phần phải đập bỏ), có thể tích cọc còn lại và phần cắt bỏ.</li>
        <li>Nút <b>▦ Mặt bằng</b>: nhìn từ trên, cắt ngang qua dầm và hiện nét 2D như bản vẽ mặt bằng; bật / tắt riêng ở lớp <i>Mặt bằng</i>.</li></ul>
        <h4>2d. Vẽ thêm trong 3D (nút ✏ Vẽ hoặc phím V)</h4><ul>
        <li>Chọn công cụ: <b>Cột, Dầm, Sàn, Cọc, Trục, Đường, Ghi chú</b>, nhập kích thước, đặt <b>mức vẽ</b> (cao độ mặt phẳng vẽ) rồi bấm lên mô hình. Điểm tự bắt vào giao trục, góc cấu kiện, tâm cọc, lưới 50 mm. Đường: nhấp đúp hoặc Enter để kết thúc; chuột phải hoặc Esc hủy thao tác.</li>
        <li>Phần vẽ thêm là cấu kiện thật: liên kết, khoét lỗ, chọn và sửa số liệu được; <kbd>Delete</kbd> xóa, <kbd>Ctrl</kbd>+<kbd>Z</kbd> hoàn tác. Dữ liệu lưu theo bản vẽ trong trình duyệt; <b>Xuất DXF</b> để ghép vào bản vẽ gốc (bản vẽ gốc không bị sửa).</li></ul>
        <h4>3. Hệ thống MEP và khoét lỗ tự động</h4><ul>
        <li>Hiển thị: <b>ống gió</b>, <b>ống cấp thoát nước</b>, <b>ống PCCC</b> (tròn) và <b>khay cáp</b> (chữ nhật). Ở cột trái, gán layer tương ứng cho loại <i>Ống nước, Ống PCCC, Khay cáp</i> (app tự đoán theo tên layer). Kích thước đọc từ tên layer, ví dụ <kbd>P-WATER-D100</kbd>, <kbd>PCCC DN65</kbd>, <kbd>KHAY CAP 400x100</kbd>; không ghi thì dùng mặc định và sửa được ở bảng bên phải.</li>
        <li>App tìm chỗ ống đi xuyên <b>dầm, sàn, vách</b> và <b>khoét lỗ thật</b> trên khối bê tông, có khung màu đánh dấu quanh lỗ. Lỗ cho ống tròn tính theo hình vuông bao quanh ống. Sàn / vách hình phức tạp (không lồi) chưa khoét được, app báo tên.</li>
        <li>Chỉnh ở mục <i>Hệ thống MEP &amp; khoét lỗ</i>: <b>Đỉnh ống thấp hơn đỉnh sàn</b> (m) cho từng hệ thống, <b>khe hở</b> quanh ống (mm), kích thước ống. Lỗ và danh sách cập nhật ngay. Hạ ống xuống dưới đáy dầm thì không còn lỗ.</li>
        <li>Đánh giá lỗ (ngưỡng tham khảo, kỹ sư kết cấu quyết định): <b>Dầm</b>: <span class="x3-chip" style="background:${TRANG_THAI.ok.css}">Đạt</span> lỗ cao ≤ 1/3 chiều cao dầm · <span class="x3-chip" style="background:${TRANG_THAI.lon.css}">Lỗ lớn</span> hơn 1/3 · <span class="x3-chip" style="background:${TRANG_THAI.mep.css}">Lẹm mép</span> lỗ chạm đáy / đỉnh dầm · <span class="x3-chip" style="background:${TRANG_THAI.dut.css}">Cắt đứt</span> ống cao bằng dầm. <b>Sàn</b>: lỗ lớn nhất ≤ 300 mm đạt, 300 đến 600 mm lỗ lớn (cần gia cường), trên 600 mm đỏ. <b>Vách</b>: ≤ 300 mm đạt; chạm đáy / đỉnh vách là lẹm mép; ống cao bằng vách là cắt đứt.</li>
        <li>Bấm một dòng trong danh sách để bay tới lỗ. Nút <b>Xuất lỗ &amp; va chạm (CSV)</b> mở được bằng Excel, dùng để gửi bên kết cấu duyệt.</li></ul>
        <h4>4. Va chạm và cao thông thủy (tự động)</h4><ul>
        <li>Ống <b>đụng cột</b> (không khoét được) và hai tuyến MEP <b>cắt ngang nhau ở cùng cao độ</b> được tô đỏ và liệt kê; bấm một dòng để bay tới. Chỗ ống rẽ nhánh (chữ T) không bị tính là va chạm.</li>
        <li><b>Cao thông thủy:</b> app báo đáy MEP thấp nhất cách sàn bao nhiêu mét và cảnh báo nếu thấp hơn mức bạn đặt (mặc định 2,4 m).</li></ul>
        <h4>5. Mặt cắt, xuyên thấu</h4><ul><li><kbd>C</kbd> bật <b>Mặt cắt</b>, kéo thanh cao độ để cắt bỏ phần phía trên và nhìn vào trong (ví dụ cắt ngay dưới sàn để thấy hệ dầm cột).</li>
        <li><kbd>X</kbd> <b>Xuyên thấu</b>: mọi khối thành trong mờ, tiện soi ống gió nằm sau dầm.</li></ul>
        <h4>6. Đo khoảng cách</h4><ul><li><kbd>M</kbd> bật đo, bấm 2 điểm (tự hít vào góc gần nhất). Kết quả gồm khoảng cách thẳng, ngang và đứng. Bấm <b>Xóa số đo</b> để làm lại.</li></ul>
        <h4>7. Tên, xuất ảnh, xuất mô hình</h4><ul><li><kbd>L</kbd> hiện <b>tên</b> cột, dầm, vách... ngay trên mô hình (tối đa 250 nhãn).</li><li><b>Chụp ảnh</b> lưu PNG khung nhìn hiện tại. <kbd>R</kbd> tự xoay để trình chiếu. Tắt <i>Đổ bóng</i> nếu máy yếu bị giật.</li><li><b>Xuất .glb</b> (cuối bảng bên phải) để mở trong SketchUp, Blender, Revit... giữ màu và các lỗ đã khoét, đơn vị mét.</li></ul>
        <h4>Phím tắt</h4><p><kbd>Esc</kbd> hủy / thoát / bỏ chọn / đóng · <kbd>W</kbd> làm việc với cấu kiện chọn · <kbd>V</kbd> vẽ · <kbd>Delete</kbd> xóa phần vẽ thêm · <kbd>Ctrl</kbd>+<kbd>Z</kbd> hoàn tác · <kbd>?</kbd> mở hướng dẫn này.</p>
        <div class="bt"><button class="cam" id="x3-gd-ok">Đã hiểu</button></div></div>`;
      gd.hidden = false; gd.querySelector("#x3-gd-ok").onclick = () => moGD(false);
      try { localStorage.setItem("azb-3d-gd", "1"); } catch (e) {}
    }
    $("#x3-hd").onclick = () => moGD(gd.hidden);
    gd.addEventListener("click", e => { if (e.target === gd) moGD(false); });

    // ---------- phím tắt ----------
    function phim(e) {
      if (e.target.tagName === "INPUT" && e.target.type !== "checkbox" && e.target.type !== "range") return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); luuBanVe(); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") { e.preventDefault(); hoanTac(); return; }
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "escape") {
        if (lop.querySelector("#x3-xn")) lop.querySelector("#x3-xn").remove();
        else if (!gd.hidden) moGD(false);
        else if (st.cc === "ve" && st.ve.pts.length) huyVe();
        else if (st.cc) datCC(false);
        else if (st.lv) thoatLamViec();
        else if (st.chon) { st.chon = null; ap(); capNhatPn(); } else thoat();
        return;
      }
      if (k === "enter" && st.cc === "ve") { xongDuong(); return; }
      if ((k === "delete" || k === "backspace") && st.chon && !st.cc) { xoaChon(); return; }
      if (k === "?" || (k === "/" && e.shiftKey)) moGD(gd.hidden);
      else if (k === "1") nhin("iso"); else if (k === "2") nhin("top"); else if (k === "3") nhin("front"); else if (k === "4") nhin("right"); else if (k === "f") nhin("fit");
      else if (k === "x") $("#x3-xr").click(); else if (k === "c") $("#x3-ct").click(); else if (k === "m") $("#x3-do").click(); else if (k === "r") $("#x3-xoay").click(); else if (k === "l") $("#x3-ten").click();
      else if (k === "v") $("#x3-ve").click(); else if (k === "w") { const o = st.chon && objs.get(st.chon); if (o) vaoLamViec(o.id); }
      else if (k === "h") hanhDong("an"); else if (k === "i") hanhDong("co"); else if (k === "a") hanhDong("hien-het");
    }
    addEventListener("keydown", phim);
    $("#x3-luu").onclick = luuBanVe;
    $("#x3-dong").onclick = () => thoat();
    // Đóng 3D: nếu còn thay đổi chưa lưu thì hỏi bằng hộp thoại riêng với 3 lựa chọn rõ ràng
    function thoat() {
      if (!(chuaLuuBV() && d.luuVe3d)) { dong(); return; }
      if (lop.querySelector("#x3-xn")) return;
      const hop = document.createElement("div"); hop.className = "x3-gd"; hop.id = "x3-xn";
      hop.innerHTML = `<div style="width:min(440px,100%)"><h3>Lưu thay đổi trước khi đóng?</h3>
        <p>Bạn đã chỉnh trong 3D (vẽ thêm, tim trục, cao độ, ghép mặt bằng...) nhưng chưa lưu vào bản vẽ. Nếu đóng ngay, các thay đổi này sẽ mất.</p>
        <div class="bt" style="flex-wrap:wrap"><button id="x3-xn-ql">Quay lại</button><button id="x3-xn-kl">Đóng, không lưu</button><button class="cam" id="x3-xn-l">💾 Lưu rồi đóng</button></div></div>`;
      lop.querySelector(".x3-main").appendChild(hop);
      const dongHop = () => hop.remove();
      hop.querySelector("#x3-xn-ql").onclick = dongHop;
      hop.querySelector("#x3-xn-kl").onclick = () => { dongHop(); dong(); };
      hop.querySelector("#x3-xn-l").onclick = () => { luuBanVe(); dongHop(); dong(); };
      hop.addEventListener("click", e => { if (e.target === hop) dongHop(); });
      hop.querySelector("#x3-xn-l").focus();
    }

    // ---------- khởi động ----------
    dung(); datMoiTruong(); ap();
    // Khung nhìn đầu tiên: ôm cụm khối chính. Khi cấu kiện rải rác trên cả bản vẽ, ôm toàn bản vẽ sẽ làm khối nhỏ chỉ còn vài pixel.
    let khungNote = "";
    {
      const ds = [...objs.values()].filter(o => o.meshes.length && o.loai !== "truc").map(o => { const b = new THREE.Box3(); o.meshes.forEach(m => b.expandByObject(m)); return {o, b}; });
      const kichXZ = ds.map(x => Math.max(x.b.max.x - x.b.min.x, x.b.max.z - x.b.min.z)).sort((p, q) => p - q);
      const trungVi = kichXZ.length ? Math.max(kichXZ[kichXZ.length >> 1], 0.2) : 1;
      const D = Math.max(50, 25 * trungVi);
      const cum = cumChinh(ds.map(x => [x.b.min.x, x.b.min.z, x.b.max.x, x.b.max.z]), D);
      const fb = new THREE.Box3();
      cum.forEach(i => fb.union(ds[i].b));
      if (!fb.isEmpty() && cum.length < ds.length) {
        const fc = fb.getCenter(new THREE.Vector3()), fs = fb.getSize(new THREE.Vector3());
        const fk = Math.max(fs.x, fs.y, fs.z, 0.5), dist = fk * 2.4 + 1.2;
        const hu = new THREE.Vector3(0.5625, 0.5, 0.6875).normalize();   // hướng góc nhìn 3D
        cam.position.copy(fc).add(hu.multiplyScalar(dist)); dk.target.copy(fc);
        dk.minDistance = Math.max(0.3, Math.min(bk * 0.02, fk * 0.2));
        khungNote = `Khung đầu tiên ôm ${cum.length} khối gần nhau nhất (${f2(fs.x, 1)} × ${f2(fs.z, 1)} m), vì ${ds.length - cum.length} khối còn lại nằm xa hơn trên ${f2(bk, 0)} m. Bấm Vừa để xem cả bản vẽ.`;
      } else {
        const [p, t] = goc("iso"); cam.position.copy(p); dk.target.copy(t);
      }
      dk.update();
    }
    datLai(); addEventListener("resize", datLai);
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(datLai) : null; ro && ro.observe(kg);
    capNhatPn(); capLuu();
    $("#x3-tt").textContent = `Bản 3D v9 · Cao tầng ${H} m · ${dsMB ? dsMB.length + " mặt bằng ghép" : (d.cau_kien || []).filter(c => c.loai_bo).length + " cấu kiện bị loại (xám mờ)"}` + (coOng ? ` · ${holes.length} lỗ khoét · ${vaCham.length + vaMep.length} va chạm` : "") + (tong.coc ? ` · ${tong.coc.n} cọc` : "") + ` · ${loiLK.length} chỗ liên kết cần kiểm tra`;
    $("#x3-ft").textContent = (khungNote ? khungNote + " · " : "") + "Chuột trái: xoay · Phải: dịch · Lăn: zoom · Bấm: chọn · Nhấp đúp: bay tới · Bấm ❔ Hướng dẫn hoặc phím ? để xem chi tiết. Khối dựng từ hình 2D và chiều cao đã tính, chưa phải mô hình BIM.";
    let chay = true;
    const bnd = new THREE.Vector3();
    (function vong() {
      if (!chay) return;
      if (anim) { const k = Math.min(1, (performance.now() - anim.s) / anim.ms), e = k < .5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2; cam.position.lerpVectors(anim.p0, anim.p1, e); dk.target.lerpVectors(anim.t0, anim.t1, e); if (k >= 1) anim = null; }
      dk.update(); r.render(scene, cam);
      if (soDo.length) { const b = r.domElement.getBoundingClientRect(), kb = kg.getBoundingClientRect(); soDo.forEach(m => { bnd.copy(m.a).add(m.b).multiplyScalar(.5).project(cam); const vis = bnd.z < 1; m.el.style.display = vis ? "" : "none"; m.el.style.left = ((bnd.x + 1) / 2 * b.width + b.left - kb.left) + "px"; m.el.style.top = ((1 - bnd.y) / 2 * b.height + b.top - kb.top) + "px"; }); }
      if (nhan.length) { const b = r.domElement.getBoundingClientRect(), kb = kg.getBoundingClientRect(); nhan.forEach(n => { bnd.copy(n.p).project(cam); const v = bnd.z < 1 && n.o.hien; n.el.style.display = v ? "" : "none"; if (v) { n.el.style.left = ((bnd.x + 1) / 2 * b.width + b.left - kb.left) + "px"; n.el.style.top = ((1 - bnd.y) / 2 * b.height + b.top - kb.top) + "px"; } }); }
      if (nhanPhu.length) { const b = r.domElement.getBoundingClientRect(), kb = kg.getBoundingClientRect(); nhanPhu.forEach(n => { bnd.copy(n.p).project(cam); const v = bnd.z < 1 && n.o.hien; n.el.style.display = v ? "" : "none"; if (v) { n.el.style.left = ((bnd.x + 1) / 2 * b.width + b.left - kb.left) + "px"; n.el.style.top = ((1 - bnd.y) / 2 * b.height + b.top - kb.top) + "px"; } }); }
      requestAnimationFrame(vong);
    })();
    let daXem = false; try { daXem = !!localStorage.getItem("azb-3d-gd"); } catch (e) {}
    if (!daXem) moGD(true);

    function dong() {
      chay = false; removeEventListener("resize", datLai); removeEventListener("keydown", phim); ro && ro.disconnect();
      xoaMo(); xoaDo(); nhan.forEach(n => n.el.remove()); nhanPhu.forEach(n => n.el.remove());
      if (nhomTruc) { scene.remove(nhomTruc); nhomTruc.traverse(o => { o.geometry && o.geometry.dispose(); o.material && o.material.dispose(); }); } [nenDat, luoi].forEach(o => { if (o) { o.geometry.dispose(); o.material.dispose(); } });
      scene.background && scene.background.dispose && scene.background.dispose();
      dk.dispose(); r.dispose(); lop.remove(); dang = null;
    }
    dang = {dong};
  };
})();
