"""Hệ quy chiếu dự án: lưới trục chuẩn, điểm gốc, bảng cao độ tầng.

Chọn một lần ngay từ đầu dự án, dùng cho cả quá trình (móng, cột, dầm sàn... ghép 3D đều quy về đây):
  - Lưới trục chuẩn: dò các đường trục trên một mặt bằng chuẩn (layer TRUC / GRID / AXIS...), đọc tên trục trong
    bong bóng ở đầu trục. Người dùng xem lại, sửa tên, thêm / bớt trục.
  - Điểm gốc: giao của một trục dọc và một trục ngang (vd A-1) = toạ độ (0, 0) của công trình.
    Điểm hướng (tuỳ chọn): một giao trục khác, cho biết chiều dương của trục X công trình.
  - Bảng tầng: mã, tên, loại, cao độ kết cấu (dùng dựng 3D), cao độ hoàn thiện, dày sàn, cao dầm.
    Chiều cao tầng tự tính = cao độ tầng trên - cao độ tầng này.

Máy chỉ đề xuất (dò trục, gợi ý cao độ đọc từ bản vẽ); người xác nhận mới thành dữ liệu chuẩn.
"""
import math
import re

from shapely.geometry import box

RE_LAYER_TRUC = re.compile(r"tr[uụ]c|grid|axis|l[uư][oơ]i", re.I)
# Tên trục: 1, 12, 1', 1a, A, AB, A', A1 (trục phụ), 22aX1 (tên kiểu gán nhãn tự động)
RE_TEN_TRUC = re.compile(r"^(?:[A-Z]{1,2}'?\d{0,2}'?|\d{1,3}[a-z]?'?|\w{0,4}[XY]\d{1,3})$")
# Cao độ: +3.600, -1.500, ±0.000, +-0.000, EL +3.6, CAO ĐỘ +3,600, +3.600m, 3.600 (không dấu thì bỏ: dễ lẫn kích thước)
RE_CAO_DO = re.compile(r"^(?:EL\.?\s*|CAO\s*[ĐD][ỘO]\s*|CĐ\s*|COTE\s*)?(±|\+-|\+/-|\+|-|−)\s*(\d+(?:[.,]\d+)?)\s*(?:m|M)?$", re.I)

DAI_TOI_THIEU = 1.0          # m - nét ngắn hơn không phải trục
TY_LE_DAI_TOI_THIEU = 0.3    # nét trục ngắn hơn 30% nét trục dài nhất cùng hướng thì bỏ (vạch kích thước, ký hiệu)
DUNG_SAI_TRUC_BO_PHIEU = 0.05   # m: hai độ dời trục coi là cùng một chỗ khi lệch nhau không quá 50 mm
BE_RONG_DAM_TOI_DA = 1.2      # m - "dầm" có cạnh ngắn rộng hơn mức này là đường bao khung / ô dầm / khung ghi chú bị đọc nhầm, không đưa vào tổng hợp (3D cũng bỏ)
DUNG_SAI_GOP = 0.02          # m - hai nét trục cách nhau dưới mức này là một trục
BAN_KINH_BONG = (0.08, 1.2)  # m - bán kính bong bóng tên trục hợp lệ
TIM_TEN_XA = 2.5             # m - tìm chữ tên trục quanh đầu trục trong bán kính này (khi không có bong bóng)
KHOANG_TRUC_NHO = 0.3        # m - hai trục gần nhau hơn mức này: cảnh báo (có thể vẽ trùng)

LOAI_TANG = {"mong": "Móng", "ham": "Hầm", "tang": "Tầng", "lung": "Tầng lửng", "ky_thuat": "Tầng kỹ thuật",
             "mai": "Mái", "tum": "Tum"}
CAO_TANG_HOP_LY = (2.2, 8.0)  # m - chiều cao tầng ngoài khoảng này thì cảnh báo


# ---------- Dò lưới trục ----------
def _so(v):
    return round(float(v), 4)


def _vung_box(ban_ve, vung):
    if vung and len(vung) == 4:
        x0, y0, x1, y1 = (float(v) for v in vung)
        return box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    b = None
    for ld in ban_ve.layers.values():
        for g in [h.geom for h in ld.hinh_kin] + list(ld.net_ho):
            bb = g.bounds
            b = list(bb) if b is None else [min(b[0], bb[0]), min(b[1], bb[1]), max(b[2], bb[2]), max(b[3], bb[3])]
    return box(*b) if b else None


def _net_truc(ban_ve, vung_box, layer_truc):
    """Các nét thẳng đứng / ngang trên layer trục, cắt vào vùng. Trả (dọc, ngang): dọc = [(x, y_min, y_max)]."""
    doc, ngang = [], []
    for ld in ban_ve.layers.values():
        la_truc = ld.ten in layer_truc if layer_truc else RE_LAYER_TRUC.search(ld.ten)
        if not la_truc or (ld.tat and not layer_truc):
            continue
        for n in ld.net_ho:
            if n.length < DAI_TOI_THIEU or not vung_box.intersects(n):
                continue
            x0, y0, x1, y1 = n.bounds
            if x1 - x0 < 0.003 * n.length:
                doc.append(((x0 + x1) / 2, y0, y1))
            elif y1 - y0 < 0.003 * n.length:
                ngang.append(((y0 + y1) / 2, x0, x1))
    return doc, ngang


def _gop(ds):
    """Gộp các nét cùng toạ độ (trục vẽ thành nhiều đoạn), bỏ nét quá ngắn so với trục dài nhất."""
    ds = sorted(ds)
    nhom = []
    for d in ds:
        if nhom and d[0] - nhom[-1][-1][0] <= DUNG_SAI_GOP:
            nhom[-1].append(d)
        else:
            nhom.append([d])
    kq = [(sum(d[0] for d in g) / len(g), min(d[1] for d in g), max(d[2] for d in g)) for g in nhom]
    if not kq:
        return kq
    dai_max = max(b - a for _, a, b in kq)
    return [t for t in kq if t[2] - t[1] >= TY_LE_DAI_TOI_THIEU * dai_max]


