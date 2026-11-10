"""Hệ quy chiếu dự án: dò lưới trục + tên, điểm gốc / điểm hướng, bảng tầng, API."""
import ezdxf
import pytest
from fastapi.testclient import TestClient

from app import he_quy_chieu as hq
from app.dxf_reader import doc_ban_ve
from app.main import app

XS = [0, 6000, 12000]           # trục số 1, 2, 3 (mm)
YS = [0, 4500]                  # trục chữ A, B


def _tao(tmp_path, co_ten=True):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for l in ("TRUC", "CHU", "KT"):
        doc.layers.add(l)
    msp = doc.modelspace()
    for x in XS:
        msp.add_line((x + 20000, -1500), (x + 20000, 6000), dxfattribs={"layer": "TRUC"})
    for y in YS:
        msp.add_line((18500, y), (33500, y), dxfattribs={"layer": "TRUC"})
    msp.add_line((20000, 0), (20000, 300), dxfattribs={"layer": "TRUC"})   # vạch ngắn: không phải trục
    if co_ten:
        for i, x in enumerate(XS):   # bong bóng + chữ ở đầu dưới trục số
            msp.add_circle((x + 20000, -1800), 300, dxfattribs={"layer": "KT"})
            msp.add_text(str(i + 1), dxfattribs={"layer": "CHU", "height": 250, "insert": (x + 20000 - 70, -1900)})
        for ten, y in zip("AB", YS):
            msp.add_circle((18200, y), 300, dxfattribs={"layer": "KT"})
            msp.add_text(ten, dxfattribs={"layer": "CHU", "height": 250, "insert": (18200 - 80, y - 100)})
    msp.add_text("+3.600", dxfattribs={"layer": "CHU", "height": 150, "insert": (21000, 2000)})
    msp.add_text("±0.000", dxfattribs={"layer": "CHU", "height": 150, "insert": (21000, 2500)})
    msp.add_text("-1.500", dxfattribs={"layer": "CHU", "height": 150, "insert": (21000, 3000)})
    f = tmp_path / "truc.dxf"
    doc.saveas(f)
    return doc_ban_ve(f)


def test_do_luoi_truc_va_ten(tmp_path):
    kq = hq.do_luoi_truc(_tao(tmp_path))
    assert [t["v"] for t in kq["doc"]] == pytest.approx([20, 26, 32])
    assert [t["ten"] for t in kq["doc"]] == ["1", "2", "3"]
    assert [t["ten"] for t in kq["ngang"]] == ["A", "B"]
    assert all(t["nguon_ten"] == "bong bóng" for t in kq["doc"] + kq["ngang"])
    assert not any("tên" in c for c in kq["canh_bao"])


def test_khong_co_ten_thi_dat_tam_va_canh_bao(tmp_path):
    kq = hq.do_luoi_truc(_tao(tmp_path, co_ten=False))
    assert [t["ten"] for t in kq["doc"]] == ["1", "2", "3"]
    assert [t["ten"] for t in kq["ngang"]] == ["A", "B"]
    assert all(t["nguon_ten"] == "tự đặt" for t in kq["doc"])
    assert any("tên tạm" in c for c in kq["canh_bao"])


def test_khong_co_layer_truc(tmp_path):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_line((0, 0), (5000, 0))
    f = tmp_path / "x.dxf"
    doc.saveas(f)
    kq = hq.do_luoi_truc(doc_ban_ve(f))
    assert kq["doc"] == [] and kq["ngang"] == [] and kq["canh_bao"]


def test_cao_do_goi_y(tmp_path):
    ds = {x["gia_tri"] for x in hq.cao_do_goi_y(_tao(tmp_path))}
    assert {3.6, 0.0, -1.5} <= ds


def test_doc_so_kieu_nguoi_nhap():
    assert hq.doc_so("+3.600") == 3.6
    assert hq.doc_so("3,6") == 3.6
    assert hq.doc_so("-1.500") == -1.5
    assert hq.doc_so("±0.000") == 0.0
    assert hq.doc_so("EL +6,8m") == 6.8
    assert hq.doc_so("") is None and hq.doc_so("abc") is None


