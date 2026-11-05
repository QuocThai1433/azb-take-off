"""Thống kê cấu kiện từ nhiều bản vẽ.

Vai trò của từng bản vẽ trong một dự án:
- mat_bang: mặt bằng. Đếm số lượng cấu kiện theo tên (nhãn chữ), kích thước đo từ hình vẽ.
- chi_tiet: chi tiết cấu kiện. Đọc tên + kích thước ghi trong chữ ("C1 200x200", "F1 1000x1000x800").
- ghi_chu: ghi chú chung. Lấy các dòng ghi chú và nhận diện thông số hay gặp (dày sàn, mác bê tông...).

Cấu kiện trên mặt bằng chỉ ghi nhãn một vài vị trí, các cái còn lại không có nhãn. Cái nào cùng loại và
cùng kích thước với một cấu kiện đã có tên thì lấy tên đó (đánh dấu "suy ra theo kích thước").
"""
import re
from collections import Counter, defaultdict
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .dam_suy_ra import suy_dam
from .dxf_reader import cat_vung
from .takeoff import _BoTinh, _hcn, doc_nhan, thong_so_mac_dinh

TEN_LOAI = {"cot": "Cột", "dam": "Dầm", "san": "Sàn", "lo_san": "Lỗ mở sàn", "mong": "Móng", "vach": "Vách/lõi"}
DUNG_SAI_KT = 0.05  # 5%: kích thước lệch dưới mức này coi là khớp

RE_DAY = re.compile(r"(?i)(?:dày|day|t\s*=)\s*(\d+(?:[.,]\d+)?)\s*(mm|cm)?")
RE_MAC_BT = re.compile(r"(?i)\b(?:B\s?\d{2}(?:\.\d)?|M\s?\d{3})\b")
RE_THEP = re.compile(r"(?i)\b(?:CB\s?\d{3}-?[VT]?|CI{1,3}|AI{1,3}|SD\s?\d{3})\b")
RE_BAO_VE = re.compile(r"(?i)lớp\s*(?:bê\s*tông\s*)?bảo\s*vệ[^0-9]{0,20}(\d+)\s*(mm|cm)?")


def _dong_chu(ban_ve):
    """Mọi dòng chữ trong bản vẽ: (nội dung, x, y, layer). MTEXT nhiều dòng được tách ra."""
    kq = []
    for ld in ban_ve.layers.values():
        for c in ld.chu:
            for dong in re.split(r"\n|\\P", c.noi_dung):
                dong = dong.strip()
                if dong:
                    kq.append((dong, c.diem.x, c.diem.y, ld.ten))
    return kq


def _kt_mm(hcn):
    return tuple(sorted((round(v * 1000) for v in hcn), reverse=True)) if hcn else ()


def _khop(a, b):
    """a, b: tuple kích thước mm đã sắp xếp. Khớp nếu từng cạnh lệch dưới dung sai."""
    if not a or not b:
        return None
    n = min(len(a), len(b))
    return all(abs(x - y) / max(y, 1) <= DUNG_SAI_KT for x, y in zip(a[:n], b[:n]))


def _chuoi_kt(kt):
    return "x".join(str(v) for v in kt)


def doc_mat_bang(ban_ve, loai_layer, vung=None):
    """Trả danh sách cấu kiện của một mặt bằng: dict(loai, ten, nguon_ten, kt (mm), dai, dien_tich)."""
    if vung and len(vung) == 4:
        ban_ve = cat_vung(ban_ve, [float(v) for v in vung])
    ban_ve, loai_layer = suy_dam(ban_ve, loai_layer)
    bt = _BoTinh(ban_ve, loai_layer, thong_so_mac_dinh(), {})
    bt.gom_hinh()
    bt.gan_nhan()
    cks = []
    for ck in bt.ck:
        if ck["loai"] == "lo_san":
            continue
        # Hình nằm lọt trong hình khác cùng loại (cổ móng vẽ trong móng) không đếm thành cấu kiện riêng
        if any(o is not ck and o["loai"] == ck["loai"] and o["geom"].area > ck["geom"].area * 1.01
               and o["geom"].intersection(ck["geom"]).area >= 0.98 * ck["geom"].area for o in bt.ck):
            continue
        hcn = _hcn(ck["geom"])
        x0, y0, x1, y1 = ck["geom"].bounds
        nhan_kt = (ck.get("_nhan") or {}).get("kt") or []
        # Chiều cao ghi trên nhãn: dầm "b x h" -> h; cột, móng, vách "a x b x h" -> h
        cao_nhan = (nhan_kt[1] if ck["loai"] == "dam" and len(nhan_kt) >= 2 else nhan_kt[2] if len(nhan_kt) >= 3 else None)
        cks.append({
            "bb": tuple(sorted((round((x1 - x0) * 1000), round((y1 - y0) * 1000)), reverse=True)),
            "cao_nhan": round(cao_nhan * 1000) if cao_nhan else None,
            "loai": ck["loai"], "ten": ck["ten"], "nguon_ten": "nhãn" if ck["ten"] else "",
            "hcn": hcn, "dien_tich": ck["geom"].area, "chu_vi": ck["geom"].length, "nhan_kt": (ck.get("_nhan") or {}).get("kt"),
        })
    return cks, bt.canh_bao_chung


