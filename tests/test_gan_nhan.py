"""Kiểm thử tự gán nhãn: nhận diện dầm, đặt tên, tỷ lệ chữ, trục, xuất DXF."""
import ezdxf
import pytest

from app.dxf_reader import doc_ban_ve
from app.gan_nhan import TEN_LAYER_NHAN, gan_nhan, ve_nhan_vao_dxf

# Mặt bằng 4 m x 4 m (đơn vị mm), 2 ô trống, dầm biên 200, dầm giữa 200, trục tại mép khung.
X0, Y0, X1, Y1 = 10000, 20000, 14000, 24000
VUNG = [9, 19, 15, 26]  # mét


def _hcn(msp, layer, x0, y0, x1, y1):
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": layer})


def _tao(tmp_path, co_nhan_cu=False, ty_le="1/50", tang_chu="MẶT BẰNG DẦM SÀN TẦNG 2"):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for l in ("KHUNG", "TRUC", "CHU"):
        doc.layers.add(l)
    msp = doc.modelspace()
    _hcn(msp, "KHUNG", X0, Y0, X1, Y1)  # khung dầm
    _hcn(msp, "KHUNG", X0 + 200, Y0 + 200, X1 - 200, Y0 + 1900)    # ô dưới
    _hcn(msp, "KHUNG", X0 + 200, Y0 + 2100, X1 - 200, Y1 - 200)   # ô trên: chừa dầm giữa 200 ở y = Y0+1900..2100
    for x in (X0, X1):
        msp.add_line((x, Y0 - 1000), (x, Y1 + 1000), dxfattribs={"layer": "TRUC"})
    for y in (Y0, Y1):
        msp.add_line((X0 - 1000, y), (X1 + 1000, y), dxfattribs={"layer": "TRUC"})
    msp.add_text(f"{tang_chu} TL:{ty_le}", dxfattribs={"layer": "CHU", "height": 150, "insert": (X0, Y0 - 2500)})
    msp.add_text("22a - NHÀ BẢO VỆ 2", dxfattribs={"layer": "CHU", "height": 300, "insert": (X0 - 6000, Y0 - 5000)})
    if co_nhan_cu:  # bảng ghi tiết diện nằm ngoài vùng
        msp.add_text("2.DX1-200X400", dxfattribs={"layer": "CHU", "height": 150, "insert": (X1 + 20000, Y0)})
        msp.add_text("2.DY1-200X500", dxfattribs={"layer": "CHU", "height": 150, "insert": (X1 + 20000, Y0 + 500)})
    f = tmp_path / "mb_dam.dxf"
    doc.saveas(f)
    return doc_ban_ve(f)


LOAI = {"KHUNG": "bo_qua"}  # để app tự dò


def test_ten_dam_truc_va_chieu_cao_chu_theo_ty_le(tmp_path):
    bv = _tao(tmp_path, co_nhan_cu=True)
    kq = gan_nhan(bv, LOAI, VUNG)
    assert kq["ty_le"] == 50 and kq["cao_chu"] == pytest.approx(0.15)   # 3 mm giấy x 50
    assert kq["tang"] == "2" and kq["tien_to"] == "22a"
    ten = sorted(n["t"] for n in kq["nhan"])
    # 2 dầm X biên (ở cạnh dưới và trên) + 1 dầm X giữa + 2 dầm Y biên; h lấy từ chữ trong bản vẽ cho DX1, DY1
    assert ten.count("2.DX1-200X400") == 2
    assert ten.count("2.DY1-200X500") == 2
    assert sum(1 for t in ten if t.startswith("2.DX2-200X")) == 1
    assert [t for t in ten if t.startswith("22a")] == ["22aX1", "22aX2", "22aY1", "22aY2"]


def test_khong_biet_chieu_cao_thi_ghi_hoi_va_canh_bao(tmp_path):
    kq = gan_nhan(_tao(tmp_path), LOAI, VUNG)
    assert any(n["t"] == "2.DX1-200X?" for n in kq["nhan"])
    assert any("chiều cao h" in c for c in kq["canh_bao"])
    dx1 = next(l for l in kq["loai_dam"] if l["ma"] == "DX1")
    assert dx1["h"] is None and dx1["b"] == 200 and dx1["so_luong"] == 2


