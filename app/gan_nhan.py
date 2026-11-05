"""Tự gán nhãn lên mặt bằng kết cấu chưa có chữ: dầm (1.DX1-200X400), trục (22aX1), cột (C1-200X200).

Mọi tọa độ là mét (đã đổi từ đơn vị bản vẽ). Quy trình cho một vùng mặt bằng:

1. Tìm dầm: layer đã gán "Dầm", hoặc "Khung dầm" + "Ô trống" (dam_suy_ra), hoặc tự dò layer có khung chứa các ô trống.
2. Với mỗi dầm đo bề rộng b từ hình học, hướng X hoặc Y từ trục dài. Dầm cùng hướng, cùng b, cùng vai trò
   (dầm biên chạm mép khung hay dầm giữa) là một loại: DX1, DX2... DY1... Biên đứng trước, b lớn đứng trước.
3. Chiều cao h của dầm không có trên mặt bằng: lấy từ người dùng nhập, hoặc từ chữ trong bản vẽ (kiểu "1.DX1-200X400",
   "D1 220x500"). Không có thì ghi "?" và cảnh báo, không đoán.
4. Tỷ lệ: đọc "TL:1/50" gần vùng nhất (không có thì ước từ cỡ chữ đang có). Chiều cao chữ = 3 mm trên giấy × mẫu số tỷ lệ,
   nên chữ trong mặt bằng 1/50 cao 0,15 m, mặt bằng 1/25 cao 0,075 m, đúng như chữ CAD in ra.
5. Đặt chữ cạnh dầm, xoay theo dầm, né chữ có sẵn, cột, dầm khác và các nhãn đã đặt.
6. Trục: lấy từ layer trục (đường thẳng dài), không có thì suy từ tim dầm. Tên = tiền tố + X/Y + số thứ tự;
   X đánh từ trái sang phải, Y từ dưới lên trên; chữ đặt trong bong bóng ở đầu dưới (X) hoặc đầu trái (Y).
"""
import math
import re
import statistics
import unicodedata
from collections import Counter
from dataclasses import replace

from shapely.affinity import rotate, translate
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from .dam_suy_ra import suy_dam
from .dxf_reader import HinhKin, LayerData, cat_vung

TEN_LAYER_NHAN = "AZB-NHAN"
CHU_GIAY_MM = 3.0          # chữ in cao 3 mm trên giấy
TY_LE_CHUAN = [10, 20, 25, 30, 40, 50, 75, 100, 150, 200, 250, 500]
HE_SO_RONG_CHU = 0.62      # bề rộng một ký tự / chiều cao chữ (ước lượng để né nhau)
KHE_NHAN = 0.25            # khe giữa nhãn và mép dầm, theo chiều cao chữ
CHU_TRUC_TY_LE = 1.25      # chữ tên trục lớn hơn chữ dầm
BONG_TRUC_TY_LE = 1.45     # bán kính bong bóng trục / chiều cao chữ trục

RE_TL = re.compile(r"(?:\bTL|T[ỶỈ]\s*L[ỆE]|SCALE)\s*[:=]?\s*1\s*[/:]\s*(\d{1,4})", re.I)
RE_TANG = re.compile(r"T[ẦA]NG\s*(\d+|M[ÁA]I|H[ẦA]M|TR[ỆE]T|L[ỬU]NG)", re.I)
RE_LAYER_KHONG_PHAI_DAM = re.compile(r"TTLB|ANNO|BORDER|TITLE|FRAME|KHUNG\s*(TEN|BV)|DEFPOINT|DIM", re.I)  # khung tên, chú thích, kích thước
RE_TIET_DIEN_DAM = re.compile(r"\(\s*\d{2,3}\s*[xX×]\s*\d{2,3}")
BE_RONG_DAM = (0.10, 1.0)  # bề rộng dầm hợp lý (m); ngoài khoảng này là nét khác bị nhận nhầm
RE_LAYER_TRUC = re.compile(r"tr[uụ]c|grid|axis|l[uư][oơ]i", re.I)
# Chữ ghi tiết diện dầm có sẵn: "1.DX1-200X400", "DX1 200x400", "D1 220x500"
RE_DAM_CHU = re.compile(r"^\s*(?:(\w+)\s*\.\s*)?(D[A-Z]*\d+[A-Z]?)\s*[-–: ]\s*(\d{2,4})\s*[xX×]\s*(\d{2,4})\s*$")
RE_TRUC_CHU = re.compile(r"^(.*?)([XY])(\d+)$")
RE_MA_DU_AN = re.compile(r"^\s*(\d+[A-Za-z]?)\s*[-–]\s*\S")


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _hop_chu(x, y, goc, cao, neo, n_ky_tu):
    """Hình chữ nhật bao quanh một dòng chữ (để né nhau)."""
    w, h = HE_SO_RONG_CHU * cao * max(n_ky_tu, 1), cao
    cot = {"l": 0.0, "c": -w / 2, "r": -w}[neo[1]]
    hang = {"b": 0.0, "m": -h / 2, "t": -h}[neo[0]]
    g = box(cot, hang, cot + w, hang + h)
    g = rotate(g, goc, origin=(0, 0))
    return translate(g, x, y)


def _lam_tron_mm(m, buoc=5):
    return int(round(m * 1000 / buoc) * buoc)


def _gom(gia_tri, dung_sai):
    """Gom các số gần nhau (trong dung_sai) thành một, trả danh sách giá trị đại diện đã sắp tăng."""
    nhom = []
    for v in sorted(gia_tri):
        if nhom and v - nhom[-1][-1] <= dung_sai:
            nhom[-1].append(v)
        else:
            nhom.append([v])
    return [sum(g) / len(g) for g in nhom]


# ---------- Tìm dầm ----------
def _tu_nhan_khung_o(ban_ve):
    """Dò layer nào có khung chứa các ô trống (mặt bằng dầm vẽ kiểu khung trừ ô). Trả tên layer hoặc None."""
    tot, diem_tot = None, 0
    for ld in ban_ve.layers.values():
        if ld.tat or RE_LAYER_KHONG_PHAI_DAM.search(ld.ten):
            continue
        hs = [h.geom for h in ld.hinh_kin if 0.01 <= h.geom.area <= 5000]
        if len(hs) < 2:
            continue
        diem = 0
        for k in hs:
            if k.area < 1.0:
                continue
            diem += sum(1 for o in hs if o is not k and k.contains(o.centroid) and 0.01 * k.area <= o.area < 0.9 * k.area)
        if diem > diem_tot:
            tot, diem_tot = ld.ten, diem
    return tot


def _co_khung_o(hs):
    hs = [g for g in hs if g.area >= 0.01]
    return any(k.area >= 1.0 and any(o is not k and k.contains(o.centroid) and 0.01 * k.area <= o.area < 0.9 * k.area for o in hs)
               for k in hs)


