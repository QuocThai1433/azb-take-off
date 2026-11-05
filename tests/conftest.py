import pytest

from app import luu_tru


@pytest.fixture(autouse=True)
def _kho_tam(tmp_path, monkeypatch):
    """Mọi test dùng kho lưu trữ tạm, không bao giờ ghi vào data/ thật (tránh a.dxf, mb.dxf, khung_mau.dxf hiện trong danh sách app)."""
    data = tmp_path / "_kho_data"
    monkeypatch.setattr(luu_tru, "DATA", data)
    monkeypatch.setattr(luu_tru, "THU_MUC_TAI_LEN", data / "uploads")
    monkeypatch.setattr(luu_tru, "FILE_TRANG_THAI", data / "du_an" / "trang_thai.json")
    monkeypatch.setattr(luu_tru, "THU_MUC_BACKUP", data / "backup")
    monkeypatch.setattr("app.main.THU_MUC_TAI_LEN", data / "uploads", raising=False)


@pytest.fixture(autouse=True)
def _ho_so_layer_tam(tmp_path, monkeypatch):
    """Hồ sơ layer đã nhớ cũng dùng file tạm, test không đọc / ghi data/ho_so_layer.yaml thật."""
    from app import ho_so_layer
    monkeypatch.setattr(ho_so_layer, "DUONG_DAN", tmp_path / "_ho_so_layer.yaml")
