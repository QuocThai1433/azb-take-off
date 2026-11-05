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
    "coc": {"P"},
}
# Nhãn cọc "P1 D300 L=16m": đường kính (mm) và chiều dài (m)
RE_COC_D = re.compile(r"(?<![A-ZĐ])(?:D|Ø|Φ|Ф)\s*=?\s*(\d{2,4})(?!\d)")
RE_COC_L = re.compile(r"(?<![A-ZĐ])L\s*[=:]?\s*(\d+(?:[.,]\d+)?)\s*M?(?![A-Z0-9])")
DONG_TAM = 0.05  # m: hai hình có tâm cách nhau không quá mức này coi là đồng tâm (vòng tròn cọc vẽ nhiều lớp)
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
TEN_LOAI = {"mong": "Móng", "coc": "Cọc", "cot": "Cột", "da_kieng": "Đà kiềng", "dam": "Dầm", "san": "Sàn", "khac": "Khác"}

DIEN_TICH_NHO = 0.02  # m2: hình kín nhỏ hơn mức này không nhãn là nét chi tiết, không phải cấu kiện
PHU_KIN = 0.95        # hai hình chồng nhau từ 95% diện tích hình nhỏ và gần bằng nhau coi là vẽ trùng
TI_LE_TRONG = 0.6     # hình nằm trong hình khác và nhỏ hơn 60% diện tích thì là hình bên trong
DUNG_SAI = 0.05       # kích thước nhãn lệch hình vẽ quá mức này thì cảnh báo
DUNG_SAI_SUY_RA = 0.02
LOT_MIN, LOT_MAX = 0.03, 0.15  # m: hình chữ nhật đồng tâm rộng hơn hình bên trong mỗi phía trong khoảng này coi là bê tông lót vẽ sẵn
KHOANG_NHAN_KT = 0.3           # m: nhãn có kích thước "800x800x700" tìm hình khớp kích thước trong phạm vi xa hơn hình gần nhất tối đa mức này


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
        if loai == "coc":
            tok = tok.replace(".", "").replace("-", "").replace("_", "")  # "P.1" và "P1" là một cọc
            u = s.upper()
            d, dai = RE_COC_D.search(u), RE_COC_L.search(u)
            return {"ky_hieu": tok, "loai": loai, "kt": [], "day": None,
                    "d": int(d.group(1)) / 1000 if d else None,
                    "dai_coc": float(dai.group(1).replace(",", ".")) if dai else None}
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


RE_KT_ROI = re.compile(r"^\s*\d{2,5}\s*[xX×*]\s*\d{2,5}(?:\s*[xX×*]\s*\d{2,5})?\s*$")
HANG_DY, HANG_DX = 0.15, 3.0  # m: chữ kích thước cùng hàng (lệch dọc tối đa) và nằm bên phải ký hiệu (cách tối đa) thì ghép


def _dong_chu_gop(ban_ve, ptr=None):
    """Như _dong_chu nhưng ghép chữ kích thước rời ("800X800X700") vào ký hiệu chưa có kích thước cùng hàng bên trái nó
    ("F1") — bảng thống kê móng thường để mỗi ô là một chữ riêng. Kết quả "F1 800X800X700" ở vị trí ký hiệu."""
    ds = list(_dong_chu(ban_ve, ptr))
    ky = [(i, d[1], d[2]) for i, d in enumerate(ds) if (k := doc_ky_hieu(d[0])) and not k["kt"] and not k.get("day")
          and len(RE_TACH.split(d[0].strip())) == 1]
    gop, bo = {}, set()
    for i, (dong, x, y, _) in enumerate(ds):
        if not RE_KT_ROI.match(dong):
            continue
        ung = [(x - kx, j) for j, kx, ky_y in ky if j not in gop and abs(ky_y - y) <= HANG_DY and 0 <= x - kx <= HANG_DX]
        if ung:
            j = min(ung)[1]
            gop[j] = dong.strip()
            bo.add(i)
    for i, (dong, x, y, ten) in enumerate(ds):
        if i in bo:
            continue
        yield (f"{dong.strip()} {gop[i]}", x, y, ten) if i in gop else (dong, x, y, ten)


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
        # Nhãn ghi kích thước ("F1 800x800x700"): ưu tiên hình gần đó có đúng kích thước ấy, kể cả khi có hình lớn hơn
        # (bê tông lót vẽ sẵn) nằm gần nhãn hơn
        if len(n.get("kt") or []) >= 2:
            khop = [(d, j) for d, j in kc if d <= d0 + KHOANG_NHAN_KT and _hop_kich_thuoc(ob[j], n["kt"])]
            if khop:
                ung[khop[0][1]].append((khop[0][0], n, None))
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


