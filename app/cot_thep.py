"""Cốt thép tính từ BẢNG THỐNG KÊ THÉP (khác với cốt thép ước tính theo hàm lượng kg/m³ ở các công cụ tính).

Nguyên tắc giống phần còn lại của app: công cụ ĐỌC và TÍNH, người duyệt.
  - Đọc bảng từ Excel/CSV, hoặc từ bảng chữ trong bản vẽ CAD (người dùng kéo khung quanh bảng).
  - Khối lượng một dòng = số cấu kiện × số thanh × chiều dài × đơn trọng; đơn trọng = 0,00617 × Ø² (kg/m).
  - Nếu bảng có sẵn cột khối lượng thì ĐỐI CHIẾU với số công cụ tính, lệch quá ngưỡng thì cảnh báo, không tự sửa.
  - Đối chiếu hàm lượng kg/m³ với bê tông đã bóc để bắt lỗi đơn vị (mm lẫn m) hoặc bảng thiếu dòng.

Bộ đọc bảng chưa được kiểm chứng trên bảng thép thật của đơn vị thiết kế nào (bản vẽ mẫu hiện có không chứa bảng
thép); đã thử trên bảng dựng theo các cách trình bày thường gặp. Luôn kiểm tra bảng đã đọc trước khi dùng.
"""
import csv
import io
import re
import statistics
import unicodedata

HE_SO_DON_TRONG = 0.00617       # kg/m trên mm²: d² × 0,00617 (thép tròn, khối lượng riêng 7850 kg/m³)
DK_HOP_LE = (4, 50)             # mm
NGUONG_LECH_KL = 0.02           # bảng ghi khối lượng lệch số tính quá 2% thì cảnh báo
HAM_LUONG_HOP_LY = (40.0, 250.0)  # kg/m³ bê tông, nhà dân dụng thông thường; ngoài khoảng chỉ cảnh báo
TOI_DA_DONG_TIEU_DE = 40        # tìm dòng tiêu đề trong chừng này dòng đầu


def don_trong(d_mm):
    """Đơn trọng thép tròn (kg/m) theo đường kính (mm)."""
    return HE_SO_DON_TRONG * d_mm * d_mm


def _bo_dau(s):
    s = unicodedata.normalize("NFD", str(s if s is not None else "").replace("đ", "d").replace("Đ", "D"))
    return re.sub(r"\s+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn").lower()).strip()


# Cột -> các cụm từ nhận diện trong tiêu đề (đã bỏ dấu, chữ thường). Thứ tự dò trong _map_cot quan trọng.
TIEU_DE = [
    ("tong_dai", [r"tong chieu dai", r"tong dai", r"total length"]),
    ("kl", [r"khoi luong", r"trong luong", r"weight", r"^kl\b", r"\bkg\b"]),
    ("duong_kinh", [r"duong kinh", r"^phi\b", r"^d\b", r"^dk\b", r"\bdia", r"^[øφþ]"]),
    ("so_ck", [r"so cau kien", r"sl ck", r"so ck", r"so cai"]),
    ("so_thanh", [r"so thanh", r"sl thanh", r"so luong thanh", r"so luong", r"^sl\b", r"^n\b", r"quantity", r"^qty"]),
    ("chieu_dai", [r"chieu dai", r"^dai\b", r"length", r"^l\b", r"dai 1 thanh"]),
    ("ky_hieu", [r"ten cau kien", r"cau kien", r"ky hieu cau kien", r"vi tri", r"ten ck", r"member", r"mark", r"ky hieu", r"^ten\b"]),
    ("hinh_dang", [r"hinh dang", r"shape", r"dang thanh"]),
    ("mac", [r"mac thep", r"^mac\b", r"nhom thep", r"loai thep", r"grade"]),
    ("stt", [r"^stt\b", r"^tt\b", r"^no\.?$"]),
]
RE_TONG = re.compile(r"^(tong|cong|total|sum)\b|tong cong")


