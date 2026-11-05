"""Tự tách nhiều mặt bằng trong một file: khung giấy, cụm nét vẽ, tiêu đề, tầng, tỷ lệ, vai trò, cảnh báo chồng lấn."""
import ezdxf
from fastapi.testclient import TestClient
from shapely.geometry import box

from app.dxf_reader import doc_ban_ve
from app.tach_mat_bang import do_mat_bang


def _doc():
    return ezdxf.new(units=6)   # mét


def _mat_bang(msp, x0, y0, tieu_de, n=8, khung=True):
    """Một 'tờ vẽ': khung giấy lớn (tùy chọn), lưới cột, nhãn cột và tiêu đề ở dưới."""
    if khung:
        msp.add_lwpolyline([(x0, y0), (x0 + 60, y0), (x0 + 60, y0 + 40), (x0, y0 + 40)], close=True, dxfattribs={"layer": "KHUNG"})
    for i in range(n):
        x = x0 + 5 + i * 6
        msp.add_lwpolyline([(x, y0 + 10), (x + .3, y0 + 10), (x + .3, y0 + 10.3), (x, y0 + 10.3)], close=True, dxfattribs={"layer": "S-COT"})
        msp.add_text(f"C{i + 1} 300x300", dxfattribs={"layer": "S-TEXT", "insert": (x, y0 + 11), "height": 0.2})
    msp.add_text(tieu_de, dxfattribs={"layer": "S-TEXT", "insert": (x0 + 5, y0 + 4), "height": 0.8})


def _doc_ve(tmp_path, doc):
    f = tmp_path / "t.dxf"
    doc.saveas(f)
    return doc_ban_ve(str(f))


def test_tach_theo_khung_giay_doc_tieu_de_tang_ty_le(tmp_path):
    d = _doc()
    m = d.modelspace()
    _mat_bang(m, 0, 0, "MẶT BẰNG DẦM SÀN TẦNG 2  TL:1/100")
    _mat_bang(m, 100, 0, "MẶT BẰNG MÓNG  TL:1/50")
    m.add_lwpolyline([(200, 0), (260, 0), (260, 40), (200, 40)], close=True, dxfattribs={"layer": "KHUNG"})
    m.add_text("CHI TIẾT CỘT C1", dxfattribs={"layer": "S-TEXT", "insert": (205, 5), "height": 0.8})
    for i in range(10):
        m.add_text(f"thép {i}", dxfattribs={"layer": "S-TEXT", "insert": (205, 10 + i), "height": 0.2})
    r = do_mat_bang(_doc_ve(tmp_path, d))
    assert r["cach"] == "khung giấy" and len(r["ds"]) == 3
    a, b, c = r["ds"]            # thứ tự đọc: trái sang phải
    assert a["vai_tro"] == "mat_bang" and a["tang"] == "TẦNG 2" and a["ty_le"] == 100 and "DẦM SÀN" in a["ten"]
    assert b["vai_tro"] == "mat_bang" and b["ty_le"] == 50 and "MÓNG" in b["ten"]
    assert c["vai_tro"] == "chi_tiet"
    k = a["khung"]
    assert k[0] <= 0 and k[2] >= 60 and k[1] <= 0 and k[3] >= 40     # khung bao đủ tờ vẽ


def test_tach_theo_cum_net_khi_khong_co_khung(tmp_path):
    d = _doc()
    m = d.modelspace()
    _mat_bang(m, 0, 0, "MẶT BẰNG TẦNG 1", khung=False)
    _mat_bang(m, 300, 0, "MẶT BẰNG TẦNG 2", khung=False)     # cách xa 250 m
    r = do_mat_bang(_doc_ve(tmp_path, d))
    assert r["cach"] == "cụm nét vẽ" and len(r["ds"]) == 2
    assert [v["tang"] for v in r["ds"]] == ["TẦNG 1", "TẦNG 2"]
    assert all(v["so_hinh"] == 8 for v in r["ds"])


def test_khoang_cach_lon_gop_hai_tap_thanh_mot(tmp_path):
    d = _doc()
    m = d.modelspace()
    _mat_bang(m, 0, 0, "MẶT BẰNG TẦNG 1", khung=False)
    _mat_bang(m, 100, 0, "MẶT BẰNG TẦNG 2", khung=False)
    bv = _doc_ve(tmp_path, d)
    assert len(do_mat_bang(bv, 20)["ds"]) == 2
    assert len(do_mat_bang(bv, 500)["ds"]) == 1


def test_mot_mat_bang_thi_chi_co_mot_vung(tmp_path):
    d = _doc()
    _mat_bang(d.modelspace(), 0, 0, "MẶT BẰNG TẦNG 1", khung=False)
    r = do_mat_bang(_doc_ve(tmp_path, d))
    assert len(r["ds"]) == 1 and r["ds"][0]["vai_tro"] == "mat_bang"


def test_net_le_loi_khong_thanh_vung(tmp_path):
    d = _doc()
    m = d.modelspace()
    _mat_bang(m, 0, 0, "MẶT BẰNG TẦNG 1", khung=False)
    m.add_line((900, 900), (901, 900))
    assert len(do_mat_bang(_doc_ve(tmp_path, d))["ds"]) == 1


def test_khung_chong_lan_va_nhieu_tieu_de_bi_canh_bao(tmp_path):
    d = _doc()
    m = d.modelspace()
    _mat_bang(m, 0, 0, "MẶT BẰNG MÓNG")
    _mat_bang(m, 20, 5, "MẶT BẰNG ĐÀ KIỀNG")                # khung thứ hai đè lên khung đầu
    r = do_mat_bang(_doc_ve(tmp_path, d))
    assert len(r["ds"]) == 2
    a, b = r["ds"]
    ba, bb = box(*a["khung"]), box(*b["khung"])
    assert ba.intersection(bb).area < 1e-6                 # đã cắt, không còn đè nhau
    nd = " ".join(c for v in r["ds"] for c in v["canh_bao"])
    assert "Đã cắt bớt" in nd and all(v["tin_cay"] <= 0.6 for v in r["ds"])


def test_ban_ve_trong_khong_loi(tmp_path):
    assert do_mat_bang(_doc_ve(tmp_path, _doc()))["ds"] == []


def test_api_tach_mat_bang(tmp_path):
    from app.main import app
    d = _doc()
    _mat_bang(d.modelspace(), 0, 0, "MẶT BẰNG TẦNG 1", khung=False)
    f = tmp_path / "mb.dxf"
    d.saveas(f)
    c = TestClient(app)
    up = c.post("/api/tai-len", files={"file": ("mb.dxf", f.read_bytes())}, data={"don_vi": "auto"})
    assert up.status_code == 200, up.text
    r = c.post("/api/tach-mat-bang", json={"id": up.json()["id"]}).json()
    assert len(r["ds"]) == 1 and r["ds"][0]["ten"].startswith("MẶT BẰNG")