def _tim_dam(ban_ve, loai_layer, canh_bao):
    loai = dict(loai_layer)
    co_dam = any(v == "dam" for v in loai.values())
    co_khung_o = any(v == "khung_dam" for v in loai.values()) and any(v == "o_dam" for v in loai.values())
    if not co_dam and not co_khung_o:
        ten = _tu_nhan_khung_o(ban_ve)
        hs = ban_ve.layers[ten].hinh_kin if ten else None
        if not ten:  # khung và ô trống nằm ở các layer khác nhau (trục + nét đứt): gộp mọi layer đang bật
            hs = [h for ld in ban_ve.layers.values() if not ld.tat for h in ld.hinh_kin if h.nguon != "CIRCLE"]
            if _co_khung_o([h.geom for h in hs]):
                ten = "nhiều layer"
        if ten:
            layers = dict(ban_ve.layers)
            layers["_TD_KHUNG"] = LayerData(ten="_TD_KHUNG", hinh_kin=list(hs))
            layers["_TD_O"] = LayerData(ten="_TD_O", hinh_kin=list(hs))
            ban_ve = replace(ban_ve, layers=layers)
            loai["_TD_KHUNG"], loai["_TD_O"] = "khung_dam", "o_dam"
            canh_bao.append(f'Chưa gán layer dầm: tự dò layer "{ten}" (khung chứa các ô trống) để suy ra dầm. Sếp kiểm tra.')
    if not co_dam and not co_khung_o:
        da_ghi = sum(1 for c in _tat_ca_chu(ban_ve) for dong in _nfc(c.noi_dung).splitlines() if RE_TIET_DIEN_DAM.search(dong))
        if da_ghi >= 5:
            canh_bao.append(f"Mặt bằng này đã ghi sẵn {da_ghi} tiết diện dầm (kiểu '(25x40)', 'DS1 (30x70)'). Dầm thường vẽ bằng nét hở nên công cụ khó tự "
                            "nhận đủ; kết quả dầm dưới đây chỉ để tham khảo, nên đối chiếu với nhãn có sẵn.")
    n_cu = len(ban_ve.canh_bao)
    bv2, loai2 = suy_dam(ban_ve, loai)
    canh_bao.extend(bv2.canh_bao[n_cu:])
    hinh = []
    for ten, v in loai2.items():
        if v == "dam" and ten in bv2.layers:
            hinh += [h.geom for h in bv2.layers[ten].hinh_kin if h.geom.area >= 0.005]
    duy_nhat = []
    for g in sorted(hinh, key=lambda g: -g.area):  # bỏ hình trùng (hatch + polyline)
        if not any(g.intersection(u).area > 0.95 * g.area for u in duy_nhat):
            duy_nhat.append(g)
    hop_ly = [g for g in duy_nhat if (d := _do_dam(g)) and BE_RONG_DAM[0] <= d[2] <= BE_RONG_DAM[1] and d[3] >= 2 * d[2]]
    if len(hop_ly) < len(duy_nhat):
        canh_bao.append(f"Dầm: bỏ {len(duy_nhat) - len(hop_ly)} hình không giống dầm (bề rộng ngoài {BE_RONG_DAM[0] * 1000:.0f}-{BE_RONG_DAM[1] * 1000:.0f} mm hoặc quá ngắn). "
                        "Nếu thiếu dầm, gán đúng layer 'Dầm' ở tab Layer.")
    return hop_ly


def _do_dam(g):
    """(tâm x, tâm y, b, L, hướng 'X'|'Y', góc độ 0..180) từ hình chữ nhật xoay nhỏ nhất."""
    r = g.minimum_rotated_rectangle
    if r.geom_type != "Polygon":
        return None
    p = list(r.exterior.coords)[:4]
    c1 = math.hypot(p[1][0] - p[0][0], p[1][1] - p[0][1])
    c2 = math.hypot(p[2][0] - p[1][0], p[2][1] - p[1][1])
    if min(c1, c2) < 1e-4:
        return None
    dai = (p[1][0] - p[0][0], p[1][1] - p[0][1]) if c1 >= c2 else (p[2][0] - p[1][0], p[2][1] - p[1][1])
    goc = math.degrees(math.atan2(dai[1], dai[0])) % 180
    huong = "X" if goc <= 45 or goc >= 135 else "Y"
    cx, cy = r.centroid.x, r.centroid.y
    return cx, cy, min(c1, c2), max(c1, c2), huong, goc


def _phan_loai_dam(ds_hinh, canh_bao):
    """Danh sách dầm kèm vai trò biên/giữa. Dầm chạm mép ngoài của cụm dầm liền nhau là dầm biên."""
    cum = unary_union([g.buffer(0.02) for g in ds_hinh])
    cum = [cum] if cum.geom_type == "Polygon" else list(cum.geoms)
    kq = []
    for g in ds_hinh:
        d = _do_dam(g)
        if d is None:
            continue
        cx, cy, b, L, huong, goc = d
        c = next((c for c in cum if c.intersects(g)), None)
        x0, y0, x1, y1 = c.bounds if c is not None else g.bounds
        gx0, gy0, gx1, gy1 = g.bounds
        t = 0.06
        if huong == "X":
            vai_tro = "bien" if (gy0 - y0 < t or y1 - gy1 < t) else "giua"
        else:
            vai_tro = "bien" if (gx0 - x0 < t or x1 - gx1 < t) else "giua"
        kq.append({"geom": g, "cx": cx, "cy": cy, "b": b, "L": L, "huong": huong, "goc": goc, "vai_tro": vai_tro,
                   "b_mm": _lam_tron_mm(b), "cum": (x0 + x1) / 2, "cum_y": (y0 + y1) / 2, "cum_bb": (x0, y0, x1, y1)})
    return kq


# ---------- Đọc thông tin xung quanh: tỷ lệ, tầng, tiền tố trục, chữ ghi tiết diện ----------
def _tat_ca_chu(ban_ve):
    return [c for ld in ban_ve.layers.values() for c in ld.chu]


def _gan_nhat(ban_ve, vung_box, regex, them=None, toi_da=None):
    """Chữ khớp regex gần vùng nhất: trả (match, chu, khoảng cách) hoặc None."""
    tot = None
    for c in _tat_ca_chu(ban_ve):
        t = _nfc(c.noi_dung)
        if them and not them(t):
            continue
        m = regex.search(t)
        if not m:
            continue
        d = vung_box.distance(c.diem)
        if toi_da is not None and d > toi_da:
            continue
        if tot is None or d < tot[2]:
            tot = (m, c, d)
    return tot


def _ty_le(ban_ve, vung_box, canh_bao, ty_le_nhap=None):
    if ty_le_nhap:
        return int(ty_le_nhap), "nhập tay"
    w, h = vung_box.bounds[2] - vung_box.bounds[0], vung_box.bounds[3] - vung_box.bounds[1]
    toi_da = max(5.0, 1.5 * max(w, h))
    kq = _gan_nhat(ban_ve, vung_box, RE_TL, toi_da=toi_da)
    if kq:
        return int(kq[0].group(1)), f'đọc "{_nfc(kq[1].noi_dung).replace(chr(10), " ").strip()[:40]}"'
    cao = [c.cao for c in _tat_ca_chu(ban_ve) if c.cao > 0 and vung_box.buffer(1.0).contains(c.diem)]
    if cao:
        uoc = statistics.median(cao) * 1000 / CHU_GIAY_MM
        mau_so = min(TY_LE_CHUAN, key=lambda s: abs(s - uoc))
        canh_bao.append(f"Không thấy chữ tỷ lệ (TL:1/…) gần vùng. Ước theo cỡ chữ đang có: 1/{mau_so}. Sếp kiểm tra ô Tỷ lệ.")
        return mau_so, "ước theo cỡ chữ có sẵn"
    canh_bao.append("Không thấy chữ tỷ lệ và không có chữ nào để ước. Tạm dùng 1/50, Sếp nhập đúng tỷ lệ.")
    return 50, "mặc định"


def _tang(ban_ve, vung_box, tang_nhap=None):
    if tang_nhap not in (None, ""):
        return str(tang_nhap)
    toi_da = max(5.0, 1.5 * max(vung_box.bounds[2] - vung_box.bounds[0], vung_box.bounds[3] - vung_box.bounds[1]))
    kq = _gan_nhat(ban_ve, vung_box, RE_TANG, them=lambda t: "MẶT BẰNG" in t.upper() or "MAT BANG" in t.upper(), toi_da=toi_da)
    if not kq:
        kq = _gan_nhat(ban_ve, vung_box, RE_TANG, toi_da=toi_da)
    if not kq:
        return "1"
    v = kq[0].group(1).upper()
    if v.isdigit():
        return str(int(v))
    if v.startswith("M"):  # tầng mái = số tầng lớn nhất trong bản vẽ + 1
        so = [int(m.group(1)) for c in _tat_ca_chu(ban_ve) for m in RE_TANG.finditer(_nfc(c.noi_dung)) if m.group(1).isdigit()]
        return str(max(so) + 1 if so else 2)
    return {"H": "H", "T": "0", "L": "L"}.get(v[0], "1")


def _tien_to_truc(ban_ve, vung_box):
    """Tiền tố tên trục. Ưu tiên tên trục có sẵn gần vùng (22aX1 -> 22a, trong 12 m), rồi mã hạng mục gần nhất
    ('22a - NHÀ BẢO VỆ'), rồi tên trục có sẵn bất kỳ."""
    truc, ma = [], []
    for c in _tat_ca_chu(ban_ve):
        d = vung_box.distance(c.diem)
        for dong in _nfc(c.noi_dung).splitlines():
            m = RE_TRUC_CHU.match(dong.strip())
            if m and m.group(1) and len(m.group(1)) <= 6:
                truc.append((d, m.group(1)))
            m = RE_MA_DU_AN.match(dong)
            if m:
                ma.append((d, m.group(1)))
    gan = [t for t in truc if t[0] <= 12]
    if gan:
        return Counter(p for d, p in gan if d <= min(x[0] for x in gan) + 12).most_common(1)[0][0]
    if ma:
        return min(ma)[1]
    return Counter(p for _, p in truc).most_common(1)[0][0] if truc else ""