def _bong(ban_ve, vung_box):
    """Vòng tròn có thể là bong bóng tên trục: (x, y, r)."""
    kq = []
    for ld in ban_ve.layers.values():
        for h in ld.hinh_kin:
            if h.nguon != "CIRCLE":
                continue
            r = math.sqrt(h.geom.area / math.pi)
            if BAN_KINH_BONG[0] <= r <= BAN_KINH_BONG[1] and vung_box.buffer(TIM_TEN_XA * 2).intersects(h.geom):
                kq.append((h.geom.centroid.x, h.geom.centroid.y, r))
    return kq


def _chu_ten(ban_ve, vung_box):
    kq = []
    for ld in ban_ve.layers.values():
        for c in ld.chu:
            t = c.noi_dung.strip().replace(" ", "")
            if RE_TEN_TRUC.match(t) and vung_box.buffer(TIM_TEN_XA * 2).contains(c.diem):
                kq.append((t, c.diem.x, c.diem.y, c.cao or 0.0))
    return kq


def _tam_chu(c):
    # điểm neo của chữ thường là góc dưới trái: dời lên nửa chiều cao cho gần tâm chữ hơn
    t, x, y, h = c
    return x + 0.3 * h * max(len(t), 1), y + 0.5 * h


def _ten_tai_dau(dau, bong, chu, da_dung):
    """Tên trục tại một đầu trục: ưu tiên chữ nằm trong bong bóng chạm đầu trục, rồi chữ gần đầu trục nhất."""
    px, py = dau
    for bx, by, r in sorted(bong, key=lambda b: math.hypot(b[0] - px, b[1] - py)):
        if math.hypot(bx - px, by - py) > r * 2.2 + 0.05:
            break
        trong = [c for c in chu if math.hypot(_tam_chu(c)[0] - bx, _tam_chu(c)[1] - by) <= r * 1.1 and id(c) not in da_dung]
        if trong:
            return min(trong, key=lambda c: math.hypot(_tam_chu(c)[0] - bx, _tam_chu(c)[1] - by)), "bong bóng"
    gan = [c for c in chu if id(c) not in da_dung and math.hypot(_tam_chu(c)[0] - px, _tam_chu(c)[1] - py) <= TIM_TEN_XA]
    if gan:
        return min(gan, key=lambda c: math.hypot(_tam_chu(c)[0] - px, _tam_chu(c)[1] - py)), "chữ gần đầu trục"
    return None, None


def _dat_ten(ds_truc, huong, bong, chu):
    """Gán tên cho từng trục. huong 'doc' (x = const) hoặc 'ngang' (y = const)."""
    da_dung, kq = set(), []
    for v, a, b in ds_truc:
        daus = [(v, a), (v, b)] if huong == "doc" else [(a, v), (b, v)]
        ten, nguon = None, None
        for dau in daus:
            c, ng = _ten_tai_dau(dau, bong, chu, da_dung)
            if c and (ten is None or ng == "bong bóng" and nguon != "bong bóng"):
                ten, nguon, cc = c[0], ng, c
        if ten:
            da_dung.add(id(cc))
        kq.append({"ten": ten or "", "v": _so(v), "tu": _so(a), "den": _so(b), "nguon_ten": nguon or ""})
    return kq


def _chu_cai(i):
    s, i = "", i + 1
    while i > 0:
        m = (i - 1) % 26
        s = chr(65 + m) + s
        i = (i - 1) // 26
    return s


def _ten_mac_dinh(ds, kieu):
    """Trục chưa đọc được tên: đặt tạm. kieu 'so' -> 1, 2, 3...; 'chu' -> A, B, C..."""
    dung = {t["ten"] for t in ds if t["ten"]}
    k = 0
    for t in ds:
        if t["ten"]:
            continue
        while True:
            ten = str(k + 1) if kieu == "so" else _chu_cai(k)
            k += 1
            if ten not in dung:
                break
        t["ten"], t["nguon_ten"] = ten, "tự đặt"
        dung.add(ten)


def do_luoi_truc(ban_ve, vung=None, layer_truc=None):
    """Dò lưới trục trong vùng `vung` = [x0, y0, x1, y1] (mét; None = cả bản vẽ).
    layer_truc: danh sách tên layer trục người dùng chọn; bỏ trống = tự nhận theo tên (TRUC, GRID, AXIS...).
    Trả {"doc": [...], "ngang": [...], "layer": [...], "canh_bao": [...]}; mỗi trục {ten, v, tu, den, nguon_ten}.
    'doc' là trục thẳng đứng (x = v), 'ngang' là trục nằm ngang (y = v), toạ độ theo bản vẽ."""
    canh_bao = []
    vb = _vung_box(ban_ve, vung)
    if vb is None:
        return {"doc": [], "ngang": [], "layer": [], "canh_bao": ["Bản vẽ trống."]}
    layer_truc = [l for l in (layer_truc or []) if l in ban_ve.layers]
    doc, ngang = _net_truc(ban_ve, vb, layer_truc)
    doc, ngang = _gop(doc), _gop(ngang)
    dung_layer = layer_truc or sorted(l for l in ban_ve.layers if RE_LAYER_TRUC.search(l))
    if not doc and not ngang:
        canh_bao.append("Không thấy đường trục: chọn đúng layer trục trong danh sách rồi dò lại, hoặc thêm trục bằng tay."
                        if dung_layer else "Bản vẽ không có layer tên TRUC / GRID / AXIS: chọn layer chứa đường trục rồi dò lại.")
        return {"doc": [], "ngang": [], "layer": dung_layer, "canh_bao": canh_bao}
    bong, chu = _bong(ban_ve, vb), _chu_ten(ban_ve, vb)
    ds_doc, ds_ngang = _dat_ten(doc, "doc", bong, chu), _dat_ten(ngang, "ngang", bong, chu)
    # Thường trục số chạy theo một hướng, trục chữ theo hướng kia: trục chưa có tên đặt theo kiểu của hướng đó
    so_doc = sum(1 for t in ds_doc if t["ten"][:1].isdigit())
    chu_doc = sum(1 for t in ds_doc if t["ten"][:1].isalpha())
    kieu_doc = "chu" if chu_doc > so_doc else "so"
    thieu = sum(1 for t in ds_doc + ds_ngang if not t["ten"])
    _ten_mac_dinh(ds_doc, kieu_doc)
    _ten_mac_dinh(ds_ngang, "so" if kieu_doc == "chu" else "chu")
    if thieu:
        canh_bao.append(f"{thieu} trục không đọc được tên trong bong bóng: đã đặt tên tạm, Sếp sửa lại cho đúng bản vẽ.")
    canh_bao += kiem_tra_luoi({"doc": ds_doc, "ngang": ds_ngang})
    return {"doc": ds_doc, "ngang": ds_ngang, "layer": dung_layer, "canh_bao": canh_bao}