def _so(v):
    """Đọc số từ ô: 12,5 / 1.250,5 / 1,250.5 / '16' / 12.5. Không đọc được thì None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(" ", "").replace(" ", "")
    s = re.sub(r"[^\d.,\-]", "", s)
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:   # dấu nào đứng sau là dấu thập phân
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:              # kiểu Việt Nam: một dấu phẩy là thập phân (12,5); nhiều dấu phẩy là phân cách nghìn
        s = s.replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3}){2,}", s):    # 1.250.000: phân cách nghìn (một nhóm như 1.250 vẫn hiểu là thập phân)
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _duong_kinh(v):
    """'Ø16', 'Φ16', 'D16', 'phi 16', 16 -> 16.0 (mm), ngoài khoảng hợp lý thì None."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        d = float(v)
    else:
        m = re.search(r"(\d{1,2}(?:[.,]\d)?)", str(v or ""))
        if not m:
            return None
        d = float(m.group(1).replace(",", "."))
    return d if DK_HOP_LE[0] <= d <= DK_HOP_LE[1] else None


def _map_cot(hang):
    """Ánh xạ cột -> trường từ một dòng tiêu đề. Trả (map, don_vi_dai) hoặc ({}, None)."""
    kq, dung, don_vi = {}, set(), None
    for j, o in enumerate(hang):
        t = _bo_dau(o)
        if not t:
            continue
        for truong, mau in TIEU_DE:
            if truong in kq.values() or j in dung:
                continue
            if any(re.search(m, t) for m in mau):
                kq[j] = truong
                dung.add(j)
                if truong == "chieu_dai":
                    if re.search(r"\(?\bmm\b\)?", t):
                        don_vi = "mm"
                    elif re.search(r"\(\s*cm\s*\)", t):
                        don_vi = "cm"
                    elif re.search(r"\(\s*m\s*\)", t):
                        don_vi = "m"
                break
    return kq, don_vi


def _tim_tieu_de(luoi):
    tot = (0, None, None, None)
    for i, hang in enumerate(luoi[:TOI_DA_DONG_TIEU_DE]):
        m, dv = _map_cot(hang)
        diem = len(set(m.values()) & {"duong_kinh", "so_thanh", "chieu_dai", "tong_dai", "kl", "ky_hieu"})
        if diem > tot[0] and "duong_kinh" in m.values():
            tot = (diem, i, m, dv)
    return tot if tot[0] >= 3 else (0, None, None, None)