def _hop_kich_thuoc(o, kt_nhan):
    """Hình chữ nhật có hai cạnh khớp (trong DUNG_SAI) hai số đầu của kích thước ghi trên nhãn."""
    if len(kt_nhan or []) < 2 or o["k"] != "hinh":
        return False
    k = _kich_thuoc(o)
    if k["b"] is None or not k["rect"]:
        return False
    ve, nh = sorted((k["a"], k["b"]), reverse=True), sorted(kt_nhan[:2], reverse=True)
    return all(abs(x - y) <= DUNG_SAI * max(y, 1e-6) for x, y in zip(ve, nh))


def _tim_lot(ob, trong=None, ngoai=None):
    """Bê tông lót vẽ sẵn: hình chữ nhật đồng tâm bao quanh một hình chữ nhật khác, rộng hơn đều mỗi phía LOT_MIN..LOT_MAX.
    Tự xét quan hệ chứa bằng hình học (lót 1000 bao móng 800 chiếm 64% diện tích, chưa đủ để _chua coi là lồng nhau).
    Trả {chỉ số hình lót: (chỉ số hình bên trong, bề rộng mở rộng mỗi phía, m)}."""
    lot = {}
    hinh = [(j, o) for j, o in enumerate(ob) if o["k"] == "hinh"]
    if not hinh:
        return lot
    cay = STRtree([o["geom"] for _, o in hinh])
    for a, (j, o) in enumerate(hinh):
        gj = o["geom"]
        hj = _hcn(gj)
        if not hj:
            continue
        for b in cay.query(gj, predicate="contains"):
            k, p = hinh[b]
            if k == j or p["geom"].area >= gj.area:
                continue
            hk = _hcn(p["geom"])
            if not hk:
                continue
            dx, dy = (hj[0] - hk[0]) / 2, (hj[1] - hk[1]) / 2
            if LOT_MIN <= dx <= LOT_MAX and LOT_MIN <= dy <= LOT_MAX and abs(dx - dy) <= 0.02 \
                    and gj.centroid.distance(ob[k]["geom"].centroid) <= 0.02:
                lot[j] = (k, round((dx + dy) / 2, 3))
                break
    return lot


def _la_vong_tron(o):
    """Hình kín là vòng tròn thật (diện tích bằng 90 đến 105% hình tròn ngoại tiếp; hình vuông ra 127% nên không lẫn)."""
    if o["k"] != "hinh":
        return False
    x0, y0, x1, y1 = o["geom"].bounds
    d = max(x1 - x0, y1 - y0)
    if not (0.05 <= d <= 3.0) or abs((x1 - x0) - (y1 - y0)) > 0.1 * d:
        return False
    return 0.9 <= o["geom"].area / (math.pi * (d / 2) ** 2) <= 1.05