def dat_ten_luoi(ban_ve, luoi):
    """Đặt tên cho các trục NGƯỜI DÙNG VỪA CHỌN TAY trên bản vẽ (ten rỗng); trục đã có tên giữ nguyên.
    Đọc tên từ bong bóng / chữ gần đầu trục như khi dò tự động; không đọc được thì đặt tạm (1, 2, 3 / A, B, C).
    luoi = {"doc": [{ten, v, tu, den}], "ngang": [...]}. Trả {"doc", "ngang", "canh_bao"} (thứ tự giữ nguyên)."""
    ds = {hx: [dict(t) for t in (luoi.get(hx) or [])] for hx in ("doc", "ngang")}
    tat_ca = [t for hx in ds for t in ds[hx]]
    if not tat_ca:
        return {"doc": [], "ngang": [], "canh_bao": []}
    x0 = min(min(t["tu"], t["v"]) if hx == "ngang" else t["v"] for hx in ds for t in ds[hx])
    x1 = max(max(t["den"], t["v"]) if hx == "ngang" else t["v"] for hx in ds for t in ds[hx])
    y0 = min(t["v"] if hx == "ngang" else min(t["tu"], t["den"]) for hx in ds for t in ds[hx])
    y1 = max(t["v"] if hx == "ngang" else max(t["tu"], t["den"]) for hx in ds for t in ds[hx])
    vb = box(x0, y0, x1, y1)
    bong, chu = _bong(ban_ve, vb), _chu_ten(ban_ve, vb)
    da_co = {t["ten"] for t in tat_ca if t.get("ten")}
    for hx in ds:
        goi = _dat_ten([(t["v"], t["tu"], t["den"]) for t in ds[hx]], hx, bong, chu)
        for t, g in zip(ds[hx], goi):
            if not t.get("ten") and g["ten"] and g["ten"] not in da_co:
                t["ten"], t["nguon_ten"] = g["ten"], g["nguon_ten"]
                da_co.add(g["ten"])
    so_doc = sum(1 for t in ds["doc"] if t.get("ten", "")[:1].isdigit())
    chu_doc = sum(1 for t in ds["doc"] if t.get("ten", "")[:1].isalpha())
    kieu_doc = "chu" if chu_doc > so_doc else "so"
    thieu = sum(1 for t in tat_ca if not t.get("ten"))
    for hx, kieu in (("doc", kieu_doc), ("ngang", "so" if kieu_doc == "chu" else "chu")):
        for t in ds[hx]:
            t.setdefault("ten", "")
        _ten_mac_dinh(ds[hx], kieu)
    canh_bao = []
    if thieu:
        canh_bao.append(f"{thieu} trục không đọc được tên trong bong bóng: đã đặt tên tạm, Sếp sửa lại cho đúng bản vẽ.")
    canh_bao += kiem_tra_luoi(ds)
    return {"doc": ds["doc"], "ngang": ds["ngang"], "canh_bao": canh_bao}


def kiem_tra_luoi(luoi):
    """Cảnh báo lưới trục: trùng tên, hai trục quá gần nhau, thiếu một hướng."""
    cb = []
    for hx, nhan in (("doc", "dọc"), ("ngang", "ngang")):
        ds = sorted(luoi.get(hx) or [], key=lambda t: t["v"])
        if not ds:
            cb.append(f"Chưa có trục {nhan}: cần ít nhất một trục dọc và một trục ngang để có điểm gốc.")
            continue
        ten = [str(t.get("ten") or "").strip() for t in ds]
        trung = sorted({t for t in ten if t and ten.count(t) > 1})
        if trung:
            cb.append(f"Trục {nhan} trùng tên: {', '.join(trung)}.")
        if any(not t for t in ten):
            cb.append(f"Có trục {nhan} chưa đặt tên.")
        for a, b in zip(ds, ds[1:]):
            if b["v"] - a["v"] < KHOANG_TRUC_NHO:
                cb.append(f"Trục {a['ten']} và {b['ten']} chỉ cách nhau {round((b['v'] - a['v']) * 1000)} mm: kiểm tra có vẽ trùng không.")
    ten_doc = {str(t.get("ten")) for t in luoi.get("doc") or []}
    chung = sorted(ten_doc & {str(t.get("ten")) for t in luoi.get("ngang") or []} - {""})
    if chung:
        cb.append(f"Tên trục có ở cả hai hướng: {', '.join(chung)}.")
    return cb


def _tim(ds, ten):
    return next((t for t in ds or [] if str(t.get("ten")) == str(ten)), None)


def diem_giao(luoi, diem):
    """Toạ độ bản vẽ của giao trục diem = {"doc": tên trục dọc, "ngang": tên trục ngang}; không có thì None."""
    if not diem:
        return None
    a, b = _tim(luoi.get("doc"), diem.get("doc")), _tim(luoi.get("ngang"), diem.get("ngang"))
    return (a["v"], b["v"]) if a and b else None


def ten_diem(diem):
    """Tên giao trục kiểu bản vẽ: trục chữ trước, trục số sau (A-1)."""
    if not diem:
        return ""
    d, n = str(diem.get("doc") or ""), str(diem.get("ngang") or "")
    return f"{d}-{n}" if d[:1].isalpha() and not n[:1].isalpha() else f"{n}-{d}"