def phan_tich_luoi(luoi):
    """Biến một lưới ô (danh sách dòng, mỗi dòng là danh sách ô) thành các dòng thép.

    Trả {dong, canh_bao, tong_ban_ve_kg, dong_tieu_de}. Mỗi dòng: stt, ky_hieu, duong_kinh (mm), so_ck, so_thanh,
    chieu_dai (m), kl_ban_ve (kg hoặc None), tong_dai_ban_ve (m hoặc None), hinh_dang, mac, nguon_dong (số dòng trong bảng).
    """
    canh_bao = []
    diem, i0, cot, don_vi = _tim_tieu_de(luoi)
    if i0 is None:
        return {"dong": [], "canh_bao": ["Không tìm thấy dòng tiêu đề của bảng thép (cần có cột đường kính Ø, số thanh, chiều dài...)."],
                "tong_ban_ve_kg": None, "dong_tieu_de": None}
    thieu = [t for t in ("duong_kinh", "so_thanh", "chieu_dai") if t not in cot.values()]
    if "tong_dai" in cot.values():
        thieu = [t for t in thieu if t != "chieu_dai" or "so_thanh" not in cot.values()]
    if thieu and not ("tong_dai" in cot.values() and "duong_kinh" in cot.values()):
        canh_bao.append("Bảng thiếu cột: " + ", ".join({"duong_kinh": "đường kính", "so_thanh": "số thanh", "chieu_dai": "chiều dài"}[t] for t in thieu)
                        + ". Các dòng không đủ dữ liệu sẽ bị bỏ qua.")
    ngc = {v: k for k, v in cot.items()}
    tho = []
    tong_bv = None
    ky_hieu_truoc = ""
    for i in range(i0 + 1, len(luoi)):
        hang = luoi[i]
        if not any(str(o or "").strip() for o in hang):
            continue
        dau = _bo_dau(" ".join(str(o) for o in hang[:3] if o is not None))
        if RE_TONG.search(dau):
            kl = _so(hang[ngc["kl"]]) if "kl" in ngc and ngc["kl"] < len(hang) else None
            if kl is None:   # tổng có thể nằm ở ô số cuối dòng
                so = [x for x in (_so(o) for o in hang) if x is not None]
                kl = so[-1] if so else None
            tong_bv = kl if kl is not None else tong_bv
            continue

        def o(truong):
            j = ngc.get(truong)
            return hang[j] if j is not None and j < len(hang) else None

        d = _duong_kinh(o("duong_kinh"))
        if d is None:
            if any(_so(x) is not None for x in hang):
                canh_bao.append(f"Dòng {i + 1} bị bỏ qua: không đọc được đường kính ('{o('duong_kinh')}').")
            continue
        kh = str(o("ky_hieu") or "").strip() or ky_hieu_truoc      # ô gộp: dòng dưới dùng lại ký hiệu của dòng trên
        ky_hieu_truoc = kh
        tho.append({"stt": o("stt"), "ky_hieu": kh, "duong_kinh": d, "so_ck": _so(o("so_ck")) or 1.0,
                    "so_thanh": _so(o("so_thanh")), "dai_tho": _so(o("chieu_dai")), "tong_dai_tho": _so(o("tong_dai")),
                    "kl_ban_ve": _so(o("kl")), "hinh_dang": str(o("hinh_dang") or "").strip(),
                    "mac": str(o("mac") or "").strip(), "nguon_dong": i + 1})
    # Đơn vị chiều dài: tiêu đề ghi rõ thì theo tiêu đề, không thì đoán theo độ lớn
    gia_tri = [r["dai_tho"] for r in tho if r["dai_tho"]]
    he = {"mm": 0.001, "cm": 0.01, "m": 1.0}.get(don_vi)
    if he is None and gia_tri:
        he = 0.001 if statistics.median(gia_tri) > 100 else 1.0
        canh_bao.append(f"Tiêu đề không ghi đơn vị chiều dài; đoán là {'mm' if he == 0.001 else 'm'} theo độ lớn số liệu (trung vị {statistics.median(gia_tri):g}). Kiểm tra lại.")
    he = he or 1.0
    dong = []
    for r in tho:
        dai = r["dai_tho"] * he if r["dai_tho"] else None
        tong_dai_bv = r["tong_dai_tho"] * he if r["tong_dai_tho"] else None
        so_thanh = r["so_thanh"]
        if dai is None and tong_dai_bv and so_thanh:
            dai = tong_dai_bv / (so_thanh * r["so_ck"])          # bảng chỉ ghi tổng chiều dài
        if dai is None and tong_dai_bv and not so_thanh:
            dai, so_thanh = tong_dai_bv, 1.0
        if not dai or not so_thanh:
            canh_bao.append(f"Dòng {r['nguon_dong']} ({r['ky_hieu'] or '?'}, Ø{r['duong_kinh']:g}) bị bỏ qua: thiếu số thanh hoặc chiều dài.")
            continue
        dong.append({"stt": r["stt"], "ky_hieu": r["ky_hieu"], "duong_kinh": r["duong_kinh"], "so_ck": r["so_ck"],
                     "so_thanh": so_thanh, "chieu_dai": round(dai, 4), "kl_ban_ve": r["kl_ban_ve"],
                     "tong_dai_ban_ve": round(tong_dai_bv, 3) if tong_dai_bv else None,
                     "hinh_dang": r["hinh_dang"], "mac": r["mac"], "nguon_dong": r["nguon_dong"]})
    if not dong:
        canh_bao.append("Không có dòng thép hợp lệ nào trong bảng.")
    return {"dong": dong, "canh_bao": canh_bao, "tong_ban_ve_kg": tong_bv, "dong_tieu_de": i0 + 1}


