"""Gợi ý layer tường theo hình học: cặp nét song song cách 8 đến 45 cm."""
from shapely.geometry import LineString

from app.dxf_reader import BanVe, LayerData
from app.goi_y_hinh_hoc import do_layer_tuong


def _bv(layers):
    return BanVe("t.dxf", 1.0, "m", layers, [])


def test_layer_co_nhieu_cap_song_song_la_tuong():
    nets = []
    for x in (0, 5, 10):                      # 3 tường dọc, mỗi tường hai nét cách 0,3 m
        nets += [LineString([(x, 0), (x, 8)]), LineString([(x + 0.3, 0), (x + 0.3, 8)])]
    for y in (0, 8):
        nets += [LineString([(0, y), (10.3, y)]), LineString([(0, y + 0.3), (10.3, y + 0.3)])]
    tuong = LayerData("LINE-L", net_ho=nets)
    luoi = LayerData("GRID", net_ho=[LineString([(x, 0), (x, 8)]) for x in range(0, 12, 3)])   # nét đơn cách xa
    kq = do_layer_tuong(_bv({"LINE-L": tuong, "GRID": luoi}))
    assert list(kq) == ["LINE-L"]


def test_layer_it_net_khong_duoc_goi_y():
    l = LayerData("X", net_ho=[LineString([(0, 0), (3, 0)]), LineString([(0, 0.3), (3, 0.3)])])
    assert do_layer_tuong(_bv({"X": l})) == {}
