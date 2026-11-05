"""Công cụ tính theo cấu kiện: bộ công thức chung của từng cấu kiện, cho người dùng sửa, và xuất Excel có công thức.

Mỗi công cụ (đào đất, móng, đà kiềng, cột, dầm, sàn, cấu kiện khác) có một bộ công thức mặc định trong
config/cong_cu.yaml. Bản người dùng sửa được ghi vào data/cong_cu_tuy_chinh.yaml, không đụng file gốc.

Công thức là biểu thức số học trên các biến của MỘT ký hiệu cấu kiện: n (số lượng), a (dài), b (rộng),
h (cao/dày), S (diện tích một cái), P (chu vi một cái), L (chiều dài một cái) và các tham số riêng của công cụ.
Biểu thức được phân tích bằng ast, chỉ cho phép số, biến đã khai báo, + - * / ** và vài hàm toán, nên không
chạy được mã tùy ý. Cùng biểu thức đó được dịch sang công thức Excel (biến thành địa chỉ ô cùng dòng) để
kỹ sư dò lại từng con số.
"""
import ast
import copy
import math
import re
from datetime import date

import yaml
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from . import config

BIEN_CO_BAN = ["n", "a", "b", "h", "S", "P", "L", "zd", "zm"]  # zd, zm: cao độ đáy, cao độ mặt (m)
BIEN_LUON_HIEN = ["n", "a", "b", "h", "S", "P", "L"]
DON_VI_HOP_LE = ["m3", "m2", "m", "cái", "kg", "tấn"]
DON_VI_HIEN = {"m3": "m³", "m2": "m²", "m": "m", "cái": "cái", "kg": "kg", "tấn": "tấn"}
HAM = {"min": min, "max": max, "abs": abs, "sqrt": math.sqrt, "round": round}
HAM_EXCEL = {"min": "MIN", "max": "MAX", "abs": "ABS", "sqrt": "SQRT", "round": "ROUND"}
RE_TEN_BIEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DUONG_TUY_CHINH = config.ROOT / "data" / "cong_cu_tuy_chinh.yaml"

NEN = PatternFill("solid", fgColor="1F4E78")
NEN_TONG = PatternFill("solid", fgColor="DDEBF7")


class ThieuBien(Exception):
    """Công thức dùng biến mà dòng này chưa có giá trị."""


# ---------- Biểu thức ----------
def _phan_tich(bt):
    if not isinstance(bt, str) or not bt.strip():
        raise ValueError("Công thức trống.")
    try:
        return ast.parse(bt.strip(), mode="eval").body
    except SyntaxError:
        raise ValueError(f"Công thức sai cú pháp: {bt}")


