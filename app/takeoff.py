"""Tính khối lượng kết cấu từ mặt bằng 2D.

Quy tắc chống tính trùng (mặc định, ghi rõ trong README):
- Sàn: toàn bộ diện tích mặt sàn (kể cả phần nằm trên dầm, cột, vách) x chiều dày sàn.
- Cột, vách có sàn phía trên: cao = chiều cao tầng - dày sàn (tính đến mặt dưới sàn).
- Dầm: chiều dài thông thủy giữa mép cột/vách; dầm có sàn phía trên lấy cao = h - dày sàn.
- Hai dầm giao nhau: phần giao tính cho dầm cao hơn.
- Ván khuôn trừ các mặt tiếp giáp (đầu dầm vào cột, dầm phụ gác vào dầm chính, cột giáp vách).

Mọi khối lượng được viết thành từng dòng diễn giải "số lượng x dài x rộng x cao"
để Excel tính lại bằng công thức, kỹ sư dò ngược được từng con số.
"""
import math
import re

import shapely
from shapely.ops import unary_union

from . import config
from .dam_suy_ra import suy_dam
from .dxf_reader import HinhKin
from .nha_tu_ban_ve import cua_tu_mat_dung, doc_cao_do

TOL = 1e-4  # m, dải đo chiều dài tiếp giáp giữa hai hình
HO_TIEP_XUC = 0.002  # m, hai hình hở nhau dưới 2 mm vẫn coi là tiếp giáp
SAT_SAN = 0.01  # m, cấu kiện cách mép sàn dưới 1 cm coi như nằm dưới sàn

# Tiền tố tên cấu kiện trên nhãn -> loại. Thứ tự kiểm tra từ trên xuống.
TIEN_TO_NHAN = [
    ("mong", r"^(M|F|PC)"),
    ("vach", r"^(V|W|LT|VL)"),
    ("cot", r"^(C|K)"),
    ("san", r"^(S|Ô|O)"),
    ("dam", r"^(D|B|GB|DC|DP|DS|DM)"),
]

RE_KICH_THUOC = re.compile(r"\d+(?:[.,]\d+)?(?:\s*[xX×*]\s*\d+(?:[.,]\d+)?)+")
RE_DAY = re.compile(r"(?<![A-Za-z])([tThH])\s*=\s*(\d+(?:[.,]\d+)?)")


def _so(s):
    v = float(s.replace(",", "."))
    return v / 1000 if v > 5 else v  # nhãn > 5 hiểu là mm


def doc_nhan(noi_dung):
    """'D1 220x500' -> {'ten': 'D1', 'loai': 'dam', 'kt': [0.22, 0.5]}"""
    # Tiền tố tầng "1.DX1-200X400" -> "DX1-200X400"
    s = re.sub(r"^\d+\s*\.\s*(?=[A-Za-zÔô])", "", noi_dung.strip())
    ten = re.split(r"[\s(\[]", s, maxsplit=1)[0].upper()
    kq = {"ten": ten, "loai": None, "kt": [], "day": None, "noi_dung": s}
    m = RE_KICH_THUOC.search(s)
    if m:
        kq["kt"] = [_so(x) for x in re.split(r"\s*[xX×*]\s*", m.group(0))]
    m = RE_DAY.search(s)
    if m:
        kq["day"] = _so(m.group(2))
    co_so_lieu = bool(kq["kt"] or kq["day"])
    for loai, mau in TIEN_TO_NHAN:
        if re.match(mau + r"\d", ten) or (co_so_lieu and re.match(mau, ten)):
            kq["loai"] = loai
            break
    return kq


def _hcn(g):
    """Nếu g là hình chữ nhật (kể cả xoay) thì trả (dài, rộng), ngược lại None."""
    if g.geom_type != "Polygon" or g.interiors or g.area <= 0:
        return None
    r = g.minimum_rotated_rectangle
    if abs(r.area - g.area) / g.area > 0.002:
        return None
    xy = list(r.exterior.coords)
    a = math.dist(xy[0], xy[1])
    b = math.dist(xy[1], xy[2])
    return (max(a, b), min(a, b))


def _manh(g):
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [x for x in getattr(g, "geoms", []) if x.geom_type == "Polygon" and x.area > 0]


def _dai_rong_min(g):
    """Cạnh ngắn của hình chữ nhật bao xoay nhỏ nhất (m)."""
    xy = list(g.minimum_rotated_rectangle.exterior.coords)
    return min(math.dist(xy[0], xy[1]), math.dist(xy[1], xy[2]))


def _tiep_xuc(a, b):
    """Chiều dài đoạn biên chung giữa hai hình không chồng nhau."""
    if a.is_empty or b.is_empty:
        return 0.0
    kc = a.distance(b)
    if kc > HO_TIEP_XUC:
        return 0.0
    L = shapely.intersection(a.boundary, b.boundary, grid_size=1e-6).length
    if L == 0:
        # Hai hình hở nhau vài mm do vẽ: đo gần đúng bằng dải bao
        d = kc + TOL
        L = a.buffer(d).intersection(b).area / TOL  # dải chồng lên b rộng d - kc = TOL
    return L


DAY_TUONG_MAC_DINH = 0.2    # m - bề dày tường khi chỉ có nét đơn
CAO_CUA = 2.1               # m - chiều cao ô cửa; phía trên là lanh tô
DAY_MAI = 0.15              # m
VUON_MAI = 0.3              # m - mái đua khi hình không phải chữ nhật
VUON_MAI_DAI = 0.3          # m - mái đua theo chiều dài nhà
VUON_MAI_NGAN = 1.0         # m - mái đua theo bề rộng nhà (mặt cắt ghi 1000 hai bên)
DAY_VACH_NGAN = 0.1         # m - vách ngăn ốp tôn


