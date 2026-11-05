"""Đường ống / khay cáp cơ điện (MEP) để dựng 3D và kiểm tra va chạm với kết cấu.

Chỉ đọc hình học tuyến (LINE, POLYLINE, LWPOLYLINE, ARC, MLINE) trên các layer đã gán loại ong_nuoc, ong_pccc, khay_cap.
Kích thước lấy theo thứ tự: ghi trong tên layer (D100, DN65, Phi60, 400x100) rồi mới đến mặc định trong config/mep.yaml.
Ống gió có công cụ riêng (app/ong_gio.py), không đọc ở đây.
"""
import re

from ezdxf import path as ezpath

from . import config
from .dxf_reader import _cac_entity, _path_thanh_diem

LOAI_DUONG = ("ong_nuoc", "ong_pccc", "khay_cap")
RE_TRON = re.compile(r"(?<![a-z0-9])(?:dn|d|phi|ø|fi)\s*[-_ ]?(\d{2,4})(?![0-9])", re.I)
RE_VUONG = re.compile(r"(?<![0-9])(\d{2,4})\s*[x×]\s*(\d{2,4})(?![0-9])", re.I)
TOI_DA_DIEM = 4000


def kich_thuoc_tu_ten(ten_layer, cau_hinh):
    """-> (rong_mm, cao_mm, tron, nguon). nguon: 'tên layer' hoặc 'mặc định'."""
    tron = cau_hinh["hinh"] == "tron"
    m = RE_VUONG.search(ten_layer)
    if m and not tron:
        return float(m.group(1)), float(m.group(2)), False, "tên layer"
    m = RE_TRON.search(ten_layer)
    if m and tron:
        d = float(m.group(1))
        return d, d, True, "tên layer"
    if tron:
        d = float(cau_hinh["d_mm"])
        return d, d, True, "mặc định"
    return float(cau_hinh["rong_mm"]), float(cau_hinh["cao_mm"]), False, "mặc định"


def doc_mep(ban_ve, loai_layer):
    """ban_ve.doc phải là ezdxf Drawing đã đọc. Trả {duong: [...], mac_dinh: {...}, canh_bao: [...]}."""
    if getattr(ban_ve, "doc", None) is None:
        raise ValueError("Phiên làm việc không còn dữ liệu gốc, Sếp tải bản vẽ lên lại.")
    cfg = config.mep()
    layers = {k: v for k, v in loai_layer.items() if v in LOAI_DUONG}
    if not layers:
        raise ValueError("Chưa có layer nào gán là Ống nước, Ống PCCC hoặc Khay cáp.")
    he_so = ban_ve.he_so
    duong, canh_bao, so_bo = [], [], 0
    for e in _cac_entity(ban_ve.doc.modelspace()):
        layer = e.dxf.get("layer", "0")
        loai = layers.get(layer)
        if not loai:
            continue
        t = e.dxftype()
        try:
            if t == "MLINE":
                pts = [(p.x * he_so, p.y * he_so) for p in e.get_locations()]
            elif t in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC"):
                if t == "POLYLINE" and not e.is_2d_polyline:
                    continue
                pts = _path_thanh_diem(ezpath.make_path(e), he_so)
            else:
                continue
        except Exception:
            so_bo += 1
            continue
        if len(pts) < 2:
            continue
        if len(pts) > TOI_DA_DIEM:
            pts = pts[:: len(pts) // TOI_DA_DIEM + 1] + [pts[-1]]
        rong, cao, tron, nguon = kich_thuoc_tu_ten(layer, cfg[loai])
        duong.append({"loai": loai, "layer": layer, "tron": tron, "rong": rong / 1000, "cao": cao / 1000,
                      "nguon_kt": nguon, "diem": [[round(x, 3), round(y, 3)] for x, y in pts]})
    if so_bo:
        canh_bao.append(f"Bỏ qua {so_bo} đường MEP không đọc được.")
    mac_cong = [l for l, k in {d["layer"]: d["nguon_kt"] for d in duong}.items() if k == "mặc định"]
    if mac_cong:
        canh_bao.append("Layer chưa ghi kích thước trong tên, đang dùng kích thước mặc định (sửa trong màn hình 3D): "
                        + ", ".join(sorted(mac_cong)[:8]) + ".")
    if not duong:
        canh_bao.append("Layer MEP đã chọn không có đường (LINE / POLYLINE / MLINE) nào.")
    return {"duong": duong, "canh_bao": canh_bao,
            "mac_dinh": {k: v for k, v in cfg.items()}}