def _chu_ghi_tiet_dien(ban_ve):
    """Các chữ ghi tiết diện dầm sẵn trong bản vẽ: danh sách (mã 'DX1', b mm, h mm, tầng hoặc None)."""
    ds = []
    for c in _tat_ca_chu(ban_ve):
        for dong in _nfc(c.noi_dung).splitlines():
            m = RE_DAM_CHU.match(dong)
            if m:
                ds.append((m.group(2).upper(), int(m.group(3)), int(m.group(4)), m.group(1)))
    return ds


def _tim_cao(ma, huong, b_mm, ghi_tiet, nhap, tang):
    """Chiều cao h (mm) của loại dầm: người nhập > bản vẽ có đúng tên và b > bản vẽ có b trùng và h duy nhất.
    Chữ có tiền tố tầng ('2.DX1-200X300') chỉ dùng cho đúng tầng đó."""
    if nhap.get(ma):
        return int(nhap[ma]), "nhập tay"
    ghi_tiet = [g for g in ghi_tiet if g[3] in (None, "", tang)]
    trung_ten = {h for (m, b, h, _) in ghi_tiet if m == ma and b == b_mm}
    if len(trung_ten) == 1:
        return trung_ten.pop(), "chữ trong bản vẽ"
    cung_b = {h for (m, b, h, _) in ghi_tiet if m.startswith("D" + huong) and b == b_mm}
    if len(cung_b) == 1:
        return cung_b.pop(), "chữ trong bản vẽ (theo b)"
    return None, None


# ---------- Trục ----------
def _truc_tu_layer(ban_ve, vung_box):
    doc, ngang = [], []  # (toạ độ, đầu mút nhỏ, đầu mút lớn)
    for ld in ban_ve.layers.values():
        if ld.tat or not RE_LAYER_TRUC.search(ld.ten):
            continue
        for n in ld.net_ho:
            if n.length < 1.0 or not vung_box.intersects(n):
                continue
            x0, y0, x1, y1 = n.bounds
            if x1 - x0 < 0.003 * n.length:
                doc.append(((x0 + x1) / 2, y0, y1))
            elif y1 - y0 < 0.003 * n.length:
                ngang.append(((y0 + y1) / 2, x0, x1))

    def gop(ds):
        kq = []
        for pos in _gom([d[0] for d in ds], 0.02):
            m = [d for d in ds if abs(d[0] - pos) <= 0.02]
            kq.append((pos, min(d[1] for d in m), max(d[2] for d in m)))
        return kq
    return gop(doc), gop(ngang)


def _truc_tu_dam(dam, canh_bao):
    canh_bao.append("Không thấy layer trục: suy trục từ tim dầm. Sếp đối chiếu với trục thật.")
    xs = _gom([d["cx"] for d in dam if d["huong"] == "Y"], 0.15)
    ys = _gom([d["cy"] for d in dam if d["huong"] == "X"], 0.15)
    x0 = min(d["geom"].bounds[0] for d in dam)
    y0 = min(d["geom"].bounds[1] for d in dam)
    x1 = max(d["geom"].bounds[2] for d in dam)
    y1 = max(d["geom"].bounds[3] for d in dam)
    return [(x, y0 - 0.3, y1 + 0.3) for x in xs], [(y, x0 - 0.3, x1 + 0.3) for y in ys]


def _bong_co_san(ban_ve, vung_box):
    kq = []
    for ld in ban_ve.layers.values():
        for h in ld.hinh_kin:
            if h.nguon != "CIRCLE":
                continue
            r = math.sqrt(h.geom.area / math.pi)
            if 0.08 <= r <= 1.2 and vung_box.buffer(2.5).intersects(h.geom):
                kq.append((h.geom.centroid.x, h.geom.centroid.y, r))
    return kq


