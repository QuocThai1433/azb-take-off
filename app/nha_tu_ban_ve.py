"""Đọc thông số ngôi nhà (chiều cao, cửa) từ các hình KHÁC trong cùng file: mặt đứng, mặt cắt.

Một file kiến trúc thường có mặt bằng + mặt đứng + mặt cắt xếp cạnh nhau. Mặt bằng chỉ cho đường bao tường; chiều cao
mái ghi ở mặt cắt (+6.050, +6.800) và cửa vẽ đủ ở mặt đứng (cùng trục x với mặt bằng).
"""
import re

RE_CAO_DO = re.compile(r"^(?:EL\.?\s*|CAO\s*DO\s*)?\+\s*(\d+(?:[.,]\d+)?)\s*(?:m|M)?$")   # +6.800, +6,8, EL +6.800, +6.800m
CAO_TOI_THIEU = 3.0        # m - cao độ nhỏ hơn mức này (vd +2.000 là đỉnh cửa / tường thấp) không phải mái
CHENH_MAI_TOI_DA = 1.5     # m - hai cao độ mái cách nhau quá mức này thì không phải hai mép một mái dốc


def doc_cao_do(ban_ve):
    """Hai cao độ cao nhất ghi dạng '+6.800' trên bản vẽ -> (mép thấp, mép cao) của mái dốc; không có thì None."""
    muc = set()
    for ld in ban_ve.layers.values():
        for c in ld.chu:
            m = RE_CAO_DO.match(c.noi_dung.strip())
            if m:
                v = float(m.group(1).replace(",", "."))
                if v >= CAO_TOI_THIEU:
                    muc.add(round(v, 3))
    ds = sorted(muc, reverse=True)
    if len(ds) >= 2 and ds[0] - ds[1] <= CHENH_MAI_TOI_DA:
        return ds[1], ds[0]
    if len(ds) == 1:
        return ds[0], ds[0]
    return None


def _hop(ld):
    out = [h.geom.bounds for h in ld.hinh_kin]
    out += [n.bounds for n in ld.net_ho]
    return out


def cua_tu_mat_dung(ban_ve, loai_layer, x0, x1, y_tru):
    """Cửa vẽ ở hình khác (mặt đứng) nằm cùng dải x với mặt bằng, ngoài dải y của tường (y_tru = (ymin, ymax)).
    Các mảnh khung + cánh cùng chiều cao và liền nhau (hở <= 3 cm) gộp thành một cửa.
    Trả [(xa, xb, cao)] sắp theo x."""
    nhom = {}
    for ten, ld in ban_ve.layers.items():
        if loai_layer.get(ten) != "cua":
            continue
        for ax, ay, bx, by in _hop(ld):
            if bx < x0 - 0.3 or ax > x1 + 0.3:
                continue
            if by > y_tru[0] - 0.5 and ay < y_tru[1] + 0.5:
                continue                                        # nằm trong dải mặt bằng: do nhánh khoét trực tiếp xử lý
            if by - ay < 1.5 or by - ay > 3.5:
                continue
            nhom.setdefault((round(ay, 2), round(by, 2)), []).append((ax, bx))
    if not nhom:
        return []
    tot = max(nhom.values(), key=len)
    (ay, by), _ = next((k, v) for k, v in nhom.items() if v is tot)
    tot.sort()
    don, cur = [], list(tot[0])
    for a, b in tot[1:]:
        if a - cur[1] <= 0.03:
            cur[1] = max(cur[1], b)
        else:
            don.append(tuple(cur))
            cur = [a, b]
    don.append(tuple(cur))
    return [(a, b, round(by - ay, 3)) for a, b in don if 0.6 <= b - a <= 4.5]
