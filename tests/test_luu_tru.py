"""Đóng bản vẽ chỉ gỡ khỏi màn hình, file vẫn được giữ và mở lại được; chỉ xóa hẳn khi gọi DELETE."""
import pytest
from fastapi.testclient import TestClient

from app import luu_tru
from app.main import app
from tools.tao_ban_ve_mau import tao


@pytest.fixture
def may(tmp_path, monkeypatch):
    """Trỏ kho lưu trữ sang thư mục tạm để không đụng dữ liệu thật trong data/."""
    data = tmp_path / "data"
    monkeypatch.setattr(luu_tru, "DATA", data)
    monkeypatch.setattr(luu_tru, "THU_MUC_TAI_LEN", data / "uploads")
    monkeypatch.setattr(luu_tru, "FILE_TRANG_THAI", data / "du_an" / "trang_thai.json")
    monkeypatch.setattr(luu_tru, "THU_MUC_BACKUP", data / "backup")
    monkeypatch.setattr("app.main.THU_MUC_TAI_LEN", data / "uploads", raising=False)
    mau = tmp_path / "khung_mau.dxf"
    tao(mau)
    return TestClient(app), mau


def _tai_len(c, mau):
    with open(mau, "rb") as f:
        r = c.post("/api/tai-len", files={"file": ("khung_mau.dxf", f)})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_dong_roi_mo_lai_khong_phai_tai_len(may):
    c, mau = may
    pid = _tai_len(c, mau)
    # Dự án đóng bản vẽ: không còn trong files nhưng nằm trong da_dong
    tt = {"files": [], "da_dong": [{"id": pid, "ten": "khung_mau.dxf", "vai_tro": "mat_bang", "layers": [], "vung": None}]}
    assert c.post("/api/du-an/trang-thai", json=tt).status_code == 200
    ds = c.get("/api/ban-ve").json()["ds"]
    assert [d["id"] for d in ds] == [pid]            # vẫn liệt kê được để mở lại
    assert c.get(f"/api/ban-ve/{pid}").status_code == 200   # đọc lại được từ file đã lưu
    assert pid in luu_tru.ids_trong(c.get("/api/du-an/trang-thai").json()["trang_thai"])  # sao lưu cũng mang theo


def test_chi_xoa_han_khi_goi_delete(may):
    c, mau = may
    pid = _tai_len(c, mau)
    tt = {"files": [], "da_dong": [{"id": pid, "ten": "khung_mau.dxf", "vai_tro": "mat_bang", "layers": [], "vung": None}]}
    c.post("/api/du-an/trang-thai", json=tt)
    assert c.delete(f"/api/ban-ve/{pid}").json()["da_xoa"] is True
    assert c.get("/api/ban-ve").json()["ds"] == []
    assert c.get("/api/du-an/trang-thai").json()["trang_thai"]["da_dong"] == []   # không còn nhớ bản vẽ đã xóa
    assert any("truoc_xoa" in b["ten"] for b in c.get("/api/du-an/sao-luu").json()["ds"])   # luôn sao lưu trước khi xóa


def test_nhap_goi_khong_xoa_file_cu(may):
    c, mau = may
    pid = _tai_len(c, mau)
    c.post("/api/du-an/trang-thai", json={"files": [{"id": pid, "ten": "khung_mau.dxf", "vai_tro": "mat_bang", "layers": [], "vung": None}]})
    goi = c.get("/api/du-an/xuat-goi").content
    pid2 = _tai_len(c, mau)
    c.post("/api/du-an/trang-thai", json={"files": [{"id": pid2, "ten": "khung_mau.dxf", "vai_tro": "mat_bang", "layers": [], "vung": None}]})
    assert c.post("/api/du-an/nhap-goi", files={"file": ("g.zip", goi)}).status_code == 200
    assert pid2 in {d["id"] for d in c.get("/api/ban-ve").json()["ds"]}   # file của dự án cũ không bị dọn mất