def _r(x):
    return None if x is None else round(x, 4)


class _BoTinh:
    def __init__(self, ban_ve, loai_layer, thong_so, dieu_chinh, ban_ve_goc=None):
        self.bv = ban_ve
        self.goc = ban_ve_goc or ban_ve     # bản vẽ đầy đủ (chưa cắt vùng): đọc cao độ, cửa ở các hình khác
        self.loai_layer = loai_layer
        self.ts = thong_so
        self.dc = dieu_chinh or {}
        self.kt = config.app_config()["kiem_tra"]
        self.n = float(thong_so.get("so_tang_giong_nhau", 1) or 1)
        self.canh_bao_chung = list(ban_ve.canh_bao)
        self.dong = []
        self.ck = []  # danh sách cấu kiện (dict)
        self.coc = []  # hình cọc (tròn) để dựng 3D; không tham gia bóc khối lượng

    # ---------- tiện ích ----------
    def them_dong(self, cong_tac, ck, dien_giai, n, dai=None, rong=None, cao=None, dien_tich=None):
        tp = [_r(x) for x in (dai, rong, cao, dien_tich)]
        gia_tri = n
        for x in tp:
            if x is not None:
                gia_tri *= x
        if abs(gia_tri) < 1e-9:
            return
        self.dong.append({
            "cong_tac": cong_tac, "ck_id": ck["id"], "ten_ck": ck["ten"], "dien_giai": dien_giai,
            "n": n, "dai": tp[0], "rong": tp[1], "cao": tp[2], "dien_tich": tp[3], "gia_tri": gia_tri,
        })

    def cb(self, ck, muc, noi_dung):
        ck["canh_bao"].append({"muc": muc, "noi_dung": noi_dung})

    # ---------- bước 1: gom hình theo loại ----------
    def gom_hinh(self):
        theo_loai = {k: [] for k in ("cot", "dam", "san", "lo_san", "mong", "vach", "tuong", "cua")}
        nguong = self.kt["nguong_trung_lap"]
        dt_min = self.kt["dien_tich_toi_thieu"]
        bo_qua_co_hinh = []  # (tên layer, số hình kín đủ lớn) của layer đang bị bỏ qua
        so_hinh_nho = {}     # tên layer -> số hình quá nhỏ bị loại
        coc_layer = []       # layer gán "Cọc": không bóc ở đây, cọc tính bằng công cụ Tính KL cọc
        for ten, ld in self.bv.layers.items():
            loai = self.loai_layer.get(ten, "bo_qua")
            if loai == "bo_qua":
                n = sum(1 for h in ld.hinh_kin if h.geom.area >= dt_min)
                if n:
                    bo_qua_co_hinh.append((ten, n))
            if loai == "coc":
                if any(h.geom.area >= dt_min for h in ld.hinh_kin):
                    coc_layer.append(ten)
                for h in ld.hinh_kin:
                    x0, y0, x1, y1 = h.geom.bounds
                    dk = max(x1 - x0, y1 - y0)
                    if 0.05 <= dk <= 3.0 and h.geom.area >= 0.002:
                        self.coc.append({"x": h.geom.centroid.x, "y": h.geom.centroid.y, "d": dk, "layer": ten, "handle": h.handle})
                continue
            if loai not in theo_loai:
                continue
            nho = sum(1 for h in ld.hinh_kin if h.geom.area < dt_min)
            if nho:
                so_hinh_nho[ten] = nho
            if ld.tat:
                self.canh_bao_chung.append(f"Layer {ten} đang tắt/đóng băng trong CAD nhưng vẫn được tính, Sếp kiểm tra.")
            if ld.net_ho:
                so_ghep = sum(1 for h in ld.hinh_kin if h.nguon == "GHEP_NET")
                self.canh_bao_chung.append(
                    f"Layer {ten}: {len(ld.net_ho)} nét rời/polyline hở, ghép được {so_ghep} hình kín. "
                    "Nét không ghép được sẽ không tính."
                )
            for h in ld.hinh_kin:
                if h.geom.area < dt_min:
                    continue
                theo_loai[loai].append((h, ten))
            if loai == "tuong":
                self._tuong_tu_net(ld, ten, theo_loai, dt_min)

        if coc_layer:
            self.canh_bao_chung.append(
                f"Layer gán 'Cọc' ({', '.join(coc_layer[:6])}) không bóc ở đây. Cọc tính bằng công cụ 'Tính KL cọc' (cột trái).")
        if bo_qua_co_hinh:
            bo_qua_co_hinh.sort(key=lambda t: -t[1])
            ds_ten = ", ".join(f"{t} ({n} hình)" for t, n in bo_qua_co_hinh[:8])
            them = f" và {len(bo_qua_co_hinh) - 8} layer khác" if len(bo_qua_co_hinh) > 8 else ""
            self.canh_bao_chung.append(
                f"{len(bo_qua_co_hinh)} layer có hình kín nhưng đang gán 'Bỏ qua' nên KHÔNG được tính: {ds_ten}{them}. "
                "Nếu trong đó có cột, dầm, sàn, móng, vách thì Sếp gán lại loại layer rồi tính lại.")
        for ten, n in so_hinh_nho.items():
            self.canh_bao_chung.append(
                f"Layer {ten}: {n} hình kín nhỏ hơn {dt_min * 1e4:g} cm² bị loại (coi là nét chi tiết), không tính.")

        so_trung = {}
        for loai, ds in theo_loai.items():
            ds.sort(key=lambda x: -x[0].geom.area)
            giu = []
            for h, ten in ds:
                trung = None
                for h2, _ in giu:
                    giao = h.geom.intersection(h2.geom).area
                    hop = h.geom.union(h2.geom).area
                    if hop > 0 and giao / hop >= nguong:
                        trung = h2
                        break
                if trung:
                    so_trung[ten] = so_trung.get(ten, 0) + 1
                    continue
                giu.append((h, ten))
            # Thứ tự đọc: trên xuống, trái sang phải
            giu.sort(key=lambda x: (-round(x[0].geom.centroid.y, 1), round(x[0].geom.centroid.x, 1)))
            for i, (h, ten) in enumerate(giu, 1):
                self.ck.append({
                    "id": f"{loai}-{i}", "loai": loai, "ten": "", "nhan": "", "layer": ten,
                    "handle": h.handle, "nguon": h.nguon, "geom": h.geom, "thong_so": {}, "canh_bao": [],
                })
        for ten, n in so_trung.items():
            self.canh_bao_chung.append(
                f"Layer {ten}: {n} hình vẽ trùng nhau (thường là hatch + polyline cùng một hình), mỗi hình chỉ tính một lần.")
        self._tuong_cua_mai()

    def _tuong_tu_net(self, ld, ten, theo_loai, dt_min):
        """Tường vẽ bằng nét: hai nét song song cách nhau <= 0,45 m là hai mặt của một bức tường (lấp khe giữa);
        nét đơn bù thành dải dày 0,2 m. Hình kín quá to (khung mặt đứng / mặt cắt, không phải tường) bị bỏ."""
        if ld.net_ho:
            lines = [ln for ln in ld.net_ho if ln.length >= 0.3]
            if lines:
                r = 0.225
                dai = unary_union(lines)
                khep = dai.buffer(r, cap_style=3, join_style=2).buffer(-r, join_style=2)
                le = dai.difference(khep.buffer(0.02))      # phần nét không nằm trong cặp song song
                don = le.buffer(DAY_TUONG_MAC_DINH / 2, cap_style=2, join_style=2) if not le.is_empty else None
                for i, p in enumerate(_manh(unary_union([khep, don] if don is not None else [khep]))):
                    if p.area >= dt_min:
                        theo_loai["tuong"].append((HinhKin(p, f"net{i}", "NET_TUONG"), ten))
        # Hình kín lớn (đường bao ngoài của nhà) không phải một bức tường đặc: dựng thành vành tường dày mặc định
        so_vanh = 0
        for k, (h, t) in enumerate(theo_loai["tuong"]):
            if t != ten or h.nguon == "NET_TUONG" or h.geom.area <= 3 or _dai_rong_min(h.geom) <= 0.8:
                continue
            vanh = h.geom.difference(h.geom.buffer(-DAY_TUONG_MAC_DINH, join_style=2))
            if not vanh.is_empty:
                theo_loai["tuong"][k] = (HinhKin(vanh, h.handle, h.nguon), t)
                so_vanh += 1
        if so_vanh:
            self.canh_bao_chung.append(
                f"Layer {ten}: {so_vanh} hình kín lớn (đường bao nhà) được dựng thành vành tường dày {DAY_TUONG_MAC_DINH * 1000:.0f} mm. "
                "Nếu layer này lẫn mặt đứng / mặt cắt thì Sếp chọn vùng quanh đúng mặt bằng.")

    def _cum_tuong(self, tuong, khoang=1.5):
        """Gom các mảnh tường cách nhau <= khoang thành từng công trình. Trả list các list chỉ số vào `tuong`."""
        n = len(tuong)
        cha = list(range(n))

        def goc(i):
            while cha[i] != i:
                cha[i] = cha[cha[i]]
                i = cha[i]
            return i
        for i in range(n):
            for j in range(i + 1, n):
                if tuong[i]["geom"].distance(tuong[j]["geom"]) <= khoang:
                    cha[goc(i)] = goc(j)
        cum = {}
        for i in range(n):
            cum.setdefault(goc(i), []).append(i)
        return list(cum.values())

    def _tuong_cua_mai(self):
        """Tường (extrude theo cao thật), cửa khoét tường kèm lanh tô, vách ngăn giữa các cửa, mái dốc có mái đua.
        Số liệu lấy từ bản vẽ: cao độ mái ghi '+6.050 / +6.800' ở mặt cắt, cửa vẽ ở mặt đứng (cùng trục x với mặt bằng)."""
        tuong = [c for c in self.ck if c["loai"] == "tuong"]
        cua = [c for c in self.ck if c["loai"] == "cua"]
        if not tuong:
            return
        # 1) bỏ mảnh tường rời nằm ngoài ngôi nhà (cụm nhỏ hơn 6 m2 khi đã có cụm lớn hơn)
        cum = self._cum_tuong(tuong)
        hull = [unary_union([tuong[i]["geom"] for i in c]).convex_hull for c in cum]
        if any(h.area >= 6.0 for h in hull):
            bo = [tuong[i] for c, h in zip(cum, hull) if h.area < 6.0 for i in c]
            if bo:
                ids = {id(c) for c in bo}
                self.ck = [c for c in self.ck if id(c) not in ids]
                tuong = [c for c in tuong if id(c) not in ids]
                self.canh_bao_chung.append(f"Bỏ {len(bo)} mảnh tường rời nằm ngoài ngôi nhà (không chạm tường nào, cụm nhỏ).")
        H = float(self.ts["chieu_cao_tang"])
        cao = doc_cao_do(self.goc)
        if cao:
            H = cao[0]
            self.canh_bao_chung.append(f"Chiều cao tường {H:g} m và mái dốc {cao[0]:g} đến {cao[1]:g} m đọc từ cao độ ghi trên bản vẽ (mặt cắt).")
        nen = unary_union([c["geom"] for c in tuong])
        x0, y0, x1, y1 = nen.bounds
        # 2) cửa: ưu tiên hình cửa nằm ngay trong mặt bằng, không có thì lấy cửa vẽ ở mặt đứng cùng dải trục x
        cua_pt = []          # (hộp khoét, chiều cao cửa)
        for c in cua:
            b = c["geom"].bounds
            if max(b[2] - b[0], b[3] - b[1]) <= 4.0 and b[2] >= x0 - 0.5 and b[0] <= x1 + 0.5 and b[3] >= y0 - 0.5 and b[1] <= y1 + 0.5:
                cua_pt.append((shapely.geometry.box(*b).buffer(0.02), CAO_CUA))
        dung = []
        if not cua_pt:
            dung = cua_tu_mat_dung(self.goc, self.loai_layer, x0, x1, (y0, y1))
            for a, b, h in dung:
                cua_pt.append((shapely.geometry.box(a, y0 - 0.05, b, y0 + 0.25), h))
            if dung:
                self.canh_bao_chung.append(f"Cửa: {len(dung)} cửa lấy từ mặt đứng (cùng trục x với mặt bằng), khoét ở tường phía y nhỏ (mặt trước).")
        moi = []
        for c in tuong:
            g = c["geom"]
            c["thong_so"] = {"cao": H}
            hit = [(b, h) for b, h in cua_pt if g.intersects(b) and g.intersection(b).area >= 0.05]   # bỏ vệt giao nhỏ ở góc tường
            if not hit:
                continue
            c["geom"] = g.difference(unary_union([b for b, _ in hit]))
            for j, (b, h) in enumerate(hit):
                for k, q in enumerate(x for x in _manh(g.intersection(b)) if x.area > 1e-4):
                    base = {"layer": c["layer"], "handle": c["handle"], "nguon": c["nguon"], "nhan": "", "canh_bao": []}
                    moi.append(dict(base, id=f"{c['id']}-lt{j + 1}.{k + 1}", loai="tuong", geom=q, ten=f"Lanh tô {c['id']}-{j + 1}",
                                    thong_so={"z0": h, "cao": max(H - h, 0.05)}))
                    moi.append(dict(base, id=f"{c['id']}-cua{j + 1}.{k + 1}", loai="cua", geom=q, ten=f"Cửa {c['id']}-{j + 1}", thong_so={"cao": h}))
        # 3) vách ngăn: mỗi cửa là một gian riêng, vách đặt giữa hai cửa liền kề (từ tường trước tới tường sau)
        if len(dung) >= 2:
            day = DAY_VACH_NGAN
            for i, ((a0, a1, _), (b0, b1, _)) in enumerate(zip(dung, dung[1:]), 1):
                xm = (a1 + b0) / 2
                g = shapely.geometry.box(xm - day / 2, y0, xm + day / 2, y1).difference(nen)
                for q in _manh(g):
                    if q.area > 1e-3:
                        moi.append({"id": f"vach-ngan-{i}", "loai": "tuong", "ten": f"Vách ngăn {i}", "nhan": "", "layer": tuong[0]["layer"], "handle": "",
                                    "nguon": "TU_SINH", "geom": q, "thong_so": {"cao": H}, "canh_bao": []})
            self.canh_bao_chung.append(f"Vách ngăn: dựng {len(dung) - 1} vách dày {day * 1000:.0f} mm giữa các cửa (suy ra từ số cửa, Sếp đối chiếu mặt bằng).")
        self.ck = [c for c in self.ck if c["loai"] != "cua"]
        self.ck = [c for c in self.ck if not (c["loai"] == "tuong" and c["geom"].is_empty)]
        self.ck += moi
        # 4) mái: gom cụm tường, phủ tấm phẳng lên bao lồi; dốc về phía cửa, đua 1 m theo bề rộng nhà, 0,3 m theo chiều dài
        manh = _manh(unary_union([c["geom"] for c in self.ck if c["loai"] == "tuong"]))
        ds = []
        for c in self._cum_tuong([{"geom": p} for p in manh]):
            h = unary_union([manh[i] for i in c]).convex_hull
            if h.geom_type == "Polygon" and h.area >= 6.0 and _dai_rong_min(h) >= 2.0:
                bx0, by0, bx1, by1 = h.bounds
                if h.area / ((bx1 - bx0) * (by1 - by0)) >= 0.95:           # gần chữ nhật nằm theo trục
                    dai_x = (bx1 - bx0) > (by1 - by0)
                    dx, dy = (VUON_MAI_DAI, VUON_MAI_NGAN) if dai_x else (VUON_MAI_NGAN, VUON_MAI_DAI)
                    ds.append((shapely.geometry.box(bx0 - dx, by0 - dy, bx1 + dx, by1 + dy), dai_x))
                else:
                    ds.append((h.buffer(VUON_MAI, join_style=2), None))
        co_cua = bool(cua_pt)
        for i, (f, dai_x) in enumerate(ds, 1):
            ts = {"day": DAY_MAI}
            if cao:
                ts["z_thap"], ts["z_cao"] = cao[0], cao[1]
                if cao[1] > cao[0] + 1e-6 and dai_x is not None:
                    # dốc theo bề rộng nhà, cao về phía có cửa (mặt trước = y nhỏ); không có cửa thì cao về phía y lớn / x lớn
                    if dai_x:
                        ts["huong"] = [0, -1] if co_cua else [0, 1]
                    else:
                        ts["huong"] = [-1, 0] if co_cua else [1, 0]
            self.ck.append({"id": f"mai-{i}", "loai": "mai", "ten": f"Mái {i}", "nhan": "", "layer": tuong[0]["layer"], "handle": "", "nguon": "TU_SINH",
                            "geom": f, "thong_so": ts, "canh_bao": []})

    # ---------- bước 2: gán nhãn ----------
    def gan_nhan(self):
        nhan = []
        for ten, ld in self.bv.layers.items():
            loai = self.loai_layer.get(ten, "bo_qua")
            if loai in ("bo_qua", "khung_dam", "o_dam", "coc") or loai in config.LOAI_MEP:
                continue
            for c in ld.chu:
                n = doc_nhan(c.noi_dung)
                if n["loai"]:
                    nhan.append((n, c))
        d_max = self.kt["khoang_cach_nhan_toi_da"]
        self.nhan_khong_gan = []
        ung_vien = {}  # ck id -> list (khoảng cách, nhan)
        for n, c in nhan:
            ds = [ck for ck in self.ck if ck["loai"] == n["loai"]]
            kc = sorted(((ck["geom"].distance(c.diem), ck) for ck in ds), key=lambda x: x[0])
            if not kc or kc[0][0] > d_max:
                self.nhan_khong_gan.append({"noi_dung": n["noi_dung"], "x": c.diem.x, "y": c.diem.y})
                continue
            d0, ck0 = kc[0]
            if d0 > 0 and len(kc) > 1 and kc[1][0] < 1.2 * d0:
                self.cb(ck0, "canh_bao", f"Nhãn '{n['noi_dung']}' nằm gần cả {kc[1][1]['id']}, Sếp kiểm tra gán đúng chưa.")
            ung_vien.setdefault(ck0["id"], []).append((d0, n))
        for ck in self.ck:
            ds = sorted(ung_vien.get(ck["id"], []), key=lambda x: x[0])
            if not ds:
                continue
            if ck["loai"] == "dam" and len(ds) > 1 and _hcn(ck["geom"]):
                # Nhiều nhãn dầm quanh dầm này: ưu tiên nhãn có bề rộng khớp bề rộng vẽ
                w = _hcn(ck["geom"])[1]
                lech = self.kt["lech_kich_thuoc_nhan"]
                khop = [x for x in ds if x[1]["kt"] and abs(x[1]["kt"][0] - w) / w <= lech]
                ds = khop + [x for x in ds if x not in khop]
            n = ds[0][1]
            ck["ten"], ck["nhan"], ck["_nhan"] = n["ten"], n["noi_dung"], n
            khac = {x[1]["noi_dung"] for x in ds[1:]} - {n["noi_dung"]}
            if khac:
                self.cb(ck, "canh_bao", f"Có nhiều nhãn khác nhau: {', '.join(khac)}. Đang dùng '{n['noi_dung']}'.")

    # ---------- bước 3: thông số từng cấu kiện ----------
    def lay_thong_so(self):
        ts = self.ts
        lech = self.kt["lech_kich_thuoc_nhan"]
        h_min, h_max = self.kt.get("h_dam_hop_ly", [0.15, 2.0])
        t_min, t_max = self.kt.get("day_san_hop_ly", [0.05, 0.6])
        # Dầm có nhãn bxh: (bề rộng, h) dùng để suy h cho dầm cùng bề rộng không có nhãn
        dam_co_nhan = []
        for ck in self.ck:
            n = ck.get("_nhan")
            hcn = _hcn(ck["geom"]) if ck["loai"] == "dam" else None
            if hcn and n and len(n["kt"]) >= 2 and not self.dc.get(ck["id"], {}).get("loai_bo"):
                dam_co_nhan.append((hcn[1], n["kt"][1]))
        con = []
        for ck in self.ck:
            dc = self.dc.get(ck["id"], {})
            if dc.get("loai_bo"):
                continue
            if dc.get("ten"):
                ck["ten"] = dc["ten"]
            if not ck["ten"]:
                ck["ten"] = ck["id"].upper()
            n = ck.get("_nhan") or {"kt": [], "day": None}
            g = ck["geom"]
            hcn = _hcn(g)
            if ck["loai"] == "dam":
                if dc.get("h"):
                    h, nguon = float(dc["h"]), "điều chỉnh"
                elif len(n["kt"]) >= 2:
                    h, nguon = n["kt"][1], "nhãn"
                elif n["day"]:
                    h, nguon = n["day"], "nhãn"
                else:
                    cung_rong = {round(hh, 4) for w, hh in dam_co_nhan if hcn and abs(w - hcn[1]) / hcn[1] <= lech}
                    if len(cung_rong) == 1:
                        h, nguon = cung_rong.pop(), "suy ra theo bề rộng"
                        self.cb(ck, "canh_bao", f"Dầm không có nhãn, lấy h = {h*1000:.0f} mm theo dầm có nhãn cùng bề rộng "
                                                f"{hcn[1]*1000:.0f} mm. Sếp kiểm tra.")
                    else:
                        h, nguon = float(ts["chieu_cao_dam"]), "mặc định"
                        them = (f" Các dầm có nhãn cùng bề rộng có h khác nhau: "
                                f"{', '.join(f'{x*1000:.0f}' for x in sorted(cung_rong))} mm." if cung_rong else "")
                        self.cb(ck, "canh_bao", f"Dầm không có nhãn kích thước, đang dùng h mặc định {h} m.{them}")
                if not h_min <= h <= h_max:
                    self.cb(ck, "canh_bao", f"h dầm {h} m nằm ngoài khoảng hợp lý {h_min}-{h_max} m (nhãn ghi cm chăng?).")
                ck["thong_so"].update(h=h, nguon_h=nguon)
                if n["kt"] and hcn and abs(hcn[1] - n["kt"][0]) / n["kt"][0] > lech:
                    self.cb(ck, "canh_bao", f"Bề rộng vẽ {hcn[1]*1000:.0f} mm khác nhãn {n['kt'][0]*1000:.0f} mm.")
            elif ck["loai"] == "san":
                if dc.get("t"):
                    t, nguon = float(dc["t"]), "điều chỉnh"
                elif n["day"]:
                    t, nguon = n["day"], "nhãn"
                else:
                    t, nguon = float(ts["day_san"]), "mặc định"
                    self.cb(ck, "canh_bao", f"Ô sàn không có nhãn chiều dày, đang dùng t mặc định {t} m.")
                if not t_min <= t <= t_max:
                    self.cb(ck, "canh_bao", f"Chiều dày sàn {t} m nằm ngoài khoảng hợp lý {t_min}-{t_max} m (nhãn ghi cm chăng?).")
                ck["thong_so"].update(t=t, nguon_t=nguon)
            elif ck["loai"] == "mong":
                if dc.get("day"):
                    d, nguon = float(dc["day"]), "điều chỉnh"
                elif len(n["kt"]) >= 3:
                    d, nguon = n["kt"][2], "nhãn"
                elif n["day"]:
                    d, nguon = n["day"], "nhãn"
                else:
                    d, nguon = float(ts["day_mong"]), "mặc định"
                    self.cb(ck, "canh_bao", f"Móng không có nhãn chiều cao, đang dùng {d} m.")
                ck["thong_so"].update(day=d, nguon_day=nguon)
            if ck["loai"] in ("cot", "mong") and len(n["kt"]) >= 2 and hcn:
                a, b = sorted(n["kt"][:2], reverse=True)
                if abs(hcn[0] - a) / a > lech or abs(hcn[1] - b) / b > lech:
                    self.cb(ck, "canh_bao",
                            f"Kích thước vẽ {hcn[0]*1000:.0f}x{hcn[1]*1000:.0f} khác nhãn {a*1000:.0f}x{b*1000:.0f}.")
            if ck["loai"] in ("cot", "vach") and dc.get("cao"):
                ck["thong_so"]["cao_dc"] = float(dc["cao"])
            con.append(ck)
        self.ck_tinh = con

    # ---------- kiểm tra đơn vị bản vẽ ----------
    def kiem_tra_don_vi(self):
        """So kích thước ghi trên nhãn cột/móng với hình vẽ gần nhất (chưa lọc hình nhỏ, không giới hạn khoảng cách).
        Lệch cùng một hệ số 10, 100, 1000 ở đa số nhãn thì nhiều khả năng sai đơn vị bản vẽ."""
        hinh = [h.geom for t, ld in self.bv.layers.items() if self.loai_layer.get(t) in ("cot", "mong")
                for h in ld.hinh_kin]
        if not hinh:
            return
        r = []
        for t, ld in self.bv.layers.items():
            if self.loai_layer.get(t, "bo_qua") in ("bo_qua", "khung_dam", "o_dam") or self.loai_layer.get(t, "bo_qua") in config.LOAI_MEP:
                continue
            for c in ld.chu:
                n = doc_nhan(c.noi_dung)
                if n["loai"] not in ("cot", "mong") or len(n["kt"]) < 2 or len(r) >= 60:
                    continue
                g = min(hinh, key=lambda x: x.distance(c.diem))
                hcn = _hcn(g)
                if hcn:
                    r.append(hcn[0] / max(n["kt"][:2]))
        if len(r) < 2:
            return
        r_giua = sorted(r)[len(r) // 2]
        for he in (0.001, 0.01, 0.1, 10, 100, 1000):
            if abs(r_giua / he - 1) <= 0.1 and sum(1 for x in r if abs(x / he - 1) <= 0.1) >= 0.5 * len(r):
                self.canh_bao_chung.append(
                    f"NGHI SAI ĐƠN VỊ BẢN VẼ: hình vẽ của {len(r)} cột/móng gấp khoảng {he:g} lần kích thước trên nhãn. "
                    "Sếp chọn đơn vị bản vẽ (mm/cm/m) khi tải lên rồi tính lại.")
                return

    # ---------- bước 4: tính ----------
    def tinh(self):
        theo = {k: [c for c in self.ck_tinh if c["loai"] == k] for k in ("cot", "vach", "dam", "san", "lo_san", "mong")}
        H = float(self.ts["chieu_cao_tang"])
        n = self.n

        def tru_dan(ds, nen=None, bao_chong=True):
            """Hình sau trừ phần đã thuộc hình trước (và trừ nền)."""
            da = nen
            for c in ds:
                net = c["geom"] if da is None else c["geom"].difference(da)
                if bao_chong and net.area < c["geom"].area * 0.99:
                    phan = (c["geom"].area - net.area) / c["geom"].area
                    self.cb(c, "canh_bao", f"Chồng lấn {phan:.0%} với cấu kiện khác, phần chồng chỉ tính một lần.")
                c["net"] = net
                da = c["geom"] if da is None else unary_union([da, c["geom"]])
            return da

        vung_cot = tru_dan(theo["cot"])
        vung_cv = tru_dan(theo["vach"], vung_cot)
        # Dầm cao hơn được ưu tiên giữ phần giao
        dam = sorted(theo["dam"], key=lambda c: (-c["thong_so"]["h"], -c["geom"].area))
        tru_dan(dam, vung_cv, bao_chong=False)  # dầm giao cột, giao dầm là bình thường
        lo = unary_union([c["geom"] for c in theo["lo_san"]]) if theo["lo_san"] else None
        tru_dan(theo["san"])
        for s in theo["san"]:
            if lo is not None:
                s["net"] = s["net"].difference(lo)
        san = [s for s in theo["san"] if s["net"].area > 0]
        vung_san = unary_union([s["net"] for s in san]) if san else None

        # Cấu kiện nào nằm dưới sàn, thuộc ô sàn nào
        phan_them = {s["id"]: [] for s in san}

        def gan_san(c, o):
            c["t_tren"] = o["thong_so"]["t"]
            c["san_tren"] = o["id"]
            ngoai = c["net"].difference(vung_san)
            if ngoai.area > 1e-6:
                phan_them[o["id"]].append(ngoai)

        # Dầm trước (sàn gác lên dầm), rồi cột/vách: cột chạm dầm đã có sàn thì đỉnh cột cũng ở đáy sàn
        for c in dam + theo["cot"] + theo["vach"]:
            c["t_tren"] = 0.0
            if vung_san is None or c["net"].is_empty:
                continue
            if c["net"].distance(vung_san) <= SAT_SAN:
                gan_san(c, max(san, key=lambda s: c["net"].buffer(SAT_SAN).intersection(s["net"]).area))
            elif c["loai"] in ("cot", "vach"):
                ke = sorted((d for d in dam if d.get("san_tren") and c["net"].distance(d["net"]) <= SAT_SAN),
                            key=lambda d: -_tiep_xuc(d["net"], c["net"]))
                if ke:
                    gan_san(c, next(s for s in san if s["id"] == ke[0]["san_tren"]))
                    self.cb(c, "thong_tin", f"Không chạm ô sàn, lấy sàn trên theo dầm {ke[0]['ten']} liền kề.")
                else:
                    self.cb(c, "thong_tin", "Không có sàn phía trên, tính cao bằng chiều cao tầng.")

        for c in dam:
            c["h_tinh"] = c["thong_so"]["h"] - c["t_tren"]
            if c["h_tinh"] <= 0:
                self.cb(c, "loi", "Chiều cao dầm nhỏ hơn hoặc bằng dày sàn, Sếp kiểm tra nhãn.")
                c["h_tinh"] = 0.0
        for c in theo["cot"] + theo["vach"]:
            c["cao_tinh"] = c["thong_so"].get("cao_dc") or (H - c["t_tren"])
            c["thong_so"]["cao"] = c["cao_tinh"]

        # --- Cột và vách ---
        for c in theo["cot"] + theo["vach"]:
            loai = c["loai"]
            ma_bt, ma_vk = ("be_tong_cot", "van_khuon_cot") if loai == "cot" else ("be_tong_vach", "van_khuon_vach")
            net, cao = c["net"], c["cao_tinh"]
            for m in _manh(net):
                hcn = _hcn(m)
                if hcn:
                    self.them_dong(ma_bt, c, f"{hcn[0]*1000:.0f}x{hcn[1]*1000:.0f}", n, dai=hcn[0], rong=hcn[1], cao=cao)
                else:
                    self.them_dong(ma_bt, c, "Tiết diện theo hình vẽ", n, dien_tich=m.area, cao=cao)
            self.them_dong(ma_vk, c, "Chu vi x chiều cao", n, dai=net.length, cao=cao)
            for d in dam:
                L = _tiep_xuc(d["net"], net)
                if L > 0:
                    self.them_dong(ma_vk, c, f"Trừ chỗ dầm {d['ten']} liên kết", -n, dai=L, cao=min(d["h_tinh"], cao))
            for k in theo["cot"] + theo["vach"]:
                if k is c:
                    continue
                L = _tiep_xuc(k["net"], net)
                if L > 0:
                    self.them_dong(ma_vk, c, f"Trừ mặt giáp {k['ten']}", -n, dai=L, cao=min(k["cao_tinh"], cao))

        # --- Dầm ---
        cv = [k for k in theo["cot"] + theo["vach"] if not k["net"].is_empty]
        for i, d in enumerate(dam):
            net, h = d["net"], d["h_tinh"]
            if net.is_empty:
                self.cb(d, "canh_bao", "Dầm nằm trọn trong cột/vách/dầm khác, không có khối lượng riêng.")
                continue
            ghi = "h - dày sàn" if d["t_tren"] else "h"
            for m in _manh(net):
                hcn = _hcn(m)
                if hcn:
                    self.them_dong("be_tong_dam", d, f"Dài thông thủy x b x ({ghi})", n, dai=hcn[0], rong=hcn[1], cao=h)
                else:
                    self.them_dong("be_tong_dam", d, f"Diện tích mặt bằng x ({ghi})", n, dien_tich=m.area, cao=h)
            # Thành dầm: chu vi trừ đoạn giáp cột/vách và giáp dầm cao hơn
            giap = sum(_tiep_xuc(k["net"], net) for k in cv)
            giap += sum(_tiep_xuc(k["net"], net) for k in dam[:i])
            self.them_dong("van_khuon_dam", d, f"Thành dầm: chu vi tự do x ({ghi})", n, dai=net.length - giap, cao=h)
            for k in dam[i + 1:]:
                L = _tiep_xuc(k["net"], net)
                if L > 0:
                    self.them_dong("van_khuon_dam", d, f"Trừ chỗ dầm {k['ten']} gác vào", -n, dai=L, cao=min(k["h_tinh"], h))
            self.them_dong("van_khuon_dam", d, "Đáy dầm", n, dien_tich=net.area)

        # --- Sàn ---
        if san:
            duoi_san = unary_union([c["net"] for c in theo["cot"] + theo["vach"] + dam if c.get("san_tren")])
            vung_r = unary_union([s["net"] for s in san] + [g for ds in phan_them.values() for g in ds])
            # Làm liền khe hở nhỏ giữa ô sàn và mép dầm/cột, nếu không mép trong bị tính thành sàn hai lần
            vung_r = vung_r.buffer(SAT_SAN / 2, join_style=2).buffer(-SAT_SAN / 2, join_style=2)
            mep = vung_r.boundary
            for s in san:
                t = s["thong_so"]["t"]
                them = unary_union(phan_them[s["id"]]) if phan_them[s["id"]] else None
                self.them_dong("be_tong_san", s, "Diện tích ô sàn (đã trừ lỗ mở) x t", n, dien_tich=s["net"].area, cao=t)
                if them is not None:
                    self.them_dong("be_tong_san", s, "Phần sàn trên dầm/cột ngoài đường bao ô sàn", n,
                                   dien_tich=them.area, cao=t)
                self.them_dong("van_khuon_san", s, "Đáy sàn", n, dien_tich=s["net"].area)
                if not duoi_san.is_empty:
                    tru = s["net"].intersection(duoi_san).area
                    self.them_dong("van_khuon_san", s, "Trừ phần đáy dầm, đầu cột, vách", -n, dien_tich=tru)
                vung_s = s["net"] if them is None else unary_union([s["net"], them])
                L = mep.intersection(vung_s.buffer(TOL)).length
                self.them_dong("van_khuon_san", s, "Thành sàn (mép ngoài, mép lỗ mở) x t", n, dai=L, cao=t)

        # --- Móng ---
        tru_dan(theo["mong"])
        mo = float(self.ts["lot_mong_mo_rong"])
        day_lot = float(self.ts["lot_mong_day"])
        for m in theo["mong"]:
            d = m["thong_so"]["day"]
            for p in _manh(m["net"]):
                hcn = _hcn(p)
                if hcn:
                    self.them_dong("be_tong_mong", m, f"{hcn[0]*1000:.0f}x{hcn[1]*1000:.0f}", n, dai=hcn[0], rong=hcn[1], cao=d)
                    self.them_dong("be_tong_lot_mong", m, f"Mở rộng {mo*1000:.0f} mỗi phía", n,
                                   dai=hcn[0] + 2 * mo, rong=hcn[1] + 2 * mo, cao=day_lot)
                else:
                    self.them_dong("be_tong_mong", m, "Diện tích theo hình vẽ", n, dien_tich=p.area, cao=d)
                    self.them_dong("be_tong_lot_mong", m, f"Mở rộng {mo*1000:.0f} mỗi phía", n,
                                   dien_tich=p.buffer(mo, join_style=2).area, cao=day_lot)
            self.them_dong("van_khuon_mong", m, "Chu vi x chiều cao", n, dai=m["net"].length, cao=d)

    # ---------- kết quả ----------
    def ket_qua(self):
        ct = config.cong_tac()
        tong = {}
        for d in self.dong:
            tong[d["cong_tac"]] = tong.get(d["cong_tac"], 0.0) + d["gia_tri"]
        tong_hop = [
            {"ma": k, "ten": v["ten"], "don_vi": v["don_vi"], "ma_hieu": v.get("ma_hieu") or "", "khoi_luong": tong[k]}
            for k, v in ct.items() if k in tong
        ]
        thu_tu = list(ct.keys())
        self.dong.sort(key=lambda d: thu_tu.index(d["cong_tac"]) if d["cong_tac"] in thu_tu else 99)

        tinh = {c["id"] for c in self.ck_tinh}
        ds_ck = []
        for c in self.ck:
            ts = dict(c["thong_so"])
            if "h_tinh" in c:
                ts["h_tinh"] = c["h_tinh"]
            ds_ck.append({
                "id": c["id"], "loai": c["loai"], "ten": c["ten"] or c["id"].upper(), "nhan": c["nhan"],
                "layer": c["layer"], "handle": c["handle"], "nguon": c["nguon"], "thong_so": ts,
                "canh_bao": c["canh_bao"], "loai_bo": c["id"] not in tinh,
                "hinh": _toa_do(c["geom"]),
            })
        giu, thay = [], set()   # cọc vẽ hai lần chồng nhau (hai vòng tròn cùng tâm) chỉ tính một
        for c in self.coc:
            k = (round(c["x"], 2), round(c["y"], 2))
            if k not in thay:
                thay.add(k)
                giu.append(c)
        coc = sorted(giu, key=lambda c: (-round(c["y"], 1), round(c["x"], 1)))
        ds_coc = [{"id": f"coc-{i}", "ten": f"P{i}", "x": round(c["x"], 3), "y": round(c["y"], 3), "d": round(c["d"], 3),
                   "layer": c["layer"], "handle": c["handle"]} for i, c in enumerate(coc, 1)]
        hinh_all = [c["geom"] for c in self.ck]
        khung = list(unary_union(hinh_all).bounds) if hinh_all else [0, 0, 1, 1]
        return {
            "don_vi": self.bv.don_vi, "ten_file": self.bv.ten_file, "thong_so": self.ts,
            "canh_bao_chung": self.canh_bao_chung, "nhan_khong_gan": self.nhan_khong_gan,
            "cau_kien": ds_ck, "coc": ds_coc, "dong": self.dong, "tong_hop": tong_hop, "khung": khung,
        }


def _toa_do(g):
    kq = []
    for p in _manh(g):
        kq.append([[[round(x, 3), round(y, 3)] for x, y in p.exterior.coords]] +
                  [[[round(x, 3), round(y, 3)] for x, y in r.coords] for r in p.interiors])
    return kq


def thong_so_mac_dinh():
    return dict(config.app_config()["mac_dinh"])


def boc_khoi_luong(ban_ve, loai_layer, thong_so=None, dieu_chinh=None, ban_ve_goc=None):
    ts = thong_so_mac_dinh()
    ts.update({k: v for k, v in (thong_so or {}).items() if v not in (None, "")})
    ban_ve, loai_layer = suy_dam(ban_ve, loai_layer)
    bt = _BoTinh(ban_ve, loai_layer, ts, dieu_chinh, ban_ve_goc)
    bt.gom_hinh()
    bt.kiem_tra_don_vi()
    bt.gan_nhan()
    bt.lay_thong_so()
    bt.tinh()
    return bt.ket_qua()