def _hqc(**kw):
    luoi = {"doc": [{"ten": "1", "v": 20}, {"ten": "2", "v": 26}, {"ten": "3", "v": 32}],
            "ngang": [{"ten": "A", "v": 0}, {"ten": "B", "v": 4.5}]}
    h = {"luoi": luoi, "goc": {"doc": "1", "ngang": "A"},
         "tang": [{"ma": "MONG", "loai": "mong", "cao_do_kc": "-1.5"},
                  {"ma": "T1", "cao_do_kc": "±0.000", "cao_do_ht": "+0.05", "day_san": 120, "cao_dam": 400},
                  {"ma": "T2", "cao_do_kc": "+3.6"}, {"ma": "MAI", "loai": "mai", "cao_do_kc": "+7.2"}]}
    h.update(kw)
    return h


def test_kiem_tra_day_du_tinh_chieu_cao_tang_va_cach_goc():
    kq = hq.kiem_tra(_hqc())
    assert kq["du"] and kq["canh_bao"] == []
    assert kq["goc"]["ten"] == "A-1" and (kq["goc"]["x"], kq["goc"]["y"]) == (20, 0)
    assert [t["cach_goc"] for t in kq["luoi"]["doc"]] == [0, 6, 12]
    assert {t["ma"]: t["chieu_cao"] for t in kq["tang"]} == {"MONG": 1.5, "T1": 3.6, "T2": 3.6, "MAI": None}


def test_thieu_goc_va_tang_thi_chua_du():
    kq = hq.kiem_tra(_hqc(goc=None, tang=[]))
    assert not kq["du"]
    assert any("điểm gốc" in c for c in kq["canh_bao"]) and any("bảng tầng" in c for c in kq["canh_bao"])


def test_goc_tro_vao_truc_da_xoa():
    kq = hq.kiem_tra(_hqc(goc={"doc": "9", "ngang": "A"}))
    assert not kq["du"] and any("không còn nằm trên lưới" in c for c in kq["canh_bao"])


def test_diem_huong_tinh_goc_quay_va_doi_toa_do():
    kq = hq.kiem_tra(_hqc(diem2={"doc": "1", "ngang": "B"}))   # điểm hướng ở trên: trục X công trình quay 90 độ
    assert kq["goc"]["goc_quay"] == pytest.approx(90)
    x, y = hq.sang_toa_do_cong_trinh(kq, 20, 4.5)
    assert (x, y) == pytest.approx((4.5, 0))


def test_canh_bao_bang_tang_bat_thuong():
    cb = hq.chuan_hoa_bang_tang([
        {"ma": "T1", "cao_do_kc": "0"}, {"ma": "T1", "cao_do_kc": "1"},
        {"ma": "T3", "cao_do_kc": "abc"}, {"ma": "T4", "cao_do_ht": "-0.5", "cao_do_kc": "10"},
        {"ma": "MONG", "loai": "mong", "cao_do_kc": "20"}])["canh_bao"]
    t = " | ".join(cb)
    assert "Trùng mã tầng" in t and "không đọc được" in t and "chiều cao tầng" in t and "móng" in t


def test_lop_phu_trung_ten_truc_va_truc_sat_nhau():
    cb = hq.kiem_tra_luoi({"doc": [{"ten": "1", "v": 0}, {"ten": "1", "v": 0.1}], "ngang": [{"ten": "A", "v": 0}]})
    t = " | ".join(cb)
    assert "trùng tên" in t and "cách nhau" in t


def test_api_kiem_tra_va_do_truc(tmp_path):
    c = TestClient(app)
    r = c.post("/api/he-quy-chieu/kiem-tra", json=_hqc())
    assert r.status_code == 200 and r.json()["du"]
    assert c.post("/api/he-quy-chieu/kiem-tra", json=[1]).status_code == 400
    assert c.post("/api/he-quy-chieu/kiem-tra", json={"luoi": {"doc": [{"ten": "1"}]}}).status_code == 400


def test_trang_thai_du_an_giu_he_quy_chieu():
    c = TestClient(app)
    tt = {"files": [], "he_quy_chieu": _hqc()}
    assert c.post("/api/du-an/trang-thai", json=tt).status_code == 200
    assert c.get("/api/du-an/trang-thai").json()["trang_thai"]["he_quy_chieu"]["goc"] == {"doc": "1", "ngang": "A"}