def _khoa_kt(c):
    if not c["hcn"]:
        return None
    return (c["loai"], (round(c["hcn"][1] * 1000),) if c["loai"] == "dam" else _kt_mm(c["hcn"]))


def suy_ten(tat_ca):
    """Cấu kiện chưa có tên lấy tên của cấu kiện cùng loại, cùng kích thước ở bất kỳ mặt bằng nào."""
    ten_theo_kt = defaultdict(Counter)
    for c in tat_ca:
        k = _khoa_kt(c)
        if c["ten"] and k:
            ten_theo_kt[k][c["ten"]] += 1
    for c in tat_ca:
        if c["ten"]:
            continue
        k = _khoa_kt(c)
        if k is None:
            continue
        for k2, cnt in ten_theo_kt.items():
            if k2[0] == k[0] and len(k2[1]) == len(k[1]) and all(abs(a - b) / max(b, 1) <= 0.02 for a, b in zip(k[1], k2[1])):
                c["ten"], c["nguon_ten"] = cnt.most_common(1)[0][0], "suy ra theo kích thước"
                break
    for c in tat_ca:
        if not c["ten"]:
            c["ten"], c["nguon_ten"] = "(chưa đặt tên)", "chưa có nhãn"


def doc_chi_tiet(ban_ve):
    """Tên cấu kiện -> kích thước ghi trong chi tiết. Trả (dict, danh sách dòng nguồn)."""
    kq = defaultdict(lambda: {"kt": Counter(), "day": Counter(), "dong": []})
    for dong, x, y, layer in _dong_chu(ban_ve):
        n = doc_nhan(dong)
        if not n["loai"] or not (n["kt"] or n["day"]) or not re.match(r"^[A-ZÔ]{1,3}\d", n["ten"]):
            continue
        e = kq[n["ten"]]
        e["loai"] = n["loai"]
        if n["kt"]:
            e["kt"][tuple(round(v * 1000) for v in n["kt"])] += 1
        if n["day"]:
            e["day"][round(n["day"] * 1000)] += 1
        e["dong"].append(dong)
    return kq


def doc_ghi_chu(ban_ve):
    dong = [d[0] for d in _dong_chu(ban_ve)]
    phat_hien, thay = [], set()

    def them(khoa, gia_tri, d):
        if (khoa, gia_tri, d) not in thay:
            thay.add((khoa, gia_tri, d))
            phat_hien.append({"khoa": khoa, "gia_tri": gia_tri, "dong": d})

    for d in dong:
        for m in RE_DAY.finditer(d):
            v = float(m.group(1).replace(",", "."))
            don_vi = (m.group(2) or "mm").lower()
            them("Chiều dày", f"{v:g} {don_vi}", d)
        for m in RE_MAC_BT.finditer(d):
            them("Mác bê tông", m.group(0).upper().replace(" ", ""), d)
        for m in RE_THEP.finditer(d):
            them("Cốt thép", m.group(0).upper().replace(" ", ""), d)
        m = RE_BAO_VE.search(d)
        if m:
            them("Lớp bảo vệ", f"{m.group(1)} {(m.group(2) or 'mm').lower()}", d)
    return {"dong": sorted(set(dong)), "phat_hien": phat_hien}