def test_nguoi_dung_nhap_chieu_cao_thang_chu_trong_ban_ve(tmp_path):
    kq = gan_nhan(_tao(tmp_path, co_nhan_cu=True), LOAI, VUNG, {"cao_dam": {"DX1": 450}})
    ten = [n["t"] for n in kq["nhan"]]
    assert ten.count("2.DX1-200X450") == 2 and "2.DX1-200X400" not in ten


def test_ty_le_1_25_chu_nho_hon_mot_nua(tmp_path):
    kq = gan_nhan(_tao(tmp_path, ty_le="1/25"), LOAI, VUNG)
    assert kq["ty_le"] == 25 and kq["cao_chu"] == pytest.approx(0.075)
    assert all(n["cao"] == pytest.approx(0.075) for n in kq["nhan"] if n["loai"] == "dam")


def test_nhap_tay_ty_le_thang_chu_doc_duoc(tmp_path):
    kq = gan_nhan(_tao(tmp_path), LOAI, VUNG, {"ty_le": 100, "tang": "5", "tien_to": "A"})
    assert kq["cao_chu"] == pytest.approx(0.3) and kq["nguon_ty_le"] == "nhập tay"
    assert any(n["t"] == "AX1" for n in kq["nhan"]) and any(n["t"].startswith("5.DX") for n in kq["nhan"])


def test_nhan_xoay_theo_dam_va_khong_de_len_dam(tmp_path):
    kq = gan_nhan(_tao(tmp_path), LOAI, VUNG)
    for n in kq["nhan"]:
        if n["loai"] != "dam":
            continue
        assert n["goc"] == (0.0 if "DX" in n["t"] else 90.0)
    # chữ dầm X nằm giữa chiều dài dầm (x = 12 m), chữ dầm Y nằm giữa chiều cao khung (y = 22 m)
    for n in kq["nhan"]:
        if "DX" in n["t"]:
            assert n["x"] == pytest.approx(12.0, abs=0.7)
        if "DY" in n["t"]:
            assert n["y"] == pytest.approx(22.0, abs=0.7)


def test_vung_khong_co_dam_khong_loi(tmp_path):
    kq = gan_nhan(_tao(tmp_path), LOAI, [100, 100, 110, 110])
    assert kq["nhan"] == [] and any("Không tìm thấy dầm" in c for c in kq["canh_bao"])


def test_xuat_dxf_dung_layer_don_vi_va_cao_chu(tmp_path):
    bv = _tao(tmp_path, co_nhan_cu=True)
    kq = gan_nhan(bv, LOAI, VUNG)
    doc = ezdxf.readfile(tmp_path / "mb_dam.dxf")
    n = ve_nhan_vao_dxf(doc, bv.he_so, kq)
    out = tmp_path / "co_nhan.dxf"
    doc.saveas(out)
    msp = ezdxf.readfile(out).modelspace()
    chu = list(msp.query(f'TEXT[layer=="{TEN_LAYER_NHAN}"]'))
    assert n == len(chu) == len(kq["nhan"])
    assert all(e.dxf.height == pytest.approx(150) for e in chu if "." in e.dxf.text)  # mm trong bản vẽ
    # không có bong bóng sẵn nên app vẽ thêm vòng tròn cho 4 trục
    assert len(list(msp.query(f'CIRCLE[layer=="{TEN_LAYER_NHAN}"]'))) == 4


