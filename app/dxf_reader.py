"""Đọc bản vẽ DWG/DXF, gom hình kín và chữ theo từng layer.

Toàn bộ tọa độ trả ra đã đổi sang mét.
"""
import math
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

import ezdxf
from ezdxf import path as ezpath
from ezdxf.addons import odafc
from shapely.geometry import LineString, Point, Polygon, box
from shapely.ops import polygonize, unary_union
from shapely.validation import make_valid

# Mã $INSUNITS trong DXF -> hệ số đổi ra mét
HE_SO_DON_VI = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0}
TEN_DON_VI = {"mm": 0.001, "cm": 0.01, "m": 1.0}

KHUNG_GIAY_M2 = 200.0  # hình kín lớn hơn mức này (m2) coi là khung giấy, không vẽ ở hình tổng quan

DO_MIN_CUNG_M = 0.00005  # sai số (m) khi chia cung tròn thành đoạn thẳng, đổi ra đơn vị bản vẽ khi dùng


@dataclass
class HinhKin:
    geom: Polygon
    handle: str
    nguon: str  # loại entity gốc: LWPOLYLINE, HATCH, CIRCLE, GHEP_NET...


@dataclass
class Chu:
    noi_dung: str
    diem: Point
    handle: str
    cao: float = 0.0  # chiều cao chữ (m); 0 = không rõ
    goc: float = 0.0  # góc xoay (độ)
    neo: str = "bl"  # điểm neo: hàng t/m/b (trên/giữa/dưới) + cột l/c/r (trái/giữa/phải)
    rong: float = 1.0  # hệ số giãn chữ (width factor)


@dataclass
class LayerData:
    ten: str
    hinh_kin: list = field(default_factory=list)
    net_ho: list = field(default_factory=list)  # LineString chưa khép kín
    chu: list = field(default_factory=list)
    tat: bool = False  # layer đang tắt hoặc đóng băng trong CAD


@dataclass
class BanVe:
    ten_file: str
    he_so: float  # đơn vị bản vẽ -> m
    don_vi: str
    layers: dict
    canh_bao: list
    doc: object = None  # ezdxf Drawing gốc, dùng cho bóc ống gió (MLINE, block)


def _doc_file(duong_dan, oda_path=None):
    duong_dan = Path(duong_dan)
    if duong_dan.suffix.lower() == ".dwg":
        if not oda_path or not Path(oda_path).exists():
            raise RuntimeError(
                "File DWG cần ODA File Converter để đổi sang DXF. "
                "Sếp cài ODA File Converter rồi sửa oda_path trong config/app.yaml, "
                "hoặc trong AutoCAD lưu bản vẽ dưới dạng DXF (SAVEAS > DXF) rồi tải lên."
            )
        ezdxf.options.set("odafc-addon", "win_exec_path", str(oda_path))
        return odafc.readfile(str(duong_dan))
    return ezdxf.readfile(str(duong_dan))


def _xac_dinh_don_vi(doc, don_vi_chon, canh_bao):
    if don_vi_chon in TEN_DON_VI:
        return TEN_DON_VI[don_vi_chon], don_vi_chon
    ma = doc.header.get("$INSUNITS", 0)
    if ma in HE_SO_DON_VI:
        ten = {1: "inch", 2: "feet", 4: "mm", 5: "cm", 6: "m"}[ma]
        return HE_SO_DON_VI[ma], ten
    canh_bao.append("Bản vẽ không khai báo đơn vị ($INSUNITS). Em tạm hiểu là mm, Sếp kiểm tra lại.")
    return 0.001, "mm"


def _cac_entity(layout_or_insert, layer_cha=None, do_sau=0):
    """Duyệt entity, bung block (INSERT) ra thành entity thường, giữ layer đúng quy tắc CAD."""
    nguon = layout_or_insert.virtual_entities() if do_sau else layout_or_insert
    for e in nguon:
        layer = e.dxf.get("layer", "0")
        if layer == "0" and layer_cha:
            layer = layer_cha  # entity trên layer 0 trong block lấy layer của block
            e.dxf.layer = layer
        if e.dxftype() == "INSERT":
            if do_sau < 8:
                for attr in e.attribs:
                    yield attr
                yield from _cac_entity(e, layer, do_sau + 1)
            continue
        yield e


def _sua_hinh(poly):
    if not poly.is_valid:
        poly = make_valid(poly)
    if poly.geom_type == "Polygon":
        return [poly]
    return [g for g in getattr(poly, "geoms", []) if g.geom_type == "Polygon"]