# ---------- Bảng tầng ----------
def doc_so(v):
    """Đọc số kiểu người nhập: '+3.600', '3,6', '-1.500', '±0.000', '' -> None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if math.isfinite(v) else None
    t = str(v).strip().replace(" ", "").replace("−", "-").replace("±", "").replace("+-", "").replace("+/-", "")
    t = re.sub(r"(?i)^(el\.?|cote|cđ)", "", t).rstrip("mM")
    if not t:
        return None
    if t.count(",") == 1 and "." not in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def chuan_hoa_bang_tang(ds):
    """Chuẩn hoá bảng tầng người nhập: đọc số, sắp theo cao độ kết cấu, tính chiều cao tầng, cảnh báo chỗ bất thường.
    Mỗi dòng vào: {ma, ten, loai, cao_do_kc, cao_do_ht, day_san, cao_dam, ghi_chu}.
    Trả {"tang": [...dòng đã chuẩn hoá, có chieu_cao], "canh_bao": [...]}."""
    cb, kq = [], []
    for i, r in enumerate(ds or []):
        if not isinstance(r, dict):
            continue
        ma = str(r.get("ma") or "").strip().upper()
        dong = {"ma": ma, "ten": str(r.get("ten") or "").strip(), "loai": r.get("loai") if r.get("loai") in LOAI_TANG else "tang",
                "cao_do_kc": doc_so(r.get("cao_do_kc")), "cao_do_ht": doc_so(r.get("cao_do_ht")),
                "day_san": doc_so(r.get("day_san")), "cao_dam": doc_so(r.get("cao_dam")),
                "ghi_chu": str(r.get("ghi_chu") or "").strip(), "chieu_cao": None}
        ten = ma or dong["ten"] or f"dòng {i + 1}"
        if not ma:
            cb.append(f"{ten}: chưa có mã tầng (vd T1, T2, MONG, MAI).")
        if dong["cao_do_kc"] is None:
            cb.append(f"{ten}: chưa nhập cao độ kết cấu.")
        for k, nhan in (("cao_do_kc", "cao độ kết cấu"), ("cao_do_ht", "cao độ hoàn thiện"), ("day_san", "dày sàn"), ("cao_dam", "cao dầm")):
            if r.get(k) not in (None, "") and dong[k] is None:
                cb.append(f"{ten}: {nhan} '{r.get(k)}' không đọc được thành số.")
        kq.append(dong)
    ma_ds = [d["ma"] for d in kq if d["ma"]]
    trung = sorted({m for m in ma_ds if ma_ds.count(m) > 1})
    if trung:
        cb.append(f"Trùng mã tầng: {', '.join(trung)}.")
    co = sorted([d for d in kq if d["cao_do_kc"] is not None], key=lambda d: d["cao_do_kc"])
    chua = [d for d in kq if d["cao_do_kc"] is None]
    for a, b in zip(co, co[1:]):
        h = round(b["cao_do_kc"] - a["cao_do_kc"], 4)
        if h == 0:
            cb.append(f"{a['ma']} và {b['ma']} cùng cao độ {a['cao_do_kc']:+.3f}.")
            continue
        a["chieu_cao"] = h
        if a["loai"] in ("tang", "ham", "lung", "ky_thuat") and not CAO_TANG_HOP_LY[0] <= h <= CAO_TANG_HOP_LY[1]:
            cb.append(f"{a['ma']}: chiều cao tầng {h:.3f} m, ngoài khoảng thường gặp {CAO_TANG_HOP_LY[0]}–{CAO_TANG_HOP_LY[1]} m.")
        if a["day_san"] and a["day_san"] / 1000 >= h:
            cb.append(f"{a['ma']}: dày sàn {a['day_san']:.0f} mm không nhỏ hơn chiều cao tầng.")
    for d in co:
        if d["cao_do_ht"] is not None and d["cao_do_ht"] < d["cao_do_kc"]:
            cb.append(f"{d['ma']}: cao độ hoàn thiện {d['cao_do_ht']:+.3f} thấp hơn cao độ kết cấu {d['cao_do_kc']:+.3f}.")
        if d["cao_do_ht"] is not None and d["cao_do_ht"] - d["cao_do_kc"] > 0.3:
            cb.append(f"{d['ma']}: lớp hoàn thiện dày {round((d['cao_do_ht'] - d['cao_do_kc']) * 1000)} mm, kiểm tra lại.")
    # thứ tự loại tầng: móng / hầm dưới các tầng, mái / tum trên cùng
    cao_tang = [d["cao_do_kc"] for d in co if d["loai"] in ("tang", "lung", "ky_thuat")]
    if cao_tang:
        for d in co:
            if d["loai"] in ("mong", "ham") and d["cao_do_kc"] > min(cao_tang):
                cb.append(f"{d['ma']}: {LOAI_TANG[d['loai']].lower()} lại cao hơn tầng thấp nhất.")
            if d["loai"] in ("mai", "tum") and d["cao_do_kc"] < max(cao_tang):
                cb.append(f"{d['ma']}: {LOAI_TANG[d['loai']].lower()} lại thấp hơn tầng cao nhất.")
    return {"tang": co + chua, "canh_bao": cb}


def cao_do_goi_y(ban_ve):
    """Các cao độ ghi trên bản vẽ (+3.600, -1.500, ±0.000...) để gợi ý khi nhập bảng tầng: [{gia_tri, so_lan}]."""
    dem = {}
    for ld in ban_ve.layers.values():
        for c in ld.chu:
            m = RE_CAO_DO.match(c.noi_dung.strip())
            if not m:
                continue
            v = float(m.group(2).replace(",", "."))
            v = -v if m.group(1) in ("-", "−") else (0.0 if m.group(1) in ("±", "+-", "+/-") else v)
            if abs(v) > 300:   # không phải cao độ (m)
                continue
            dem[round(v, 3)] = dem.get(round(v, 3), 0) + 1
    return [{"gia_tri": v, "so_lan": n} for v, n in sorted(dem.items())]


# ---------- Gán vùng mặt bằng vào hệ quy chiếu ----------
CAU_KIEN = {"mong": "Móng", "cot_vach": "Cột - vách", "dam_san": "Dầm - sàn", "kien_truc": "Kiến trúc", "mep": "MEP", "khac": "Khác"}
DUNG_SAI_TRUC = 0.05          # m - trục của vùng lệch khỏi lưới chuẩn quá mức này sau khi căn thì cảnh báo
DUNG_SAI_KHOANG_CACH = 0.05   # m - khoảng cách hai điểm căn ở vùng khác ở lưới chuẩn quá mức này thì cảnh báo


def _chon_truc_khop(local, chuan, ten_uu_tien=None, dung_sai=DUNG_SAI_TRUC_BO_PHIEU):
    """Chọn trục của vùng làm điểm căn theo cách bỏ phiếu: mỗi trục local trùng tên với trục chuẩn cho một độ dời
    (vị trí chuẩn - vị trí local). Độ dời nào được nhiều trục cùng đồng ý nhất thì thắng, nên một đường khác cùng tên
    (mặt cắt, chi tiết vẽ ở chỗ khác) không thể làm lệch cả vùng. Trả (trục local được chọn, số trục đồng ý)."""
    cv = {str(t["ten"]): t["v"] for t in chuan}
    ds = [(cv[str(t["ten"])] - t["v"], t) for t in local if str(t["ten"]) in cv]
    if not ds:
        return None, 0
    nhom = []
    for d, t in ds:
        for g in nhom:
            if abs(g["d"] - d) <= dung_sai:
                g["ts"].append(t)
                break
        else:
            nhom.append({"d": d, "ts": [t]})
    tot = max(nhom, key=lambda g: (len({str(t["ten"]) for t in g["ts"]}), len(g["ts"])))
    chon = next((t for t in tot["ts"] if str(t["ten"]) == str(ten_uu_tien)), tot["ts"][0])
    return chon, len({str(t["ten"]) for t in tot["ts"]})


def goi_y_diem_vung(ban_ve, vung, hqc_da_kiem):
    """Đề xuất điểm căn của một vùng: dò lưới trục trong vùng, nếu có trục trùng tên với lưới chuẩn thì lấy giao
    của trục trùng tên (ưu tiên trục của điểm gốc chuẩn). Trả {luoi, diem, goc_local, ly_do, canh_bao}."""
    luoi_c = hqc_da_kiem.get("luoi") or {}
    kq = do_luoi_truc(ban_ve, vung)
    ten_c = {hx: {str(t["ten"]) for t in luoi_c.get(hx) or []} for hx in ("doc", "ngang")}
    chung = {hx: [t for t in kq[hx] if str(t["ten"]) in ten_c[hx]] for hx in ("doc", "ngang")}
    cb = [c for c in kq["canh_bao"] if "tên" not in c]
    out = {"luoi": {"doc": kq["doc"], "ngang": kq["ngang"]}, "diem": None, "goc_local": None, "ly_do": "", "canh_bao": cb}
    if not (kq["doc"] and kq["ngang"]):
        out["canh_bao"].append("Vùng này chưa dò được đủ trục dọc và trục ngang: chọn điểm căn bằng tay trên bản vẽ.")
        return out
    if not (chung["doc"] and chung["ngang"]):
        out["canh_bao"].append("Tên trục trong vùng không trùng tên trục chuẩn: kiểm tra tên trục, hoặc chọn điểm căn bằng tay.")
        return out
    uu_tien = (hqc_da_kiem.get("goc") or {}).get("diem") or {}   # ưu tiên trục của điểm gốc chuẩn
    a, na = _chon_truc_khop(kq["doc"], luoi_c.get("doc") or [], uu_tien.get("doc"))
    b, nb = _chon_truc_khop(kq["ngang"], luoi_c.get("ngang") or [], uu_tien.get("ngang"))
    out["diem"] = {"doc": a["ten"], "ngang": b["ten"]}
    out["goc_local"] = [a["v"], b["v"]]
    out["ly_do"] = (f"Trục {a['ten']} và {b['ten']} trong vùng trùng tên với lưới chuẩn "
                    f"(chọn vị trí khớp nhiều trục nhất: {na} trục dọc, {nb} trục ngang).")
    if na < 2 or nb < 2:
        out["canh_bao"].append("Chỉ khớp được rất ít trục với lưới chuẩn: kiểm tra điểm căn trên bản vẽ.")
    return out


def tinh_can_vung(hqc_da_kiem, diem, goc_local, diem_b=None, goc_local_b=None, luoi_local=None):
    """Phép đưa một vùng về toạ độ của mặt bằng chuẩn, rồi về toạ độ công trình.
    diem = {"doc","ngang"}: giao trục chuẩn mà điểm A của vùng đang nằm trên; goc_local = toạ độ điểm A trên bản vẽ của vùng.
    Có điểm B (giao trục khác + toạ độ) thì tính cả góc xoay. luoi_local (lưới trục dò trong vùng) để kiểm tra chéo.
    Trả {"dich": [dx, dy], "quay": độ, "tam": [x, y], "canh_bao": [...], "kiem_tra_truc": [...], "ok": bool}:
      toạ độ chuẩn  p' = R(quay) (p - tam) + tam + dich    (tam = điểm A của vùng)."""
    luoi = hqc_da_kiem.get("luoi") or {}
    cb, kt = [], []
    ra = diem_giao(luoi, diem)
    if not ra or not goc_local or len(goc_local) != 2:
        return {"dich": None, "quay": 0.0, "tam": None, "canh_bao": ["Chưa có điểm căn của vùng (giao trục + vị trí trên bản vẽ)."], "kiem_tra_truc": [], "ok": False}
    quay = 0.0
    if diem_b and goc_local_b and len(goc_local_b) == 2:
        rb = diem_giao(luoi, diem_b)
        if not rb:
            cb.append("Điểm B không nằm trên lưới trục chuẩn: bỏ qua, chỉ dời không xoay.")
        else:
            va, vr = (goc_local_b[0] - goc_local[0], goc_local_b[1] - goc_local[1]), (rb[0] - ra[0], rb[1] - ra[1])
            lv, lr = math.hypot(*va), math.hypot(*vr)
            if lv < 1e-6 or lr < 1e-6:
                cb.append("Hai điểm căn trùng nhau: bỏ qua điểm B.")
            else:
                quay = round(math.degrees(math.atan2(vr[1], vr[0]) - math.atan2(va[1], va[0])), 4)
                quay = (quay + 180) % 360 - 180
                if abs(lv - lr) > DUNG_SAI_KHOANG_CACH:
                    cb.append(f"Khoảng cách hai điểm căn trong vùng {lv:.3f} m khác lưới chuẩn {lr:.3f} m (lệch {abs(lv - lr) * 1000:.0f} mm): "
                              "bản vẽ vùng có thể khác tỷ lệ hoặc chọn sai trục.")
    dich = [round(ra[0] - goc_local[0], 4), round(ra[1] - goc_local[1], 4)]
    if abs(quay) < 1e-6:
        quay = 0.0
    kq = {"dich": dich, "quay": quay, "tam": [round(goc_local[0], 4), round(goc_local[1], 4)], "canh_bao": cb, "kiem_tra_truc": kt, "ok": True}
    # kiểm tra chéo: các trục của vùng, sau khi căn, phải nằm đúng chỗ trục cùng tên ở lưới chuẩn
    if luoi_local and abs(quay) > 0.01:
        cb.append("Vùng có xoay: chưa kiểm tra chéo vị trí trục, Sếp đối chiếu bằng mắt trên bản vẽ.")
    elif luoi_local:
        for hx, i in (("doc", 0), ("ngang", 1)):
            chuan = {str(t["ten"]): t["v"] for t in luoi.get(hx) or []}
            tot = {}   # nhiều đường cùng tên (mặt cắt, chi tiết...): chỉ xét đường khớp nhất với lưới chuẩn
            for t in luoi_local.get(hx) or []:
                ten = str(t.get("ten"))
                if ten not in chuan:
                    continue
                lech = round(t["v"] + dich[i] - chuan[ten], 4)
                if ten not in tot or abs(lech) < abs(tot[ten]):
                    tot[ten] = lech
            for ten, lech in tot.items():
                kt.append({"truc": ten, "huong": hx, "lech_mm": round(lech * 1000)})
                if abs(lech) > DUNG_SAI_TRUC:
                    cb.append(f"Trục {ten} trong vùng lệch {abs(lech) * 1000:.0f} mm so với lưới chuẩn sau khi căn.")
    return kq