def thong_ke(files):
    """files: list dict(id, ten_file, vai_tro, loai_layer, vung, ban_ve)."""
    hang, canh_bao, chi_tiet, ghi_chu = [], [], {}, {}
    cks_file, tat_ca = [], []
    for f in files:
        if f["vai_tro"] != "mat_bang":
            continue
        if not any(v in TEN_LOAI or v in ("khung_dam", "o_dam") for v in f["loai_layer"].values()):
            canh_bao.append(f"{f['ten_file']}: chưa gán layer cột/dầm/móng nào nên không đếm được cấu kiện.")
            continue
        cks, cb = doc_mat_bang(f["ban_ve"], f["loai_layer"], f.get("vung"))
        canh_bao += [f"{f['ten_file']}: {c}" for c in dict.fromkeys(cb)]
        cks_file.append((f, cks))
        tat_ca += cks
    suy_ten(tat_ca)
    for f in files:
        vt, bv = f["vai_tro"], f["ban_ve"]
        if vt == "mat_bang":
            cks = next((c for ff, c in cks_file if ff is f), None)
            if cks is None:
                continue
            nhom = defaultdict(list)
            for c in cks:
                # Cấu kiện chưa có tên: tách theo kích thước / hình dạng để không trộn lẫn các hình khác nhau
                phu = (_khoa_kt(c) or ("db", c["bb"]),) if c["ten"] == "(chưa đặt tên)" else ()
                nhom[(c["loai"], c["ten"]) + phu].append(c)
            for (loai, ten, *_), ds in nhom.items():
                kts = Counter(_kt_mm(c["hcn"]) if loai != "dam" else (round(c["hcn"][1] * 1000),) if c["hcn"] else ()
                              for c in ds)
                kt = kts.most_common(1)[0][0]
                dac_biet = sum(1 for c in ds if not c["hcn"]) > len(ds) / 2
                if dac_biet:
                    mau = max((c for c in ds if not c["hcn"]), key=lambda c: c["dien_tich"])
                    dai, rong = mau["bb"]  # hình đặc biệt: lấy hộp bao
                else:
                    mau = max((c for c in ds if c["hcn"]), key=lambda c: c["hcn"][0] * c["hcn"][1])
                    dai, rong = round(mau["hcn"][0] * 1000), round(mau["hcn"][1] * 1000)
                    if loai == "dam":
                        dai = Counter(round(c["hcn"][0] * 1000) for c in ds if c["hcn"]).most_common(1)[0][0]
                cao = next((c["cao_nhan"] for c in ds if c["cao_nhan"]), None)
                hang.append({
                    "dai": dai, "rong": rong, "cao": cao, "dang": "Đặc biệt" if dac_biet else "Chữ nhật",
                    # Chu vi, diện tích của một cấu kiện (chỉ cần với hình đặc biệt, hình chữ nhật tính được từ dài x rộng)
                    "chu_vi": round(mau["chu_vi"], 3), "dien_tich": round(mau["dien_tich"], 4),
                    "file": f["ten_file"], "ten": ten, "loai": loai, "loai_ten": TEN_LOAI.get(loai, loai),
                    "so_luong": len(ds), "kt_mat_bang": kt,
                    "tong_dai": (sum(c["hcn"][0] for c in ds if c["hcn"]) if loai == "dam" else None),
                    "tong_dien_tich": sum(c["dien_tich"] for c in ds),
                    "nguon_ten": ", ".join(sorted({c["nguon_ten"] for c in ds})),
                })
        elif vt == "chi_tiet":
            for ten, e in doc_chi_tiet(bv).items():
                cu = chi_tiet.setdefault(ten, {"loai": e["loai"], "kt": Counter(), "day": Counter(), "file": set(), "dong": []})
                cu["kt"].update(e["kt"])
                cu["day"].update(e["day"])
                cu["file"].add(f["ten_file"])
                cu["dong"] += e["dong"]
        elif vt == "ghi_chu":
            ghi_chu[f["ten_file"]] = doc_ghi_chu(bv)

    # Đối chiếu kích thước mặt bằng với chi tiết
    for h in hang:
        ct = chi_tiet.get(h["ten"].upper()) or chi_tiet.get(h["ten"])
        h["kt_chi_tiet"], h["doi_chieu"] = None, ""
        if ct and ct["kt"]:
            kt_ct = ct["kt"].most_common(1)[0][0]
            h["kt_chi_tiet"] = kt_ct
            if h["cao"] is None:
                h["cao"] = kt_ct[1] if h["loai"] == "dam" and len(kt_ct) >= 2 else kt_ct[2] if len(kt_ct) >= 3 else None
            if h["loai"] == "dam":
                so = _khop((h["kt_mat_bang"][0],), (min(kt_ct),)) if h["kt_mat_bang"] else None
            else:
                so = _khop(h["kt_mat_bang"], tuple(sorted(kt_ct, reverse=True)))
            h["doi_chieu"] = {True: "Khớp chi tiết", False: "Lệch chi tiết", None: "Không so được"}[so]
            if len(ct["kt"]) > 1:
                h["doi_chieu"] += " (chi tiết có nhiều kích thước)"
        elif h["ten"] != "(chưa đặt tên)":
            h["doi_chieu"] = "Chưa có chi tiết"
    ten_co = {h["ten"].upper() for h in hang}
    def drc(loai, k):
        """Kích thước trong chi tiết thành (dài, rộng, cao). Dầm ghi b x h nên chỉ có rộng và cao."""
        if loai == "dam":
            return [None, k[0], k[1] if len(k) > 1 else None]
        return [k[0], k[1] if len(k) > 1 else None, k[2] if len(k) > 2 else None]

    chi_tiet_ds = [{"ten": t, "drc": [drc(e["loai"], k) for k, _ in e["kt"].most_common()], "loai": e["loai"], "loai_ten": TEN_LOAI.get(e["loai"], e["loai"]),
                    "kt": [list(k) for k, _ in e["kt"].most_common()], "day": [d for d, _ in e["day"].most_common()],
                    "file": sorted(e["file"]), "co_tren_mat_bang": t.upper() in ten_co}
                   for t, e in sorted(chi_tiet.items())]

    # Tổng hợp theo tên trên mọi mặt bằng
    tong = {}
    for h in hang:
        khoa_tong = (h["loai"], h["ten"]) + ((h["dai"], h["rong"], h["dang"]) if h["ten"] == "(chưa đặt tên)" else ())
        t = tong.setdefault(khoa_tong, {"ten": h["ten"], "loai": h["loai"], "loai_ten": h["loai_ten"],
                                                    "so_luong": 0, "so_luong_max": 0, "so_mat_bang": 0, "kt_mat_bang": h["kt_mat_bang"],
                                                    "dai": h["dai"], "rong": h["rong"], "cao": h["cao"], "dang": h["dang"],
                                                    "chu_vi": h["chu_vi"], "dien_tich": h["dien_tich"],
                                                    "kt_chi_tiet": h["kt_chi_tiet"], "doi_chieu": h["doi_chieu"],
                                                    "tong_dai": 0.0, "tong_dien_tich": 0.0, "file": []})
        t["so_luong"] += h["so_luong"]
        t["so_luong_max"] = max(t["so_luong_max"], h["so_luong"])
        t["so_mat_bang"] += 1
        if t["cao"] is None:
            t["cao"] = h["cao"]
        t["tong_dai"] += h["tong_dai"] or 0
        t["tong_dien_tich"] += h["tong_dien_tich"]
        t["file"].append(h["file"])
    thu_tu = list(TEN_LOAI)
    tong_hop = sorted(tong.values(), key=lambda x: (thu_tu.index(x["loai"]) if x["loai"] in thu_tu else 9, x["ten"]))
    for t in tong_hop:
        if t["so_mat_bang"] > 1:
            canh_bao.append(
                f"{t['ten']} xuất hiện trên {t['so_mat_bang']} mặt bằng (tổng {t['so_luong']}, nhiều nhất một mặt bằng {t['so_luong_max']}). "
                "Cấu kiện vẽ lặp ở nhiều mặt bằng (móng, định vị cột, dầm...) thì lấy số ở cột 'Tối đa 1 MB', đừng cộng.")
    if any(h["ten"] == "(chưa đặt tên)" for h in hang):
        canh_bao.append("Có cấu kiện chưa có nhãn và không trùng kích thước với cấu kiện nào đã có tên.")
    for c in chi_tiet_ds:
        if not c["co_tren_mat_bang"] and hang:
            canh_bao.append(f"Chi tiết {c['ten']} chưa thấy trên mặt bằng đã thêm (hoặc nhãn trên mặt bằng ghi khác).")
    return {"tong_hop": tong_hop, "theo_mat_bang": hang, "chi_tiet": chi_tiet_ds, "ghi_chu": ghi_chu,
            "canh_bao": canh_bao}