_MA_DAC_BIET = {"c": "Ø", "d": "°", "p": "±"}


def _giai_ma_chu(t):
    """Đổi mã đặc biệt của CAD (%%c, %%d, %%p, mã Unicode U+XXXX) sang ký tự thật, bỏ gạch chân/gạch trên (%%u, %%o)."""
    t = re.sub(r"%%([cdpCDP])", lambda m: _MA_DAC_BIET[m.group(1).lower()], t)
    t = re.sub(r"%%[uUoO]", "", t)
    t = re.sub(r"%%(\d{3})", lambda m: chr(int(m.group(1))), t)
    t = re.sub(r"\\U\+([0-9A-Fa-f]{4})", lambda m: chr(int(m.group(1), 16)), t)
    return t


def _dung_bang_vni():
    """Bảng đổi bảng mã VNI (Windows) sang Unicode. Chữ gõ bằng font VNI lưu trong file dưới dạng ký tự Latin,
    ví dụ "NHAØ XÖÔÛNG" = "NHÀ XƯỞNG"."""
    import unicodedata as ud
    dau = {"ù": "́", "ø": "̀", "û": "̉", "õ": "̃", "ï": "̣"}   # sắc huyền hỏi ngã nặng
    mu = {"á": "́", "à": "̀", "å": "̉", "ã": "̃", "ä": "̣"}    # dấu mũ + dấu thanh
    trang = {"é": "́", "è": "̀", "ú": "̉", "ü": "̃", "ë": "̣"}  # dấu trăng + dấu thanh
    cap2, cap1 = {}, {}
    for hoa in (False, True):
        f = (lambda s: s.upper()) if hoa else (lambda s: s)
        nc = lambda s: ud.normalize("NFC", s)  # noqa: E731
        for k, v in dau.items():
            for x in "aeouy":
                cap2[f(x) + f(k)] = nc(f(x) + v)
            cap2[f("ô") + f(k)] = nc(f("o") + "̛" + v)   # ơ + dấu
            cap2[f("ö") + f(k)] = nc(f("u") + "̛" + v)   # ư + dấu
        for x in "aeo":
            cap2[f(x) + f("â")] = nc(f(x) + "̂")
            for k, v in mu.items():
                cap2[f(x) + f(k)] = nc(f(x) + "̂" + v)
        cap2[f("a") + f("ê")] = nc(f("a") + "̆")
        for k, v in trang.items():
            cap2[f("a") + f(k)] = nc(f("a") + "̆" + v)
        cap1.update({f("ñ"): f("đ"), f("ô"): nc(f("o") + "̛"), f("ö"): nc(f("u") + "̛"),
                     f("í"): f("í"), f("ì"): f("ì"), f("æ"): "ỉ" if not hoa else "Ỉ",
                     f("ó"): "ĩ" if not hoa else "Ĩ", f("ò"): "ị" if not hoa else "Ị",
                     f("î"): "ỵ" if not hoa else "Ỵ"})
    return cap2, cap1


_VNI_CAP2, _VNI_CAP1 = _dung_bang_vni()
_VNI_RE = re.compile("|".join(sorted(map(re.escape, _VNI_CAP2), key=len, reverse=True))
                     + "|[" + re.escape("".join(_VNI_CAP1)) + "]")
_VNI_NHAN_BIET = re.compile(r"[AEIOUYaeiouy][ÙØÛÕÏùøûõïÂÁÀÅÃÄâáàåãäÊÉÈÚÜËêéèúüë]|[ÖÔÑöôñ][A-Za-z]|[A-Za-z][ÖÔÑöôñ]")
_CHU_VIET_THAT = re.compile("[ĂăĐđĨĩŨũƠơƯưẠ-ỹ]")


def _font_vni(e):
    """Style/font của chữ có phải font VNI không (tên chứa 'vni', hoặc font VNI dạng VHxxx/VAxxx.ttf)."""
    try:
        ten = str(e.dxf.get("style", "")).lower()
        st = e.doc.styles.get(e.dxf.get("style", "Standard"))
        font = str(st.dxf.get("font", "")).lower()
    except Exception:
        return False
    return "vni" in ten or "vni" in font or bool(re.match(r"(vh|va)[a-z0-9_]*\.ttf$", font))