def ap_phep_vung(can, hqc_da_kiem, x, y):
    """Toạ độ công trình của điểm (x, y) trên bản vẽ của vùng đã căn `can` (kết quả tinh_can_vung)."""
    a = math.radians(can.get("quay") or 0.0)
    tx, ty = can["tam"]
    px, py = x - tx, y - ty
    rx, ry = px * math.cos(a) - py * math.sin(a), px * math.sin(a) + py * math.cos(a)
    return sang_toa_do_cong_trinh(hqc_da_kiem, rx + tx + can["dich"][0], ry + ty + can["dich"][1])


def kiem_tra_gan_vung(ds, hqc_da_kiem):
    """Kiểm tra bảng gán vùng: mỗi dòng {ten, tang, cau_kien, xac_nhan, can}. Trả cảnh báo cấp dự án + trạng thái từng dòng."""
    ma_tang = {d["ma"] for d in hqc_da_kiem.get("tang") or []}
    cb, dong, thay = [], [], {}
    for i, r in enumerate(ds or []):
        ten = str(r.get("ten") or f"vùng {i + 1}")
        c = []
        if not r.get("tang"):
            c.append("chưa chọn tầng")
        elif r["tang"] not in ma_tang:
            c.append(f"tầng '{r['tang']}' không có trong bảng tầng")
        if not r.get("cau_kien"):
            c.append("chưa chọn cấu kiện")
        elif r["cau_kien"] not in CAU_KIEN:
            c.append("cấu kiện không hợp lệ")
        if not (r.get("can") or {}).get("ok"):
            c.append("chưa căn vào lưới trục")
        elif not r.get("xac_nhan"):
            c.append("chưa xác nhận")
        dong.append({"ten": ten, "van_de": c, "xong": not c})
        if r.get("tang") and r.get("cau_kien"):
            k = (r["tang"], r["cau_kien"])
            thay.setdefault(k, []).append(ten)
    for (t, ck), ten_ds in thay.items():
        if len(ten_ds) > 1:
            cb.append(f"{len(ten_ds)} vùng cùng tầng {t} và cùng loại {CAU_KIEN.get(ck, ck).lower()}: {', '.join(ten_ds)}. Kiểm tra có bị gán trùng không.")
    for d in dong:
        if d["van_de"]:
            cb.append(f"{d['ten']}: {', '.join(d['van_de'])}.")
    return {"dong": dong, "canh_bao": cb, "xong": bool(dong) and all(d["xong"] for d in dong)}


