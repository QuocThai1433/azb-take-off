"""Cốt thép theo bảng thống kê thép: đọc Excel/CSV/CAD, đơn trọng, đối chiếu, xuất Excel bằng công thức, API."""
import io
import re

import ezdxf
import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook

from app import cot_thep
from app.dxf_reader import doc_ban_ve
from app.excel_thep import xuat_excel_thep

# Đơn trọng thép tròn theo bảng tra thông dụng (kg/m)
BANG_TRA = {6: 0.222, 8: 0.395, 10: 0.617, 12: 0.888, 14: 1.21, 16: 1.58, 18: 2.00, 20: 2.47, 22: 2.98, 25: 3.85, 28: 4.83, 32: 6.31}


@pytest.mark.parametrize("d,kg_m", BANG_TRA.items())
def test_don_trong_khop_bang_tra(d, kg_m):
    assert cot_thep.don_trong(d) == pytest.approx(kg_m, abs=0.012)


def _xlsx(hang):
    wb = Workbook()
    ws = wb.active
    for r in hang:
        ws.append(r)
    bo = io.BytesIO()
    wb.save(bo)
    return bo.getvalue()


TIEU_DE = ["STT", "Cấu kiện", "Đường kính Ø (mm)", "Số thanh", "Chiều dài (mm)", "Tổng chiều dài (m)", "Khối lượng (kg)"]


def test_doc_excel_tinh_dung_va_khop_cot_khoi_luong():
    kl1 = 12 * 5000 / 1000 * cot_thep.don_trong(16)     # 12 thanh Ø16 dài 5000 mm
    kl2 = 40 * 1200 / 1000 * cot_thep.don_trong(8)
    du_lieu = _xlsx([["BẢNG THỐNG KÊ THÉP DẦM"], [], TIEU_DE,
                     [1, "D1", "Ø16", 12, 5000, 60, round(kl1, 1)],
                     [2, "D1", "Ø8", 40, 1200, 48, round(kl2, 1)],
                     ["", "Tổng", "", "", "", "", round(kl1 + kl2, 1)]])
    r = cot_thep.doc_excel_csv(du_lieu, "thep.xlsx")
    assert len(r["dong"]) == 2 and r["canh_bao"] == [] and r["tong_ban_ve_kg"] == pytest.approx(kl1 + kl2, abs=0.1)
    assert r["dong"][0]["chieu_dai"] == pytest.approx(5.0) and r["dong"][0]["duong_kinh"] == 16
    kq = cot_thep.tinh(r["dong"])
    assert kq["tong_kg"] == pytest.approx(kl1 + kl2, abs=0.1) and kq["canh_bao"] == []   # khớp cột khối lượng của bảng
    assert [p["duong_kinh"] for p in kq["theo_phi"]] == [8, 16]


def test_canh_bao_khi_bang_ghi_kl_lech_so_tinh():
    du_lieu = _xlsx([TIEU_DE, [1, "C1", "Ø20", 8, 3000, 24, 100.0]])   # đúng phải là 24*2.468 = 59,2 kg
    kq = cot_thep.tinh(cot_thep.doc_excel_csv(du_lieu, "t.xlsx")["dong"])
    assert len(kq["canh_bao"]) == 1 and "lệch" in kq["canh_bao"][0] and "C1" in kq["canh_bao"][0]


def test_csv_cham_phay_so_thap_phan_phay_dai_theo_met():
    csv = "STT;Ký hiệu;Phi;SL thanh;Chiều dài (m);Ghi chú\n1;M1;Ø12;10;3,5;\n2;M1;Ø10;20;1,25;\n"
    r = cot_thep.doc_excel_csv(csv.encode("utf-8-sig"), "t.csv")
    assert [(d["duong_kinh"], d["so_thanh"], d["chieu_dai"]) for d in r["dong"]] == [(12, 10, 3.5), (10, 20, 1.25)]