def vni_sang_unicode(t, chac_la_vni=False):
    """Đổi chữ VNI sang Unicode. Bỏ qua nếu chữ đã có dấu tiếng Việt thật. Nếu không biết font,
    chỉ đổi khi thấy mẫu VNI rõ ràng (nguyên âm + dấu thanh, hoặc Ö/Ô/Ñ cạnh chữ cái)."""
    if _CHU_VIET_THAT.search(t):
        return t
    if not (chac_la_vni or _VNI_NHAN_BIET.search(t)):
        return t
    return _VNI_RE.sub(lambda m: _VNI_CAP2.get(m.group(0)) or _VNI_CAP1[m.group(0)], t)


_NEO_MTEXT = {1: "tl", 2: "tc", 3: "tr", 4: "ml", 5: "mc", 6: "mr", 7: "bl", 8: "bc", 9: "br"}
_COT = {0: "l", 1: "c", 2: "r"}
_HANG = {0: "b", 1: "b", 2: "m", 3: "t"}  # valign TEXT: 0 baseline, 1 bottom, 2 middle, 3 top


def _chu_tu_entity(e, loai, he_so, handle):
    """Chữ kèm vị trí, chiều cao, góc xoay và điểm neo thật để khung xem vẽ giống CAD."""
    if loai == "MTEXT":
        noi_dung = _giai_ma_chu(vni_sang_unicode(e.plain_text(), _font_vni(e)))
        p = e.dxf.insert
        cao = float(e.dxf.get("char_height", 0) or 0)
        goc = float(e.dxf.get("rotation", 0) or 0)
        if e.dxf.hasattr("text_direction"):
            d = e.dxf.text_direction
            goc = math.degrees(math.atan2(d.y, d.x))
        neo = _NEO_MTEXT.get(int(e.dxf.get("attachment_point", 1)), "tl")
        rong = 1.0
    else:
        noi_dung = _giai_ma_chu(vni_sang_unicode(e.dxf.text, _font_vni(e)))
        p = e.dxf.insert
        cao = float(e.dxf.get("height", 0) or 0)
        goc = float(e.dxf.get("rotation", 0) or 0)
        rong = float(e.dxf.get("width", 1) or 1)
        ha, va = int(e.dxf.get("halign", 0)), int(e.dxf.get("valign", 0))
        if (ha or va) and ha not in (3, 5) and e.dxf.hasattr("align_point"):
            p = e.dxf.align_point  # canh lề khác trái/dưới: điểm neo nằm ở align_point
            neo = _HANG[va] + _COT.get(ha, "l")
        else:
            neo = "bl" if va in (0, 1) else _HANG[va] + "l"
    return Chu(noi_dung.strip(), Point(p.x * he_so, p.y * he_so), handle,
               round(cao * he_so, 4), round(goc, 2), neo, round(rong, 3))


def _path_thanh_diem(p, he_so):
    return [(v.x * he_so, v.y * he_so) for v in p.flattening(DO_MIN_CUNG_M / he_so)]