# ---------- Tổng hợp theo tầng / cấu kiện và đưa về tim trục ----------
NHOM_CAU_KIEN = {"cot": "cot_vach", "vach": "cot_vach", "dam": "dam_san", "san": "dam_san", "lo_san": "dam_san",
                 "mong": "mong", "coc": "mong", "tuong": "kien_truc", "cua": "kien_truc",
                 "ong_gio": "mep", "ong_nuoc": "mep", "ong_pccc": "mep", "khay_cap": "mep"}


def ve_toa_do_chuan(can, x, y):
    """Toạ độ trên mặt bằng chuẩn của điểm (x, y) thuộc vùng đã căn `can` (chưa đổi sang gốc công trình)."""
    a = math.radians(can.get("quay") or 0.0)
    tx, ty = can["tam"]
    px, py = x - tx, y - ty
    return (px * math.cos(a) - py * math.sin(a) + tx + can["dich"][0], px * math.sin(a) + py * math.cos(a) + ty + can["dich"][1])


def _hinh_sang(hinh, ham):
    return [[[list(map(_so, ham(p[0], p[1]))) for p in vong] for vong in poly] for poly in hinh]


def _poly_shapely(poly):
    from shapely.geometry import Polygon
    try:
        p = Polygon(poly[0], poly[1:])
        return p if p.is_valid else p.buffer(0)
    except (ValueError, IndexError):
        return None


def _cao_do(loai, ts, tang):
    """(đáy, đỉnh, ghi chú) của một cấu kiện theo cao độ tầng. Thiếu số liệu thì trả None ở chỗ đó, kèm lý do."""
    z, h_tang = tang["cao_do_kc"], tang.get("chieu_cao")
    ts = ts or {}
    if loai in ("cot", "vach"):
        h = h_tang or ts.get("h_tinh") or ts.get("h")
        return (z, round(z + h, 4), "cao từ cao độ tầng lên tầng trên") if h else (z, None, "tầng trên cùng: chưa biết chiều cao")
    if loai == "dam":
        h = ts.get("h") or ((tang.get("cao_dam") or 0) / 1000 or None)
        return (round(z - h, 4), z, "mặt trên dầm = cao độ kết cấu tầng") if h else (None, z, "chưa biết chiều cao dầm")
    if loai in ("san", "lo_san"):
        t = ts.get("t") or ((tang.get("day_san") or 0) / 1000 or None)
        return (round(z - t, 4), z, "mặt trên sàn = cao độ kết cấu tầng") if t else (None, z, "chưa biết chiều dày sàn")
    if loai == "mong":
        d = ts.get("day")
        return (round(z - d, 4), z, "mặt trên móng = cao độ tầng móng") if d else (None, z, "chưa biết chiều cao móng")
    return (None, z, "")


