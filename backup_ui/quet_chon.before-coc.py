"""Quét chọn trên bản vẽ để bóc theo công cụ (móng, đà kiềng, cột...): đọc ký hiệu, phân loại, gom nhóm, đọc chi tiết.

Bước 1, quét chọn mặt bằng: người dùng kéo khung chọn các hình trên mặt bằng. Với từng hình, công cụ tìm ký hiệu
(M1, F2, C1, DK1...) ở bên cạnh hoặc bên trong, rồi quyết định hình đó là móng, cột, đà kiềng... theo thứ tự tin cậy:

1. Nhãn chữ gần hình nhất (chỉ cần nhãn đọc được là đủ, không phụ thuộc layer).
2. Quan hệ hình học: hình bao quanh một hình nhỏ hơn là móng, hình nhỏ nằm trong nó là cột/cổ cột.
   Đây là chỗ mặt bằng móng hay bị nhầm: cột vẽ trong móng, cùng layer hoặc layer cột.
3. Tên layer.
4. Mặc định theo công cụ đang dùng (đánh dấu "chưa chắc").

Các hình cùng loại, cùng ký hiệu gom thành một nhóm, mỗi nhóm có số lượng n và kích thước trung bình a, b, S, P, L
của một cái; đúng các biến mà công thức trong cong_cu.py dùng. Hình vẽ trùng (hatch chồng polyline) chỉ tính một.

Bước 2, quét chọn chi tiết: đọc chữ trong khung chọn để lấy kích thước theo ký hiệu ("M1 1500x1500x400", "h=400").
Con số rời trong chi tiết được trả về làm danh sách ứng viên để người dùng bấm chọn.
"""
import math
import re
from collections import Counter, defaultdict

from shapely import STRtree
from shapely.geometry import Point

from . import config
from .takeoff import _hcn, doc_nhan

# Tiền tố ký hiệu -> loại cấu kiện
TIEN_TO = {
    "mong": {"M", "MĐ", "MD", "F", "FM", "PC"},
    "cot": {"C", "K", "CL"},
    "da_kieng": {"DK", "ĐK", "GM", "GK", "DG", "ĐG", "GB"},
    "dam": {"D", "B", "DP", "DC", "DS", "DM"},
    "san": {"S", "Ô"},
}
RE_KY_HIEU = re.compile(r"^([A-ZĐÔ]{1,3})[-_.]?(\d{1,2}[A-Z]?(?:[-.]\d{1,2})?)$")
RE_TACH = re.compile(r"[\s()\[\]{}:;,=/]+")
# Cao độ ghi trong chi tiết: "-1.700", "+0.000", "±0.000", "COTE -1.500" (bắt buộc có dấu để khỏi nhầm với kích thước)
RE_CAO_DO = re.compile(r"^\(?\s*(?:(?:COTE|CỐT|CÓT|CĐ|CD)\s*[:=]?\s*)?([+\-−±])\s*(\d{1,3})[.,](\d{1,3})\s*m?\s*\)?$", re.I)
RE_SO_RIENG = re.compile(r"^\s*(\d{2,5})(?:[.,](\d{1,3}))?\s*$")
# Gợi ý loại theo tên layer cho loại mà layer_map.yaml chưa có
GOI_Y_LAYER = [
    ("da_kieng", re.compile(r"da[_ -]?kieng|đà[_ -]?kiềng|giang[_ -]?mong|giằng|grade[_ -]?beam|tie[_ -]?beam|(^|[-_ ])(gb|dk)([-_ ]|$)", re.I)),
]
NGUON_DUONG = {"da_kieng", "dam", "khac"}  # công cụ lấy cả đường hở (tim dầm); công cụ khác chỉ lấy hình kín
LOAI_LAYER_DUNG = ("mong", "cot", "dam", "san")
TEN_LOAI = {"mong": "Móng", "cot": "Cột", "da_kieng": "Đà kiềng", "dam": "Dầm", "san": "Sàn", "khac": "Khác"}