def _duyet(nut, ten_hop_le, dung):
    if isinstance(nut, ast.BinOp) and isinstance(nut.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
        _duyet(nut.left, ten_hop_le, dung)
        _duyet(nut.right, ten_hop_le, dung)
    elif isinstance(nut, ast.UnaryOp) and isinstance(nut.op, (ast.USub, ast.UAdd)):
        _duyet(nut.operand, ten_hop_le, dung)
    elif isinstance(nut, ast.Constant) and isinstance(nut.value, (int, float)) and not isinstance(nut.value, bool):
        pass
    elif isinstance(nut, ast.Name):
        if nut.id not in ten_hop_le:
            raise ValueError(f"Công thức dùng biến '{nut.id}' không có. Biến hợp lệ: {', '.join(ten_hop_le)}.")
        dung.add(nut.id)
    elif isinstance(nut, ast.Call) and isinstance(nut.func, ast.Name) and nut.func.id in HAM and not nut.keywords:
        for a in nut.args:
            _duyet(a, ten_hop_le, dung)
    else:
        raise ValueError("Công thức chỉ được dùng số, biến, + - * / ** , ngoặc và hàm min, max, abs, sqrt, round.")


def kiem_tra_bt(bt, ten_hop_le):
    """Trả tập biến đã dùng; ValueError (tiếng Việt) nếu công thức sai."""
    dung = set()
    _duyet(_phan_tich(bt), list(ten_hop_le), dung)
    return dung


def _tinh(nut, bien):
    if isinstance(nut, ast.Constant):
        return nut.value
    if isinstance(nut, ast.Name):
        v = bien.get(nut.id)
        if v is None:
            raise ThieuBien(nut.id)
        return v
    if isinstance(nut, ast.UnaryOp):
        v = _tinh(nut.operand, bien)
        return -v if isinstance(nut.op, ast.USub) else v
    if isinstance(nut, ast.BinOp):
        x, y = _tinh(nut.left, bien), _tinh(nut.right, bien)
        op = nut.op
        return x + y if isinstance(op, ast.Add) else x - y if isinstance(op, ast.Sub) else x * y if isinstance(op, ast.Mult) \
            else x / y if isinstance(op, ast.Div) else x ** y
    return HAM[nut.func.id](*[_tinh(a, bien) for a in nut.args])


def tinh_bt(bt, bien):
    """Giá trị của biểu thức. ThieuBien nếu biến chưa có giá trị, ZeroDivisionError nếu chia 0."""
    nut = _phan_tich(bt)
    _duyet(nut, list(bien), set())
    return _tinh(nut, bien)


def sang_excel(bt, dia_chi):
    """Dịch biểu thức sang công thức Excel; dia_chi: tên biến -> địa chỉ ô (ví dụ 'F7')."""
    def go(nut, goc=False):
        if isinstance(nut, ast.Constant):
            return repr(nut.value)
        if isinstance(nut, ast.Name):
            return dia_chi[nut.id]
        if isinstance(nut, ast.UnaryOp):
            return ("-" if isinstance(nut.op, ast.USub) else "") + go(nut.operand)
        if isinstance(nut, ast.BinOp):
            ky = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Pow: "^"}[type(nut.op)]
            s = f"{go(nut.left)}{ky}{go(nut.right)}"
            return s if goc else f"({s})"
        return f"{HAM_EXCEL[nut.func.id]}({','.join(go(a, True) for a in nut.args)})"
    return "=" + go(_phan_tich(bt), True)