def xuat_excel(kq, du_an=""):
    wb = Workbook()
    nen = PatternFill("solid", fgColor="1F4E78")
    trang = Font(bold=True, color="FFFFFF")

    def tieu_de(ws, hang, cot):
        for i, c in enumerate(cot, 1):
            x = ws.cell(hang, i, c)
            x.fill, x.font = nen, trang
            x.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def kt(v):
        return _chuoi_kt(v) if v else ""

    ws = wb.active
    ws.title = "TONG HOP"
    ws["A1"] = "THỐNG KÊ CẤU KIỆN"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Dự án: {du_an}"
    tieu_de(ws, 4, ["STT", "Tên cấu kiện", "Loại", "Số lượng (cộng các mặt bằng)", "Tối đa trên 1 mặt bằng", "Dài (mm)", "Rộng (mm)",
                    "Cao (mm)", "Dạng", "Chu vi (m) - hình đặc biệt", "Diện tích (m²) - hình đặc biệt", "Kích thước trong chi tiết (mm)",
                    "Đối chiếu", "Tổng dài dầm (m)", "Tổng diện tích mặt bằng (m²)", "Bản vẽ"])
    for i, h in enumerate(kq["tong_hop"], 1):
        db = h["dang"] == "Đặc biệt"
        ws.append([i, h["ten"], h["loai_ten"], h["so_luong"], h["so_luong_max"], h["dai"], h["rong"], h["cao"], h["dang"],
                   h["chu_vi"] if db else None, h["dien_tich"] if db else None, kt(h["kt_chi_tiet"]),
                   h["doi_chieu"], round(h["tong_dai"], 3) if h["tong_dai"] else None, round(h["tong_dien_tich"], 3),
                   ", ".join(sorted(set(h["file"])))])
    for i, w in enumerate([6, 22, 12, 14, 14, 10, 10, 10, 11, 16, 18, 24, 26, 16, 20, 40], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws2 = wb.create_sheet("THEO MAT BANG")
    tieu_de(ws2, 1, ["Bản vẽ", "Tên cấu kiện", "Loại", "Số lượng", "Dài (mm)", "Rộng (mm)", "Cao (mm)", "Dạng",
                     "Chu vi (m)", "Diện tích (m²)", "Nguồn tên", "Đối chiếu chi tiết"])
    for h in kq["theo_mat_bang"]:
        db = h["dang"] == "Đặc biệt"
        ws2.append([h["file"], h["ten"], h["loai_ten"], h["so_luong"], h["dai"], h["rong"], h["cao"], h["dang"],
                    h["chu_vi"] if db else None, h["dien_tich"] if db else None, h["nguon_ten"], h["doi_chieu"]])
    for i, w in enumerate([40, 22, 12, 10, 10, 10, 10, 11, 12, 14, 28, 30], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w

    ws3 = wb.create_sheet("CHI TIET")
    tieu_de(ws3, 1, ["Tên cấu kiện", "Loại", "Dài (mm)", "Rộng (mm)", "Cao (mm)", "Chiều dày (mm)", "Có trên mặt bằng", "Bản vẽ"])
    for c in kq["chi_tiet"]:
        for d in (c["drc"] or [[None, None, None]]):
            ws3.append([c["ten"], c["loai_ten"], d[0], d[1], d[2], "; ".join(str(x) for x in c["day"]),
                        "Có" if c["co_tren_mat_bang"] else "Không", ", ".join(c["file"])])
    for i, w in enumerate([20, 12, 10, 10, 10, 16, 16, 40], 1):
        ws3.column_dimensions[get_column_letter(i)].width = w

    ws4 = wb.create_sheet("GHI CHU")
    tieu_de(ws4, 1, ["Bản vẽ", "Thông số phát hiện", "Giá trị", "Dòng ghi chú"])
    for ten, g in kq["ghi_chu"].items():
        for p in g["phat_hien"]:
            ws4.append([ten, p["khoa"], p["gia_tri"], p["dong"]])
    for i, w in enumerate([40, 20, 16, 80], 1):
        ws4.column_dimensions[get_column_letter(i)].width = w

    if kq["canh_bao"]:
        ws5 = wb.create_sheet("CANH BAO")
        for c in kq["canh_bao"]:
            ws5.append([c])
        ws5.column_dimensions["A"].width = 120
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
