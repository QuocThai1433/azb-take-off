"""Vận hành: sao lưu không phình to (bỏ bản trùng, giới hạn dung lượng) và nhật ký hoạt động."""
import logging
import os
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import luu_tru, nhat_ky
from app.main import app
from tools.tao_ban_ve_mau import tao


@pytest.fixture
def may(tmp_path):
    mau = tmp_path / "khung_mau.dxf"
    tao(mau)
    c = TestClient(app)
    with open(mau, "rb") as f:
        pid = c.post("/api/tai-len", files={"file": ("khung_mau.dxf", f)}).json()["id"]
    tt = {"files": [{"id": pid, "ten": "khung_mau.dxf", "vai_tro": "mat_bang", "layers": [], "vung": None}], "da_dong": []}
    c.post("/api/du-an/trang-thai", json=tt)
    return c, pid, tt


def _tu_dong():
    return list(luu_tru.THU_MUC_BACKUP.glob("AZB_*_tu_dong.zip"))


def test_sao_luu_tu_dong_giong_het_thi_khong_giu_them(may):
    luu_tru.tao_backup("tu_dong")
    n0 = len(_tu_dong())
    time.sleep(1.1)                         # tên file theo giây: bản thứ hai là bản khác tên
    kq = luu_tru.tao_backup("tu_dong")
    assert len(_tu_dong()) == n0 and kq is not None      # nội dung y hệt: bản mới bị bỏ, vẫn trả bản cũ


def test_sao_luu_tu_dong_khac_noi_dung_thi_giu(may):
    c, pid, tt = may
    luu_tru.tao_backup("tu_dong")
    time.sleep(1.1)
    tt["du_an"] = "doi ten"                                # trạng thái đổi -> nội dung zip đổi
    c.post("/api/du-an/trang-thai", json=tt)
    luu_tru.tao_backup("tu_dong")
    assert len(_tu_dong()) >= 2


def test_sao_luu_thu_cong_luon_giu_du_trung(may):
    luu_tru.tao_backup("thu_cong")
    time.sleep(1.1)
    luu_tru.tao_backup("thu_cong")
    assert len(list(luu_tru.THU_MUC_BACKUP.glob("AZB_*_thu_cong.zip"))) == 2


def test_gioi_han_dung_luong_xoa_ban_cu_nhat_giu_ban_moi_nhat(may, monkeypatch):
    monkeypatch.setattr(luu_tru, "SO_BACKUP_TU_DONG", 99)
    monkeypatch.setattr(luu_tru, "SO_BACKUP_KHAC", 99)
    luu_tru.THU_MUC_BACKUP.mkdir(parents=True, exist_ok=True)
    cu = []
    for i in range(5):                                   # 5 bản tự động giả, mỗi bản ~100 KB, tên khác nhau
        p = luu_tru.THU_MUC_BACKUP / f"AZB_2026010{i + 1}_000000_tu_dong.zip"
        with zipfile.ZipFile(p, "w") as z:
            z.writestr("x", os.urandom(100_000))
        os.utime(p, (1_700_000_000 + i * 100, 1_700_000_000 + i * 100))
        cu.append(p)
    monkeypatch.setattr(luu_tru, "DUNG_LUONG_BACKUP_TOI_DA", 250_000)
    luu_tru.tao_backup("thu_cong")
    con = sorted(p.name for p in luu_tru.THU_MUC_BACKUP.glob("AZB_*.zip"))
    tong = sum(p.stat().st_size for p in luu_tru.THU_MUC_BACKUP.glob("AZB_*.zip"))
    assert tong <= 250_000 + 60_000                      # dưới ngưỡng (bản thủ công mới luôn được giữ)
    assert not cu[0].exists() and not cu[1].exists()     # xóa từ bản CŨ NHẤT
    assert any(n.endswith("_thu_cong.zip") for n in con)


# ---------- nhật ký ----------
def test_nhat_ky_ghi_file_va_doc_duoi(tmp_path):
    log = nhat_ky.bat(tmp_path / "logs")
    log.info("xin chào nhật ký")
    for h in log.handlers:
        h.flush()
    dong = nhat_ky.doc_duoi(10, tmp_path / "logs" / "azb.log")
    assert any("xin chào nhật ký" in d for d in dong)
    nhat_ky.bat(tmp_path / "logs")                       # gọi lại không gắn thêm bộ ghi
    assert len([h for h in log.handlers if getattr(h, "baseFilename", "").startswith(str(tmp_path))]) == 1
    for h in list(log.handlers):
        if getattr(h, "baseFilename", "").startswith(str(tmp_path)):
            log.removeHandler(h); h.close()


def test_loi_khong_luong_truoc_tra_ma_loi_va_ghi_nhat_ky(caplog):
    from fastapi import APIRouter
    r = APIRouter()

    @r.get("/api/_thu_loi")
    def _boom():
        raise ZeroDivisionError("x")
    app.include_router(r)
    c = TestClient(app, raise_server_exceptions=False)
    logging.getLogger("azb.main").propagate = True
    with caplog.at_level(logging.ERROR, logger="azb.main"):
        resp = c.get("/api/_thu_loi")
    assert resp.status_code == 500 and "mã " in resp.json()["detail"] and "Traceback" not in resp.text
    assert any("Lỗi không lường trước" in m for m in caplog.messages)


def test_api_nhat_ky_tra_van_ban(monkeypatch, tmp_path):
    f = tmp_path / "azb.log"
    f.write_text("dong 1\ndong 2\n", encoding="utf-8")
    monkeypatch.setattr(nhat_ky, "FILE_LOG", f)
    r = TestClient(app).get("/api/nhat-ky?dong=5")
    assert r.status_code == 200 and "dong 2" in r.text