# ---------- Chương trình chính ----------
def gan_nhan(ban_ve, loai_layer, vung, tuy_chon=None):
    """Sinh nhãn cho vùng mặt bằng `vung` = [x0, y0, x1, y1] (mét).

    tuy_chon: ty_le (mẫu số), tang (chuỗi), tien_to (tiền tố trục), cao_dam {"DX1": 400},
              nhan_dam, nhan_truc, nhan_cot (bool).
    Trả dict: ty_le, cao_chu, tang, tien_to, nhan (danh sách chữ), bong (vòng tròn trục cần vẽ thêm),
    loai_dam, canh_bao, da_co (số nhãn dầm đã có sẵn trong vùng).
    """
    tc = tuy_chon or {}
    canh_bao = []
    if len(vung) != 4:
        raise ValueError("Thiếu khung vùng mặt bằng cần gán nhãn.")
    x0, y0, x1, y1 = (float(v) for v in vung)
    vung_box = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    trong = cat_vung(ban_ve, vung)

    ty_le, nguon_ty_le = _ty_le(ban_ve, vung_box, canh_bao, tc.get("ty_le"))
    cao_chu = round(CHU_GIAY_MM / 1000 * ty_le, 4)
    tang = _tang(ban_ve, vung_box, tc.get("tang"))
    tien_to = tc["tien_to"] if tc.get("tien_to") is not None else _tien_to_truc(ban_ve, vung_box)
    ghi_tiet = _chu_ghi_tiet_dien(ban_ve)
    da_co = sum(1 for c in _tat_ca_chu(trong) for dong in _nfc(c.noi_dung).splitlines() if RE_DAM_CHU.match(dong))

    can_dam = tc.get("nhan_dam", True) or tc.get("nhan_truc", True) or tc.get("nhan_san", True)  # sàn cũng dựa vào dầm
    dam = _phan_loai_dam(_tim_dam(trong, loai_layer, canh_bao), canh_bao) if can_dam else []
    if not dam and can_dam:
        canh_bao.append("Không tìm thấy dầm trong vùng. Gán layer 'Dầm' (hoặc 'Khung dầm' + 'Ô trống giữa dầm') rồi thử lại.")

    # Chướng ngại để né: dầm, cột, chữ có sẵn
    cot_hinh = [h.geom for t, v in loai_layer.items() if v == "cot" and t in trong.layers for h in trong.layers[t].hinh_kin]
    if tc.get("nhan_cot", False) and not cot_hinh:  # chưa gán layer Cột: tự dò theo bảng kích thước cột ghi sẵn (40x60...)
        tu_do = _do_layer_cot(trong, loai_layer)
        if tu_do:
            cot_hinh = [h.geom for t in tu_do for h in trong.layers[t].hinh_kin]
            canh_bao.append(f'Chưa gán layer "Cột": tự dò các layer {", ".join(repr(t) for t in tu_do)} (hình chữ nhật đúng kích thước cột ghi trong bản vẽ). '
                            'Sếp kiểm tra, hoặc gán layer Cột ở tab Layer.')
    vat_can = [d["geom"] for d in dam] + [g for g in cot_hinh if g.area >= 0.005]
    hop_cu = [_hop_chu(c.diem.x, c.diem.y, c.goc, c.cao or cao_chu, c.neo, len(c.noi_dung.splitlines()[0]) if c.noi_dung else 1)
              for c in _tat_ca_chu(trong)]
    da_dat = []  # hộp của các nhãn mới

    def va_cham(hop):
        if any(hop.intersects(g) for g in vat_can) or any(hop.intersects(g) for g in hop_cu) or any(hop.intersects(g) for g in da_dat):
            return True
        return False

    nhan = []

    def them(loai, t, x, y, goc, cao, neo, **them_):
        da_dat.append(_hop_chu(x, y, goc, cao, neo, len(t)))
        nhan.append({"loai": loai, "t": t, "x": round(x, 4), "y": round(y, 4), "goc": round(goc, 2), "cao": cao, "neo": neo, **them_})

    # ----- Dầm -----
    loai_dam = []
    if tc.get("nhan_dam", True) and dam:
        thu_tu_vai_tro = {"bien": 0, "giua": 1}
        khoa = {}
        for d in dam:
            khoa.setdefault((d["huong"], d["b_mm"], d["vai_tro"]), []).append(d)
        cao_nhap = {k.upper(): v for k, v in (tc.get("cao_dam") or {}).items()}
        for huong in ("X", "Y"):
            ds_khoa = sorted((k for k in khoa if k[0] == huong), key=lambda k: (thu_tu_vai_tro[k[2]], -k[1]))
            for i, k in enumerate(ds_khoa, 1):
                ma = f"D{huong}{i}"
                h_mm, nguon_h = _tim_cao(ma, huong, k[1], ghi_tiet, cao_nhap, tang)
                ten = f"{tang}.{ma}" if tang else ma
                ds = khoa[k]
                loai_dam.append({"ma": ma, "ten": ten, "huong": huong, "b": k[1], "h": h_mm, "nguon_h": nguon_h,
                                 "vai_tro": k[2], "so_luong": len(ds), "tong_dai": round(sum(d["L"] for d in ds), 3)})
                chu = f"{ten}-{k[1]}X{h_mm if h_mm else '?'}"
                for d in ds:
                    d["chu"], d["ma"] = chu, ma
        chua_cao = [l["ma"] for l in loai_dam if not l["h"]]
        if chua_cao:
            canh_bao.append(f"Chưa biết chiều cao h của {', '.join(chua_cao)} (mặt bằng không có, bản vẽ cũng không ghi). "
                            "Sếp nhập h ở bảng loại dầm rồi gán lại; hiện nhãn ghi 'X?'.")
        for d in sorted(dam, key=lambda d: (d["huong"], d["cy"] if d["huong"] == "X" else d["cx"])):
            if "chu" not in d:
                continue
            _dat_nhan_dam(d, cao_chu, va_cham, them, d["chu"], canh_bao)

    ghi_de = {str(k).upper(): v for k, v in (tc.get("kt_mong") or {}).items()}  # sếp sửa số trong bảng loại (khoá = tên loại)
    loai_cot, loai_san, loai_coc = [], [], []

    # ----- Cột -----
    if tc.get("nhan_cot", False):
        if not cot_hinh:
            doc, ngang = _truc_tu_layer(trong, vung_box)
            if doc and ngang:  # bản vẽ chưa vẽ cột: đề xuất tên cột tại giao điểm lưới trục
                doc, ngang = sorted(doc), sorted(ngang)
                khe = KHE_NHAN * cao_chu
                gd = ghi_de.get("C") or {}
                kt = f" {int(gd['a'])}X{int(gd['b'])}" if gd.get("a") and gd.get("b") else ""
                for i, (x, _, _) in enumerate(doc, 1):
                    for j, (y, _, _) in enumerate(ngang, 1):
                        them("cot", f"C({tien_to}X{i}-Y{j}){kt}", x + khe, y + khe, 0.0, cao_chu, "bl")
                loai_cot.append({"ten": "C", "a": int(gd["a"]) if gd.get("a") else None, "b": int(gd["b"]) if gd.get("b") else None,
                                 "so_luong": len(doc) * len(ngang), "khac_nhau": False})
                canh_bao.append(f"Bản vẽ chưa có hình cột: đã đặt {len(doc) * len(ngang)} nhãn cột tại giao điểm lưới trục, "
                                "chỉ có tên vị trí, chưa có kích thước. Sếp bỏ nhãn ở vị trí không có cột và ghi kích thước sau.")
            else:
                canh_bao.append("Không tìm thấy cột trong vùng: chưa có layer nào được gán loại 'Cột' (hoặc layer đó không có hình kín "
                                "trong khung) và cũng không thấy lưới trục. Gán layer chứa hình cột là 'Cột' ở tab Layer rồi bấm Dán nhãn lại.")
        else:
            n0 = len(nhan)
            _nhan_cot(cot_hinh, cao_chu, va_cham, them, ghi_de, loai_cot)
            if len(nhan) == n0:
                canh_bao.append("Có hình cột nhưng không tìm được chỗ trống để đặt nhãn (đều vướng dầm/chữ khác).")

    # ----- Sàn -----
    if tc.get("nhan_san", True) and dam:
        _nhan_san(ban_ve, dam, tang, cao_chu, va_cham, them, canh_bao, ghi_de, loai_san)

    # ----- Móng -----
    loai_mong = []
    if tc.get("nhan_mong", True):
        n_mong = _nhan_mong(ban_ve, trong, loai_layer, cao_chu, va_cham, them, canh_bao, ghi_de=tc.get("kt_mong"), loai_mong=loai_mong)
        if not n_mong and any(_ten_mong(c.noi_dung) for c in _tat_ca_chu(trong)):
            canh_bao.append("Có chữ tên móng (F1...) nhưng không tìm thấy hình móng gần đó. Gán layer 'Móng' cho layer chứa hình móng rồi thử lại.")

    # ----- Cọc -----
    if tc.get("nhan_coc", True):
        _nhan_coc(ban_ve, trong, cao_chu, va_cham, them, canh_bao, ghi_de=ghi_de, loai_coc=loai_coc, loai_layer=loai_layer)  # tự báo lý do khi không dán được cọc nào

    # ----- Trục -----
    bong = []
    if tc.get("nhan_truc", True) and dam:
        doc, ngang = _truc_tu_layer(trong, vung_box)
        if not doc and not ngang:
            doc, ngang = _truc_tu_dam(dam, canh_bao)
        bong_cs = _bong_co_san(trong, vung_box)
        cao_truc = round(cao_chu * CHU_TRUC_TY_LE, 4)
        r_bong = BONG_TRUC_TY_LE * cao_truc
        for i, (x, ya, yb) in enumerate(doc, 1):  # trục đứng X1, X2... từ trái qua phải, chữ ở đầu dưới
            cx, cy, ve_bong = _tam_bong(bong_cs, x, ya, "doc", r_bong, cao_truc)
            them("truc", f"{tien_to}X{i}", cx, cy, 0.0, cao_truc, "mc")
            if ve_bong:
                bong.append({"x": round(cx, 4), "y": round(cy, 4), "r": round(r_bong, 4)})
        for j, (y, xa, xb) in enumerate(ngang, 1):  # trục ngang Y1, Y2... từ dưới lên, chữ ở đầu trái
            cx, cy, ve_bong = _tam_bong(bong_cs, y, xa, "ngang", r_bong, cao_truc)
            them("truc", f"{tien_to}Y{j}", cx, cy, 0.0, cao_truc, "mc")
            if ve_bong:
                bong.append({"x": round(cx, 4), "y": round(cy, 4), "r": round(r_bong, 4)})

    if da_co:
        canh_bao.append(f"Vùng này đã có {da_co} nhãn dầm trong bản vẽ; nhãn mới sẽ nằm cạnh/chồng lên, Sếp xem lại trước khi xuất.")
    return {"ty_le": ty_le, "nguon_ty_le": nguon_ty_le, "cao_chu": cao_chu, "tang": tang, "tien_to": tien_to,
            "nhan": nhan, "bong": bong, "loai_dam": loai_dam, "loai_mong": loai_mong, "loai_cot": loai_cot, "loai_coc": loai_coc, "loai_san": loai_san, "canh_bao": canh_bao, "da_co": da_co}


def _tam_bong(bong_cs, pos, dau, huong, r_bong, cao_truc):
    """Tâm bong bóng của một trục: lấy vòng tròn có sẵn ở đầu trục, không có thì đặt cách đầu trục và báo cần vẽ thêm."""
    tot, dm = None, 1e9
    for (bx, by, r) in bong_cs:
        if huong == "doc":
            if abs(bx - pos) < 0.06 and abs(by - dau) < 1.2 and by < dau + 0.3 and abs(by - dau) < dm:
                tot, dm = (bx, by), abs(by - dau)
        else:
            if abs(by - pos) < 0.06 and abs(bx - dau) < 1.2 and bx < dau + 0.3 and abs(bx - dau) < dm:
                tot, dm = (bx, by), abs(bx - dau)
    if tot:
        return tot[0], tot[1], False
    lui = r_bong + 0.5 * cao_truc
    return (pos, dau - lui, True) if huong == "doc" else (dau - lui, pos, True)


