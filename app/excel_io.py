"""Xuất bảng khối lượng ra Excel và đọc bảng đối chiếu.

Bảng khối lượng dùng công thức Excel (=Số lượng x PRODUCT(Dài:Diện tích)) để kỹ sư
dò lại từng con số. Sheet DOI CHIEU là mẫu để nhập khối lượng bóc thủ công.
"""
from datetime import date
from io import BytesIO

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from . import config

VIEN = Border(*(Side(style="thin", color="999999"),) * 4)
NEN_TIEU_DE = PatternFill("solid", fgColor="1F4E78")
NEN_NHOM = PatternFill("solid", fgColor="DDEBF7")
NEN_THIEU = PatternFill("solid", fgColor="FFF2CC")
CHU_TRANG = Font(bold=True, color="FFFFFF")
SO = "#,##0.000"

TEN_SHEET_DOI_CHIEU = "DOI CHIEU"


def _tieu_de(ws, hang, cot_ds):
    for i, ten in enumerate(cot_ds, 1):
        c = ws.cell(hang, i, ten)
        c.font, c.fill, c.border = CHU_TRANG, NEN_TIEU_DE, VIEN
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _do_rong(ws, ds):
    for i, w in enumerate(ds, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def xuat_excel(kq, du_an=""):
    wb = Workbook()
    ct = config.cong_tac()
    ts = kq["thong_so"]

    # ----- Sheet 1: bảng khối lượng -----
    ws = wb.active
    ws.title = "BANG KHOI LUONG"
    ws["A1"] = "BẢNG TÍNH KHỐI LƯỢNG KẾT CẤU"
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = f"Dự án: {du_an}"
    ws["A3"] = f"Bản vẽ: {kq['ten_file']}  |  Đơn vị bản vẽ: {kq['don_vi']}  |  Ngày xuất: {date.today():%d/%m/%Y}"
    ws["A4"] = (f"Chiều cao tầng {ts['chieu_cao_tang']} m  |  Số tầng giống nhau {ts['so_tang_giong_nhau']}  |  "
                "Kết quả do công cụ tính, cần kỹ sư kiểm tra và ký duyệt trước khi sử dụng.")
    ws["A4"].font = Font(italic=True, color="C00000")
    cot = ["STT", "Mã hiệu", "Nội dung công việc / Diễn giải", "Đơn vị", "Số lượng",
           "Dài (m)", "Rộng (m)", "Cao (m)", "Diện tích (m2)", "Khối lượng", "Ghi chú"]
    _tieu_de(ws, 6, cot)
    _do_rong(ws, [6, 14, 52, 8, 10, 10, 10, 10, 13, 14, 30])
    ws.freeze_panes = "A7"

    hang = 7
    vi_tri_tong = {}
    for stt, th in enumerate(kq["tong_hop"], 1):
        ds = [d for d in kq["dong"] if d["cong_tac"] == th["ma"]]
        h0 = hang
        vals = [stt, th["ma_hieu"], th["ten"], th["don_vi"]]
        for i, v in enumerate(vals, 1):
            ws.cell(h0, i, v)
        for i in range(1, len(cot) + 1):
            c = ws.cell(h0, i)
            c.font, c.fill, c.border = Font(bold=True), NEN_NHOM, VIEN
        if not th["ma_hieu"]:
            ws.cell(h0, 2).fill = NEN_THIEU
            ws.cell(h0, 11, "Chưa có mã hiệu định mức")
        hang += 1
        for d in ds:
            ws.cell(hang, 3, f"- {d['ten_ck']}: {d['dien_giai']}")
            ws.cell(hang, 5, d["n"])
            for j, k in enumerate(("dai", "rong", "cao", "dien_tich"), 6):
                if d[k] is not None:
                    ws.cell(hang, j, d[k]).number_format = "0.000"
            ws.cell(hang, 10, f"=E{hang}*PRODUCT(F{hang}:I{hang})").number_format = SO
            ws.cell(hang, 11, d["ck_id"])
            for i in range(1, len(cot) + 1):
                ws.cell(hang, i).border = VIEN
            hang += 1
        ws.cell(h0, 10, f"=SUM(J{h0 + 1}:J{hang - 1})").number_format = SO
        vi_tri_tong[th["ma"]] = f"'BANG KHOI LUONG'!J{h0}"

    # ----- Sheet 2: chi tiết cấu kiện -----
    ws2 = wb.create_sheet("CHI TIET CAU KIEN")
    cot2 = ["Mã CK", "Loại", "Tên", "Nhãn trên bản vẽ", "Layer", "Handle CAD", "h dầm (m)", "t sàn (m)",
            "Cao cột/vách (m)", "Cao móng (m)", "Nguồn thông số", "Loại bỏ", "Cảnh báo"]
    _tieu_de(ws2, 1, cot2)
    _do_rong(ws2, [10, 8, 10, 22, 14, 11, 10, 10, 12, 11, 16, 9, 70])
    for r, c in enumerate(kq["cau_kien"], 2):
        t = c["thong_so"]
        nguon = t.get("nguon_h") or t.get("nguon_t") or t.get("nguon_day") or ""
        vals = [c["id"], c["loai"], c["ten"], c["nhan"], c["layer"], c["handle"], t.get("h"), t.get("t"),
                t.get("cao"), t.get("day"), nguon, "x" if c["loai_bo"] else "",
                " | ".join(x["noi_dung"] for x in c["canh_bao"])]
        for i, v in enumerate(vals, 1):
            ws2.cell(r, i, v).border = VIEN
        if c["canh_bao"]:
            ws2.cell(r, 13).fill = NEN_THIEU
    ws2.freeze_panes = "A2"

    # ----- Sheet 3: cảnh báo -----
    ws3 = wb.create_sheet("CANH BAO")
    _tieu_de(ws3, 1, ["Mức", "Cấu kiện", "Nội dung"])
    _do_rong(ws3, [12, 14, 110])
    for x in kq["canh_bao_chung"]:
        ws3.append(["chung", "", x])
    for x in kq["nhan_khong_gan"]:
        ws3.append(["canh_bao", "", f"Nhãn '{x['noi_dung']}' tại ({x['x']:.2f}, {x['y']:.2f}) không gán được cho cấu kiện nào"])
    for c in kq["cau_kien"]:
        for x in c["canh_bao"]:
            ws3.append([x["muc"], c["id"], x["noi_dung"]])

    # ----- Sheet 4: đối chiếu -----
    ws4 = wb.create_sheet(TEN_SHEET_DOI_CHIEU)
    ws4["A1"] = "ĐỐI CHIẾU VỚI KHỐI LƯỢNG BÓC THỦ CÔNG"
    ws4["A1"].font = Font(bold=True, size=13)
    nguong = config.app_config()["kiem_tra"]["sai_lech_cho_phep"]
    ws4["A2"] = f"Nhập khối lượng thủ công vào cột F. Tiêu chí đạt: sai lệch tuyệt đối ≤ {nguong:.0%}."
    _tieu_de(ws4, 4, ["Mã công tác", "Mã hiệu", "Công tác", "Đơn vị", "KL công cụ", "KL thủ công",
                      "Chênh lệch", "Sai lệch %", "Đạt"])
    _do_rong(ws4, [18, 14, 26, 8, 14, 14, 14, 12, 8])
    for r, (k, v) in enumerate(ct.items(), 5):
        ws4.cell(r, 1, k)
        ws4.cell(r, 2, v.get("ma_hieu") or "")
        ws4.cell(r, 3, v["ten"])
        ws4.cell(r, 4, v["don_vi"])
        ws4.cell(r, 5, f"={vi_tri_tong[k]}" if k in vi_tri_tong else 0).number_format = SO
        ws4.cell(r, 6).fill = NEN_THIEU
        ws4.cell(r, 6).number_format = SO
        ws4.cell(r, 7, f'=IF(F{r}="","",E{r}-F{r})').number_format = SO
        ws4.cell(r, 8, f'=IF(OR(F{r}="",F{r}=0),"",G{r}/F{r})').number_format = "0.00%"
        ws4.cell(r, 9, f'=IF(H{r}="","",IF(ABS(H{r})<={nguong},"Đạt","Không"))')
        for i in range(1, 10):
            ws4.cell(r, i).border = VIEN

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def doi_chieu(file_bytes, kq):
    """Đọc sheet DOI CHIEU (đã nhập KL thủ công) và so với kết quả công cụ đang có."""
    wb = load_workbook(BytesIO(file_bytes), data_only=True)
    if TEN_SHEET_DOI_CHIEU not in wb.sheetnames:
        raise ValueError(f"Không thấy sheet '{TEN_SHEET_DOI_CHIEU}'. Sếp dùng đúng file Excel do công cụ xuất ra.")
    ws = wb[TEN_SHEET_DOI_CHIEU]
    nguong = config.app_config()["kiem_tra"]["sai_lech_cho_phep"]
    cong_cu = {t["ma"]: t["khoi_luong"] for t in kq["tong_hop"]}
    ten = {k: v["ten"] for k, v in config.cong_tac().items()}
    ds = []
    for row in ws.iter_rows(min_row=5, values_only=True):
        ma, tc = row[0], row[5]
        if not ma or tc in (None, ""):
            continue
        try:
            tc = float(tc)
        except (TypeError, ValueError):
            continue
        cc = cong_cu.get(ma, 0.0)
        lech = (cc - tc) / tc if tc else None
        ds.append({
            "ma": ma, "ten": ten.get(ma, ma), "cong_cu": cc, "thu_cong": tc, "chenh": cc - tc,
            "sai_lech": lech, "dat": lech is not None and abs(lech) <= nguong,
        })
    return {"nguong": nguong, "dong": ds, "dat_tat_ca": bool(ds) and all(d["dat"] for d in ds)}