def test_khong_ghi_don_vi_thi_doan_theo_do_lon_va_bao():
    r = cot_thep.phan_tich_luoi([["Ký hiệu", "Ø", "Số thanh", "Chiều dài"], ["C1", 16, 4, 3200], ["C2", 18, 4, 2800]])
    assert r["dong"][0]["chieu_dai"] == pytest.approx(3.2)
    assert any("đoán" in c and "mm" in c for c in r["canh_bao"])


def test_o_gop_ky_hieu_dung_lai_ky_hieu_dong_tren():
    r = cot_thep.phan_tich_luoi([["Cấu kiện", "Ø", "Số thanh", "Dài (m)"], ["D1", 16, 4, 5], ["", 8, 20, 1.2]])
    assert [d["ky_hieu"] for d in r["dong"]] == ["D1", "D1"]


def test_bang_chi_co_tong_chieu_dai():
    r = cot_thep.phan_tich_luoi([["Cấu kiện", "Đường kính", "Tổng chiều dài (m)"], ["D1", "Ø16", 300]])
    kq = cot_thep.tinh(r["dong"])
    assert kq["tong_kg"] == pytest.approx(300 * cot_thep.don_trong(16))


def test_khong_co_tieu_de_thi_bao_loi_ro_rang():
    r = cot_thep.phan_tich_luoi([["a", "b"], [1, 2]])
    assert r["dong"] == [] and "tiêu đề" in r["canh_bao"][0]


def test_dong_khong_doc_duoc_duong_kinh_bi_bo_qua_va_bao():
    r = cot_thep.phan_tich_luoi([["Cấu kiện", "Ø", "Số thanh", "Dài (m)"], ["D1", "?", 4, 5], ["D2", 16, 4, 5]])
    assert len(r["dong"]) == 1 and any("Dòng 2" in c for c in r["canh_bao"])


def test_ham_luong_ngoai_khoang_bi_canh_bao():
    dong = cot_thep.phan_tich_luoi([["Cấu kiện", "Ø", "Số thanh", "Dài (m)"], ["D1", 20, 100, 10]])["dong"]
    t = cot_thep.tinh(dong)["tong_kg"]
    ok = cot_thep.tinh(dong, bt_m3=t / 120)
    xau = cot_thep.tinh(dong, bt_m3=t / 5)
    assert ok["doi_chieu"]["hop_ly"] and ok["canh_bao"] == []
    assert not xau["doi_chieu"]["hop_ly"] and "Hàm lượng thép" in xau["canh_bao"][0]


def test_loai_bo_dong():
    dong = cot_thep.phan_tich_luoi([["Cấu kiện", "Ø", "Số thanh", "Dài (m)"], ["D1", 16, 4, 5], ["D2", 8, 4, 5]])["dong"]
    assert len(cot_thep.tinh(dong, loai_bo=[0])["dong"]) == 1


# ---------- đọc từ chữ trong CAD ----------
def _bang_cad(tmp_path, can="l"):
    doc = ezdxf.new(units=6)
    m = doc.modelspace()
    cot_x = [0, 3, 8, 11, 15, 20]
    td = ["STT", "Cấu kiện", "Đường kính", "Số thanh", "Chiều dài", "Khối lượng"]
    don_vi = ["", "", "(mm)", "", "(mm)", "(kg)"]
    hang = [["1", "D1", "Ø16", "12", "5000", "94.7"], ["2", "D1", "Ø8", "40", "1200", "19.0"], ["3", "C1", "Ø20", "8", "3000", "59.2"]]
    for r_i, noi in enumerate([td, don_vi] + hang):
        for x, t in zip(cot_x, noi):
            if t:
                m.add_text(t, dxfattribs={"layer": "BANG", "insert": (x, -r_i * 0.8), "height": 0.3})
    m.add_text("ghi chú ngoài bảng", dxfattribs={"layer": "BANG", "insert": (60, 5), "height": 0.3})
    f = tmp_path / "bang.dxf"
    doc.saveas(f)
    return doc_ban_ve(str(f))


