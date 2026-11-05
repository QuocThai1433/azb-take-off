"""Đọc bản vẽ PDF (xuất từ CAD, còn nét vector) và đổi thành file DXF để đi qua đúng luồng DXF hiện có.

PDF lưu nét theo điểm trên giấy (1/72 inch), không có đơn vị thật. Công cụ đổi sang mm trên giấy rồi nhân với mẫu số
tỷ lệ bản vẽ (1/100 -> x100) để ra mm thực tế. Tỷ lệ lấy từ chữ "TL 1/100" trong trang, hoặc người dùng nhập tay.
PDF scan (chỉ có ảnh, không có nét vector) không đọc được hình học: báo lỗi rõ ràng, không đoán.
"""
import math
import re
from collections import Counter
from pathlib import Path

import ezdxf

MM_MOI_PT = 25.4 / 72.0
TY_LE_HOP_LE = (1, 5000)         # mẫu số tỷ lệ chấp nhận
SO_DOAN_BEZIER = 8                # chia mỗi đường cong Bezier thành bấy nhiêu đoạn thẳng
SAI_SO_KHEP_PT = 0.05             # hai điểm cách nhau dưới mức này (điểm PDF) coi là trùng
SO_NET_TOI_THIEU = 5              # ít nét hơn mức này coi như PDF không có vector

_MAU_TY_LE = [
    re.compile(r"(?:T\s*[/.:]?\s*L|T[ỶY]\s*L[ỆE]|SCALE)\s*[:=]?\s*1\s*[/:]\s*(\d{1,4})", re.I),
]
_MAU_TY_LE_TRAN = re.compile(r"(?<![\d.,/])1\s*[/:]\s*(20|25|30|40|50|75|100|150|200|250|300|500)(?![\d])")


def doc_ty_le(van_ban):
    """Mẫu số tỷ lệ hay gặp nhất trong chữ của trang (TL 1/100, TỶ LỆ 1:50 ...). Không thấy thì None."""
    dem = Counter()
    for m in _MAU_TY_LE[0].finditer(van_ban):
        dem[int(m.group(1))] += 1
    if not dem:
        for m in _MAU_TY_LE_TRAN.finditer(van_ban):
            dem[int(m.group(1))] += 1
    dem = Counter({k: v for k, v in dem.items() if TY_LE_HOP_LE[0] <= k <= TY_LE_HOP_LE[1]})
    return dem.most_common(1)[0][0] if dem else None


def _ten_layer(ten):
    s = re.sub(r"[^\w\-]+", "_", str(ten or ""), flags=re.UNICODE).strip("_")
    return (s or "PDF")[:60]


def _hex_mau(rgb):
    if not rgb:
        return None
    return "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in rgb[:3])


def _bezier(p0, p1, p2, p3):
    out = []
    for i in range(1, SO_DOAN_BEZIER + 1):
        t = i / SO_DOAN_BEZIER
        u = 1 - t
        out.append((u**3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t**3 * p3[0],
                    u**3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t**3 * p3[1]))
    return out


def _gan(a, b):
    return abs(a[0] - b[0]) <= SAI_SO_KHEP_PT and abs(a[1] - b[1]) <= SAI_SO_KHEP_PT


def _duong_tu_item(items):
    """Nối các item của một path thành các chuỗi điểm liên tục. Trả về [(ds_diem, khep)]."""
    chuoi, hien = [], []
    for it in items:
        k = it[0]
        if k == "l":
            doan = [(it[1].x, it[1].y), (it[2].x, it[2].y)]
        elif k == "c":
            p0 = (it[1].x, it[1].y)
            doan = [p0] + _bezier(p0, (it[2].x, it[2].y), (it[3].x, it[3].y), (it[4].x, it[4].y))
        elif k == "re":
            r = it[1]
            chuoi.append(([(r.x0, r.y0), (r.x1, r.y0), (r.x1, r.y1), (r.x0, r.y1)], True))
            continue
        elif k == "qu":
            q = it[1]
            chuoi.append(([(q.ul.x, q.ul.y), (q.ur.x, q.ur.y), (q.lr.x, q.lr.y), (q.ll.x, q.ll.y)], True))
            continue
        else:
            continue
        if hien and _gan(hien[-1], doan[0]):
            hien.extend(doan[1:])
        else:
            if len(hien) >= 2:
                chuoi.append((hien, False))
            hien = list(doan)
    if len(hien) >= 2:
        chuoi.append((hien, False))
    ra = []
    for ds, khep in chuoi:
        if not khep and len(ds) >= 4 and _gan(ds[0], ds[-1]):
            ds, khep = ds[:-1], True
        ra.append((ds, khep))
    return ra