DIEN_TICH_NHO = 0.02  # m2: hình kín nhỏ hơn mức này không nhãn là nét chi tiết, không phải cấu kiện
PHU_KIN = 0.95        # hai hình chồng nhau từ 95% diện tích hình nhỏ và gần bằng nhau coi là vẽ trùng
TI_LE_TRONG = 0.6     # hình nằm trong hình khác và nhỏ hơn 60% diện tích thì là hình bên trong
DUNG_SAI = 0.05       # kích thước nhãn lệch hình vẽ quá mức này thì cảnh báo
DUNG_SAI_SUY_RA = 0.02


# ---------- Đọc ký hiệu ----------
def loai_cua_tien_to(tien_to):
    for loai, ds in TIEN_TO.items():
        if tien_to in ds:
            return loai
    return None


def doc_ky_hieu(dong):
    """Ký hiệu đầu tiên trong một dòng chữ: {'ky_hieu': 'M1', 'loai': 'mong', 'kt': [...], 'day': ...} hoặc None."""
    s = re.sub(r"^\d+\s*\.\s*(?=[A-Za-zĐÔđô])", "", dong.strip())  # tiền tố tầng "1.M1"
    for tok in RE_TACH.split(s.upper()):
        tok = tok.strip(".-_")
        m = RE_KY_HIEU.match(tok)
        if not m:
            continue
        loai = loai_cua_tien_to(m.group(1))
        if loai:
            n = doc_nhan(s)
            return {"ky_hieu": tok, "loai": loai, "kt": n["kt"], "day": n["day"]}
    return None


def _dong_chu(ban_ve, ptr=None):
    """(dòng chữ, x, y, layer) của mọi chữ trong layer đang bật; ptr là hộp (x0, y0, x1, y1) để lọc."""
    for ld in ban_ve.layers.values():
        if ld.tat:
            continue
        for c in ld.chu:
            x, y = c.diem.x, c.diem.y
            if ptr and not (ptr[0] <= x <= ptr[2] and ptr[1] <= y <= ptr[3]):
                continue
            for dong in re.split(r"\n|\\P", c.noi_dung):
                dong = dong.strip()
                if dong:
                    yield dong, x, y, ld.ten


def _loai_theo_layer(ten):
    for loai, mau in GOI_Y_LAYER:
        if mau.search(ten):
            return loai
    loai = config.goi_y_loai_layer(ten)
    return loai if loai in LOAI_LAYER_DUNG else None


# ---------- Bước 1: quét chọn mặt bằng ----------
def _doi_tuong(ban_ve, chon, lay_net):
    ob = []
    for ten, sel in chon.items():
        ld = ban_ve.layers.get(ten)
        if ld is None:
            continue
        for i in sel.get("h", []):
            if 0 <= i < len(ld.hinh_kin):
                ob.append({"ten": ten, "k": "hinh", "i": i, "geom": ld.hinh_kin[i].geom, "nguon": ld.hinh_kin[i].nguon})
        for i in (sel.get("n", []) if lay_net else []):
            if 0 <= i < len(ld.net_ho):
                ob.append({"ten": ten, "k": "net", "i": i, "geom": ld.net_ho[i], "nguon": "Đường hở"})
    return ob


def _bo_trung(ob, dien_tich_min):
    """Bỏ hình quá nhỏ và hình vẽ trùng (hatch chồng polyline). Trả (danh sách giữ lại, số hình trùng đã bỏ)."""
    ob = [o for o in ob if o["k"] == "net" or o["geom"].area >= dien_tich_min]
    hinh = [o for o in ob if o["k"] == "hinh"]
    bo = set()
    if hinh:
        cay = STRtree([o["geom"] for o in hinh])
        for a, o in enumerate(hinh):
            if a in bo:
                continue
            for b in cay.query(o["geom"]):
                if b <= a or b in bo:
                    continue
                g, h = o["geom"], hinh[b]["geom"]
                nho, lon = min(g.area, h.area), max(g.area, h.area)
                if nho > 0 and nho / lon >= 0.9 and g.intersection(h).area >= PHU_KIN * nho:
                    bo.add(b)
    giu = [o for o in ob if o["k"] == "net"] + [o for a, o in enumerate(hinh) if a not in bo]
    return giu, len(bo)


