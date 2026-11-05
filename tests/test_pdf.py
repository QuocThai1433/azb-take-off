import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pdf_reader import doc_ty_le

client = TestClient(app)


def _tao_pdf(duong, ty_le_chu="TL 1/100", them_trang=False):
    pdf = pymupdf.open()
    pg = pdf.new_page(width=842, height=595)
    # cột 300x300 thực tế (1/100 -> 3mm giấy = 8.504 pt) và dầm 4 net hở
    c = 3 / 25.4 * 72
    pg.draw_rect(pymupdf.Rect(100, 100, 100 + c, 100 + c))
    for i in range(6):
        pg.draw_line((200 + i * 30, 100), (200 + i * 30, 160))
    if ty_le_chu:
        pg.insert_text((50, 550), ty_le_chu, fontsize=10)
    pg.insert_text((100, 90), "C1 300x300", fontsize=8)
    if them_trang:
        pdf.new_page(width=842, height=595).draw_line((10, 10), (200, 200))
    pdf.save(str(duong))
    pdf.close()


def test_doc_ty_le():
    assert doc_ty_le("MẶT BẰNG TẦNG 2 TL: 1/50") == 50
    assert doc_ty_le("TỶ LỆ 1:100") == 100
    assert doc_ty_le("không có gì") is None


def test_tai_pdf_doc_ty_le_va_kich_thuoc(tmp_path):
    f = tmp_path / "mb.pdf"
    _tao_pdf(f)
    with open(f, "rb") as fh:
        r = client.post("/api/tai-len", files={"file": ("mb.pdf", fh, "application/pdf")}, data={"don_vi": "auto"})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["ten_file"] == "mb.dxf" and j["don_vi"] == "mm"
    assert any("1/100" in c for c in j["canh_bao"])
    h = client.get("/api/hinh", params={"id": j["id"]}).json()
    assert h  # có dữ liệu hình để vẽ


def test_ty_le_nhap_tay_ghi_de(tmp_path):
    f = tmp_path / "mb.pdf"
    _tao_pdf(f, ty_le_chu=None)
    with open(f, "rb") as fh:
        r = client.post("/api/tai-len", files={"file": ("mb.pdf", fh, "application/pdf")}, data={"ty_le": "50"})
    assert r.status_code == 200
    assert any("1/50" in c for c in r.json()["canh_bao"])


def test_khong_co_ty_le_canh_bao(tmp_path):
    f = tmp_path / "mb.pdf"
    _tao_pdf(f, ty_le_chu=None)
    with open(f, "rb") as fh:
        j = client.post("/api/tai-len", files={"file": ("mb.pdf", fh, "application/pdf")}).json()
    assert any("tỷ lệ" in c.lower() for c in j["canh_bao"])


def test_pdf_nhieu_trang_chon_trang(tmp_path):
    f = tmp_path / "mb.pdf"
    _tao_pdf(f, them_trang=True)
    with open(f, "rb") as fh:
        j = client.post("/api/tai-len", files={"file": ("mb.pdf", fh, "application/pdf")}).json()
    assert j["so_trang_pdf"] == 2
    with open(f, "rb") as fh:
        r = client.post("/api/tai-len", files={"file": ("mb.pdf", fh, "application/pdf")}, data={"trang": "9"})
    assert r.status_code == 400


def test_pdf_scan_khong_co_vector(tmp_path):
    f = tmp_path / "scan.pdf"
    pdf = pymupdf.open()
    pdf.new_page().insert_text((50, 50), "chi co chu")
    pdf.save(str(f))
    with open(f, "rb") as fh:
        r = client.post("/api/tai-len", files={"file": ("scan.pdf", fh, "application/pdf")})
    assert r.status_code == 400 and "vector" in r.json()["detail"]
