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


def test_chi_dan_dung_loai_da_chon(tmp_path):
    """Nhân sự chọn loại nào thì chỉ dán loại đó (không tự dán dầm, trục, móng... khi chưa được lệnh)."""
    tat = {"nhan_dam": False, "nhan_truc": False, "nhan_cot": False, "nhan_mong": False, "nhan_coc": False, "nhan_san": False}
    assert gan_nhan(_tao(tmp_path), LOAI, VUNG, tat)["nhan"] == []
    kq = gan_nhan(_tao(tmp_path), LOAI, VUNG, {**tat, "nhan_san": True})  # sàn vẫn cần dầm để suy ra ô sàn
    assert {n["loai"] for n in kq["nhan"]} <= {"san"}
    kq = gan_nhan(_tao(tmp_path), LOAI, VUNG, {**tat, "nhan_dam": True})
    assert kq["nhan"] and {n["loai"] for n in kq["nhan"]} == {"dam"}