def _gan_nhan(ob, nhan, d_max):
    """Mỗi nhãn gán cho hình gần nhất; mỗi hình lấy nhãn gần nhất. Trả {id(hình): (khoảng cách, nhãn, nhắc)}."""
    ung = defaultdict(list)
    if not ob:
        return {}
    for n in nhan:
        p = Point(n["x"], n["y"])
        kc = sorted(((o["geom"].distance(p), j) for j, o in enumerate(ob)), key=lambda t: t[0])
        d0 = kc[0][0]
        if d0 > d_max:
            continue
        # Nhãn nằm trong nhiều hình lồng nhau (khoảng cách đều 0): nhãn móng về hình lớn nhất, nhãn khác về hình nhỏ nhất
        hoa = [j for d, j in kc if d <= 1e-9]
        if len(hoa) > 1:
            j0 = max(hoa, key=lambda j: ob[j]["geom"].area) if n["loai"] == "mong" else min(hoa, key=lambda j: ob[j]["geom"].area)
            nhac = None
        else:
            j0 = kc[0][1]
            nhac = f"Nhãn '{n['dong']}' nằm gần cả hình khác, Sếp kiểm tra." if d0 > 0 and len(kc) > 1 and kc[1][0] < 1.2 * d0 else None
        ung[j0].append((d0, n, nhac))
    return {j: sorted(ds, key=lambda t: t[0])[0] for j, ds in ung.items()}


def _chua(ob):
    """Với mỗi hình kín: hình nhỏ hơn nằm trọn trong nó (chỉ số), và hình lớn nhỏ nhất bao quanh nó."""
    hinh = [(j, o) for j, o in enumerate(ob) if o["k"] == "hinh"]
    trong, ngoai = defaultdict(list), {}
    if not hinh:
        return trong, ngoai
    cay = STRtree([o["geom"] for _, o in hinh])
    for a, (j, o) in enumerate(hinh):
        for b in cay.query(o["geom"], predicate="contains"):
            k, p = hinh[b]
            if k != j and p["geom"].area <= TI_LE_TRONG * o["geom"].area:
                trong[j].append(k)
                if k not in ngoai or o["geom"].area < ob[ngoai[k]]["geom"].area:
                    ngoai[k] = j
    return trong, ngoai


def _phan_loai(j, o, nhan, trong, ngoai, nguon):
    """(loại, lý do, chắc?) cho một hình."""
    if nhan:
        return nhan["loai"], f"nhãn {nhan['ky_hieu']}", True
    if o["k"] == "hinh" and o["geom"].area < DIEN_TICH_NHO:
        return "khac", "hình rất nhỏ (nét chi tiết), không tính", False
    if nguon == "mong":
        if trong.get(j):
            return "mong", "bao quanh hình nhỏ hơn (cột/cổ cột)", True
        if j in ngoai:
            return "cot", "nằm trong một hình lớn hơn (cột/cổ cột trong móng)", True
    lay = _loai_theo_layer(o["ten"])
    if lay:
        return lay, f"layer {o['ten']}", lay == nguon
    return nguon, "mặc định theo công cụ, không có nhãn", False


def _kich_thuoc(o):
    g = o["geom"]
    if o["k"] == "net":
        return {"a": g.length, "b": None, "S": 0.0, "P": g.length, "L": g.length, "rect": None}
    hcn = _hcn(g)
    if hcn:
        a, b = hcn
    else:
        x0, y0, x1, y1 = g.bounds
        a, b = sorted((x1 - x0, y1 - y0), reverse=True)
    return {"a": a, "b": b, "S": g.area, "P": g.length, "L": a, "rect": bool(hcn)}


def _h_tu_nhan(loai, kt, day):
    """Chiều cao/dày ghi trên nhãn: 'h=400' hoặc dầm b x h, cột/móng a x b x h."""
    if day:
        return day
    if loai in ("dam", "da_kieng") and len(kt) >= 2:
        return kt[1]
    if len(kt) >= 3:
        return kt[2]
    return None


