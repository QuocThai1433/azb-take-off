"""Xuất Excel bảng cốt thép tính từ bảng thống kê thép. Mọi con số là công thức Excel để dò lại được."""
from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .cot_thep import HE_SO_DON_TRONG

NEN = PatternFill("solid", fgColor="1F4E78")
NEN_TONG = PatternFill("solid", fgColor="DDEBF7")
LUU_Y = ("Khối lượng tính từ BẢNG THỐNG KÊ THÉP (số thanh × chiều dài × đơn trọng), không phải ước tính theo hàm lượng kg/m³. "
         "Kỹ sư kiểm tra, đối chiếu với bản vẽ và ký duyệt trước khi dùng cho dự toán hoặc thanh toán.")


def _dau(ws, hang, tieu_de):
    for j, t in enumerate(tieu_de, 1):
        c = ws.cell(hang, j, t)
        c.font, c.fill = Font(bold=True, color="FFFFFF"), NEN
        c.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")


def xuat_excel_thep(kq, du_an="", nguon=""):
    """kq: kết quả cot_thep.tinh(). Trả bytes .xlsx gồm sheet BANG THEP, TONG HOP, CANH BAO."""
    wb = Workbook()
    ws = wb.active
    ws.title = "BANG THEP"
    ws["A1"] = "KHỐI LƯỢNG CỐT THÉP THEO BẢNG THỐNG KÊ THÉP"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Dự án: {du_an}    Ngày: {date.today():%d/%m/%Y}    Nguồn bảng: {nguon}"
    ws["A3"] = LUU_Y
    ws["A3"].font = Font(italic=True, color="C00000")
    ws["N1"] = "Hệ số đơn trọng (kg/m trên mm²)"
    ws["N2"] = HE_SO_DON_TRONG
    dau = ["STT", "Cấu kiện", "Ø (mm)", "Số cấu kiện", "Số thanh / CK", "Dài 1 thanh (m)", "Đơn trọng (kg/m)",
           "Tổng dài (m)", "Khối lượng (kg)", "KL ghi trong bảng (kg)", "Lệch so với bảng", "Hình dạng / mác", "Dòng trong bảng gốc"]
    _dau(ws, 5, dau)
    r0 = 6
    for k, d in enumerate(kq["dong"]):
        r = r0 + k
        ws.cell(r, 1, k + 1)
        ws.cell(r, 2, d.get("ky_hieu") or "")
        ws.cell(r, 3, d["duong_kinh"])
        ws.cell(r, 4, d.get("so_ck", 1))
        ws.cell(r, 5, d["so_thanh"])
        ws.cell(r, 6, d["chieu_dai"])
        ws.cell(r, 7, f"=$N$2*C{r}^2")
        ws.cell(r, 8, f"=D{r}*E{r}*F{r}")
        ws.cell(r, 9, f"=H{r}*G{r}")
        if d.get("kl_ban_ve"):
            ws.cell(r, 10, d["kl_ban_ve"])
            ws.cell(r, 11, f"=(I{r}-J{r})/J{r}").number_format = "0.0%"
        ws.cell(r, 12, " ".join(x for x in (d.get("hinh_dang"), d.get("mac")) if x))
        ws.cell(r, 13, d.get("nguon_dong"))
        for c in (7, 8, 9):
            ws.cell(r, c).number_format = "#,##0.000" if c == 7 else "#,##0.00"
    r1 = r0 + len(kq["dong"]) - 1
    rt = r1 + 2
    ws.cell(rt, 2, "TỔNG").font = Font(bold=True)
    for c, nhan in ((8, "H"), (9, "I")):
        x = ws.cell(rt, c, f"=SUM({nhan}{r0}:{nhan}{r1})" if kq["dong"] else 0)
        x.font, x.fill, x.number_format = Font(bold=True), NEN_TONG, "#,##0.00"
    for col, w in zip("ABCDEFGHIJKLM", (6, 22, 8, 10, 12, 14, 14, 13, 15, 16, 12, 18, 12)):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A6"

    th = wb.create_sheet("TONG HOP")
    th["A1"] = "TỔNG HỢP THEO ĐƯỜNG KÍNH"
    th["A1"].font = Font(bold=True, size=14)
    _dau(th, 3, ["Ø (mm)", "Tổng dài (m)", "Khối lượng (kg)", "Tỷ trọng"])
    phi = sorted({d["duong_kinh"] for d in kq["dong"]})
    rng = lambda c: f"'BANG THEP'!${c}${r0}:${c}${r1}"
    for k, p in enumerate(phi):
        r = 4 + k
        th.cell(r, 1, p)
        th.cell(r, 2, f"=SUMIF({rng('C')},A{r},{rng('H')})").number_format = "#,##0.0"
        th.cell(r, 3, f"=SUMIF({rng('C')},A{r},{rng('I')})").number_format = "#,##0.0"
    rt2 = 4 + len(phi)
    for k in range(len(phi)):
        th.cell(4 + k, 4, f"=C{4 + k}/$C${rt2}").number_format = "0.0%"
    th.cell(rt2, 1, "TỔNG").font = Font(bold=True)
    for c, nhan in ((2, "B"), (3, "C")):
        x = th.cell(rt2, c, f"=SUM({nhan}4:{nhan}{rt2 - 1})" if phi else 0)
        x.font, x.fill, x.number_format = Font(bold=True), NEN_TONG, "#,##0.0"
    th.cell(rt2 + 1, 1, "Tổng (tấn)")
    th.cell(rt2 + 1, 3, f"=C{rt2}/1000").number_format = "#,##0.000"
    dc = kq.get("doi_chieu")
    if dc:
        th.cell(rt2 + 3, 1, "Đối chiếu hàm lượng").font = Font(bold=True)
        th.cell(rt2 + 4, 1, "Bê tông đã bóc (m³)")
        th.cell(rt2 + 4, 3, dc["bt_m3"])
        th.cell(rt2 + 5, 1, "Hàm lượng thép (kg/m³)")
        th.cell(rt2 + 5, 3, f"=C{rt2}/C{rt2 + 4}").number_format = "#,##0"
    th.column_dimensions["A"].width = 24
    for col in "BCD":
        th.column_dimensions[col].width = 16

    cb = wb.create_sheet("CANH BAO")
    cb["A1"] = "CẢNH BÁO"
    cb["A1"].font = Font(bold=True, size=14)
    cb["A2"] = LUU_Y
    for k, t in enumerate(kq.get("canh_bao_doc", []) + kq["canh_bao"], 4):
        cb.cell(k, 1, t)
    cb.column_dimensions["A"].width = 140
    bo = BytesIO()
    wb.save(bo)
    return bo.getvalue()
