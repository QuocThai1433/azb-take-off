"""Bóc khối lượng ống gió từ bản vẽ HVAC 2D.

Quy ước đọc bản vẽ (khớp bản vẽ mẫu của AZB):
- Ống thẳng là đường MLINE, bề rộng MLINE (scale_factor) = cạnh ống trên mặt bằng.
  Cạnh còn lại lấy từ nhãn chữ / tên block có dạng "500x300" gần nhất.
- Phụ kiện (côn, chuyển vuông-tròn, cút, chân rẽ) là block, kích thước đọc từ tên block:
    HTS-CON-Can-250x200-300x250-L350    côn thu
    HTS-VT-Can-300x250-D311.9-L300      chuyển vuông -> tròn
    HTS-TV-Can-D341.8-500x300-L300      chuyển tròn -> vuông
    HTS-CO-V47-150x150-R75-A90          cút (co)
    HTS-VT-TAP-Phai-150x150-L75-D75     chân rẽ vuông -> tròn
- Block còn lại (miệng gió, van, quạt, louver...) chỉ đếm số lượng.

Diện tích tôn = chu vi x chiều dài (ống thẳng) hoặc công thức khai triển gần đúng (phụ kiện).
Độ dày tôn theo cạnh lớn nhất, bảng ngưỡng trong config/ong_gio.yaml.
"""
import math
import re
from collections import defaultdict

from shapely.geometry import LineString, Point

from . import config

RE_KT = re.compile(r"(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)")
RE_D = re.compile(r"(?<![A-Za-z])[DØ]\s*(\d+(?:[.,]\d+)?)")


def _f(s):
    return float(s.replace(",", "."))


def day_ton(canh_max_mm, bang):
    for nguong, day in bang:
        if canh_max_mm <= nguong:
            return day
    return bang[-1][1]


def _lam_tron(x, n):
    """Làm tròn nửa lên như Excel (round() của Python làm tròn chẵn và lệch do số thực)."""
    return math.floor(x * 10 ** n + 0.5 + 1e-9) / 10 ** n


def _bang_day():
    cfg = config.ong_gio()
    ds = [(float(n), float(d)) for n, d in cfg["day_ton"]]
    return sorted(ds)


def _chu_vi_vuong(a, b):
    return 2 * (a + b) / 1000


def _chu_vi_tron(d):
    return math.pi * d / 1000


def _doc_block(ten):
    """Tên block -> dict phụ kiện hoặc None nếu không phải phụ kiện tôn."""
    n = ten.upper()
    kt = [(_f(a), _f(b)) for a, b in RE_KT.findall(ten)]
    mL = re.search(r"-L(\d+(?:\.\d+)?)", ten)
    L = _f(mL.group(1)) if mL else None
    if n.startswith("HTS-CON-") and len(kt) >= 2 and L:
        (a1, b1), (a2, b2) = kt[0], kt[1]
        m2 = (_chu_vi_vuong(a1, b1) + _chu_vi_vuong(a2, b2)) / 2 * L / 1000
        return {"loai": "Côn thu", "kich_thuoc": f"{a1:g}x{b1:g}→{a2:g}x{b2:g} L{L:g}",
                "canh_max": max(a1, b1, a2, b2), "m2": m2}
    if n.startswith("HTS-VT-TAP-") and kt and L:
        a, b = kt[0]
        mD = RE_D.search(ten.split("-L")[-1]) or RE_D.search(ten)
        d = _f(mD.group(1)) if mD else min(a, b)
        # Chân rẽ: ống vuông ngắn L nối vào cổ tròn, lấy chu vi vuông x L (xấp xỉ khai triển)
        m2 = _chu_vi_vuong(a, b) * L / 1000
        return {"loai": "Chân rẽ vuông→tròn", "kich_thuoc": f"{a:g}x{b:g} L{L:g} (cổ Ø{min(a, b):g}, loe {d:g})",
                "canh_max": max(a, b), "m2": m2}
    if n.startswith("HTS-VT-") and kt and L:
        a, b = kt[0]
        mD = RE_D.search(ten)
        if mD:
            d = _f(mD.group(1))
            m2 = (_chu_vi_vuong(a, b) + _chu_vi_tron(d)) / 2 * L / 1000
            return {"loai": "Chuyển vuông→tròn", "kich_thuoc": f"{a:g}x{b:g}→Ø{d:g} L{L:g}",
                    "canh_max": max(a, b, d), "m2": m2}
    if n.startswith("HTS-TV-") and kt and L:
        a, b = kt[0]
        mD = RE_D.search(ten)
        if mD:
            d = _f(mD.group(1))
            m2 = (_chu_vi_vuong(a, b) + _chu_vi_tron(d)) / 2 * L / 1000
            return {"loai": "Chuyển tròn→vuông", "kich_thuoc": f"Ø{d:g}→{a:g}x{b:g} L{L:g}",
                    "canh_max": max(a, b, d), "m2": m2}
    if n.startswith("HTS-CO-") and kt:
        a, b = kt[0]
        mR = re.search(r"-R(\d+(?:\.\d+)?)", ten)
        mA = re.search(r"-A(\d+(?:\.\d+)?)", ten)
        r_trong = _f(mR.group(1)) if mR else 0.0
        goc = _f(mA.group(1)) if mA else 90.0
        # Bán kính tim = bán kính trong + nửa cạnh trong mặt phẳng uốn (lấy cạnh đầu a)
        r_tim = (r_trong + a / 2) / 1000
        m2 = _chu_vi_vuong(a, b) * math.radians(goc) * r_tim
        return {"loai": "Cút (co)", "kich_thuoc": f"{a:g}x{b:g} R{r_trong:g} {goc:g}°",
                "canh_max": max(a, b), "m2": m2}
    return None


