"""Tường / cửa / mái chỉ để dựng 3D: không sinh dòng khối lượng, cửa khoét tường, có lanh tô và mái."""
from shapely.geometry import LineString, box

from app.dxf_reader import BanVe, HinhKin, LayerData
from app.takeoff import boc_khoi_luong


def _ban_ve():
    t = LayerData("TUONG", hinh_kin=[HinhKin(box(0, 0, 6, 0.2), "1", "LWPOLYLINE")], net_ho=[LineString([(0, 4), (6, 4)])])
    c = LayerData("CUA", hinh_kin=[HinhKin(box(2, -0.3, 3, 0.5), "2", "LWPOLYLINE")])
    return BanVe("t.dxf", 1.0, "m", {"TUONG": t, "CUA": c}, [])


def test_tuong_khoet_cua_lanh_to_va_mai():
    kq = boc_khoi_luong(_ban_ve(), {"TUONG": "tuong", "CUA": "cua"}, {})
    ds = kq["cau_kien"]
    loai = [c["loai"] for c in ds]
    assert loai.count("mai") >= 1 and loai.count("cua") == 1
    lanh_to = [c for c in ds if c["loai"] == "tuong" and c["thong_so"].get("z0")]
    assert len(lanh_to) == 1 and abs(lanh_to[0]["thong_so"]["z0"] - 2.1) < 1e-9
    assert kq["dong"] == [] and kq["tong_hop"] == []           # không bóc khối lượng
    # tường chính bị khoét đúng bề rộng ô cửa (6 - 1,04 = 4,96 m dài, dày 0,2)
    chinh = [c for c in ds if c["loai"] == "tuong" and not c["thong_so"].get("z0") and c["nguon"] == "LWPOLYLINE"]
    dt = sum(abs(__import__("shapely").geometry.Polygon(p[0]).area) for c in chinh for p in c["hinh"])
    assert abs(dt - (6 - 1.04) * 0.2) < 1e-3


def test_tuong_net_don_duoc_bu_thanh_dai():
    kq = boc_khoi_luong(_ban_ve(), {"TUONG": "tuong", "CUA": "bo_qua"}, {})
    assert any(c["nguon"] == "NET_TUONG" for c in kq["cau_kien"])