def quet_mat_bang(ban_ve, chon, khung, nguon="khac"):
    """chon: {layer: {"h": [chỉ số hình kín], "n": [chỉ số đường hở]}}; khung: [x0, y0, x1, y1] (m) vùng quét."""
    kt = config.app_config()["kiem_tra"]
    d_max = max(kt["khoang_cach_nhan_toi_da"], 1.5)
    ob, so_trung = _bo_trung(_doi_tuong(ban_ve, chon, nguon in NGUON_DUONG), kt["dien_tich_toi_thieu"])
    canh_bao = []
    if not ob:
        return {"nhom": [], "so_hinh": 0, "canh_bao": ["Không có hình nào để bóc trong vùng đã chọn (kiểm tra layer đang khoá/ẩn)."]}
    if so_trung:
        canh_bao.append(f"Đã bỏ {so_trung} hình vẽ trùng (hatch chồng polyline), mỗi hình chỉ tính một lần.")

    x0, y0, x1, y1 = khung
    hop = (min(x0, x1) - d_max, min(y0, y1) - d_max, max(x0, x1) + d_max, max(y0, y1) + d_max)
    nhan = []
    for dong, x, y, _ in _dong_chu(ban_ve, hop):
        d = doc_ky_hieu(dong)
        # Mặt bằng móng/cột: nhãn dầm, sàn... gần đó thuộc đối tượng khác chưa được chọn, bỏ qua để không gán nhầm
        if d and (nguon not in ("mong", "cot") or d["loai"] in ("mong", "cot")):
            nhan.append({**d, "dong": dong, "x": x, "y": y})
    gan = _gan_nhan(ob, nhan, d_max)
    trong, ngoai = _chua(ob)

    # Phân loại từng hình
    for j, o in enumerate(ob):
        nh = gan[j][1] if j in gan else None
        o["nhan"] = nh
        o["loai"], o["ly_do"], o["chac"] = _phan_loai(j, o, nh, trong, ngoai, nguon)
        if j in gan and gan[j][2]:
            o["chac"] = False
            o["nhac"] = gan[j][2]
        o["kt"] = _kich_thuoc(o)

    # Hình chưa có nhãn lấy ký hiệu của hình cùng loại, cùng kích thước đã có nhãn
    ten_theo_kt = defaultdict(Counter)
    for o in ob:
        if o["nhan"] and o["kt"]["b"] is not None:
            ten_theo_kt[o["loai"]][(o["nhan"]["ky_hieu"], round(o["kt"]["a"], 3), round(o["kt"]["b"], 3))] += 1
    for o in ob:
        o["ky_hieu"], o["nguon_ten"] = None, "chưa có nhãn"
        if o["nhan"]:
            o["ky_hieu"], o["nguon_ten"] = o["nhan"]["ky_hieu"], "nhãn"
            continue
        if o["kt"]["b"] is None:
            continue
        for (kh, a, b), _ in ten_theo_kt[o["loai"]].most_common():
            if abs(o["kt"]["a"] - a) <= DUNG_SAI_SUY_RA * a and abs(o["kt"]["b"] - b) <= DUNG_SAI_SUY_RA * max(b, 1e-6):
                o["ky_hieu"], o["nguon_ten"] = kh, "suy ra theo kích thước"
                break

    # Gom nhóm theo (loại, ký hiệu); hình chưa đặt tên tách theo kích thước
    nhom = defaultdict(list)
    for o in ob:
        if o["ky_hieu"]:
            khoa = (o["loai"], o["ky_hieu"], "")
        else:
            a, b = o["kt"]["a"], o["kt"]["b"]
            khoa = (o["loai"], "", f"{round(a * 1000)}x{round(b * 1000)}" if b is not None else "dai")
        nhom[khoa].append(o)

    ket_qua = []
    for (loai, kh, kich), ds in nhom.items():
        n = len(ds)
        tb = lambda k: sum(o["kt"][k] for o in ds if o["kt"][k] is not None) / max(1, sum(1 for o in ds if o["kt"][k] is not None))
        co_b = any(o["kt"]["b"] is not None for o in ds)
        nhan_goc = next((o["nhan"] for o in ds if o["nhan"]), None)
        kt_nhan = nhan_goc["kt"] if nhan_goc else []
        h = _h_tu_nhan(loai, kt_nhan, nhan_goc["day"] if nhan_goc else None)
        a, b = tb("a"), (tb("b") if co_b else None)
        if b is None and loai in ("dam", "da_kieng") and len(kt_nhan) >= 2:
            b = kt_nhan[0]  # tim dầm/đà kiềng vẽ bằng đường: bề rộng lấy từ nhãn "b x h"
        cb = [o["nhac"] for o in ds if o.get("nhac")][:2]
        if len({round(o["kt"]["a"], 2) for o in ds}) > 1 and loai not in ("dam", "da_kieng"):
            cb.append("Các hình cùng ký hiệu có kích thước khác nhau, đang lấy trung bình. Sếp kiểm tra nhãn.")
        if nhan_goc and kt_nhan and len(kt_nhan) >= 2 and b is not None and loai not in ("dam", "da_kieng"):
            ve = sorted((a, b), reverse=True)
            nh = sorted(kt_nhan[:2], reverse=True)
            if any(abs(x - y) / max(x, 1e-6) > DUNG_SAI for x, y in zip(ve, nh)):
                cb.append(f"Kích thước nhãn {'x'.join(str(round(v * 1000)) for v in kt_nhan[:2])} lệch hình vẽ "
                          f"{round(ve[0] * 1000)}x{round(ve[1] * 1000)}.")
        if ds[0]["kt"]["rect"] is None:
            dang = "Đường"
        else:
            dang = "Chữ nhật" if all(o["kt"]["rect"] for o in ds) else "Đặc biệt"
        ket_qua.append({
            "ma": f"{loai}|{kh}|{kich}", "ky_hieu": kh, "loai": loai, "loai_ten": TEN_LOAI.get(loai, loai),
            "chac": all(o["chac"] for o in ds), "ly_do": sorted({o["ly_do"] for o in ds}),
            "nguon_ten": ", ".join(sorted({o["nguon_ten"] for o in ds})),
            "n": n, "a": round(a, 6), "b": None if b is None else round(b, 6),
            "S": round(tb("S"), 6), "P": round(tb("P"), 6), "L": round(tb("L"), 6),
            "h": h, "h_nguon": "nhãn" if h else "", "kt_nhan": kt_nhan, "dang": dang,
            "layers": dict(Counter(o["ten"] for o in ds)),
            "doi_tuong": [_mo_ta(o) for o in ds],
            "canh_bao": cb, "dung": (loai == nguon or nguon == "khac") and not all(o["ly_do"].startswith("hình rất nhỏ") for o in ds),
        })
    thu_tu = [nguon] + [k for k in TEN_LOAI if k != nguon]
    ket_qua.sort(key=lambda g: (thu_tu.index(g["loai"]) if g["loai"] in thu_tu else 99, g["ky_hieu"] == "", _tu_nhien(g["ky_hieu"]), -g["n"]))
    if nguon == "mong" and any(g["loai"] == "cot" for g in ket_qua):
        canh_bao.append("Các hình xác định là cột (cột/cổ cột vẽ trong móng) được liệt kê riêng và không tính vào móng. "
                        "Nếu sai, Sếp đổi cột 'Loại' của nhóm đó sang Móng.")
    if any(not g["ky_hieu"] for g in ket_qua if g["loai"] == nguon):
        canh_bao.append("Có hình chưa đọc được ký hiệu. Sếp gõ ký hiệu vào ô 'Ký hiệu' của nhóm đó, hoặc kéo khung rộng hơn để lấy cả nhãn chữ.")
    return {"nhom": ket_qua, "so_hinh": len(ob), "canh_bao": canh_bao, "so_nhan": len(nhan)}


