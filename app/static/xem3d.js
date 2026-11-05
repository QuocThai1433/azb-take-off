// Xem 3D kết cấu: dựng khối (extrude) từ kết quả /api/tinh. Mặt bằng X,Y (m) -> three: x = X, z = -Y, cao = y.
(function () {
  const MAU3D = {cot: 0xe0584f, dam: 0xe0a93a, san: 0x6fa8dc, mong: 0x8d8d8d, vach: 0x9b6fd1};
  const TEN3D = {cot: "Cột", dam: "Dầm", san: "Sàn", mong: "Móng", vach: "Vách/lõi"};
  let dang = null;

  function khoiDoc(ck, H) {
    // trả về [đáy, đỉnh] theo mét, 0 = mặt sàn tầng
    const ts = ck.thong_so || {};
    if (ck.loai === "cot" || ck.loai === "vach") {
      const cao = ts.cao || H;
      return [0, cao];
    }
    if (ck.loai === "dam") {
      const h = ts.h || 0.5, ht = ts.h_tinh != null ? ts.h_tinh : h;
      return [H - h, H - h + ht];
    }
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

  function dung(THREE, scene, d, loc) {
    const H = parseFloat(d.thong_so.chieu_cao_tang) || 3.6;
    const nhom = new THREE.Group();
    const dem = {};
    d.cau_kien.forEach(ck => {
      const dz = khoiDoc(ck, H);
      if (!dz) return;
      const loai = ck.loai_bo ? "loai_bo" : ck.loai;
      const coLoi = ck.canh_bao.some(c => c.muc === "loi" || c.muc === "canh_bao");
      ck.hinh.forEach(poly => {
        let geo;
        try { geo = new THREE.ExtrudeGeometry(hinhShape(THREE, poly), {depth: Math.max(dz[1] - dz[0], 0.01), bevelEnabled: false}); }
        catch (e) { return; }
        geo.rotateX(-Math.PI / 2);          // (x, y, z-extrude) -> (x, z-up, -y)
        geo.translate(0, dz[0], 0);
        const mau = ck.loai_bo ? 0x555555 : MAU3D[ck.loai];
        const mat = new THREE.MeshLambertMaterial({
          color: coLoi && loc.canhBao ? 0xff2020 : mau,
          transparent: ck.loai === "san" || ck.loai_bo, opacity: ck.loai === "san" ? 0.45 : (ck.loai_bo ? 0.25 : 1)});
        const mesh = new THREE.Mesh(geo, mat);
        mesh.userData = {ten: ck.ten, loai: ck.loai, loai_bo: ck.loai_bo, dz};
        mesh.visible = !!loc[ck.loai];
        nhom.add(mesh);
        const vien = new THREE.LineSegments(new THREE.EdgesGeometry(geo, 30), new THREE.LineBasicMaterial({color: 0x000000, transparent: true, opacity: 0.35}));
        vien.visible = mesh.visible;
        mesh.userData.vien = vien;
        nhom.add(vien);
      });
      dem[ck.loai] = (dem[ck.loai] || 0) + 1;
    });
    return {nhom, dem, H};
  }

  window.xem3D = function (d) {
    if (typeof THREE === "undefined" || !THREE.OrbitControls) {
      alert("Không tải được thư viện three.js (cần mạng lần đầu). Kiểm tra kết nối rồi thử lại.");
      return;
    }
    if (dang) dang.dong();
    const loc = {cot: true, dam: true, san: true, mong: true, vach: true, canhBao: false};
    const lop = document.createElement("div");
    lop.style.cssText = "position:fixed;inset:0;z-index:9999;background:#1b1d22;display:flex;flex-direction:column";
    lop.innerHTML = `<div style="display:flex;gap:14px;align-items:center;padding:8px 12px;background:#26292f;color:#eee;font:13px Roboto,sans-serif;flex-wrap:wrap">
      <b>Xem 3D kết cấu</b><span id="x3-loc"></span>
      <label><input type="checkbox" id="x3-cb"> Tô đỏ cấu kiện có cảnh báo</label>
      <span id="x3-tt" style="opacity:.8"></span>
      <span style="flex:1"></span><button id="x3-dong" style="padding:4px 14px">✕ Đóng</button></div>
      <div id="x3-cv" style="flex:1;position:relative;min-height:0"></div>
      <div style="padding:4px 12px;background:#26292f;color:#aaa;font:12px Roboto,sans-serif">Chuột trái: xoay · Chuột phải: dịch · Lăn: phóng/thu · Khối chỉ dựng từ hình 2D và chiều cao đã tính, chưa phải mô hình BIM.</div>`;
    document.body.appendChild(lop);
    const kg = lop.querySelector("#x3-cv");

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x1b1d22);
    scene.add(new THREE.AmbientLight(0xffffff, 0.65));
    const den = new THREE.DirectionalLight(0xffffff, 0.7); den.position.set(30, 60, 20); scene.add(den);
    const r = new THREE.WebGLRenderer({antialias: true});
    kg.appendChild(r.domElement);
    const cam = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
    const dk = new THREE.OrbitControls(cam, r.domElement);

    let kq = dung(THREE, scene, d, loc);
    scene.add(kq.nhom);
    const hop = new THREE.Box3().setFromObject(kq.nhom);
    const tam = hop.getCenter(new THREE.Vector3()), kich = hop.getSize(new THREE.Vector3());
    const bk = Math.max(kich.x, kich.z, kich.y, 1);
    const luoi = new THREE.GridHelper(Math.ceil(bk * 2), Math.ceil(bk * 2), 0x555a63, 0x33363c);
    luoi.position.set(tam.x, hop.min.y - 0.01, tam.z); scene.add(luoi);
    cam.position.set(tam.x + bk * 0.9, tam.y + bk * 0.9, tam.z + bk * 1.1);
    dk.target.copy(tam); dk.update();

    function datLai() {
      const w = kg.clientWidth, h = kg.clientHeight;
      r.setSize(w, h); cam.aspect = w / h; cam.updateProjectionMatrix();
    }
    datLai(); addEventListener("resize", datLai);
    let chay = true;
    (function vong() { if (!chay) return; dk.update(); r.render(scene, cam); requestAnimationFrame(vong); })();

    function hienLai() {
      kq.nhom.children.forEach(m => {
        if (m.userData.loai) { m.visible = !!loc[m.userData.loai]; m.userData.vien.visible = m.visible; }
      });
    }
    lop.querySelector("#x3-loc").innerHTML = Object.keys(TEN3D).map(k =>
      `<label style="margin-right:6px"><input type="checkbox" data-l="${k}" checked> <span style="color:#${MAU3D[k].toString(16).padStart(6, "0")}">■</span> ${TEN3D[k]} (${kq.dem[k] || 0})</label>`).join("");
    lop.querySelector("#x3-loc").onchange = e => { const k = e.target.dataset.l; if (k) { loc[k] = e.target.checked; hienLai(); } };
    lop.querySelector("#x3-cb").onchange = e => {
      loc.canhBao = e.target.checked;
      scene.remove(kq.nhom); kq.nhom.traverse(o => { if (o.geometry) o.geometry.dispose(); });
      kq = dung(THREE, scene, d, loc); scene.add(kq.nhom); hienLai();
    };
    lop.querySelector("#x3-tt").textContent = `Cao tầng ${kq.H} m · ${d.cau_kien.filter(c => c.loai_bo).length} cấu kiện bị loại (xám mờ)`;

    // rê chuột: hiện tên cấu kiện
    const tip = document.createElement("div");
    tip.style.cssText = "position:absolute;pointer-events:none;background:#000c;color:#fff;font:12px Roboto,sans-serif;padding:3px 8px;border-radius:4px;display:none";
    kg.appendChild(tip);
    const ray = new THREE.Raycaster(), p = new THREE.Vector2();
    r.domElement.addEventListener("mousemove", e => {
      const b = r.domElement.getBoundingClientRect();
      p.set(((e.clientX - b.left) / b.width) * 2 - 1, -((e.clientY - b.top) / b.height) * 2 + 1);
      ray.setFromCamera(p, cam);
      const hit = ray.intersectObjects(kq.nhom.children.filter(m => m.userData.loai && m.visible), false)[0];
      if (hit) {
        const u = hit.object.userData;
        tip.textContent = `${u.ten} · ${TEN3D[u.loai]} · đáy ${u.dz[0].toFixed(2)} → đỉnh ${u.dz[1].toFixed(2)} m` + (u.loai_bo ? " · (loại bỏ)" : "");
        tip.style.left = (e.clientX - b.left + 12) + "px"; tip.style.top = (e.clientY - b.top + 12) + "px"; tip.style.display = "block";
      } else tip.style.display = "none";
    });

    function dong() {
      chay = false; removeEventListener("resize", datLai); removeEventListener("keydown", phim);
      kq.nhom.traverse(o => { if (o.geometry) o.geometry.dispose(); });
      r.dispose(); lop.remove(); dang = null;
    }
    function phim(e) { if (e.key === "Escape") dong(); }
    addEventListener("keydown", phim);
    lop.querySelector("#x3-dong").onclick = dong;
    dang = {dong};
  };
})();