# ---------- Định nghĩa công cụ (mặc định + bản người dùng sửa) ----------
def _doc_yaml(duong_dan):
    if not duong_dan.exists():
        return {}
    with open(duong_dan, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def mac_dinh():
    return _doc_yaml(config.CONFIG_DIR / "cong_cu.yaml")


def _tuy_chinh():
    return _doc_yaml(DUONG_TUY_CHINH)


def danh_sach():
    """Danh sách công cụ theo thứ tự trong file mặc định, gộp phần người dùng đã sửa."""
    goc, sua = mac_dinh(), _tuy_chinh()
    kq = []
    for ma, d in goc.items():
        d = copy.deepcopy(d)
        d["ma"] = ma
        d["da_sua"] = ma in sua
        if ma in sua:
            d["tham_so"] = sua[ma].get("tham_so", d.get("tham_so") or {})
            d["cong_thuc"] = sua[ma].get("cong_thuc", d["cong_thuc"])
        d["tham_so"] = d.get("tham_so") or {}
        d["goc"] = {"tham_so": goc[ma].get("tham_so") or {}, "cong_thuc": goc[ma]["cong_thuc"]}
        kq.append(d)
    return kq


def _chuan_hoa(tham_so, cong_thuc):
    """Kiểm tra và làm sạch dữ liệu người dùng gửi lên, ValueError nếu sai."""
    ts = {}
    for ten, v in (tham_so or {}).items():
        if not RE_TEN_BIEN.match(ten) or ten in BIEN_CO_BAN or ten in HAM:
            raise ValueError(f"Tên tham số '{ten}' không hợp lệ (chữ, số, gạch dưới; không trùng n, a, b, h, S, P, L).")
        try:
            gia_tri = float(v["gia_tri"])
        except (KeyError, TypeError, ValueError):
            raise ValueError(f"Tham số '{ten}' chưa có giá trị số.")
        ts[ten] = {"ten": str(v.get("ten") or ten), "gia_tri": gia_tri}
    ct = []
    for i, c in enumerate(cong_thuc or [], 1):
        ten = str(c.get("ten", "")).strip()
        if not ten:
            raise ValueError(f"Công thức {i}: chưa có tên hạng mục.")
        if c.get("dv") not in DON_VI_HOP_LE:
            raise ValueError(f"Công thức '{ten}': đơn vị phải là một trong {', '.join(DON_VI_HOP_LE)}.")
        try:
            kiem_tra_bt(c.get("bt"), BIEN_CO_BAN + list(ts))
        except ValueError as ex:
            raise ValueError(f"Công thức '{ten}': {ex}")
        ct.append({"ten": ten, "dv": c["dv"], "bt": str(c["bt"]).strip()})
    if not ct:
        raise ValueError("Cần ít nhất một công thức.")
    return ts, ct


def luu_tuy_chinh(ma, tham_so, cong_thuc):
    if ma not in mac_dinh():
        raise KeyError(ma)
    ts, ct = _chuan_hoa(tham_so, cong_thuc)
    sua = _tuy_chinh()
    sua[ma] = {"tham_so": ts, "cong_thuc": ct}
    DUONG_TUY_CHINH.parent.mkdir(parents=True, exist_ok=True)
    with open(DUONG_TUY_CHINH, "w", encoding="utf-8") as f:
        yaml.safe_dump(sua, f, allow_unicode=True, sort_keys=False)
    return next(d for d in danh_sach() if d["ma"] == ma)


def khoi_phuc(ma):
    if ma not in mac_dinh():
        raise KeyError(ma)
    sua = _tuy_chinh()
    if sua.pop(ma, None) is not None:
        with open(DUONG_TUY_CHINH, "w", encoding="utf-8") as f:
            yaml.safe_dump(sua, f, allow_unicode=True, sort_keys=False)
    return next(d for d in danh_sach() if d["ma"] == ma)


# ---------- Tính ----------
def _so(v):
    return None if v in (None, "") else round(float(v), 6)


def tinh(tham_so, cong_thuc, nhom):
    """nhom: list dict(ky_hieu, n, a, b, h, S, P, L). Trả {dong: [...], tong: {dv: giá trị}, loi: [...]}.

    Mỗi dòng: ký hiệu x công thức. Biến thiếu giá trị thì dòng đó không có kết quả và ghi rõ biến nào thiếu.
    """
    ts, ct = _chuan_hoa(tham_so, cong_thuc)
    dong, tong = [], {}
    for g in nhom:
        bien = {k: _so(g.get(k)) for k in BIEN_CO_BAN}
        bien.update({k: v["gia_tri"] for k, v in ts.items()})
        for c in ct:
            gia_tri, loi = None, None
            try:
                gia_tri = tinh_bt(c["bt"], bien)
            except ThieuBien as ex:
                loi = f"Chưa có giá trị '{ex}'"
            except ZeroDivisionError:
                loi = "Chia cho 0"
            dong.append({"ky_hieu": g.get("ky_hieu", ""), "ten": c["ten"], "dv": c["dv"], "bt": c["bt"],
                         "bien": bien, "gia_tri": None if gia_tri is None else round(gia_tri, 6), "loi": loi})
            if gia_tri is not None:
                tong[c["dv"]] = tong.get(c["dv"], 0.0) + gia_tri
    return {"dong": dong, "tong": {k: round(v, 6) for k, v in tong.items()}}


# ---------- Excel ----------
def ghi_sheet(wb, dong, du_an="", ten_sheet="CONG CU"):
    """Ghi các dòng có công thức (bt) vào sheet mới: mỗi biến một cột, khối lượng là công thức Excel."""
    ws = wb.create_sheet(ten_sheet)
    ws["A1"] = "BẢNG BÓC KHỐI LƯỢNG THEO CÔNG CỤ (CÔNG THỨC CHUNG CỦA TỪNG CẤU KIỆN)"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Dự án: {du_an}   |   Ngày xuất: {date.today():%d/%m/%Y}"
    ws["A3"] = "Kết quả do công cụ tính từ hình vẽ, cần kỹ sư kiểm tra trước khi sử dụng."
    ws["A3"].font = Font(italic=True, color="C00000")
    phu = sorted({k for d in dong for k in (d.get("bien") or {}) if k not in BIEN_CO_BAN})
    co_gia_tri = {k for d in dong for k, v in (d.get("bien") or {}).items() if v is not None}
    cot_bien = [k for k in BIEN_CO_BAN if k in BIEN_LUON_HIEN or k in co_gia_tri] + phu
    dau = ["STT", "Công cụ", "Ký hiệu", "Hạng mục", "ĐV"] + cot_bien + ["Công thức", "Khối lượng"]
    for i, c in enumerate(dau, 1):
        x = ws.cell(5, i, c)
        x.fill, x.font = NEN, Font(bold=True, color="FFFFFF")
        x.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    vi_tri = {k: 6 + i for i, k in enumerate(cot_bien)}
    c_bt, c_kl = 6 + len(cot_bien), 7 + len(cot_bien)
    r = 6
    for i, d in enumerate(dong, 1):
        bien = d.get("bien") or {}
        ws.cell(r, 1, i)
        ws.cell(r, 2, d.get("cong_cu", ""))
        ws.cell(r, 3, d.get("ky_hieu", ""))
        ws.cell(r, 4, d.get("ten", ""))
        ws.cell(r, 5, DON_VI_HIEN.get(d.get("dv"), d.get("dv", "")))
        for k, cot in vi_tri.items():
            v = bien.get(k)
            if v is not None:
                ws.cell(r, cot, v).number_format = "#,##0.000"
        ws.cell(r, c_bt, d["bt"])
        dia_chi = {k: f"{get_column_letter(cot)}{r}" for k, cot in vi_tri.items()}
        ws.cell(r, c_kl, sang_excel(d["bt"], dia_chi)).number_format = "#,##0.000"
        r += 1
    if dong:
        r += 1
        ws.cell(r, 4, "TỔNG THEO ĐƠN VỊ").font = Font(bold=True)
        col_dv, col_kl = get_column_letter(5), get_column_letter(c_kl)
        for dv in DON_VI_HOP_LE:
            hien = DON_VI_HIEN[dv]
            if not any(DON_VI_HIEN.get(d.get("dv"), d.get("dv")) == hien for d in dong):
                continue
            r += 1
            ws.cell(r, 4, f"Cộng ({hien})")
            ws.cell(r, c_kl, f'=SUMIF({col_dv}6:{col_dv}{5 + len(dong)},"{hien}",{col_kl}6:{col_kl}{5 + len(dong)})').number_format = "#,##0.000"
            for c in range(1, c_kl + 1):
                ws.cell(r, c).fill, ws.cell(r, c).font = NEN_TONG, Font(bold=True)
    rong = [6, 18, 14, 30, 7] + [10] * len(cot_bien) + [34, 16]
    for i, w in enumerate(rong, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A6"
    return ws


TIEU_DE_BIEN = {"n": "SL", "a": "Dài D (m)", "b": "Rộng R (m)", "h": "Cao C (m)", "S": "Diện tích DT (m²)", "P": "Chu vi CV (m)",
                "L": "Chiều dài L (m)", "zd": "Cao độ đáy (m)", "zm": "Cao độ mặt (m)"}


def ghi_tong_hop(wb, dong, du_an=""):
    """Bảng tổng hợp mỗi ký hiệu một dòng: STT, tên, ĐV, SL, D, R, C, CV, DT, cao độ và khối lượng từng hạng mục.

    Khối lượng là công thức Excel trỏ vào các ô cùng dòng. Mỗi công cụ một sheet.
    """
    theo_cc = {}
    for d in dong:
        theo_cc.setdefault(d.get("cong_cu", ""), []).append(d)
    for cc, ds in theo_cc.items():
        nhom = {}
        for d in ds:
            g = nhom.setdefault(d.get("ky_hieu", ""), {"bien": d.get("bien") or {}, "vi_tri": d.get("vi_tri", ""), "kl": {}})
            g["kl"][(d["ten"], d["dv"])] = d["bt"]
        hang_muc = list(dict.fromkeys((d["ten"], d["dv"]) for d in ds))
        phu = sorted({k for d in ds for k in (d.get("bien") or {}) if k not in BIEN_CO_BAN})
        ten_bien = BIEN_CO_BAN + phu
        dung = set()
        for d in ds:
            dung |= kiem_tra_bt(d["bt"], ten_bien)
        co_gia_tri = {k for d in ds for k, v in (d.get("bien") or {}).items() if v is not None}
        # Cột hiện: n, a, b, h, S, P luôn có; L, cao độ và tham số chỉ khi có công thức dùng hoặc có số liệu
        cot = [k for k in ["n", "a", "b", "h", "P", "S"] ] + [k for k in ["L", "zd", "zm"] + phu if k in dung or k in co_gia_tri]
        ws = wb.create_sheet(re.sub(r"[\/*?:\[\]]", "", f"TH {cc}")[:31] or "TONG HOP")
        ws["A1"] = f"BẢNG TỔNG HỢP - {cc.upper()}"
        ws["A1"].font = Font(bold=True, size=14)
        ws["A2"] = f"Dự án: {du_an}   |   Ngày xuất: {date.today():%d/%m/%Y}"
        ws["A3"] = "Số lượng đếm theo ký hiệu trên mặt bằng, kích thước lấy từ chi tiết khi có. Khối lượng là công thức Excel, cần kỹ sư kiểm tra."
        ws["A3"].font = Font(italic=True, color="C00000")
        dau = ["STT", "Tên", "ĐV"] + [TIEU_DE_BIEN.get(k, k) for k in cot] + [f"{t} ({DON_VI_HIEN.get(u, u)})" for t, u in hang_muc] + ["Vị trí trên mặt bằng (x; y, m)"]
        for i, c in enumerate(dau, 1):
            x = ws.cell(5, i, c)
            x.fill, x.font = NEN, Font(bold=True, color="FFFFFF")
            x.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        vi_tri_cot = {k: 4 + i for i, k in enumerate(cot)}
        c_kl0 = 4 + len(cot)
        r = 6
        for i, (kh, g) in enumerate(nhom.items(), 1):
            ws.cell(r, 1, i)
            ws.cell(r, 2, kh)
            ws.cell(r, 3, "cái")
            for k, c in vi_tri_cot.items():
                v = g["bien"].get(k)
                if v is not None:
                    ws.cell(r, c, v).number_format = "#,##0.000" if k != "n" else "0"
            dia_chi = {k: f"{get_column_letter(c)}{r}" for k, c in vi_tri_cot.items()}
            for j, hm in enumerate(hang_muc):
                if hm in g["kl"]:
                    ws.cell(r, c_kl0 + j, sang_excel(g["kl"][hm], dia_chi)).number_format = "#,##0.000"
            ws.cell(r, c_kl0 + len(hang_muc), g["vi_tri"])
            r += 1
        if nhom:
            ws.cell(r, 2, "CỘNG")
            ws.cell(r, vi_tri_cot["n"], f"=SUM({get_column_letter(vi_tri_cot['n'])}6:{get_column_letter(vi_tri_cot['n'])}{r - 1})")
            for j in range(len(hang_muc)):
                col = get_column_letter(c_kl0 + j)
                ws.cell(r, c_kl0 + j, f"=SUM({col}6:{col}{r - 1})").number_format = "#,##0.000"
            for c in range(1, len(dau) + 1):
                ws.cell(r, c).fill, ws.cell(r, c).font = NEN_TONG, Font(bold=True)
        for i, w in enumerate([6, 24, 6] + [12] * len(cot) + [18] * len(hang_muc) + [60], 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "D6"