def _phan_loai(j, o, nhan, trong, ngoai, nguon, lot=None, cha=None):
    """(loại, lý do, chắc?) cho một hình. lot: {j: (con, mở rộng)} hình lót vẽ sẵn; cha(j): hình bao thật (bỏ qua lót)."""
    if nguon == "mong" and lot and j in lot and not (nhan and _hop_kich_thuoc(o, nhan.get("kt"))):
        return "khac", (f"bê tông lót vẽ sẵn (rộng hơn hình bên trong {round(lot[j][1] * 1000)} mm mỗi phía); "
                        "công cụ đã tự tính lót dưới móng nên không tính lại. Muốn tính riêng thì đổi Loại sang Móng và tắt lót tự động"), False
    if nhan:
        return nhan["loai"], f"nhãn {nhan['ky_hieu']}", True
    if nguon == "coc":
        # Cọc luôn có tên P1, P2...: hình không có nhãn (bong bóng trục, vòng tròn phụ) không phải cọc
        return "khac", "không có ký hiệu cọc (P1...) gần hình, không tính", False
    if o["k"] == "hinh" and o["geom"].area < DIEN_TICH_NHO:
        return "khac", "hình rất nhỏ (nét chi tiết), không tính", False
    if nguon == "mong":
        if _la_vong_tron(o) and not trong.get(j):
            return "khac", "vòng tròn không có nhãn (bong bóng trục, ký hiệu), không tính. Nếu là móng tròn, đổi Loại sang Móng", False
        if cha and cha(j) is not None:
            if trong.get(j):
                return "cot", "nằm trong một hình lớn hơn và bao quanh hình nhỏ hơn: coi là cổ cột, Sếp kiểm tra", False
            return "cot", "nằm trong một hình lớn hơn (cột/cổ cột trong móng)", True
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


def _la_hinh_tron(o):
    """Hình kín gần tròn (diện tích ≥ 90% hình tròn ngoại tiếp hộp bao), đường kính 0,05 đến 3 m."""
    if o["k"] != "hinh":
        return False
    g = o["geom"]
    x0, y0, x1, y1 = g.bounds
    d = max(x1 - x0, y1 - y0)
    return 0.05 <= d <= 3.0 and g.area / (math.pi * (d / 2) ** 2) >= 0.9


def _xu_ly_coc(ob, nhan=(), mac_dinh=(None, None)):
    """Mặt bằng cọc: mỗi cọc thường vẽ nhiều vòng tròn đồng tâm (vòng ngoài, vòng trong, ký hiệu tim). Giữ một hình cho mỗi cọc
    (ưu tiên hình có nhãn kèm D/L), bỏ các hình đồng tâm còn lại. Có D trên nhãn thì S, P lấy theo D (π·D²/4), không theo hình vẽ.
    Trả (danh sách mới, số hình đồng tâm đã bỏ)."""
    coc = sorted((o for o in ob if o["loai"] == "coc"),
                 key=lambda o: (0 if (o["nhan"].get("d") or o["nhan"].get("dai_coc")) else 1, o["geom"].area))
    giu = []
    for o in coc:
        c = o["geom"].centroid
        if not any(c.distance(k["geom"].centroid) <= DONG_TAM for k in giu):
            giu.append(o)
    cac_tam = [k["geom"].centroid for k in giu]
    ket = list(giu)
    bo = len(coc) - len(giu)
    for o in ob:
        if o["loai"] == "coc":
            continue
        if cac_tam and o["k"] == "hinh" and any(o["geom"].centroid.distance(c) <= DONG_TAM for c in cac_tam):
            bo += 1  # vòng phụ đồng tâm với một cọc
            continue
        ket.append(o)
    # Mỗi hình chỉ giữ một nhãn gần nhất (có thể là nhãn phụ "P.1"), nên D và L lấy theo tên cọc từ mọi nhãn cùng tên
    thong_tin = {}
    for n in nhan:
        if n["loai"] == "coc":
            e = thong_tin.setdefault(n["ky_hieu"], {})
            for k in ("d", "dai_coc"):
                if n.get(k) and not e.get(k):
                    e[k] = n[k]
    dk_bang, dai_bang = mac_dinh  # bảng "THỐNG KÊ CỌC" hoặc ghi chú trong bản vẽ: đường kính (mm), chiều dài (m)
    for o in giu:
        o["nhan"] = {**o["nhan"], **{k: v for k, v in thong_tin.get(o["nhan"]["ky_hieu"], {}).items() if not o["nhan"].get(k)}}
        if not o["nhan"].get("d") and dk_bang:
            o["nhan"]["d"] = dk_bang / 1000
        if not o["nhan"].get("dai_coc") and dai_bang:
            o["nhan"]["dai_coc"] = dai_bang
        o["chac"] = True  # cọc có nhãn tên rõ ràng; hình đồng tâm đã gộp nên không còn nghi ngờ nhãn gần hình khác
        o.pop("nhac", None)
        d = o["nhan"].get("d")
        if d:
            o["kt"] = {"a": d, "b": d, "S": math.pi * d * d / 4, "P": math.pi * d, "L": d, "rect": False}
            o["ly_do"] = f"nhãn {o['nhan']['ky_hieu']} (D{round(d * 1000)})"
    return ket, bo