def _dat_nhan_dam(d, cao_chu, va_cham, them, chu, canh_bao):
    """Đặt nhãn của một dầm: giữa dầm, cạnh dầm phía trong khung trước, rồi phía kia; trượt dọc dầm nếu bị vướng."""
    x0, y0, x1, y1 = d["geom"].bounds
    khe = KHE_NHAN * cao_chu
    n = len(chu)
    cum = d["cum_bb"]
    tam_cum = ((cum[0] + cum[2]) / 2, (cum[1] + cum[3]) / 2)
    if d["huong"] == "X":
        phia_trong = "tren" if d["cy"] < tam_cum[1] else "duoi"
        phia = [phia_trong, "duoi" if phia_trong == "tren" else "tren"]
        goc = 0.0
    else:
        phia_trong = "phai" if d["cx"] < tam_cum[0] else "trai"
        phia = [phia_trong, "trai" if phia_trong == "phai" else "phai"]
        goc = 90.0
    for t in (0.5, 0.3, 0.7, 0.15, 0.85):
        for p in phia:
            if d["huong"] == "X":
                x = x0 + t * (x1 - x0)
                if p == "tren":
                    ox, oy, neo = x, y1 + khe, "bc"
                else:
                    ox, oy, neo = x, y0 - khe, "tc"
            else:
                y = y0 + t * (y1 - y0)
                if p == "trai":  # chữ xoay 90°: đáy chữ hướng sang phải, thân chữ lồi sang trái
                    ox, oy, neo = x0 - khe, y, "bc"
                else:
                    ox, oy, neo = x1 + khe, y, "tc"
            if not va_cham(_hop_chu(ox, oy, goc, cao_chu, neo, n)):
                them("dam", chu, ox, oy, goc, cao_chu, neo, ma=d["ma"])
                return
    # Vướng hết chỗ: vẫn đặt ở chỗ ưu tiên đầu tiên và báo
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if d["huong"] == "X":
        them("dam", chu, cx, y1 + khe, 0.0, cao_chu, "bc", ma=d["ma"])
    else:
        them("dam", chu, x0 - khe, cy, 90.0, cao_chu, "bc", ma=d["ma"])
    canh_bao.append(f"Nhãn {chu} không tìm được chỗ trống, đang đè lên nét khác. Sếp kéo nhãn sang chỗ thoáng trong CAD.")


RE_KT_COT_CM = re.compile(r"^\s*(\d{2,3})\s*[xX×]\s*(\d{2,3})\s*$")


def _do_layer_cot(trong, loai_layer):
    """Layer chứa hình cột khi sếp chưa gán: bản vẽ mặt bằng cột hay ghi kích thước (cm) kiểu "40x60", "40x80".
    Chọn các layer chưa gán loại khác có ít nhất 2 hình chữ nhật kín đúng một trong các kích thước đó (±5%)."""
    kt = set()
    for c in _tat_ca_chu(trong):
        m = RE_KT_COT_CM.match(_nfc(c.noi_dung))
        if m:
            a, b = int(m.group(1)) * 10, int(m.group(2)) * 10
            kt.add((max(a, b), min(a, b)))
    if not kt:
        return []
    khong = {t for t, v in loai_layer.items() if v in ("mong", "dam", "san", "khung_dam", "o_dam", "coc")}
    kq = []
    for t, ld in trong.layers.items():
        if t in khong:
            continue
        n = 0
        for h in ld.hinh_kin:
            if h.geom.area < 0.01 or h.geom.area > 4:
                continue
            a, b, dc = _hinh_chu_nhat(h.geom)
            if dc >= 0.95 and any(abs(a * 1000 - ka) <= 0.05 * ka and abs(b * 1000 - kb) <= 0.05 * kb for ka, kb in kt):
                n += 1
        if n >= 2:
            kq.append(t)
    return kq


def _nhan_cot(cot_hinh, cao_chu, va_cham, them, ghi_de=None, loai_cot=None):
    duy_nhat = []
    for g in sorted(cot_hinh, key=lambda g: -g.area):
        if g.area >= 0.005 and not any(g.intersection(u).area > 0.95 * g.area for u in duy_nhat):
            duy_nhat.append(g)
    loai = {}
    for g in duy_nhat:
        r = g.minimum_rotated_rectangle
        p = list(r.exterior.coords)[:4]
        a, b = math.hypot(p[1][0] - p[0][0], p[1][1] - p[0][1]), math.hypot(p[2][0] - p[1][0], p[2][1] - p[1][1])
        loai.setdefault((_lam_tron_mm(max(a, b)), _lam_tron_mm(min(a, b))), []).append(g)
    for i, (k, ds) in enumerate(sorted(loai.items(), key=lambda kv: -kv[0][0] * kv[0][1]), 1):
        gd = (ghi_de or {}).get(f"C{i}") or {}
        ka, kb = int(gd.get("a") or k[0]), int(gd.get("b") or k[1])
        chu = f"C{i}-{ka}X{kb}"
        if loai_cot is not None:
            loai_cot.append({"ten": f"C{i}", "a": ka, "b": kb, "so_luong": len(ds), "khac_nhau": False})
        for g in ds:
            x0, y0, x1, y1 = g.bounds
            khe = KHE_NHAN * cao_chu
            for ox, oy, neo in ((x1 + khe, (y0 + y1) / 2, "ml"), (x0 - khe, (y0 + y1) / 2, "mr"),
                                ((x0 + x1) / 2, y1 + khe, "bc"), ((x0 + x1) / 2, y0 - khe, "tc")):
                if not va_cham(_hop_chu(ox, oy, 0.0, cao_chu, neo, len(chu))):
                    them("cot", chu, ox, oy, 0.0, cao_chu, neo)
                    break


# ---------- Móng: tên + kích thước (F1 800x800x700) ----------
RE_TEN_MONG = re.compile(r"^\s*(?:M[OÓ]NG\s*)?(F|M|MG|FM|DM)\s*[.\-]?\s*(\d+[A-Z]?)\s*$", re.I)
RE_KT_MONG = re.compile(r"^\s*(\d{2,4})\s*[xX×]\s*(\d{2,4})(?:\s*[xX×]\s*(\d{2,4}))?\s*$")


def _ten_mong(t):
    m = RE_TEN_MONG.match(_nfc(t))
    return f"{m.group(1).upper()}{m.group(2).upper()}" if m else None


def _bang_thong_ke_mong(ban_ve):
    """Đọc "THỐNG KÊ MÓNG": tên móng (F1) và ô kích thước cùng hàng bên phải (800X800X700). Trả {tên: (a, b, h|None)} theo mm."""
    chu = _tat_ca_chu(ban_ve)
    kt = [(c, RE_KT_MONG.match(_nfc(c.noi_dung))) for c in chu]
    kt = [(c, m) for c, m in kt if m]
    bang = {}
    for c in chu:
        ten = _ten_mong(c.noi_dung)
        if not ten or ten in bang:
            continue
        cao = c.cao or 0.1
        tot = None
        for k, m in kt:
            dy, dx = abs(k.diem.y - c.diem.y), k.diem.x - c.diem.x
            if dy <= 0.5 * cao and 0 < dx <= 20 * cao and (tot is None or dx < tot[0]):
                tot = (dx, m)
        if tot:
            g = tot[1].groups()
            bang[ten] = (int(g[0]), int(g[1]), int(g[2]) if g[2] else None)
    return bang


def _hinh_chu_nhat(g):
    r = g.minimum_rotated_rectangle
    p = list(r.exterior.coords)[:4]
    a, b = math.hypot(p[1][0] - p[0][0], p[1][1] - p[0][1]), math.hypot(p[2][0] - p[1][0], p[2][1] - p[1][1])
    return max(a, b), min(a, b), g.area / max(r.area, 1e-12)


def _co_hinh_mong(chu_mong, ds_hinh, mong_layer, toi_da):
    """Đã có layer Móng gán sẵn và layer đó có hình chữ nhật nằm gần ít nhất một chữ tên móng?"""
    if not mong_layer:
        return False
    for c, _ in chu_mong:
        for t, g in ds_hinh:
            if t in mong_layer and g.distance(c.diem) <= toi_da and _hinh_chu_nhat(g)[2] >= 0.95:
                return True
    return False