def _nhan_kich_thuoc(doc, he_so):
    """Các nhãn chữ / tên block có kích thước WxH: list (a, b, (x, y) m hoặc None)."""
    ds = []
    for e in doc.modelspace():
        t = e.dxftype()
        if t in ("TEXT", "MTEXT"):
            nd = e.plain_text() if t == "MTEXT" else e.dxf.text
            p = e.dxf.insert
            for a, b in RE_KT.findall(nd or ""):
                ds.append((_f(a), _f(b), Point(p.x * he_so, p.y * he_so), "chu"))
        elif t == "INSERT":
            p = e.dxf.insert
            for a, b in RE_KT.findall(e.dxf.name):
                ds.append((_f(a), _f(b), Point(p.x * he_so, p.y * he_so), "block"))
    return ds


def _chon_kich_thuoc(w_mm, diem_giua, nhan, canh_bao):
    """Chọn cạnh còn lại của ống rộng w_mm trên mặt bằng, theo nhãn gần nhất."""
    ung = []
    for a, b, p, nguon in nhan:
        for dau, cuoi, thu_tu in ((a, b, 0), (b, a, 1)):
            if abs(dau - w_mm) < 1:
                ung.append((thu_tu, 0 if nguon == "chu" else 1, p.distance(diem_giua), cuoi))
    if not ung:
        canh_bao.append(
            f"Ống rộng {w_mm:g} không có nhãn kích thước nào khớp, tạm tính vuông {w_mm:g}x{w_mm:g}, Sếp kiểm tra.")
        return w_mm
    ung.sort()
    return ung[0][3]


