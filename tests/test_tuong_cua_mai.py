"""Tường / cửa / mái chỉ để dựng 3D: không sinh dòng khối lượng, cửa khoét tường, có lanh tô và mái."""
from shapely.geometry import LineString, box

from app.dxf_reader import BanVe, HinhKin, LayerData
from app.takeoff import boc_khoi_luong


def _ban_ve():
    t = LayerData("TUONG", hinh_kin=[HinhKin(box(0, 0, 6, 0.2), "1", "LWPOLYLINE"), HinhKin(box(0, 3.8, 6, 4), "3", "LWPOLYLINE"),
                                       HinhKin(box(0, 0.2, 0.2, 3.8), "4", "LWPOLYLINE"), HinhKin(box(5.8, 0.2, 6, 3.8), "5", "LWPOLYLINE")])
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
    # bốn bức tường (dày 0,2), bức dưới bị khoét đúng bề rộng ô cửa (6 - 1,04 = 4,96 m)
    chinh = [c for c in ds if c["loai"] == "tuong" and not c["thong_so"].get("z0") and c["nguon"] == "LWPOLYLINE"]
    dt = sum(abs(__import__("shapely").geometry.Polygon(p[0]).area) for c in chinh for p in c["hinh"])
    assert abs(dt - ((6 - 1.04) * 0.2 + 6 * 0.2 + 2 * 3.6 * 0.2)) < 1e-3


def test_tuong_net_don_duoc_bu_thanh_dai():
    t = LayerData("T", net_ho=[LineString([(0, 4), (6, 4)])])
    kq = boc_khoi_luong(BanVe("t.dxf", 1.0, "m", {"T": t}, []), {"T": "tuong"}, {})
    assert any(c["nguon"] == "NET_TUONG" for c in kq["cau_kien"])


def test_hai_net_song_song_thanh_mot_buc_tuong_day():
    t = LayerData("T", net_ho=[LineString([(0, 0), (4, 0)]), LineString([(0, 0.35), (4, 0.35)])])
    kq = boc_khoi_luong(BanVe("t.dxf", 1.0, "m", {"T": t}, []), {"T": "tuong"}, {})
    from shapely.geometry import Polygon
    ds = [c for c in kq["cau_kien"] if c["loai"] == "tuong"]
    assert len(ds) == 1
    p = Polygon(ds[0]["hinh"][0][0])
    assert abs(p.area - 4 * 0.35) < 0.05