def test_api_gan_nhan_va_xuat_dxf(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import main
    bv = _tao(tmp_path)
    monkeypatch.setitem(main.PHIEN, "abc123abc123", {"ban_ve": bv, "kq": None})
    monkeypatch.setattr(main.luu_tru, "tim_file", lambda pid: tmp_path / "mb_dam.dxf")
    c = TestClient(main.app)
    r = c.post("/api/gan-nhan", json={"id": "abc123abc123", "khung": VUNG, "loai_layer": LOAI})
    assert r.status_code == 200 and r.json()["ty_le"] == 50 and len(r.json()["nhan"]) >= 9
    r = c.post("/api/gan-nhan", json={"id": "abc123abc123", "khung": [1, 2]})
    assert r.status_code == 400
    r = c.post("/api/xuat-dxf-nhan", json={"id": "abc123abc123", "khung": VUNG, "loai_layer": LOAI})
    assert r.status_code == 200 and b"AZB-NHAN" in r.content


def test_xuat_dxf_nhieu_mat_bang(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app import main
    bv = _tao(tmp_path)
    monkeypatch.setitem(main.PHIEN, "abc123abc124", {"ban_ve": bv, "kq": None})
    monkeypatch.setattr(main.luu_tru, "tim_file", lambda pid: tmp_path / "mb_dam.dxf")
    c = TestClient(main.app)
    ds = [{"khung": VUNG, "tang": "1", "ty_le": 50}, {"khung": VUNG, "tang": "2", "ty_le": 25}]
    r = c.post("/api/xuat-dxf-nhan", json={"id": "abc123abc124", "khung": VUNG, "ds": ds})
    assert r.status_code == 200
    f = tmp_path / "n.dxf"
    f.write_bytes(r.content)
    chu = {e.dxf.text: e.dxf.height for e in ezdxf.readfile(f).modelspace().query('TEXT[layer=="AZB-NHAN"]')}
    assert chu["1.DX1-200X?"] == pytest.approx(150) and chu["2.DX1-200X?"] == pytest.approx(75)


def test_nhan_mong_lay_kich_thuoc_tu_bang_thong_ke(tmp_path):
    """Móng chỉ có chữ "F1": nhãn mới ghi "F1 800x800x700", kích thước đọc từ bảng thống kê móng ngoài vùng."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for l in ("MONG", "CHU"):
        doc.layers.add(l)
    msp = doc.modelspace()
    _hcn(msp, "MONG", X0 - 400, Y0 - 400, X0 + 400, Y0 + 400)      # móng 800x800
    _hcn(msp, "MONG", X1 - 400, Y0 - 400, X1 + 400, Y0 + 400)
    for x in (X0, X1):
        msp.add_text("F1", dxfattribs={"layer": "CHU", "height": 150, "insert": (x - 100, Y0 + 700)})
    msp.add_text("MẶT BẰNG MÓNG TL:1/50", dxfattribs={"layer": "CHU", "height": 150, "insert": (X0, Y0 - 2500)})
    # bảng thống kê móng nằm ngoài vùng
    msp.add_text("F1", dxfattribs={"layer": "CHU", "height": 125, "insert": (X1 + 20000, Y0)})
    msp.add_text("800X800X700", dxfattribs={"layer": "CHU", "height": 125, "insert": (X1 + 21400, Y0)})
    f = tmp_path / "mong.dxf"
    doc.saveas(f)
    bv = doc_ban_ve(f)
    kq = gan_nhan(bv, {"MONG": "mong"}, VUNG, {"nhan_dam": False, "nhan_truc": False, "nhan_mong": True})
    mong = [n for n in kq["nhan"] if n["loai"] == "mong"]
    assert [n["t"] for n in mong] == ["F1 800x800x700", "F1 800x800x700"]


def test_nhan_mong_tu_do_layer_khi_chua_gan(tmp_path):
    """Chưa gán layer Móng: tự chọn layer có hình chữ nhật gần chữ tên móng, không trả 0 nhãn."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for l in ("HINH_LA", "CHU"):
        doc.layers.add(l)
    msp = doc.modelspace()
    for x in (X0, X1):
        _hcn(msp, "HINH_LA", x - 400, Y0 - 400, x + 400, Y0 + 400)
        msp.add_text("F1", dxfattribs={"layer": "CHU", "height": 150, "insert": (x - 100, Y0 + 700)})
    f = tmp_path / "mong2.dxf"
    doc.saveas(f)
    kq = gan_nhan(doc_ban_ve(f), {}, VUNG, {"nhan_dam": False, "nhan_truc": False, "nhan_mong": True, "nhan_coc": False, "nhan_san": False, "ty_le": 50})
    assert [n["t"] for n in kq["nhan"] if n["loai"] == "mong"] == ["F1 800x800x?", "F1 800x800x?"]
    assert any("HINH_LA" in w for w in kq["canh_bao"])


def _tao_coc(tmp_path, ten_cac, dk_mm, dk_bang=None):
    """Mặt bằng cọc: 4 hình tròn, chữ tên cạnh mỗi cọc (ten_cac), bảng thống kê ghi đường kính dk_bang."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for l in ("COC", "CHU"):
        doc.layers.add(l)
    msp = doc.modelspace()
    pos = [(10500, 20500), (13500, 20500), (10500, 23500), (13500, 23500)]
    for i, (x, y) in enumerate(pos, 1):
        if dk_mm:
            msp.add_circle((x, y), dk_mm / 2, dxfattribs={"layer": "COC"})
        if ten_cac:
            msp.add_text(f"P{i}", dxfattribs={"layer": "CHU", "height": 150, "insert": (x + 250, y)})
    if dk_bang:
        msp.add_text("ĐƯỜNG KÍNH CỌC", dxfattribs={"layer": "CHU", "height": 125, "insert": (17000, 19500)})
        msp.add_text(str(dk_bang), dxfattribs={"layer": "CHU", "height": 125, "insert": (19000, 19500)})
    f = tmp_path / "coc.dxf"
    doc.saveas(f)
    return doc_ban_ve(f)


COC_CHON = {"nhan_dam": False, "nhan_truc": False, "nhan_mong": False, "nhan_coc": True, "nhan_san": False}


def test_coc_dan_nhan_dung_duong_kinh_bang(tmp_path):
    kq = gan_nhan(_tao_coc(tmp_path, True, 300, dk_bang=300), LOAI, VUNG, COC_CHON)
    assert sorted(n["t"] for n in kq["nhan"]) == ["P1 D300", "P2 D300", "P3 D300", "P4 D300"]
    assert not any("không khớp" in c or "không thấy" in c or "không đọc được đường kính" in c for c in kq["canh_bao"])


def test_coc_khong_co_chu_ten_van_dan_theo_layer_coc(tmp_path):
    kq = gan_nhan(_tao_coc(tmp_path, False, 300, dk_bang=300), LOAI, VUNG, COC_CHON)
    assert [n["t"] for n in kq["nhan"]] == ["D300"] * 4 and any("không ghi tên cọc" in c for c in kq["canh_bao"])


def test_coc_duong_kinh_khong_khop_bang_van_dan_va_bao(tmp_path):
    kq = gan_nhan(_tao_coc(tmp_path, True, 400, dk_bang=300), LOAI, VUNG, COC_CHON)
    assert len(kq["nhan"]) == 4 and all(n["t"].startswith("P") and "D400" in n["t"] for n in kq["nhan"])
    assert any("không khớp đường kính bảng" in c for c in kq["canh_bao"])


def test_coc_khong_co_hinh_tron_thi_bao(tmp_path):
    kq = gan_nhan(_tao_coc(tmp_path, True, None), LOAI, VUNG, COC_CHON)
    assert kq["nhan"] == [] and any("không thấy hình tròn cọc" in c for c in kq["canh_bao"])


def test_chi_dan_dung_loai_da_chon(tmp_path):
    """Nhân sự chọn loại nào thì chỉ dán loại đó (không tự dán dầm, trục, móng... khi chưa được lệnh)."""
    tat = {"nhan_dam": False, "nhan_truc": False, "nhan_cot": False, "nhan_mong": False, "nhan_coc": False, "nhan_san": False}
    assert gan_nhan(_tao(tmp_path), LOAI, VUNG, tat)["nhan"] == []
    kq = gan_nhan(_tao(tmp_path), LOAI, VUNG, {**tat, "nhan_san": True})  # sàn vẫn cần dầm để suy ra ô sàn
    assert {n["loai"] for n in kq["nhan"]} <= {"san"}
    kq = gan_nhan(_tao(tmp_path), LOAI, VUNG, {**tat, "nhan_dam": True})
    assert kq["nhan"] and {n["loai"] for n in kq["nhan"]} == {"dam"}


def test_nhan_mong_sep_nhap_kich_thuoc_theo_loai(tmp_path):
    """Sếp sửa dài/rộng/sâu của loại M1 trong bảng: mọi nhãn M1 ghi số mới, bảng loai_mong trả đúng số."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for l in ("MONG", "CHU"):
        doc.layers.add(l)
    msp = doc.modelspace()
    _hcn(msp, "MONG", X0 - 400, Y0 - 400, X0 + 400, Y0 + 400)
    _hcn(msp, "MONG", X1 - 400, Y0 - 400, X1 + 400, Y0 + 400)
    for x in (X0, X1):
        msp.add_text("F1", dxfattribs={"layer": "CHU", "height": 150, "insert": (x - 100, Y0 + 700)})
    msp.add_text("MẶT BẰNG MÓNG TL:1/50", dxfattribs={"layer": "CHU", "height": 150, "insert": (X0, Y0 - 2500)})
    f = tmp_path / "mong2.dxf"
    doc.saveas(f)
    bv = doc_ban_ve(f)
    tc = {"nhan_dam": False, "nhan_truc": False, "nhan_mong": True, "nhan_coc": False, "nhan_san": False}
    kq = gan_nhan(bv, {"MONG": "mong"}, VUNG, tc)
    assert kq["loai_mong"] == [{"ten": "F1", "a": 800, "b": 800, "h": None, "so_luong": 2, "khac_nhau": False}]
    kq = gan_nhan(bv, {"MONG": "mong"}, VUNG, {**tc, "kt_mong": {"F1": {"a": 1000, "h": 900}}})
    assert [n["t"] for n in kq["nhan"] if n["loai"] == "mong"] == ["F1 1000x800x900"] * 2
    assert kq["loai_mong"][0]["h"] == 900 and kq["loai_mong"][0]["a"] == 1000


def test_coc_sep_nhap_duong_kinh_va_chieu_dai_theo_loai(tmp_path):
    bv = _tao_coc(tmp_path, True, 300, dk_bang=300)
    kq = gan_nhan(bv, LOAI, VUNG, COC_CHON)
    assert [l["ten"] for l in kq["loai_coc"]] == ["P1", "P2", "P3", "P4"] and kq["loai_coc"][0]["d"] == 300
    kq = gan_nhan(bv, LOAI, VUNG, {**COC_CHON, "kt_mong": {"P1": {"d": 350, "l": 22}}})
    chu = {n["t"] for n in kq["nhan"]}
    assert "P1 D350 L=22m" in chu and "P2 D300" in chu
    assert any(l["ten"] == "P1" and l["d"] == 350 and l["l"] == 22 for l in kq["loai_coc"])


def test_san_sep_nhap_chieu_day_theo_bang(tmp_path):
    tc = {"nhan_dam": False, "nhan_truc": False, "nhan_cot": False, "nhan_mong": False, "nhan_coc": False, "nhan_san": True}
    kq = gan_nhan(_tao(tmp_path), LOAI, VUNG, tc)
    if kq["loai_san"]:  # fixture có ô sàn
        kq = gan_nhan(_tao(tmp_path), LOAI, VUNG, {**tc, "kt_mong": {"S1": {"t": 120}}})
        assert kq["loai_san"][0]["t"] == 120 and all(n["t"] == "S1 t=120" for n in kq["nhan"])


def test_nhan_cot_tu_do_layer_theo_kich_thuoc_ghi_trong_ban_ve(tmp_path):
    """Chưa gán layer Cột: lấy layer có hình chữ nhật đúng kích thước cột ghi sẵn ("40x60"), bỏ layer khác."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for l in ("COT_LA", "KHAC", "CHU"):
        doc.layers.add(l)
    msp = doc.modelspace()
    for x in (X0, X1):
        _hcn(msp, "COT_LA", x - 200, Y0 - 300, x + 200, Y0 + 300)   # 400x600
        _hcn(msp, "KHAC", x - 150, Y0 + 2000, x + 150, Y0 + 2300)   # 300x300: không có trong bảng
    msp.add_text("40x60", dxfattribs={"layer": "CHU", "height": 150, "insert": (X0, Y0 + 900)})
    f = tmp_path / "cot.dxf"
    doc.saveas(f)
    kq = gan_nhan(doc_ban_ve(f), {}, VUNG, {"nhan_dam": False, "nhan_truc": False, "nhan_mong": False, "nhan_coc": False,
                                           "nhan_san": False, "nhan_cot": True, "ty_le": 50})
    assert [n["t"] for n in kq["nhan"] if n["loai"] == "cot"] == ["C1-600X400"] * 2
    assert any("COT_LA" in c and "tự dò" in c for c in kq["canh_bao"])


def test_coc_khong_ten_dan_theo_duong_kinh_o_layer_pile(tmp_path):
    """Chỉ vẽ hình tròn cọc ở layer PILE, không có chữ P1: vẫn dán "D300" và có bảng loại cọc khoá "P"."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for l in ("PILE", "KHAC", "CHU"):
        doc.layers.add(l)
    msp = doc.modelspace()
    for x in (X0, X1):
        msp.add_circle((x, Y0), 150, dxfattribs={"layer": "PILE"})
        msp.add_circle((x, Y0 + 2000), 500, dxfattribs={"layer": "KHAC"})  # tròn khác, không phải cọc
    msp.add_text("DUONG KINH COC", dxfattribs={"layer": "CHU", "height": 150, "insert": (X0, Y0 - 3000)})
    msp.add_text("300", dxfattribs={"layer": "CHU", "height": 150, "insert": (X0 + 3000, Y0 - 3000)})
    f = tmp_path / "pile.dxf"
    doc.saveas(f)
    bv = doc_ban_ve(f)
    kq = gan_nhan(bv, {}, VUNG, {**COC_CHON, "ty_le": 50})
    assert [n["t"] for n in kq["nhan"]] == ["D300", "D300"]
    assert kq["loai_coc"][0]["ten"] == "P" and kq["loai_coc"][0]["so_luong"] == 2
    kq = gan_nhan(bv, {}, VUNG, {**COC_CHON, "ty_le": 50, "kt_mong": {"P": {"d": 350, "l": 20}}})
    assert {n["t"] for n in kq["nhan"]} == {"D350 L=20m"}


def test_sua_tay_tung_nhan_doi_xoa_them(tmp_path):
    """Sếp sửa chữ, xóa, thêm nhãn: áp lại được sau mỗi lần dán (khoá theo vị trí)."""
    from app.gan_nhan import khoa_nhan
    bv = _tao_coc(tmp_path, True, 300, dk_bang=300)
    goc = gan_nhan(bv, LOAI, VUNG, COC_CHON)["nhan"]
    a, b = goc[0], goc[1]
    sua = {"doi": {khoa_nhan(a["x"], a["y"]): "COC DAC BIET"}, "xoa": [khoa_nhan(b["x"], b["y"])], "them": [{"t": "GHI CHU", "x": 1.5, "y": 2.5}]}
    kq = gan_nhan(bv, LOAI, VUNG, {**COC_CHON, "sua": sua})["nhan"]
    chu = [n["t"] for n in kq]
    assert len(kq) == len(goc) and "COC DAC BIET" in chu and b["t"] not in chu and "GHI CHU" in chu
    assert next(n for n in kq if n["t"] == "GHI CHU")["loai"] == "tay"


def _tao_net_dam(tmp_path, ve_dam=True):
    """Dầm vẽ bằng hai nét LINE hở đầu song song (200 mm), không có hình kín, không gán layer."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for l in ("NET_DAM", "KHUNG", "TRUC", "CHU"):
        doc.layers.add(l)
    msp = doc.modelspace()
    if ve_dam:
        for y in (21000, 21200):  # 2 dầm X chạy ngang
            msp.add_line((X0, y), (X1, y), dxfattribs={"layer": "NET_DAM"})
        for x in (10500, 10700):  # 2 dầm Y chạy đứng
            msp.add_line((x, Y0), (x, Y1), dxfattribs={"layer": "NET_DAM"})
    else:
        msp.add_line((X0, 21000), (X1, 21000), dxfattribs={"layer": "NET_DAM"})  # một nét lẻ, không phải dầm
    msp.add_text("MẶT BẰNG DẦM TL:1/50", dxfattribs={"layer": "CHU", "height": 150, "insert": (X0, Y0 - 2500)})
    f = tmp_path / "net_dam.dxf"
    doc.saveas(f)
    return doc_ban_ve(f)


def test_nhan_dam_tu_cap_net_song_song_khi_chua_gan_layer(tmp_path):
    kq = gan_nhan(_tao_net_dam(tmp_path), LOAI, VUNG, {"nhan_truc": False, "nhan_san": False, "nhan_mong": False, "nhan_coc": False})
    huong = sorted((l["huong"], l["b"]) for l in kq["loai_dam"])
    assert ("X", 200) in huong and ("Y", 200) in huong
    assert sum(l["so_luong"] for l in kq["loai_dam"]) == 2  # mỗi cặp nét là một dầm
    assert any("cặp nét song song" in c for c in kq["canh_bao"])
    assert any(n["loai"] == "dam" for n in kq["nhan"])


def test_mot_net_le_khong_thanh_dam(tmp_path):
    kq = gan_nhan(_tao_net_dam(tmp_path, ve_dam=False), LOAI, VUNG, {"nhan_truc": False, "nhan_san": False, "nhan_mong": False, "nhan_coc": False})
    assert kq["loai_dam"] == [] and any("Không tìm thấy dầm" in c for c in kq["canh_bao"])

def test_khong_co_khung_o_thi_suy_dam_tu_hinh_manh(tmp_path):
    """Dầm vẽ thành các hình dài mảnh rời (không có khung bao ô trống): vẫn nhận dầm, cột vuông không bị nhận."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.layers.add("G-ANNO-TTLB")
    msp = doc.modelspace()
    for y in (Y0, Y1):  # 2 dầm X dài 4 m, rộng 200
        _hcn(msp, "G-ANNO-TTLB", X0, y - 100, X1, y + 100)
    for x in (X0, X1):  # 2 dầm Y dài 4 m, rộng 200
        _hcn(msp, "G-ANNO-TTLB", x - 100, Y0, x + 100, Y1)
    _hcn(msp, "G-ANNO-TTLB", X0 + 1000, Y0 + 1000, X0 + 1400, Y0 + 1400)  # cột 400x400: không phải dầm
    f = tmp_path / "manh.dxf"
    doc.saveas(f)
    kq = gan_nhan(doc_ban_ve(f), {}, VUNG)
    dam = [n for n in kq["nhan"] if n["loai"] == "dam"]
    assert len(dam) == 4
    assert any("tự suy dầm từ 4 hình" in c for c in kq["canh_bao"])


def test_layer_dam_da_gan_nhung_trong_vung_thi_van_tu_do(tmp_path):
    """Layer 'S-Beam' gán Dầm theo tên nhưng không có hình trong vùng: trước đây bỏ qua tự dò → 0 nhãn."""
    ban_ve = _tao(tmp_path)
    kq = gan_nhan(ban_ve, {"KHUNG": "bo_qua", "S-Beam": "dam"}, VUNG)
    assert any(n["loai"] == "dam" for n in kq["nhan"])
    assert any("'S-Beam'" in c and "không có hình" in c for c in kq["canh_bao"])


def test_san_la_luoi_o_chu_nhat_khong_co_dam(tmp_path):
    """Mặt bằng nền vẽ thành lưới ô kín, không có dầm: mỗi ô nhận một nhãn sàn."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.layers.add("LUOI")
    msp = doc.modelspace()
    for i in range(4):
        for j in range(3):
            _hcn(msp, "LUOI", 10000 + i * 3000, 20000 + j * 3000, 12900 + i * 3000, 22900 + j * 3000)
    f = tmp_path / "luoi.dxf"
    doc.saveas(f)
    kq = gan_nhan(doc_ban_ve(f), {}, [9, 19, 25, 31], {"nhan_dam": False, "nhan_truc": False, "nhan_mong": False, "nhan_coc": False})
    assert len([n for n in kq["nhan"] if n["loai"] == "san"]) == 12
    assert any("ô chữ nhật kín" in c for c in kq["canh_bao"])