def boc_ong_gio(ban_ve, loai_layer):
    """ban_ve.doc phải là ezdxf Drawing đã đọc. loai_layer: {tên layer: loại}."""
    if getattr(ban_ve, "doc", None) is None:
        raise ValueError("Phiên làm việc không còn dữ liệu gốc, Sếp tải bản vẽ lên lại.")
    layers = {k for k, v in loai_layer.items() if v == "ong_gio"}
    if not layers:
        raise ValueError('Sếp chọn ít nhất một layer là "Ống gió" ở bước 2.')
    he_so = ban_ve.he_so
    bang = _bang_day()
    cfg = config.ong_gio()
    # Công cụ CAD gốc làm tròn tổng dài và m²/cái trước khi nhân, giữ đúng quy ước để đối chiếu
    so_le_dai, so_le_m2_cai = int(cfg["lam_tron_dai"]), int(cfg["lam_tron_m2_cai"])
    ghi_de = cfg.get("m2_cai_ghi_de") or {}
    canh_bao = []
    nhan = _nhan_kich_thuoc(ban_ve.doc, he_so)

    run = defaultdict(lambda: {"mat_bang": 0.0, "so_doan": 0, "diem": []})
    phu_kien = defaultdict(int)
    thiet_bi = defaultdict(int)
    so_mline = 0
    for e in ban_ve.doc.modelspace():
        if e.dxf.layer not in layers:
            continue
        t = e.dxftype()
        if t == "MLINE":
            so_mline += 1
            pts = [(p.x * he_so, p.y * he_so) for p in e.get_locations()]
            if len(pts) < 2:
                continue
            if e.is_closed:
                pts.append(pts[0])
            dai = LineString(pts).length
            w_mm = round(e.dxf.scale_factor * he_so * 1000, 3)
            r = run[w_mm]
            r["mat_bang"] += dai
            r["so_doan"] += 1
            r["diem"].append(LineString(pts).interpolate(0.5, normalized=True))
        elif t == "INSERT":
            ten = e.dxf.name
            if ten.startswith("*"):
                continue
            (phu_kien if _doc_block(ten) else thiet_bi)[ten] += 1

    if not so_mline and not phu_kien and not thiet_bi:
        canh_bao.append("Layer đã chọn không có MLINE hay block nào. Ống gió vẽ bằng LINE/POLYLINE chưa được hỗ trợ.")

    ong = []
    for w_mm, r in sorted(run.items(), reverse=True):
        diem = r["diem"][0]
        h_mm = _chon_kich_thuoc(w_mm, diem, nhan, canh_bao)
        day = day_ton(max(w_mm, h_mm), bang)
        chu_vi = _chu_vi_vuong(w_mm, h_mm)
        dai = _lam_tron(r["mat_bang"], so_le_dai)
        ong.append({
            "kich_thuoc": f"{w_mm:g}x{h_mm:g}", "rong": w_mm, "cao": h_mm, "so_doan": r["so_doan"],
            "mat_bang": dai, "tong": dai, "chu_vi": chu_vi, "day": day,
            "dien_tich": dai * chu_vi,
        })

    pk = []
    for ten, sl in sorted(phu_kien.items()):
        b = _doc_block(ten)
        day = day_ton(b["canh_max"], bang)
        m2_cai = _lam_tron(b["m2"], so_le_m2_cai)
        if ten in ghi_de:
            m2_cai = float(ghi_de[ten])
            canh_bao.append(f"{ten}: m² tôn/cái lấy theo bảng ghi đè trong config/ong_gio.yaml ({m2_cai:g}), không theo công thức.")
        pk.append({"loai": b["loai"], "block": ten, "kich_thuoc": b["kich_thuoc"], "so_luong": sl,
                   "day": day, "m2_cai": m2_cai, "m2": m2_cai * sl})
    thu_tu = {"Côn thu": 0, "Chuyển vuông→tròn": 1, "Chuyển tròn→vuông": 2, "Cút (co)": 3, "Chân rẽ vuông→tròn": 4}
    pk.sort(key=lambda x: (thu_tu.get(x["loai"], 9), x["block"]))

    days = sorted({o["day"] for o in ong} | {p["day"] for p in pk})
    tong_hop = []
    for d in days:
        a = sum(o["dien_tich"] for o in ong if o["day"] == d)
        b = sum(p["m2"] for p in pk if p["day"] == d)
        tong_hop.append({"day": d, "ong_thang": a, "phu_kien": b, "cong": a + b})

    return {
        "ten_file": ban_ve.ten_file, "don_vi": ban_ve.don_vi, "layers": sorted(layers), "canh_bao": canh_bao,
        "ong_thang": ong, "phu_kien": pk,
        "thiet_bi": [{"block": k, "so_luong": v} for k, v in sorted(thiet_bi.items())],
        "tong_hop": tong_hop,
        "tong": {
            "mat_bang": sum(o["mat_bang"] for o in ong), "ong_thang": sum(o["dien_tich"] for o in ong),
            "so_phu_kien": sum(p["so_luong"] for p in pk), "phu_kien": sum(p["m2"] for p in pk),
            "cong": sum(o["dien_tich"] for o in ong) + sum(p["m2"] for p in pk),
        },
    }