def _h_tu_nhan(loai, kt, day):
    """Chiều cao/dày ghi trên nhãn: 'h=400' hoặc dầm b x h, cột/móng a x b x h."""
    if day:
        return day
    if loai in ("dam", "da_kieng") and len(kt) >= 2:
        return kt[1]
    if len(kt) >= 3:
        return kt[2]
    return None


def _trong_vung(o, vung):
    """Điểm đại diện của hình (tâm với hình kín, giữa đường với nét hở) nằm trong hộp Vùng (m)."""
    x, y = _diem(o["geom"])
    return min(vung[0], vung[2]) <= x <= max(vung[0], vung[2]) and min(vung[1], vung[3]) <= y <= max(vung[1], vung[3])


def quet_mat_bang(ban_ve, chon, khung, nguon="khac", vung=None):
    """chon: {layer: {"h": [chỉ số hình kín], "n": [chỉ số đường hở]}}; khung: [x0, y0, x1, y1] (m) vùng quét.
    vung: [x0, y0, x1, y1] (m) Vùng đã chọn ở thanh trên; có thì chỉ lấy hình nằm trong vùng, không có thì lấy cả khung quét."""
    kt = config.app_config()["kiem_tra"]
    d_max = max(kt["khoang_cach_nhan_toi_da"], 1.5)
    ob = _doi_tuong(ban_ve, chon, nguon in NGUON_DUONG)
    so_ngoai_vung = 0
    if vung and len(vung) == 4:
        truoc = len(ob)
        ob = [o for o in ob if _trong_vung(o, vung)]
        so_ngoai_vung = truoc - len(ob)
    ob, so_trung = _bo_trung(ob, kt["dien_tich_toi_thieu"])
    if nguon == "coc":  # cọc là hình tròn nhỏ; khung lưới trục, đường bao... bị loại để không giành nhãn của cọc
        ob = [o for o in ob if _la_hinh_tron(o)]
    canh_bao = []
    if so_ngoai_vung:
        canh_bao.append(f"Đã bỏ {so_ngoai_vung} hình nằm ngoài Vùng đã chọn (thanh trên). Bấm 'Bỏ vùng' nếu muốn lấy cả khung quét.")
    if not ob:
        return {"nhom": [], "so_hinh": 0, "canh_bao": ["Không có hình nào để bóc trong vùng đã chọn (kiểm tra layer đang khoá/ẩn)."]}
    if so_trung:
        canh_bao.append(f"Đã bỏ {so_trung} hình vẽ trùng (hatch chồng polyline), mỗi hình chỉ tính một lần.")

    x0, y0, x1, y1 = khung
    hop = (min(x0, x1) - d_max, min(y0, y1) - d_max, max(x0, x1) + d_max, max(y0, y1) + d_max)
    nhan = []
    for dong, x, y, _ in _dong_chu_gop(ban_ve, hop):
        d = doc_ky_hieu(dong)
        # Mặt bằng móng/cột: nhãn dầm, sàn... gần đó thuộc đối tượng khác chưa được chọn, bỏ qua để không gán nhầm
        if not d:
            continue
        if nguon == "coc":
            ok = d["loai"] == "coc"
        elif nguon in ("mong", "cot"):
            ok = d["loai"] in ("mong", "cot")
        else:
            ok = d["loai"] != "coc" or nguon == "khac"
        if ok:
            nhan.append({**d, "dong": dong, "x": x, "y": y})
    # Nhãn cọc có đường kính/chiều dài được ưu tiên hơn nhãn "P.1" chỉ có tên
    nhan.sort(key=lambda n: 0 if n.get("d") or n.get("dai_coc") else 1)
    gan = _gan_nhan(ob, nhan, d_max)
    trong, ngoai = _chua(ob)

    # Nhãn của từng hình; hình lót vẽ sẵn nhận nhầm nhãn móng (nhãn không ghi kích thước) thì nhường nhãn cho hình bên trong
    nh_cua = {j: (gan[j][1] if j in gan else None) for j in range(len(ob))}
    lot = _tim_lot(ob, trong, ngoai) if nguon == "mong" else {}
    for j, (con, _) in lot.items():
        n = nh_cua[j]
        if n and not _hop_kich_thuoc(ob[j], n.get("kt")):
            if nh_cua.get(con) is None:
                nh_cua[con] = n
            nh_cua[j] = None

    def cha_that(j):  # hình lớn nhất gần nhất bao quanh, bỏ qua lớp lót
        p = ngoai.get(j)
        while p is not None and p in lot:
            p = ngoai.get(p)
        return p

    # Phân loại từng hình
    for j, o in enumerate(ob):
        nh = nh_cua[j]
        o["nhan"] = nh
        o["loai"], o["ly_do"], o["chac"] = _phan_loai(j, o, nh, trong, ngoai, nguon, lot, cha_that)
        if j in gan and gan[j][2] and nh is gan[j][1]:
            o["chac"] = False
            o["nhac"] = gan[j][2]
        o["kt"] = _kich_thuoc(o)
    so_lot = sum(1 for j in lot if ob[j]["loai"] == "khac")
    if so_lot:
        canh_bao.append(f"Phát hiện {so_lot} hình là bê tông lót vẽ sẵn (rộng hơn móng khoảng 100 mm mỗi phía). Đã không tính vì công cụ tự tính "
                        "lót dưới móng; tính thêm sẽ bị trùng. Sếp xem nhóm 'Khác' nếu cần đổi.")

    if nguon == "coc":
        from .gan_nhan import _bang_coc  # đọc bảng thống kê cọc (đã dùng cho nhãn tự động)
        dk_bang, dai_bang = _bang_coc(ban_ve)
        ob, so_dong_tam = _xu_ly_coc(ob, nhan, (dk_bang, dai_bang))
        if dk_bang or dai_bang:
            canh_bao.append("Cọc không ghi D/L trên nhãn nên lấy từ bảng thống kê cọc trong bản vẽ: "
                            f"D{dk_bang or '?'}, L={dai_bang if dai_bang else '?'} m. Sếp đối chiếu.")
        if any(o["loai"] == "coc" and not o["nhan"].get("dai_coc") for o in ob):
            canh_bao.append("Chưa tìm thấy chiều dài cọc (nhãn hoặc bảng thống kê). Sếp nhập ở cột h.")
        if so_dong_tam:
            canh_bao.append(f"Đã gộp {so_dong_tam} vòng tròn đồng tâm của cọc (mỗi cọc vẽ nhiều lớp), mỗi cọc chỉ tính một lần.")

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

    # Kích thước ghi trên mọi nhãn cùng ký hiệu (một móng thường có nhãn "F1" gần và nhãn "F1 800x800x700" xa hơn)
    kt_theo_kh = defaultdict(Counter)
    for n in nhan:
        if len(n["kt"]) >= 2 or n.get("day"):
            kt_theo_kh[n["ky_hieu"]][(tuple(n["kt"]), n.get("day"))] += 1

    ket_qua = []
    for (loai, kh, kich), ds in nhom.items():
        n = len(ds)
        tb = lambda k: sum(o["kt"][k] for o in ds if o["kt"][k] is not None) / max(1, sum(1 for o in ds if o["kt"][k] is not None))
        co_b = any(o["kt"]["b"] is not None for o in ds)
        nhan_goc = next((o["nhan"] for o in ds if o["nhan"]), None)
        kt_nhan = nhan_goc["kt"] if nhan_goc else []
        day_nhan = nhan_goc["day"] if nhan_goc else None
        if not kt_nhan and not day_nhan and kh and kt_theo_kh.get(kh):
            (kt_t, day_nhan), _ = kt_theo_kh[kh].most_common(1)[0]
            kt_nhan = list(kt_t)
        h = _h_tu_nhan(loai, kt_nhan, day_nhan)
        if loai == "coc":  # h của cọc = chiều dài cọc ghi trên nhãn (L=16m)
            h = next((o["nhan"]["dai_coc"] for o in ds if o["nhan"] and o["nhan"].get("dai_coc")), None)
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
    for dong, x, y, _ in _dong_chu_gop(ban_ve, hop):
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