def doc_ban_ve(duong_dan, oda_path=None, don_vi="auto"):
    canh_bao = []
    doc = _doc_file(duong_dan, oda_path)
    he_so, ten_don_vi = _xac_dinh_don_vi(doc, don_vi, canh_bao)

    layers = {}
    for lay in doc.layers:
        layers[lay.dxf.name] = LayerData(ten=lay.dxf.name, tat=lay.is_off() or lay.is_frozen())

    def lay_layer(ten):
        if ten not in layers:
            layers[ten] = LayerData(ten=ten)
        return layers[ten]

    for e in _cac_entity(doc.modelspace()):
        loai = e.dxftype()
        ld = lay_layer(e.dxf.get("layer", "0"))
        handle = e.dxf.get("handle", "") or ""
        try:
            if loai in ("TEXT", "ATTRIB", "MTEXT"):
                chu = _chu_tu_entity(e, loai, he_so, handle)
                if chu.noi_dung:
                    ld.chu.append(chu)
            elif loai == "HATCH":
                # Tô theo quy tắc chẵn lẻ: vòng trong vòng ngoài là lỗ
                vung = None
                for p in ezpath.from_hatch(e):
                    pts = _path_thanh_diem(p, he_so)
                    if len(pts) < 3:
                        continue
                    for g in _sua_hinh(Polygon(pts)):
                        vung = g if vung is None else vung.symmetric_difference(g)
                if vung is not None:
                    for g in _sua_hinh(vung):
                        ld.hinh_kin.append(HinhKin(g, handle, "HATCH"))
            elif loai in ("LWPOLYLINE", "POLYLINE", "CIRCLE", "ELLIPSE", "SPLINE", "LINE", "ARC"):
                if loai == "POLYLINE" and not e.is_2d_polyline:
                    continue  # bỏ qua lưới 3D
                p = ezpath.make_path(e)
                pts = _path_thanh_diem(p, he_so)
                if len(pts) < 2:
                    continue
                kin = loai == "CIRCLE" or (
                    loai == "ELLIPSE" and abs(e.dxf.end_param - e.dxf.start_param - 2 * math.pi) < 1e-6
                )
                if loai in ("LWPOLYLINE", "POLYLINE"):
                    kin = e.closed or Point(pts[0]).distance(Point(pts[-1])) < 1e-6
                if loai == "SPLINE":
                    kin = e.closed
                if kin and len(pts) >= 3:
                    for g in _sua_hinh(Polygon(pts)):
                        ld.hinh_kin.append(HinhKin(g, handle, loai))
                else:
                    ld.net_ho.append(LineString(pts))
        except Exception as ex:  # entity hỏng không được làm dừng cả bản vẽ
            canh_bao.append(f"Bỏ qua entity {loai} (handle {handle}) trên layer {ld.ten}: {ex}")

    # Thử ghép các nét rời (LINE, ARC, polyline hở) thành hình kín
    for ld in layers.values():
        if not ld.net_ho:
            continue
        mang = unary_union(ld.net_ho)
        ghep = [g for g in polygonize(mang)]
        da_co = unary_union([h.geom for h in ld.hinh_kin]) if ld.hinh_kin else None
        for g in ghep:
            if da_co is not None and g.intersection(da_co).area > 0.5 * g.area:
                continue  # vùng này đã có hình kín vẽ sẵn
            ld.hinh_kin.append(HinhKin(g, "", "GHEP_NET"))

    ten = Path(duong_dan).name
    return BanVe(ten_file=ten, he_so=he_so, don_vi=ten_don_vi, layers=layers, canh_bao=canh_bao, doc=doc)


VERSION_CACHE = 1  # tăng số này khi đổi logic doc_ban_ve để bỏ cache cũ


def doc_ban_ve_cache(duong_dan, oda_path, don_vi, file_cache):
    """Như doc_ban_ve nhưng lưu kết quả đã xử lý (hình học) ra file_cache.

    Lần mở sau chỉ cần nạp lại cache, không đọc/đổi DWG và không ghép nét lại.
    Cache hết hạn khi file bản vẽ đổi (kích thước/ngày sửa), đổi đơn vị hoặc đổi VERSION_CACHE.
    ban_ve.doc để None trong trường hợp nạp từ cache; ai cần thì gọi nap_doc().
    """
    import pickle
    duong_dan, file_cache = Path(duong_dan), Path(file_cache)
    st = duong_dan.stat()
    khoa = (VERSION_CACHE, st.st_size, st.st_mtime_ns, don_vi)
    try:
        with open(file_cache, "rb") as f:
            kh, bv = pickle.load(f)
        if kh == khoa:
            return bv
    except Exception:
        pass  # không có cache hoặc cache hỏng: đọc lại từ file gốc
    bv = doc_ban_ve(duong_dan, oda_path, don_vi)
    try:
        file_cache.parent.mkdir(parents=True, exist_ok=True)
        tam = file_cache.with_name(file_cache.name + ".tmp")
        with open(tam, "wb") as f:
            pickle.dump((khoa, replace(bv, doc=None)), f, protocol=pickle.HIGHEST_PROTOCOL)
        tam.replace(file_cache)
    except Exception:
        pass  # ghi cache lỗi không được làm hỏng việc mở bản vẽ
    return bv


def nap_doc(ban_ve, duong_dan, oda_path=None):
    """Đảm bảo ban_ve.doc (ezdxf Drawing) có mặt; chỉ cần cho bóc ống gió."""
    if ban_ve.doc is None:
        ban_ve.doc = _doc_file(duong_dan, oda_path)
    return ban_ve.doc