# ---------- đọc từ file ----------
def doc_excel_csv(du_lieu, ten_file, ten_sheet=None):
    """Đọc bảng thép từ .xlsx/.xlsm/.csv. Xlsx nhiều sheet: lấy sheet đầu tiên có bảng thép (hoặc sheet được chỉ định)."""
    duoi = ten_file.lower().rsplit(".", 1)[-1]
    if duoi == "csv":
        van_ban = du_lieu.decode("utf-8-sig", errors="replace")
        dau = ";" if van_ban.count(";") > van_ban.count(",") else ("\t" if van_ban.count("\t") > van_ban.count(",") else ",")
        return phan_tich_luoi(list(csv.reader(io.StringIO(van_ban), delimiter=dau)))
    if duoi not in ("xlsx", "xlsm"):
        raise ValueError("Chỉ đọc file .xlsx, .xlsm hoặc .csv.")
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(du_lieu), data_only=True, read_only=True)
    except Exception as ex:
        raise ValueError(f"Không mở được file Excel: {ex}")
    ten = [ten_sheet] if ten_sheet else wb.sheetnames
    ket = None
    for t in ten:
        if t not in wb.sheetnames:
            raise ValueError(f"Không có sheet '{t}'.")
        luoi = [list(r) for r in wb[t].iter_rows(values_only=True)]
        kq = phan_tich_luoi(luoi)
        kq["sheet"] = t
        if kq["dong"]:
            return kq
        ket = ket or kq
    return ket


# ---------- đọc từ bản vẽ CAD ----------
def doc_bang_cad(ban_ve, khung):
    """Đọc bảng thép dựng bằng chữ trong bản vẽ: gom chữ trong khung (x0, y0, x1, y1; mét) thành lưới.

    Dòng = các chữ cùng cao độ; cột = theo vị trí các ô trong dòng tiêu đề (ranh giới là trung điểm giữa hai tiêu đề kề nhau).
    Bảng vẽ bằng nét và chữ rời nhau đọc được nếu chữ mỗi cột canh thẳng theo cột.
    """
    x0, y0, x1, y1 = min(khung[0], khung[2]), min(khung[1], khung[3]), max(khung[0], khung[2]), max(khung[1], khung[3])
    chu = [c for ld in ban_ve.layers.values() for c in ld.chu if x0 <= c.diem.x <= x1 and y0 <= c.diem.y <= y1 and c.noi_dung.strip()]
    if len(chu) < 6:
        return {"dong": [], "canh_bao": [f"Khung chỉ có {len(chu)} chữ, quá ít để là bảng thép. Kéo khung rộng hơn, trùm cả dòng tiêu đề."],
                "tong_ban_ve_kg": None, "dong_tieu_de": None}
    cao = statistics.median([c.cao for c in chu if c.cao > 0] or [0.2])
    dung_sai = 0.6 * cao
    chu.sort(key=lambda c: -c.diem.y)
    hang, hien = [], []
    for c in chu:
        if hien and abs(c.diem.y - hien[0].diem.y) > dung_sai:
            hang.append(hien)
            hien = []
        hien.append(c)
    if hien:
        hang.append(hien)
    for h in hang:
        h.sort(key=lambda c: c.diem.x)
    # Dòng tiêu đề: dòng có nhiều ô khớp từ khóa nhất
    tot, i_td, cot_td = 0, None, None
    for i, h in enumerate(hang):
        m, _ = _map_cot([c.noi_dung for c in h])
        diem = len(set(m.values()) & {"duong_kinh", "so_thanh", "chieu_dai", "tong_dai", "kl", "ky_hieu"})
        if diem > tot:
            tot, i_td, cot_td = diem, i, h
    if tot < 3:
        return {"dong": [], "canh_bao": ["Không nhận ra dòng tiêu đề bảng thép trong khung (cần chữ Ø/Đường kính, Số thanh, Chiều dài...)."],
                "tong_ban_ve_kg": None, "dong_tieu_de": None}
    xs = [c.diem.x for c in cot_td]
    bien = [(xs[k] + xs[k + 1]) / 2 for k in range(len(xs) - 1)]

    def cot_cua(x):
        return sum(1 for b in bien if x > b)

    luoi = []
    for h in hang[i_td:]:
        o = [""] * len(xs)
        for c in h:
            k = cot_cua(c.diem.x)
            o[k] = (o[k] + " " + c.noi_dung.strip()).strip()
        luoi.append(o)
    # Tiêu đề hai dòng: dòng ngay dưới tiêu đề chỉ có đơn vị "(mm)", "(m)" thì ghép vào tiêu đề cột
    if len(luoi) > 1 and all(not re.search(r"\d{2,}", x) and (not x or re.fullmatch(r"\(?\s*(mm|cm|m|kg)\s*\)?", x.strip().lower())) for x in luoi[1]):
        luoi[0] = [(a + " " + b).strip() for a, b in zip(luoi[0], luoi[1])]
        luoi.pop(1)
    kq = phan_tich_luoi(luoi)
    kq["canh_bao"].insert(0, "Bảng đọc từ chữ trong bản vẽ CAD: kiểm tra từng dòng với bản vẽ (ô chữ bị lệch cột sẽ đọc sai).")
    return kq