def _do_layer_mong(chu_mong, ds_hinh, loai_layer, toi_da, dien_tich=(0.2, 80.0)):
    """Layer chưa gán loại nhưng chứa hình móng: mỗi chữ tên móng bỏ một phiếu cho layer của hình chữ nhật NHỎ NHẤT
    trong bán kính toi_da (ô lưới/ô sàn bao quanh móng luôn lớn hơn móng, chữ tên thường nằm trong ô đó).
    Bỏ hình quá nhỏ/quá lớn (ô cọc bên trong, khung bản vẽ) và layer đã gán cột/dầm/sàn. Layer nhiều phiếu nhất thắng."""
    khong = {t for t, v in loai_layer.items() if v in ("cot", "dam", "san", "khung_dam", "o_dam", "coc")}
    ung = [(t, g) for t, g in ds_hinh if t not in khong and dien_tich[0] <= g.area <= dien_tich[1] and _hinh_chu_nhat(g)[2] >= 0.95]
    phieu = Counter()
    for c, _ in chu_mong:
        tot = None
        for t, g in ung:
            if g.distance(c.diem) <= toi_da and (tot is None or g.area < tot[0]):
                tot = (g.area, t)
        if tot:
            phieu[tot[1]] += 1
    return phieu.most_common(1)[0][0] if phieu else None


def _nhan_mong(ban_ve, trong, loai_layer, cao_chu, va_cham, them, canh_bao, toi_da=1.5, ghi_de=None, loai_mong=None):
    """Mỗi chữ tên móng (F1) trong vùng → tìm hình móng gần nhất, ghi "F1 800x800x700".

    Kích thước: lấy từ bảng thống kê móng nếu có, đối chiếu với hình vẽ (lệch quá 5% thì cảnh báo).
    Không có bảng thì lấy theo hình vẽ, chiều sâu ghi "?". Hình móng: layer đã gán "Móng";
    chưa gán thì chọn hình chữ nhật gần chữ nhất có kích thước khớp bảng."""
    bang = _bang_thong_ke_mong(ban_ve)
    mong_layer = {t for t, v in loai_layer.items() if v == "mong"}
    ds_hinh = []
    for t, ld in trong.layers.items():
        for h in ld.hinh_kin:
            if h.geom.area >= 0.01:
                ds_hinh.append((t, h.geom))
    da_dat, so_nhan, thieu_sau, chong = set(), 0, {}, 0
    ghi_de = {str(k).upper(): v for k, v in (ghi_de or {}).items()}
    thong_ke = {}  # tên móng -> {kích thước (a, b, h): số lượng}
    chu_mong = [(c, _ten_mong(c.noi_dung)) for c in _tat_ca_chu(trong)]
    chu_mong = [(c, ten) for c, ten in chu_mong if ten]
    if chu_mong and not _co_hinh_mong(chu_mong, ds_hinh, mong_layer, toi_da):
        tu_do = _do_layer_mong(chu_mong, ds_hinh, loai_layer, toi_da)
        if tu_do:  # chưa gán layer Móng: tự chọn layer có hình chữ nhật gần chữ tên móng nhất
            mong_layer = {tu_do}
            canh_bao.append(f'Chưa gán layer "Móng": tự dò layer "{tu_do}" (hình chữ nhật gần chữ tên móng). Sếp kiểm tra, hoặc gán layer Móng ở tab Layer.')
    for c, ten in chu_mong:
        ung_vien = []
        for t, g in ds_hinh:
            d = g.distance(c.diem)
            if d > toi_da:
                continue
            a, b, do_chu_nhat = _hinh_chu_nhat(g)
            if do_chu_nhat < 0.95:
                continue
            if t in mong_layer:
                ung_vien.append((0, d, g, a, b))
            elif ten in bang:
                ta, tb = sorted(bang[ten][:2], reverse=True)
                if abs(a * 1000 - ta) <= 0.05 * ta and abs(b * 1000 - tb) <= 0.05 * tb:
                    ung_vien.append((1, d, g, a, b))
        if not ung_vien:
            continue
        ung_vien.sort(key=lambda u: (u[0], u[1]))
        _, _, g, a, b = ung_vien[0]
        for u in ung_vien:  # hình lồng nhau cùng layer (móng 600x600 có ô 300x300 bên trong): lấy hình ngoài cùng
            if u[0] == ung_vien[0][0] and u[2].area > g.area and u[2].contains(g.centroid):
                _, _, g, a, b = u
        x0, y0, x1, y1 = g.bounds
        khoa = (ten, round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2))
        if khoa in da_dat:
            continue
        da_dat.add(khoa)
        if ten in bang:
            ka, kb, kh = bang[ten]
            if abs(max(ka, kb) - a * 1000) > 0.05 * max(ka, kb) or abs(min(ka, kb) - b * 1000) > 0.05 * min(ka, kb):
                canh_bao.append(f"Móng {ten}: bảng thống kê ghi {ka}x{kb} nhưng hình vẽ đo {_lam_tron_mm(a)}x{_lam_tron_mm(b)}. Nhãn dùng số trong bảng.")
        else:
            ka, kb, kh = _lam_tron_mm(a), _lam_tron_mm(b), None
        gd = ghi_de.get(ten) or {}  # sếp nhập tay thì dùng số của sếp
        ka, kb = int(gd.get("a") or ka), int(gd.get("b") or kb)
        kh = int(gd.get("h") or 0) or kh
        thong_ke.setdefault(ten, Counter())[(ka, kb, kh or None)] += 1
        kich_thuoc = f"{ka}x{kb}x{kh if kh else '?'}"
        if not kh:
            thieu_sau[ten] = thieu_sau.get(ten, 0) + 1
        khe = KHE_NHAN * cao_chu
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        vi_tri = ((x1 + khe, y0, 0.0, "bl"), (x0 - khe, y0, 0.0, "br"), (cx, y0 - khe, 0.0, "tc"), (cx, y1 + khe, 0.0, "bc"),
                  (x1 + khe, cy, 90.0, "bl"), (x0 - khe, cy, 90.0, "br"))
        dat = False
        # Thử nhãn đầy đủ "M7 3000x2750x?" trước; chật quá thì chỉ ghi kích thước (tên móng đã có sẵn trong bản vẽ)
        for chu in (f"{ten} {kich_thuoc}", kich_thuoc):
            for ox, oy, goc, neo in vi_tri:
                if not va_cham(_hop_chu(ox, oy, goc, cao_chu, neo, len(chu))):
                    them("mong", chu, ox, oy, goc, cao_chu, neo)
                    dat = True
                    break
            if dat:
                break
        if not dat:
            them("mong", kich_thuoc, x1 + khe, y0, 0.0, cao_chu, "bl")
            chong += 1
        so_nhan += 1
    if loai_mong is not None:
        for ten, dem in sorted(thong_ke.items()):
            (ka, kb, kh), _ = dem.most_common(1)[0]
            loai_mong.append({"ten": ten, "a": ka, "b": kb, "h": kh, "so_luong": sum(dem.values()), "khac_nhau": len(dem) > 1})
    if chong:
        canh_bao.append(f"{chong} nhãn móng không tìm được chỗ trống nên chồng lên nét/chữ khác (mặt bằng móng dày). Sếp thử nhập Tỷ lệ 1/ nhỏ hơn (chữ nhỏ lại) rồi dán lại, hoặc dời nhãn trong CAD.")
    if thieu_sau:  # gộp một dòng cho cả loại, không lặp mỗi cái móng một cảnh báo
        ds = ", ".join(f"{t} ({n})" for t, n in sorted(thieu_sau.items()))
        canh_bao.append(f"Chưa biết chiều sâu móng {ds} (không có trong bảng thống kê móng), nhãn ghi '?'. Số trong ngoặc là số cái móng.")
    return so_nhan


# ---------- Cọc: tên + đường kính + chiều dài (P1 D300 L=16m) ----------
RE_TEN_COC = re.compile(r"^\s*P\s*[.\-]?\s*(\d+[A-Z]?)\s*$", re.I)
RE_SO = re.compile(r"^\s*(\d+(?:[.,]\d+)?)\s*$")


def _khong_dau(t):
    t = unicodedata.normalize("NFD", _nfc(t).replace("Đ", "D").replace("đ", "d"))
    return "".join(ch for ch in t if unicodedata.category(ch) != "Mn").upper()


