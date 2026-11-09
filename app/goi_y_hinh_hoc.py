"""Gợi ý loại layer theo HÌNH HỌC khi tên layer không cho biết gì.

Tường kiến trúc thường vẽ bằng từng cặp nét song song cách nhau 8 đến 45 cm (hai mặt tường). Layer nào có nhiều
cặp như vậy nhất (và tên layer không nói là trục, kích thước, chữ...) thì gợi ý là Tường.
"""
import math
from bisect import bisect_left

DAY_MIN, DAY_MAX = 0.08, 0.45     # m - khoảng cách hai mặt tường
DAI_NET_MIN = 1.0                 # m - nét ngắn hơn không tính
TONG_DAI_MIN = 30.0               # m - tổng chiều dài các cặp tối thiểu để coi là layer tường
TY_LE_VOI_MAX = 0.5               # layer chỉ được chọn khi tổng >= 50% layer nhiều nhất
DT_KHUNG_LON = 300.0              # m2 - hình kín lớn hơn là khung giấy / khung mặt đứng, bỏ


def _doan(ld):
    out = []
    for n in ld.net_ho:
        c = list(n.coords)
        out += zip(c, c[1:])
    for h in ld.hinh_kin:
        if h.geom.area > DT_KHUNG_LON:
            continue
        c = list(h.geom.exterior.coords)
        out += zip(c, c[1:])
    return [(a, b) for a, b in out if math.dist(a, b) >= DAI_NET_MIN]


def _dai_cap(ds):
    """ds: [(toa_do_vuong_goc, tu, den)]. Tổng chiều dài phần chồng nhau của các cặp song song gần nhau."""
    ds.sort()
    khoa = [d[0] for d in ds]
    tong = 0.0
    for i, (v, a0, a1) in enumerate(ds):
        j = bisect_left(khoa, v + DAY_MIN - 1e-9, i + 1)
        while j < len(ds) and ds[j][0] - v <= DAY_MAX + 1e-9:
            ov = min(a1, ds[j][2]) - max(a0, ds[j][1])
            if ov >= DAI_NET_MIN:
                tong += ov
            j += 1
    return tong


def do_layer_tuong(ban_ve, bo_qua=()):
    """Trả {tên layer: tổng chiều dài cặp nét song song (m)} của các layer đạt chuẩn là layer tường."""
    diem = {}
    for ten, ld in ban_ve.layers.items():
        if ten in bo_qua:
            continue
        S = _doan(ld)
        if len(S) < 4 or len(S) > 6000:
            continue
        ngang = [(a[1], min(a[0], b[0]), max(a[0], b[0])) for a, b in S if abs(a[1] - b[1]) < 1e-3]
        doc = [(a[0], min(a[1], b[1]), max(a[1], b[1])) for a, b in S if abs(a[0] - b[0]) < 1e-3]
        t = _dai_cap(ngang) + _dai_cap(doc)
        if t >= TONG_DAI_MIN:
            diem[ten] = t
    if not diem:
        return {}
    cao = max(diem.values())
    return {t: v for t, v in diem.items() if v >= TY_LE_VOI_MAX * cao}