def _kich_thuoc(g):
    """Hai cạnh của hình chữ nhật nhỏ nhất bao đối tượng (dài, rộng); không phải hình có diện tích thì rỗng."""
    if g.geom_type not in ("Polygon", "MultiPolygon") or g.area <= 0:
        return []
    r = g.minimum_rotated_rectangle
    if r.geom_type != "Polygon":
        return []
    c = list(r.exterior.coords)
    return sorted([math.dist(c[0], c[1]), math.dist(c[1], c[2])], reverse=True)


def _nhom_theo_ten(ds):
    """Sắp tên kiểu tự nhiên: C2 trước C10."""
    return sorted(ds, key=lambda d: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(d["ten"]))])


def tong_hop_cong_trinh(hqc_da_kiem, ds_vung):
    """Gom đối tượng của các mặt bằng theo Tầng -> Cấu kiện -> Đối tượng và đưa về tim trục.
    ds_vung: [{fi, ten, tang, cau_kien, xac_nhan, can, ck: [cấu kiện đã tính], coc: [cọc]}].
    Chỉ lấy đối tượng thuộc loại cấu kiện mà vùng khai báo ('khac' = lấy hết). Mỗi đối tượng có toạ độ công trình
    (gốc tại điểm gốc, chiều theo điểm hướng), toạ độ trên mặt bằng chuẩn, cao độ đáy / đỉnh, diện tích, thể tích."""
    from shapely.ops import unary_union
    tang_theo_ma = {d["ma"]: d for d in hqc_da_kiem.get("tang") or []}
    canh_bao, bo_qua, theo_tang = [], [], {}
    if not hqc_da_kiem.get("goc"):
        return {"tang": [], "canh_bao": ["Chưa có điểm gốc: chọn điểm gốc ở mục 2 trước khi tổng hợp."], "bo_qua": [], "tong": {"so_doi_tuong": 0, "so_vung": 0}}
    n_vung = 0
    for v in ds_vung or []:
        ten_v = str(v.get("ten") or "vùng")
        can, tang = v.get("can") or {}, tang_theo_ma.get(v.get("tang"))
        if not can.get("ok"):
            canh_bao.append(f"{ten_v}: chưa căn vào lưới trục, bỏ qua.")
            continue
        if not tang or tang["cao_do_kc"] is None:
            canh_bao.append(f"{ten_v}: chưa có tầng hợp lệ (hoặc tầng chưa có cao độ), bỏ qua.")
            continue
        if not v.get("xac_nhan"):
            canh_bao.append(f"{ten_v}: chưa xác nhận căn đúng, vẫn tổng hợp nhưng Sếp cần kiểm tra.")
        khai_bao = v.get("cau_kien") or "khac"
        n_vung += 1
        doi_tuong = list(v.get("ck") or [])
        coc = [{"id": c["id"], "loai": "coc", "ten": c["ten"], "layer": c.get("layer", ""), "thong_so": {"d": c.get("d")},
                "hinh": [[[[c["x"] + math.cos(k * math.pi / 8) * c["d"] / 2, c["y"] + math.sin(k * math.pi / 8) * c["d"] / 2] for k in range(16)]]],
                "canh_bao": []} for c in v.get("coc") or []]
        so_bo = so_dam_rong = 0
        for c in doi_tuong + coc:
            if c.get("loai_bo"):
                continue
            nhom = NHOM_CAU_KIEN.get(c["loai"], "khac")
            if khai_bao != "khac" and nhom != khai_bao:
                so_bo += 1
                continue
            polys = [p for p in map(_poly_shapely, c.get("hinh") or []) if p is not None and not p.is_empty]
            if not polys:
                continue
            g = unary_union(polys)
            ct = lambda x, y, can=can: ap_phep_vung(can, hqc_da_kiem, x, y)
            cx, cy = g.centroid.x, g.centroid.y
            kt = _kich_thuoc(g)
            if c["loai"] == "dam" and len(kt) >= 2 and kt[1] > BE_RONG_DAM_TOI_DA:
                so_dam_rong += 1
                continue
            z_day, z_dinh, ghi = _cao_do(c["loai"], c.get("thong_so"), tang)
            dien_tich = round(g.area, 4)
            the_tich = round(dien_tich * (z_dinh - z_day), 4) if z_day is not None and z_dinh is not None else None
            o = {"id": f"{v.get('fi')}:{c['id']}", "fi": v.get("fi"), "ma_goc": c["id"], "ten": c.get("ten") or c["id"], "loai": c["loai"],
                 "nhom": nhom, "layer": c.get("layer", ""), "vung": ten_v, "kich_thuoc": [round(x, 4) for x in kt[:2]],
                 "tam_local": [_so(cx), _so(cy)], "tam_chuan": [_so(t) for t in ve_toa_do_chuan(can, cx, cy)], "tam_ct": list(ct(cx, cy)),
                 "z_day": z_day, "z_dinh": z_dinh, "ghi_chu_cao_do": ghi, "dien_tich": dien_tich, "the_tich": the_tich,
                 "thong_so": c.get("thong_so") or {}, "canh_bao": list(c.get("canh_bao") or []),
                 "hinh_chuan": _hinh_sang([[[list(p) for p in r] for r in poly] for poly in c["hinh"]], lambda x, y, can=can: ve_toa_do_chuan(can, x, y)),
                 "hinh_ct": _hinh_sang(c["hinh"], ct)}
            theo_tang.setdefault(tang["ma"], {}).setdefault(nhom, []).append(o)
        if so_bo:
            bo_qua.append({"vung": ten_v, "so": so_bo, "ly_do": f"khác loại khai báo ({CAU_KIEN.get(khai_bao, khai_bao)})"})
        if so_dam_rong:
            bo_qua.append({"vung": ten_v, "so": so_dam_rong, "ly_do": f"hình 'dầm' rộng hơn {BE_RONG_DAM_TOI_DA} m (khung ghi chú, đường bao khung dầm)"})
    tang_ds = []
    for ma, d in sorted(tang_theo_ma.items(), key=lambda kv: kv[1]["cao_do_kc"] if kv[1]["cao_do_kc"] is not None else 1e9):
        if ma not in theo_tang:
            continue
        nhoms = []
        for ck in CAU_KIEN:
            ds = _nhom_theo_ten(theo_tang[ma].get(ck, []))
            if ds:
                nhoms.append({"cau_kien": ck, "ten": CAU_KIEN[ck], "so": len(ds), "dien_tich": round(sum(o["dien_tich"] for o in ds), 3),
                              "the_tich": round(sum(o["the_tich"] or 0 for o in ds), 3), "thieu_the_tich": sum(1 for o in ds if o["the_tich"] is None),
                              "doi_tuong": ds})
        tang_ds.append({"ma": ma, "ten": d["ten"], "loai": d["loai"], "cao_do_kc": d["cao_do_kc"], "chieu_cao": d.get("chieu_cao"),
                        "so": sum(n["so"] for n in nhoms), "nhom": nhoms})
    # đối tượng trùng nhau giữa hai vùng cùng tầng, cùng loại: cùng loại, tâm cách nhau dưới 5 cm
    for t in tang_ds:
        for n in t["nhom"]:
            vi_tri = {}
            for o in n["doi_tuong"]:
                vi_tri.setdefault((o["loai"], round(o["tam_ct"][0], 1), round(o["tam_ct"][1], 1)), []).append(o)
            trung = [o for k, ds in vi_tri.items() if len({x["vung"] for x in ds}) > 1 for o in ds]
            if trung:
                canh_bao.append(f"Tầng {t['ma']} - {n['ten']}: {len(trung)} đối tượng nằm trùng vị trí ở nhiều vùng ({', '.join(sorted({o['vung'] for o in trung}))}). Kiểm tra có vẽ lặp không.")
                for o in trung:
                    o["canh_bao"].append("Trùng vị trí với đối tượng cùng loại ở vùng khác.")
    return {"tang": tang_ds, "canh_bao": canh_bao, "bo_qua": bo_qua,
            "tong": {"so_doi_tuong": sum(t["so"] for t in tang_ds), "so_vung": n_vung, "so_tang": len(tang_ds)}}