def _so_ben_phai(ban_ve, c, toi_da_ky_tu=60):
    """Ô số nằm cùng hàng, bên phải chữ c và gần c nhất (dùng đọc bảng thống kê)."""
    cao = c.cao or 0.1
    tot = None
    for k in _tat_ca_chu(ban_ve):
        m = RE_SO.match(_nfc(k.noi_dung))
        if not m:
            continue
        dy, dx = abs(k.diem.y - c.diem.y), k.diem.x - c.diem.x
        if dy <= 0.5 * cao and 0 < dx <= toi_da_ky_tu * cao and (tot is None or dx < tot[0]):
            tot = (dx, float(m.group(1).replace(",", ".")))
    return tot[1] if tot else None


def _bang_coc(ban_ve):
    """Từ bảng "THỐNG KÊ CỌC": (đường kính mm, chiều dài m); mục không có thì None."""
    dk = dai = None
    for c in _tat_ca_chu(ban_ve):
        t = _khong_dau(c.noi_dung)
        if dk is None and "DUONG KINH COC" in t:
            v = _so_ben_phai(ban_ve, c)
            dk = int(v) if v else None
        elif dai is None and "CHIEU DAI COC" in t:
            dai = _so_ben_phai(ban_ve, c)
    if dk is None or dai is None:  # không có bảng → đọc từ ghi chú kiểu "COC D300 ... -L=22m, Lmax=22m"
        dk_gc, dai_gc = _ghi_chu_coc(ban_ve)
        dk = dk or dk_gc
        dai = dai or dai_gc
    return dk, dai


RE_GC_DK = re.compile(r"\bCOC\s*D\s*=?\s*(\d{2,4})\b")
RE_GC_DAI = re.compile(r"(?<![A-Z0-9])L\s*=\s*(\d+(?:[.,]\d+)?)\s*M\b")


def _ghi_chu_coc(ban_ve):
    """Đường kính (mm) và chiều dài (m) cọc từ ghi chú: "COC D300: SL=4 COC", "-L=22m, Lmax=22m, Ptk=30T".
    Chiều dài chỉ nhận ở dòng có Lmax/Lmin/Ptk/Pmax (đặc trưng ghi chú cọc) hoặc chữ nằm trong 3 m quanh dòng "COC Dxxx",
    để không nhầm "L=4.0m" của dầm. Chỉ nhận khi đúng một giá trị (nhiều giá trị khác nhau thì không đoán)."""
    dks, dais, goc = set(), set(), []
    chu_ds = [(c, _khong_dau(c.noi_dung)) for c in _tat_ca_chu(ban_ve)]
    for c, t in chu_ds:
        ks = [int(x) for dong in t.splitlines() for x in RE_GC_DK.findall(dong)]
        if ks:
            dks.update(ks)
            goc.append(c.diem)
    for c, t in chu_ds:
        for dong in t.splitlines():
            ds = [float(x.replace(",", ".")) for x in RE_GC_DAI.findall(dong)]
            if not ds:
                continue
            dac_trung = re.search(r"LMAX|LMIN|PTK|PMAX|PMIN", dong)
            if dac_trung or any(c.diem.distance(g) <= 3.0 for g in goc):
                dais.update(ds)
    return (dks.pop() if len(dks) == 1 else None), (dais.pop() if len(dais) == 1 else None)


def _nhan_coc(ban_ve, trong, cao_chu, va_cham, them, canh_bao, toi_da=0.8, ghi_de=None, loai_coc=None, loai_layer=None):
    dk_bang, dai_bang = _bang_coc(ban_ve)
    tron = []
    for ld in trong.layers.values():
        for h in ld.hinh_kin:
            g = h.geom
            x0, y0, x1, y1 = g.bounds
            d = max(x1 - x0, y1 - y0)
            if 0.05 <= d <= 3.0 and g.area / (math.pi * (d / 2) ** 2) >= 0.9:
                tron.append((g, d))
    ten_coc = [c for c in _tat_ca_chu(trong) if RE_TEN_COC.match(_nfc(c.noi_dung))]
    da_dat, so, lech_dk = set(), 0, []
    ghi_de, thong_ke, thieu_dai = ghi_de or {}, {}, 0
    for c in ten_coc:
        m = RE_TEN_COC.match(_nfc(c.noi_dung))
        ten = f"P{m.group(1).upper()}"
        gan = [(g.distance(c.diem), g, d) for g, d in tron if g.distance(c.diem) <= toi_da]
        if not gan:
            continue
        # Đúng đường kính trong bảng thống kê trước; nếu không khớp cái nào thì vẫn dán theo hình vẽ và báo lại.
        uv = [u for u in gan if not dk_bang or abs(u[2] * 1000 - dk_bang) <= 0.05 * dk_bang]
        if not uv:
            uv = gan
            lech_dk.append(_lam_tron_mm(min(u[2] for u in gan)))
        kc, g, d = min(uv, key=lambda u: u[0])
        x0, y0, x1, y1 = g.bounds
        khoa = (ten, round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2))
        if khoa in da_dat:
            continue
        da_dat.add(khoa)
        dung_bang = bool(dk_bang) and abs(d * 1000 - dk_bang) <= 0.05 * dk_bang
        dk = dk_bang if dung_bang else _lam_tron_mm(d)
        gd = ghi_de.get(ten) or {}  # sếp nhập tay: d (mm), l (m)
        dk = int(gd.get("d") or dk)
        dai = float(gd.get("l") or 0) or dai_bang
        thong_ke.setdefault(ten, Counter())[(dk, dai)] += 1
        thieu_dai += 0 if dai else 1
        chu = f"{ten} D{dk}" + (f" L={dai:g}m" if dai else "")
        khe, cy, cx = KHE_NHAN * cao_chu, (y0 + y1) / 2, (x0 + x1) / 2
        dat = False
        for ox, oy, neo in ((x1 + khe, cy, "ml"), (x0 - khe, cy, "mr"), (cx, y0 - khe, "tc"), (cx, y1 + khe, "bc")):
            if not va_cham(_hop_chu(ox, oy, 0.0, cao_chu, neo, len(chu))):
                them("coc", chu, ox, oy, 0.0, cao_chu, neo)
                dat = True
                break
        if not dat:
            them("coc", chu, x1 + khe, cy, 0.0, cao_chu, "ml")
        so += 1
    if so and not dk_bang:
        canh_bao.append("Cọc: không đọc được đường kính từ bảng thống kê cọc, nhãn dùng số đo từ hình vẽ.")
    if not ten_coc and tron:  # không có chữ P1...: dán "D300 L=.." cho hình tròn đúng đường kính cọc ở layer cọc
        so = _nhan_coc_khong_ten(trong, tron, dk_bang, dai_bang, ghi_de, cao_chu, va_cham, them, canh_bao, loai_layer or {}, thong_ke)
    if loai_coc is not None:
        for ten, dem in sorted(thong_ke.items(), key=lambda kv: (len(kv[0]), kv[0])):
            (dk, dai), _ = dem.most_common(1)[0]
            loai_coc.append({"ten": ten, "d": dk, "l": dai, "so_luong": sum(dem.values()), "khac_nhau": len(dem) > 1})
    if so and thieu_dai:
        canh_bao.append("Cọc: không đọc được chiều dài cọc từ bảng thống kê, nhãn không ghi L.")
    if lech_dk:
        canh_bao.append(f"Cọc: hình tròn đo được D{sorted(set(lech_dk))} không khớp đường kính bảng thống kê D{dk_bang}. "
                        "Nhãn ghi theo hình vẽ, Sếp kiểm tra lại.")
    if not so:  # báo lý do thay vì trả 0 nhãn im lặng
        so_tron = len(tron)
        if ten_coc and not so_tron:
            canh_bao.append(f"Cọc: có {len(ten_coc)} chữ tên cọc (P1...) nhưng không thấy hình tròn cọc trong vùng. "
                            "Kiểm tra layer chứa hình cọc (tròn kín, đường kính 0,05-3 m).")
        elif ten_coc:
            canh_bao.append(f"Cọc: có {len(ten_coc)} chữ tên cọc nhưng không có hình tròn cọc nào nằm trong {toi_da} m quanh chữ.")
        elif so_tron:
            canh_bao.append(f"Cọc: thấy {so_tron} hình tròn cọc nhưng không có chữ tên cọc (P1...) trong vùng, nên không dán nhãn cọc.")
        else:
            canh_bao.append("Cọc: không thấy hình tròn cọc cũng không thấy chữ tên cọc (P1...) trong vùng.")
    return so