def test_doc_bang_thep_tu_chu_trong_cad(tmp_path):
    bv = _bang_cad(tmp_path)
    r = cot_thep.doc_bang_cad(bv, [-1, -5, 25, 1])        # khung trùm bảng, không trùm chữ ngoài bảng
    assert len(r["dong"]) == 3 and "CAD" in r["canh_bao"][0]
    assert [(d["ky_hieu"], d["duong_kinh"], d["so_thanh"], d["chieu_dai"]) for d in r["dong"]] == \
        [("D1", 16, 12, 5.0), ("D1", 8, 40, 1.2), ("C1", 20, 8, 3.0)]
    kq = cot_thep.tinh(r["dong"])
    assert kq["canh_bao"] == []                            # cột khối lượng trong bảng khớp số tính (sai số làm tròn dưới 2%)


def test_khung_cad_it_chu_hoac_khong_co_tieu_de(tmp_path):
    bv = _bang_cad(tmp_path)
    assert "quá ít" in cot_thep.doc_bang_cad(bv, [55, 0, 70, 8])["canh_bao"][0]
    r = cot_thep.doc_bang_cad(bv, [-1, -5, 25, -0.5])      # khung cắt mất dòng tiêu đề
    assert r["dong"] == [] and "tiêu đề" in r["canh_bao"][0]


# ---------- Excel xuất ra và API ----------
def _tinh_excel(ws, o):
    bieu_thuc = re.sub(r"\$?([A-Z]{1,2})\$?(\d+)", lambda m: str(ws[f"{m.group(1)}{m.group(2)}"].value or 0), o[1:]).replace("^", "**")
    return eval(bieu_thuc)


def test_excel_xuat_cong_thuc_khop_python():
    dong = cot_thep.phan_tich_luoi([["Cấu kiện", "Ø", "Số thanh", "Dài (m)"], ["D1", 16, 12, 5], ["D1", 8, 40, 1.2], ["C1", 16, 8, 3]])["dong"]
    kq = cot_thep.tinh(dong)
    wb = load_workbook(io.BytesIO(xuat_excel_thep(kq, "Thử", "thep.xlsx")))
    assert wb.sheetnames == ["BANG THEP", "TONG HOP", "CANH BAO"]
    ws = wb["BANG THEP"]
    assert "không phải ước tính" in ws["A3"].value
    for k, d in enumerate(kq["dong"]):
        r = 6 + k
        assert ws.cell(r, 9).value.startswith("=")
        # khối lượng = tổng dài × đơn trọng, mỗi ô là công thức trỏ về ô khác: tính lại phải ra đúng số của Python
        don_trong = _tinh_excel(ws, ws.cell(r, 7).value)
        tong_dai = _tinh_excel(ws, ws.cell(r, 8).value)
        assert don_trong * tong_dai == pytest.approx(d["kl"], rel=1e-9)
    assert ws.cell(6 + len(dong) + 1, 9).value == f"=SUM(I6:I{5 + len(dong)})"
    th = wb["TONG HOP"]
    assert th["A4"].value == 8 and th["A5"].value == 16 and th["C4"].value.startswith("=SUMIF(")


def test_api_doc_file_tinh_va_xuat_excel():
    from app.main import app
    c = TestClient(app)
    du_lieu = _xlsx([TIEU_DE, [1, "D1", "Ø16", 12, 5000, 60, 94.8]])
    r = c.post("/api/cot-thep/doc-file", files={"file": ("t.xlsx", du_lieu)}).json()
    assert len(r["dong"]) == 1
    t = c.post("/api/cot-thep/tinh", json={"dong": r["dong"]}).json()
    assert t["tong_kg"] == pytest.approx(94.8, abs=0.2) and t["doi_chieu"] is None
    x = c.post("/api/cot-thep/xuat-excel", json={"dong": r["dong"], "du_an": "Thử", "nguon": "t.xlsx"})
    assert x.status_code == 200 and load_workbook(io.BytesIO(x.content)).sheetnames[0] == "BANG THEP"
    assert c.post("/api/cot-thep/xuat-excel", json={"dong": []}).status_code == 400
    assert c.post("/api/cot-thep/doc-file", files={"file": ("t.pdf", b"x")}).status_code == 400