# ---------- Tổng hợp hệ quy chiếu ----------
def kiem_tra(hqc):
    """Kiểm tra cả hệ quy chiếu người dùng đã nhập: lưới trục, điểm gốc, điểm hướng, bảng tầng.
    Trả {"luoi": {doc, ngang có thêm 'cach_goc'}, "goc": {...}, "tang": [...], "canh_bao": [...], "du": bool}."""
    hqc = hqc or {}
    luoi = {"doc": sorted([dict(t) for t in (hqc.get("luoi") or {}).get("doc") or []], key=lambda t: t["v"]),
            "ngang": sorted([dict(t) for t in (hqc.get("luoi") or {}).get("ngang") or []], key=lambda t: t["v"])}
    cb = kiem_tra_luoi(luoi)
    goc_xy = diem_giao(luoi, hqc.get("goc"))
    goc = None
    if hqc.get("goc") and not goc_xy:
        cb.append("Điểm gốc không còn nằm trên lưới trục (trục đã bị đổi tên hoặc xoá): chọn lại điểm gốc.")
    elif not hqc.get("goc"):
        cb.append("Chưa chọn điểm gốc (giao của một trục dọc và một trục ngang).")
    if goc_xy:
        goc = {"ten": ten_diem(hqc["goc"]), "diem": dict(hqc["goc"]), "x": _so(goc_xy[0]), "y": _so(goc_xy[1]), "goc_quay": 0.0, "dao_x": False, "dao_y": False}
        h2 = diem_giao(luoi, hqc.get("diem2"))
        if hqc.get("diem2") and not h2:
            cb.append("Điểm hướng không còn nằm trên lưới trục: chọn lại hoặc bỏ điểm hướng.")
        elif h2:
            dx, dy = h2[0] - goc_xy[0], h2[1] - goc_xy[1]
            if abs(dx) < 1e-6 and abs(dy) < 1e-6:
                cb.append("Điểm hướng trùng điểm gốc: chọn giao trục khác.")
            else:
                goc["goc_quay"] = round(math.degrees(math.atan2(dy, dx)), 4)
                goc["diem2"] = ten_diem(hqc["diem2"])
        for t in luoi["doc"]:
            t["cach_goc"] = _so(t["v"] - goc_xy[0])
        for t in luoi["ngang"]:
            t["cach_goc"] = _so(t["v"] - goc_xy[1])
    bt = chuan_hoa_bang_tang(hqc.get("tang"))
    if not bt["tang"]:
        cb.append("Chưa nhập bảng tầng.")
    cb += bt["canh_bao"]
    du = bool(goc and luoi["doc"] and luoi["ngang"] and bt["tang"] and not any(d["cao_do_kc"] is None for d in bt["tang"]))
    return {"luoi": luoi, "goc": goc, "tang": bt["tang"], "canh_bao": cb, "du": du}


def sang_toa_do_cong_trinh(hqc_da_kiem, x, y):
    """Đổi toạ độ bản vẽ của mặt bằng chuẩn sang toạ độ công trình (gốc tại điểm gốc, trục X theo điểm hướng)."""
    g = hqc_da_kiem.get("goc")
    if not g:
        raise ValueError("Chưa có điểm gốc.")
    a = math.radians(g.get("goc_quay") or 0.0)
    dx, dy = x - g["x"], y - g["y"]
    return _so(dx * math.cos(a) + dy * math.sin(a)), _so(-dx * math.sin(a) + dy * math.cos(a))


__all__ = ["do_luoi_truc", "kiem_tra_luoi", "diem_giao", "ten_diem", "doc_so", "chuan_hoa_bang_tang", "cao_do_goi_y",
           "kiem_tra", "sang_toa_do_cong_trinh", "LOAI_TANG", "CAU_KIEN", "goi_y_diem_vung", "tinh_can_vung",
           "ap_phep_vung", "kiem_tra_gan_vung", "tong_hop_cong_trinh", "ve_toa_do_chuan", "NHOM_CAU_KIEN"]