def _mo_ta(o):
    """Một đối tượng trong nhóm kèm số liệu riêng, để giao diện gộp/tách nhóm mà không phải hỏi lại máy chủ."""
    k = o["kt"]
    x, y = _diem(o["geom"])
    return {"ten": o["ten"], "k": o["k"], "i": o["i"], "x": x, "y": y, "a": round(k["a"], 6),
            "b": None if k["b"] is None else round(k["b"], 6), "S": round(k["S"], 6), "P": round(k["P"], 6),
            "L": round(k["L"], 6), "rect": k["rect"]}


def _diem(g):
    p = g.representative_point() if g.geom_type != "LineString" else g.interpolate(0.5, normalized=True)
    return round(p.x, 3), round(p.y, 3)


def _tu_nhien(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


# ---------- Bước 2: quét chọn chi tiết ----------
def quet_chi_tiet(ban_ve, khung):
    """Đọc chữ trong khung chi tiết: kích thước theo ký hiệu và danh sách con số rời làm ứng viên."""
    x0, y0, x1, y1 = khung
    hop = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    theo_kh, so_roi, cao_do, so_chu = {}, [], [], 0
    for dong, x, y, _ in _dong_chu(ban_ve, hop):
        so_chu += 1
        d = doc_ky_hieu(dong)
        if d:
            e = theo_kh.setdefault(d["ky_hieu"], {"loai": d["loai"], "kt": Counter(), "h": Counter(), "dong": [], "diem": [], "so": Counter(), "cd": Counter()})
            if d["kt"]:
                e["kt"][tuple(round(v * 1000) for v in d["kt"])] += 1
            h = _h_tu_nhan(d["loai"], d["kt"], d["day"])
            if h:
                e["h"][round(h * 1000)] += 1
            e["dong"].append(dong)
            e["diem"].append((x, y))
            continue
        m = RE_CAO_DO.match(dong)
        if m:
            v = 0.0 if m.group(1) == "±" else float(f"{m.group(2)}.{m.group(3)}") * (-1 if m.group(1) in "-−" else 1)
            cao_do.append((round(v, 3), x, y))
            continue
        m = RE_SO_RIENG.match(dong)
        if m:
            v = float(f"{m.group(1)}.{m.group(2)}") if m.group(2) else float(m.group(1))
            v = v / 1000 if (v >= 50 and not m.group(2)) else v
            if 0.05 <= v <= 20:
                so_roi.append((round(v, 3), x, y))

    # Con số rời thuộc ký hiệu gần nhất (chi tiết có nhiều ký hiệu), không có ký hiệu thì để chung
    chung = Counter()
    for v, x, y in so_roi:
        gan = min(((min(math.hypot(x - px, y - py) for px, py in e["diem"]), k) for k, e in theo_kh.items()), default=None)
        (theo_kh[gan[1]]["so"] if gan else chung)[v] += 1
    cd_chung = Counter()
    for v, x, y in cao_do:
        gan = min(((min(math.hypot(x - px, y - py) for px, py in e["diem"]), k) for k, e in theo_kh.items()), default=None)
        (theo_kh[gan[1]]["cd"] if gan else cd_chung)[v] += 1
    ket_qua = []
    for kh, e in sorted(theo_kh.items(), key=lambda t: _tu_nhien(t[0])):
        h = e["h"].most_common(1)[0][0] / 1000 if e["h"] else None
        ket_qua.append({"ky_hieu": kh, "loai": e["loai"], "loai_ten": TEN_LOAI.get(e["loai"], e["loai"]),
                        "kt": [list(k) for k, _ in e["kt"].most_common()], "h": h, "h_nguon": "chi tiết" if h else "",
                        "dong": e["dong"], "ung_vien": sorted(e["so"]), "cao_do": sorted(e["cd"])})
    canh_bao = []
    if not so_chu:
        canh_bao.append("Khung chọn không có chữ nào. Sếp kéo khung trùm cả phần ghi kích thước.")
    elif not ket_qua:
        canh_bao.append("Không đọc được ký hiệu trong khung (M1, F1...). Sếp chọn chiều cao từ các số tìm thấy, hoặc gõ tay.")
    return {"ky_hieu": ket_qua, "ung_vien_chung": sorted(chung), "cao_do_chung": sorted(cd_chung), "so_chu": so_chu, "canh_bao": canh_bao}