RE_LAYER_COC = re.compile(r"pile|c[oọ]c", re.I)


def _nhan_coc_khong_ten(trong, tron, dk_bang, dai_bang, ghi_de, cao_chu, va_cham, them, canh_bao, loai_layer, thong_ke):
    """Bản vẽ chỉ vẽ hình tròn cọc, không ghi tên P1...: chọn layer cọc (đã gán "Cọc" hoặc tên có pile/cọc, nhiều hình tròn nhất),
    mỗi hình tròn đúng đường kính cọc nhận nhãn "D300 L=22m". Khoá bảng sửa số là "P"."""
    ten_layer = {t for t, v in loai_layer.items() if v == "coc"}
    dem = Counter()
    ds = []
    for t, ld in trong.layers.items():
        if t not in ten_layer and not RE_LAYER_COC.search(t):
            continue
        for h in ld.hinh_kin:
            x0, y0, x1, y1 = h.geom.bounds
            d = max(x1 - x0, y1 - y0)
            if 0.05 <= d <= 3.0 and h.geom.area / (math.pi * (d / 2) ** 2) >= 0.9:
                ds.append((t, h.geom, d))
                dem[_lam_tron_mm(d, 10)] += 1
    if not ds:
        return 0
    dk0 = dk_bang or dem.most_common(1)[0][0]
    gd = ghi_de.get("P") or {}
    dk = int(gd.get("d") or dk0)
    dai = float(gd.get("l") or 0) or dai_bang
    da, so, chong = set(), 0, 0
    chu = f"D{dk}" + (f" L={dai:g}m" if dai else "")
    for t, g, d in ds:
        if abs(d * 1000 - dk0) > 0.05 * dk0:
            continue
        x0, y0, x1, y1 = g.bounds
        khoa = (round((x0 + x1) / 2, 2), round((y0 + y1) / 2, 2))
        if khoa in da:
            continue
        da.add(khoa)
        khe, cx, cy = KHE_NHAN * cao_chu, (x0 + x1) / 2, (y0 + y1) / 2
        for ox, oy, neo in ((x1 + khe, cy, "ml"), (x0 - khe, cy, "mr"), (cx, y0 - khe, "tc"), (cx, y1 + khe, "bc")):
            if not va_cham(_hop_chu(ox, oy, 0.0, cao_chu, neo, len(chu))):
                them("coc", chu, ox, oy, 0.0, cao_chu, neo)
                so += 1
                break
        else:
            chong += 1
    if so:
        thong_ke.setdefault("P", Counter())[(dk, dai)] = so
        canh_bao.append(f"Cọc: bản vẽ không ghi tên cọc (P1...), đã dán nhãn \"{chu}\" cho {so} cọc ở layer {', '.join(sorted({t for t, _, _ in ds}))}. "
                        "Sếp kiểm tra layer và đường kính; sửa D, L ở bảng loại cọc.")
        if not dai:
            canh_bao.append("Cọc: chưa biết chiều dài L (không có trong bảng thống kê cọc/ghi chú). Nhập L ở bảng loại cọc.")
    if chong:
        canh_bao.append(f"Cọc: {chong} cọc không còn chỗ trống để đặt nhãn (dày quá). Thử nhập Tỷ lệ 1/ nhỏ hơn rồi dán lại.")
    return so


# ---------- Sàn: S1 t=100 ----------
RE_GHI_CHU_SAN = re.compile(r"S[ÀA]N\s+(.+?)\s+D[ÀA]Y\s*(\d{2,3})\s*mm", re.I)


def _day_san(ban_ve, tang):
    """Chiều dày sàn (mm) từ ghi chú kiểu "SÀN TẦNG 1 DÀY 100mm". Trả (mm | None, nguồn)."""
    ds = []
    for c in _tat_ca_chu(ban_ve):
        for dong in _nfc(c.noi_dung).splitlines():
            m = RE_GHI_CHU_SAN.search(dong)
            if m:
                ds.append((_khong_dau(m.group(1)), int(m.group(2))))
    if tang:
        khop = {mm for ten, mm in ds if re.search(rf"TANG\s*{re.escape(_khong_dau(tang))}\b", ten)}
        if len(khop) == 1:
            return khop.pop(), f"ghi chú sàn tầng {tang}"
    tat_ca = {mm for _, mm in ds}
    if len(tat_ca) == 1:
        return tat_ca.pop(), "ghi chú bản vẽ"
    return None, ""


def _nhan_san(ban_ve, dam, tang, cao_chu, va_cham, them, canh_bao, ghi_de=None, loai_san=None):
    """Ô sàn = lỗ hổng bên trong cụm dầm. Mỗi ô ghi "S1 t={mm}"."""
    cum = unary_union([d["geom"].buffer(0.01) for d in dam])
    cum = [cum] if cum.geom_type == "Polygon" else list(cum.geoms)
    o = [Polygon(ring) for c in cum for ring in c.interiors if Polygon(ring).area >= 0.3]
    if not o:
        canh_bao.append("Sàn: không thấy ô sàn nào (lỗ kín ≥ 0,3 m² nằm giữa các dầm) nên không dán nhãn sàn. "
                        "Mặt bằng móng thường không có sàn; mặt bằng sàn thì kiểm tra layer dầm đã gán đúng chưa.")
        return 0
    t_mm, _ = _day_san(ban_ve, tang)
    t_mm = int((ghi_de or {}).get("S1", {}).get("t") or 0) or t_mm
    if loai_san is not None:
        loai_san.append({"ten": "S1", "t": t_mm, "so_luong": len(o), "khac_nhau": False})
    if not t_mm:
        canh_bao.append("Sàn: bản vẽ không có ghi chú chiều dày sàn (kiểu 'SÀN TẦNG 1 DÀY 100mm'), nhãn ghi 't=?'.")
    chu = f"S1 t={t_mm if t_mm else '?'}"
    for g in sorted(o, key=lambda g: (-g.centroid.y, g.centroid.x)):
        cx, cy = g.centroid.x, g.centroid.y
        x0, y0, x1, y1 = g.bounds
        dat = False
        for dx, dy in ((0, 0), (0, 0.15), (0, -0.15), (0.3, 0), (-0.3, 0)):
            ox, oy = cx + dx * (x1 - x0), cy + dy * (y1 - y0)
            if not va_cham(_hop_chu(ox, oy, 0.0, cao_chu, "mc", len(chu))):
                them("san", chu, ox, oy, 0.0, cao_chu, "mc")
                dat = True
                break
        if not dat:
            them("san", chu, cx, cy, 0.0, cao_chu, "mc")
    return len(o)


# ---------- Xuất DXF có nhãn ----------
def ve_nhan_vao_dxf(doc, he_so, ket_qua, mau=6):
    """Thêm nhãn (TEXT) và bong bóng trục (CIRCLE) vào bản vẽ ezdxf, trên layer AZB-NHAN. Toạ độ đổi từ mét về đơn vị bản vẽ."""
    from ezdxf.enums import TextEntityAlignment as A
    neo_map = {"bl": A.BOTTOM_LEFT, "bc": A.BOTTOM_CENTER, "br": A.BOTTOM_RIGHT, "ml": A.MIDDLE_LEFT, "mc": A.MIDDLE_CENTER,
               "mr": A.MIDDLE_RIGHT, "tl": A.TOP_LEFT, "tc": A.TOP_CENTER, "tr": A.TOP_RIGHT}
    if TEN_LAYER_NHAN not in doc.layers:
        doc.layers.add(TEN_LAYER_NHAN, color=mau)
    msp = doc.modelspace()
    for n in ket_qua["nhan"]:
        e = msp.add_text(n["t"], dxfattribs={"layer": TEN_LAYER_NHAN, "height": n["cao"] / he_so, "rotation": n["goc"]})
        e.set_placement((n["x"] / he_so, n["y"] / he_so), align=neo_map[n["neo"]])
    for b in ket_qua["bong"]:
        msp.add_circle((b["x"] / he_so, b["y"] / he_so), b["r"] / he_so, dxfattribs={"layer": TEN_LAYER_NHAN})
    return len(ket_qua["nhan"])