def pdf_sang_dxf(duong_pdf, duong_dxf, trang=1, ty_le=None):
    """Đổi 1 trang PDF thành DXF (mm thực tế). trang đếm từ 1. ty_le: mẫu số (100 = 1/100); None = tự đọc từ chữ.

    Trả về dict: {so_trang, ty_le, ty_le_nguon ('nhap'|'doc'|'mac_dinh'), so_net, so_chu, canh_bao: [..]}.
    """
    import pymupdf
    canh_bao = []
    with pymupdf.open(str(duong_pdf)) as pdf:
        if pdf.needs_pass:
            raise RuntimeError("PDF có đặt mật khẩu, Sếp mở khóa rồi tải lại.")
        so_trang = pdf.page_count
        if not 1 <= trang <= so_trang:
            raise RuntimeError(f"PDF chỉ có {so_trang} trang, không có trang {trang}.")
        pg = pdf[trang - 1]
        rect = pg.rect                  # đã tính xoay trang
        xoay = pg.rotation_matrix if pg.rotation else None

        def bien(x, y):
            if xoay is not None:
                p = pymupdf.Point(x, y) * xoay
                x, y = p.x, p.y
            return x, rect.height - y   # PDF gốc y hướng xuống, CAD y hướng lên

        paths = pg.get_drawings()
        tu_dien_chu = pg.get_text("dict")

    chu_trang = []
    for kh in tu_dien_chu.get("blocks", []):
        for dong in kh.get("lines", []):
            s = "".join(sp.get("text", "") for sp in dong.get("spans", [])).strip()
            if s:
                chu_trang.append(s)
    van_ban = "\n".join(chu_trang)

    if len(paths) < SO_NET_TOI_THIEU:
        raise RuntimeError(
            "PDF này không có nét vector (có thể là bản scan hoặc ảnh chụp), công cụ không đọc được hình học. "
            "Sếp xuất lại PDF từ AutoCAD (lệnh PLOT/EXPORT, giữ vector) hoặc tải file DXF/DWG gốc.")

    if ty_le:
        nguon = "nhap"
    else:
        ty_le = doc_ty_le(van_ban)
        nguon = "doc" if ty_le else "mac_dinh"
        if not ty_le:
            ty_le = 1
            canh_bao.append("Không thấy chữ tỷ lệ (TL 1/xx) trong trang PDF. Em tạm lấy 1/1, kích thước đang là mm trên giấy. "
                            "Sếp nhập tỷ lệ ở ô \"Tỷ lệ PDF\" rồi tải lại để ra kích thước thật.")
    if not TY_LE_HOP_LE[0] <= ty_le <= TY_LE_HOP_LE[1]:
        raise RuntimeError(f"Tỷ lệ 1/{ty_le} không hợp lệ.")
    he_so = MM_MOI_PT * ty_le           # điểm PDF -> mm thực tế

    doc = ezdxf.new("R2010", setup=False)
    doc.header["$INSUNITS"] = 4         # mm
    doc.header["$MEASUREMENT"] = 1
    msp = doc.modelspace()
    cac_layer = set()

    def dam_bao_layer(ten):
        if ten not in cac_layer:
            cac_layer.add(ten)
            if ten not in doc.layers:
                doc.layers.add(ten)

    so_net = 0
    for p in paths:
        mau = _hex_mau(p.get("color")) or _hex_mau(p.get("fill"))
        ten_oc = p.get("layer")
        ten = _ten_layer(ten_oc) if ten_oc else (f"PDF_{mau}" if mau else "PDF_0")
        for ds, khep in _duong_tu_item(p.get("items", [])):
            pts = [(bien(x, y)[0] * he_so, bien(x, y)[1] * he_so) for x, y in ds]
            if len(pts) < 2:
                continue
            dam_bao_layer(ten)
            if len(pts) == 2 and not khep:
                msp.add_line(pts[0], pts[1], dxfattribs={"layer": ten})
            else:
                msp.add_lwpolyline(pts, close=khep, dxfattribs={"layer": ten})
            so_net += 1
    if so_net < SO_NET_TOI_THIEU:
        raise RuntimeError("Không lấy được nét vector nào từ trang PDF này.")

    so_chu = 0
    ten_chu = "PDF_CHU"
    for kh in tu_dien_chu.get("blocks", []):
        for dong in kh.get("lines", []):
            dx, dy = dong.get("dir", (1.0, 0.0))
            if xoay is not None:
                v = pymupdf.Point(dx, dy) * pymupdf.Matrix(xoay.a, xoay.b, xoay.c, xoay.d, 0, 0)
                dx, dy = v.x, v.y
            goc = math.degrees(math.atan2(-dy, dx)) % 360   # lật trục y
            for sp in dong.get("spans", []):
                s = sp.get("text", "").strip()
                if not s:
                    continue
                ox, oy = sp.get("origin", sp["bbox"][:2])
                x, y = bien(ox, oy)
                dam_bao_layer(ten_chu)
                cao = max(float(sp.get("size", 10.0)) * 0.72 * he_so, 1e-6)  # chiều cao chữ hoa ~ 0,72 cỡ chữ
                t = msp.add_text(s, dxfattribs={"layer": ten_chu, "height": cao, "rotation": goc})
                t.set_placement((x * he_so, y * he_so))
                so_chu += 1

    if not so_chu:
        canh_bao.append("Trang PDF không có chữ (nhãn, kích thước đã bị chuyển thành nét hoặc ảnh). "
                        "Công cụ sẽ không tự nhận ký hiệu cột/dầm; Sếp gán tay hoặc dùng bản PDF có chữ.")
    canh_bao.append(f"Bản vẽ lấy từ PDF trang {trang}/{so_trang}, tỷ lệ 1/{ty_le}"
                    + (" (đọc từ chữ trong bản vẽ)" if nguon == "doc" else " (Sếp nhập)" if nguon == "nhap" else "")
                    + ". Kiểm tra lại bằng một kích thước đã biết trước khi bóc.")
    Path(duong_dxf).parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(str(duong_dxf))
    return {"so_trang": so_trang, "ty_le": ty_le, "ty_le_nguon": nguon, "so_net": so_net, "so_chu": so_chu,
            "canh_bao": canh_bao}