# ---------- tính ----------
def tinh(dong, loai_bo=(), bt_m3=None, nguong_lech=NGUONG_LECH_KL):
    """Tính khối lượng thép từ các dòng đã đọc.

    Trả: dong (kèm don_trong, tong_dai, kl, lech), theo_phi, theo_cau_kien, tong_kg, canh_bao, doi_chieu (ham_luong nếu có bt_m3).
    """
    loai_bo = set(loai_bo or [])
    out, canh_bao = [], []
    for i, r in enumerate(dong):
        if i in loai_bo:
            continue
        dt = don_trong(r["duong_kinh"])
        tong_dai = r.get("so_ck", 1.0) * r["so_thanh"] * r["chieu_dai"]
        kl = tong_dai * dt
        lech = None
        if r.get("kl_ban_ve"):
            lech = (kl - r["kl_ban_ve"]) / r["kl_ban_ve"]
            if abs(lech) > nguong_lech:
                canh_bao.append(f"Dòng {r.get('nguon_dong', i + 1)} ({r.get('ky_hieu') or '?'}, Ø{r['duong_kinh']:g}): bảng ghi {r['kl_ban_ve']:.1f} kg, "
                                f"công cụ tính {kl:.1f} kg (lệch {lech:+.1%}). Kiểm tra số thanh, chiều dài hoặc đơn vị.")
        out.append({**r, "chi_so": i, "don_trong": round(dt, 4), "tong_dai": round(tong_dai, 3), "kl": kl, "lech": lech})
    theo_phi, theo_ck = {}, {}
    for r in out:
        p = theo_phi.setdefault(r["duong_kinh"], {"duong_kinh": r["duong_kinh"], "tong_dai": 0.0, "kl": 0.0})
        p["tong_dai"] += r["tong_dai"]
        p["kl"] += r["kl"]
        c = theo_ck.setdefault(r["ky_hieu"] or "(không tên)", {"ky_hieu": r["ky_hieu"] or "(không tên)", "kl": 0.0})
        c["kl"] += r["kl"]
    tong = sum(r["kl"] for r in out)
    kq = {"dong": out, "theo_phi": sorted(theo_phi.values(), key=lambda p: p["duong_kinh"]),
          "theo_cau_kien": list(theo_ck.values()), "tong_kg": tong, "canh_bao": canh_bao, "doi_chieu": None}
    if bt_m3 and bt_m3 > 0:
        hl = tong / bt_m3
        thap, cao = HAM_LUONG_HOP_LY
        kq["doi_chieu"] = {"bt_m3": bt_m3, "thep_kg": tong, "ham_luong": hl, "hop_ly": thap <= hl <= cao}
        if not thap <= hl <= cao:
            kq["canh_bao"].append(f"Hàm lượng thép = {hl:.0f} kg/m³ bê tông, ngoài khoảng thường gặp {thap:.0f}–{cao:.0f}. "
                                  "Có thể bảng thép thiếu dòng, lẫn đơn vị (mm/m), hoặc bê tông bóc chưa đủ cấu kiện của bảng này.")
    return kq
