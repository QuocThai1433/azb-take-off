"""Đọc cao độ mái và cửa từ mặt đứng / mặt cắt của cùng file."""
from shapely.geometry import Point, box

from app.dxf_reader import BanVe, Chu, HinhKin, LayerData
from app.nha_tu_ban_ve import cua_tu_mat_dung, doc_cao_do
from app.takeoff import boc_khoi_luong


def _chu(t):
    return Chu(t, Point(0, 0), "h")


def test_doc_cao_do_mai_dok():
    ld = LayerData("0", chu=[_chu("+6.800"), _chu("+6.050"), _chu("+2.000"), _chu("± 0.000"), _chu("EL ±0.000")])
    assert doc_cao_do(BanVe("t", 1.0, "m", {"0": ld}, [])) == (6.05, 6.8)


def test_doc_cao_do_khong_co():
    ld = LayerData("0", chu=[_chu("+2.000"), _chu("D1")])
    assert doc_cao_do(BanVe("t", 1.0, "m", {"0": ld}, [])) is None


def _mat_dung():
    # hai cửa ở mặt đứng (y 10 đến 12), mỗi cửa gồm cột khung 5 cm + hai cánh liền nhau; hở 0,5 m giữa hai cửa
    hs = [box(0, 10, 0.05, 12), box(0.05, 10, 0.95, 12), box(0.95, 10, 1.85, 12), box(1.85, 10, 1.9, 12),
          box(2.4, 10, 2.45, 12), box(2.45, 10, 3.35, 12), box(3.35, 10, 4.25, 12), box(4.25, 10, 4.3, 12)]
    return LayerData("CUA", hinh_kin=[HinhKin(g, str(i), "LWPOLYLINE") for i, g in enumerate(hs)])


def test_cua_mat_dung_gom_manh_lien_nhau():
    bv = BanVe("t", 1.0, "m", {"CUA": _mat_dung()}, [])
    ds = cua_tu_mat_dung(bv, {"CUA": "cua"}, 0, 4.3, (0, 5))
    assert [(round(a, 2), round(b, 2), h) for a, b, h in ds] == [(0.0, 1.9, 2.0), (2.4, 4.3, 2.0)]


def test_tuong_khoet_cua_tu_mat_dung_va_mai_doc():
    tuong = LayerData("T", hinh_kin=[HinhKin(g, "w", "LWPOLYLINE") for g in
                                     (box(0, 0, 4.3, 0.2), box(0, 4.0, 4.3, 4.2), box(0, 0.2, 0.2, 4.0), box(4.1, 0.2, 4.3, 4.0))])
    chu = LayerData("0", chu=[_chu("+6.800"), _chu("+6.050")])
    bv = BanVe("t", 1.0, "m", {"T": tuong, "CUA": _mat_dung(), "0": chu}, [])
    kq = boc_khoi_luong(bv, {"T": "tuong", "CUA": "cua"}, {})
    ds = kq["cau_kien"]
    assert sum(1 for c in ds if c["loai"] == "cua") == 2
    assert any(c["loai"] == "tuong" and c["thong_so"].get("z0") == 2.0 for c in ds)          # lanh tô trên cửa
    assert all(c["thong_so"]["cao"] == 6.05 for c in ds if c["loai"] == "tuong" and "z0" not in c["thong_so"])
    mai = [c for c in ds if c["loai"] == "mai"][0]["thong_so"]
    assert mai["z_thap"] == 6.05 and mai["z_cao"] == 6.8 and mai["huong"] == [0, -1]
