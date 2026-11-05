"""Bảng bóc khối lượng theo đối tượng người dùng chọn trên bản vẽ (hover chọn, bấm để thêm vào bảng)."""
from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .cong_cu import ghi_sheet, ghi_tong_hop

NEN = PatternFill("solid", fgColor="1F4E78")
NEN_TONG = PatternFill("solid", fgColor="DDEBF7")

# Cách bóc -> (tiêu đề cột kết quả, đơn vị, công thức theo hàng r; cột: F=Dài/chu vi, G=Diện tích, H=Cao/dày, E=Số lượng)
CACH_BOC = {
    "dien_tich": ("Diện tích", "m²", "=E{r}*G{r}"),
    "the_tich": ("Thể tích = S × dày", "m³", "=E{r}*G{r}*H{r}"),
    "chieu_dai": ("Chiều dài", "m", "=E{r}*F{r}"),
    "van_khuon": ("Ván khuôn thành = chu vi × cao", "m²", "=E{r}*F{r}*H{r}"),
    # Khối lượng đã tính ở tab Khối lượng: cột H chứa khối lượng của 1 lần, E là hệ số nhân. Đơn vị lấy theo từng dòng.
    "co_san": ("Khối lượng đã tính (tab Khối lượng)", "", "=E{r}*H{r}"),
}


_DV = {"m3": "m³", "m2": "m²"}


def _dv(x):
    return _DV.get(x, x or "")


def xuat_excel(dong, du_an=""):
    """Dòng có 'bt' (công thức của công cụ) vào sheet CONG CU, còn lại vào sheet BANG BOC như trước."""
    dong_cc = [d for d in dong if d.get("bt")]
    dong = [d for d in dong if not d.get("bt")]
    wb = Workbook()
    ws = wb.active
    ws.title = "BANG BOC"
    ws["A1"] = "BẢNG BÓC KHỐI LƯỢNG THEO ĐỐI TƯỢNG CHỌN TRÊN BẢN VẼ"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Dự án: {du_an}   |   Ngày xuất: {date.today():%d/%m/%Y}"
    ws["A3"] = "Kết quả do công cụ tính từ hình vẽ, cần kỹ sư kiểm tra trước khi sử dụng."
    ws["A3"].font = Font(italic=True, color="C00000")
    cot = ["STT", "Tên / diễn giải", "Layer", "Cách bóc", "Số lượng", "Dài / chu vi (m)", "Diện tích (m²)",
           "Dày / cao (m)", "Khối lượng", "Đơn vị", "Nguồn"]
    for i, c in enumerate(cot, 1):
        x = ws.cell(5, i, c)
        x.fill, x.font = NEN, Font(bold=True, color="FFFFFF")
        x.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    r = 6
    for i, d in enumerate(dong, 1):
        tieu_de, don_vi, ct = CACH_BOC.get(d.get("cach", "dien_tich"), CACH_BOC["dien_tich"])
        ws.cell(r, 1, i)
        ws.cell(r, 2, d.get("ten", ""))
        ws.cell(r, 3, d.get("layer", ""))
        ws.cell(r, 4, tieu_de)
        ws.cell(r, 5, d.get("so_luong", 1))
        ws.cell(r, 6, round(float(d.get("chu_vi") or d.get("dai") or 0), 3))
        ws.cell(r, 7, round(float(d.get("dien_tich") or 0), 3))
        ws.cell(r, 8, d.get("cao") if d.get("cao") not in (None, "") else None)
        ws.cell(r, 9, ct.format(r=r))
        ws.cell(r, 10, _dv(d.get("don_vi")) if d.get("cach") == "co_san" else don_vi)
        ws.cell(r, 11, d.get("nguon", ""))
        for c in (5, 6, 7, 8, 9):
            ws.cell(r, c).number_format = "#,##0.000"
        r += 1
    # Tổng theo đơn vị (không cộng lẫn m² với m³)
    if dong:
        r += 1
        ws.cell(r, 2, "TỔNG THEO ĐƠN VỊ").font = Font(bold=True)
        dvs = ["m²", "m³", "m"] + sorted({_dv(d.get("don_vi")) for d in dong if d.get("cach") == "co_san"} - {"m²", "m³", "m"})
        for dv in dvs:
            ws.cell(r + 1, 2, f"Cộng ({dv})")
            ws.cell(r + 1, 9, f'=SUMIF(J6:J{5 + len(dong)},"{dv}",I6:I{5 + len(dong)})')
            ws.cell(r + 1, 9).number_format = "#,##0.000"
            for c in range(1, 12):
                ws.cell(r + 1, c).fill, ws.cell(r + 1, c).font = NEN_TONG, Font(bold=True)
            r += 1
    for i, w in enumerate([6, 34, 24, 30, 10, 16, 16, 14, 16, 8, 22], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A6"
    if dong_cc:
        ghi_tong_hop(wb, dong_cc, du_an)
        ghi_sheet(wb, dong_cc, du_an)
        if not dong:
            wb.remove(ws)
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