def cat_vung(ban_ve, vung):
    """Chỉ giữ phần bản vẽ nằm trong khung vung = (x0, y0, x1, y1) tính bằng mét.

    Một file thường chứa nhiều mặt bằng và chi tiết; cắt vùng để bóc từng mặt bằng.
    Hình, nét, chữ được giữ nếu tâm của nó nằm trong khung.
    """
    x0, y0, x1, y1 = vung
    khung = box(min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
    layers = {}
    for ten, ld in ban_ve.layers.items():
        layers[ten] = LayerData(
            ten=ten, tat=ld.tat,
            hinh_kin=[h for h in ld.hinh_kin if khung.contains(h.geom.centroid)],
            net_ho=[n for n in ld.net_ho if khung.contains(n.centroid)],
            chu=[c for c in ld.chu if khung.contains(c.diem)],
        )
    return replace(ban_ve, layers=layers)


def hinh_xem(ban_ve, toan_bo=True):
    """Hình học theo từng layer cho khung xem kiểu CAD: hinh (đa giác), net (đường), chu (chữ)."""
    layers = {}
    xs, ys = [], []

    def lam(pts):
        for x, y in pts:
            xs.append(x)
            ys.append(y)
        return [[round(x, 2), round(y, 2)] for x, y in pts]

    for ten, ld in ban_ve.layers.items():
        if not (ld.hinh_kin or ld.net_ho or ld.chu):
            continue
        hinh, hi = [], []
        for h in ld.hinh_kin:
            if h.geom.area >= KHUNG_GIAY_M2 and not toan_bo:
                continue  # khung giấy, không dùng để chọn vùng
            hinh.append(lam(list(h.geom.exterior.coords)))
            # Diện tích và chu vi tính trên hình thật (đã trừ lỗ), dùng để bóc khi người dùng chọn đối tượng
            hi.append({"a": round(h.geom.area, 4), "c": round(h.geom.length, 3), "n": h.nguon, "h": h.handle,
                       "lo": len(h.geom.interiors)})
        net = [lam(list(n.coords)) for n in ld.net_ho]
        ni = [round(n.length, 3) for n in ld.net_ho]
        chu = [{"t": c.noi_dung[:200], "x": round(c.diem.x, 3), "y": round(c.diem.y, 3),
                "h": c.cao, "r": c.goc, "a": c.neo, "w": c.rong} for c in ld.chu]
        layers[ten] = {"hinh": hinh, "hi": hi, "net": net, "ni": ni, "chu": chu, "tat": ld.tat}
    khung = [min(xs), min(ys), max(xs), max(ys)] if xs else [0, 0, 1, 1]
    return {"khung": khung, "layers": layers, "don_vi": ban_ve.don_vi}


def tong_quan(ban_ve, toi_da=20000):
    """Dữ liệu vẽ phác toàn bộ bản vẽ để người dùng chọn vùng trên giao diện."""
    hinh, net, chu, dem = [], [], [], 0
    for ld in ban_ve.layers.values():
        for h in ld.hinh_kin:
            # Bỏ khung giấy / khung viewport (hàng trăm m2, hay chồng lên nhau, làm rối hình tổng quan)
            if dem < toi_da and h.geom.area < KHUNG_GIAY_M2:
                hinh.append([[round(x, 3), round(y, 3)] for x, y in h.geom.exterior.coords])
                dem += 1
        for n in ld.net_ho:
            if dem < toi_da:
                net.append([[round(x, 3), round(y, 3)] for x, y in n.coords])
                dem += 1
        for c in ld.chu:
            chu.append({"t": c.noi_dung[:40], "x": round(c.diem.x, 3), "y": round(c.diem.y, 3)})
    tat_ca = [p for d in (hinh, net) for g in d for p in g]
    if not tat_ca:
        return {"khung": [0, 0, 1, 1], "hinh": [], "net": [], "chu": chu}
    xs, ys = [p[0] for p in tat_ca], [p[1] for p in tat_ca]
    return {"khung": [min(xs), min(ys), max(xs), max(ys)], "hinh": hinh, "net": net, "chu": chu}


def tom_tat_layer(ban_ve):
    """Thống kê nhanh từng layer để hiện lên giao diện."""
    kq = []
    for ld in ban_ve.layers.values():
        if not (ld.hinh_kin or ld.net_ho or ld.chu):
            continue
        kq.append({
            "ten": ld.ten,
            "so_hinh_kin": sum(1 for h in ld.hinh_kin if h.nguon != "GHEP_NET"),
            "so_hinh_ghep": sum(1 for h in ld.hinh_kin if h.nguon == "GHEP_NET"),
            "so_net_ho": len(ld.net_ho),
            "so_chu": len(ld.chu),
            "tat": ld.tat,
        })
    return sorted(kq, key=lambda x: x["ten"].lower())
