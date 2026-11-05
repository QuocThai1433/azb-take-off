"""Xuất bảng bóc ống gió ra Excel: 3 bảng như công cụ CAD, diện tích dùng công thức Excel."""
from datetime import date
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font

from .excel_io import NEN_NHOM, _do_rong, _tieu_de

XANH = Font(bold=True, color="1F4E78")


def _dong_tong(ws, r, so_cot):
    for c in range(1, so_cot + 1):
        ws.cell(r, c).fill, ws.cell(r, c).font = NEN_NHOM, Font(bold=True)


def xuat_excel_ong_gio(kq, du_an=""):
    wb = Workbook()
    ws = wb.active
    ws.title = "ONG GIO"
    ws["A1"] = "BẢNG BÓC KHỐI LƯỢNG ỐNG GIÓ"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Dự án: {du_an}"
    ws["A3"] = (f"Bản vẽ: {kq['ten_file']}  |  Đơn vị bản vẽ: {kq['don_vi']}  |  Ngày xuất: {date.today():%d/%m/%Y}  |  "
                "Kết quả do công cụ tính, cần kỹ sư kiểm tra trước khi sử dụng.")
    ws["A3"].font = Font(italic=True, color="C00000")

    # ----- Bảng 1: ống thẳng -----
    ws["A5"] = "BẢNG 1 — ỐNG THẲNG (theo đường MLINE; m² tôn = chu vi × tổng dài)"
    ws["A5"].font = XANH
    _tieu_de(ws, 6, ["STT", "Loại", "Hình dạng", "Kích thước (mm)", "Rộng (mm)", "Cao (mm)", "Tổng dài (m)",
                     "Chu vi (m)", "Dày tôn (mm)", "Diện tích tôn (m²)"])
    r = 7
    a1 = r
    for i, o in enumerate(kq["ong_thang"], 1):
        ws.cell(r, 1, i)
        ws.cell(r, 2, "HTS")
        ws.cell(r, 3, "Vuông")
        ws.cell(r, 4, o["kich_thuoc"])
        ws.cell(r, 5, o["rong"])
        ws.cell(r, 6, o["cao"])
        ws.cell(r, 7, round(o["tong"], 3))
        ws.cell(r, 8, f"=2*(E{r}+F{r})/1000")
        ws.cell(r, 9, o["day"])
        ws.cell(r, 10, f"=G{r}*H{r}")
        r += 1
    b1 = max(r - 1, a1)
    ws.cell(r, 2, "TỔNG CỘNG")
    ws.cell(r, 7, f"=SUM(G{a1}:G{b1})")
    ws.cell(r, 10, f"=SUM(J{a1}:J{b1})")
    _dong_tong(ws, r, 10)
    cuoi_b1 = r
    r += 2

    # ----- Bảng 2: phụ kiện -----
    ws.cell(r, 1, "BẢNG 2 — PHỤ KIỆN (theo block; m² tôn / cái theo công thức khai triển gần đúng)").font = XANH
    r += 1
    _tieu_de(ws, r, ["STT", "Loại", "Loại phụ kiện", "Quy cách (block)", "Kích thước tính (mm)", "Số lượng",
                     "Dày tôn (mm)", "m² tôn / cái", "m² tôn"])
    r += 1
    a2 = r
    for i, p in enumerate(kq["phu_kien"], 1):
        ws.cell(r, 1, i)
        ws.cell(r, 2, "HTS")
        ws.cell(r, 3, p["loai"])
        ws.cell(r, 4, p["block"])
        ws.cell(r, 5, p["kich_thuoc"])
        ws.cell(r, 6, p["so_luong"])
        ws.cell(r, 7, p["day"])
        ws.cell(r, 8, round(p["m2_cai"], 4))
        ws.cell(r, 9, f"=F{r}*H{r}")
        r += 1
    b2 = max(r - 1, a2)
    ws.cell(r, 3, "TỔNG CỘNG")
    ws.cell(r, 6, f"=SUM(F{a2}:F{b2})")
    ws.cell(r, 9, f"=SUM(I{a2}:I{b2})")
    _dong_tong(ws, r, 9)
    r += 2

    # ----- Bảng 3: tổng hợp theo độ dày -----
    ws.cell(r, 1, "BẢNG 3 — TỔNG HỢP DIỆN TÍCH TÔN THEO ĐỘ DÀY").font = XANH
    r += 1
    _tieu_de(ws, r, ["STT", "Độ dày tôn (mm)", "Ống thẳng (m²)", "Phụ kiện (m²)", "Cộng (m²)"])
    r += 1
    a3 = r
    for i, t in enumerate(kq["tong_hop"], 1):
        ws.cell(r, 1, i)
        ws.cell(r, 2, t["day"])
        ws.cell(r, 3, f"=SUMIF($I${a1}:$I${b1},B{r},$J${a1}:$J${b1})")
        ws.cell(r, 4, f"=SUMIF($G${a2}:$G${b2},B{r},$I${a2}:$I${b2})")
        ws.cell(r, 5, f"=C{r}+D{r}")
        r += 1
    b3 = max(r - 1, a3)
    ws.cell(r, 2, "TỔNG CỘNG")
    for c, col in ((3, "C"), (4, "D"), (5, "E")):
        ws.cell(r, c, f"=SUM({col}{a3}:{col}{b3})")
    _dong_tong(ws, r, 5)
    cuoi_b3 = r
    r += 2

    # ----- Bảng 4: thiết bị -----
    if kq["thiet_bi"]:
        ws.cell(r, 1, "BẢNG 4 — THIẾT BỊ, MIỆNG GIÓ, VAN (đếm số lượng, không tính tôn)").font = XANH
        r += 1
        _tieu_de(ws, r, ["STT", "Block", "", "", "", "Số lượng"])
        r += 1
        for i, t in enumerate(kq["thiet_bi"], 1):
            ws.cell(r, 1, i)
            ws.cell(r, 2, t["block"])
            ws.cell(r, 6, t["so_luong"])
            r += 1
        r += 1
    for cb in kq["canh_bao"]:
        ws.cell(r, 1, cb).font = Font(color="C00000")
        r += 1

    for row in ws.iter_rows(min_row=7):
        for x in row:
            if x.row <= cuoi_b1 and x.column in (7, 8, 10):
                x.number_format = "0.00"
            elif x.row > cuoi_b1 and x.column in (8, 9):
                x.number_format = "0.00"
            elif x.row > cuoi_b1 and x.row <= cuoi_b3 and x.column in (3, 4, 5):
                x.number_format = "0.00"
    _do_rong(ws, [6, 14, 24, 38, 26, 10, 12, 12, 13, 16])
    ws.freeze_panes = "A5"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
