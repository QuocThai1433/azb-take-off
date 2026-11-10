"""Kiểm tra chuẩn layer cho 3D, đọc cao độ kiểu khác, và giới hạn dung lượng file tải lên."""
import io

from fastapi.testclient import TestClient
from shapely.geometry import LineString, Point, box

from app import main
from app.dxf_reader import BanVe, Chu, HinhKin, LayerData
from app.kiem_tra_layer import kiem_tra_chuan_3d
from app.nha_tu_ban_ve import doc_cao_do


def _chu(t):
    return Chu(t, Point(0, 0), "h")


def _bv(layers):
    return BanVe("t", 1.0, "m", layers, [])


def test_cao_do_nhieu_kieu_ghi():
    ld = LayerData("0", chu=[_chu("EL +6.800"), _chu("+6,050"), _chu("+3.200m")])
    assert doc_cao_do(_bv({"0": ld})) == (6.05, 6.8)


def test_chuan_3d_khong_co_tuong_thi_khong_bao():
    assert kiem_tra_chuan_3d(_bv({"C": LayerData("C")}), {"C": "cot"}) == []


def test_chuan_3d_thieu_hinh_kin_cua_va_cao_do():
    tuong = LayerData("T", net_ho=[LineString([(i, 0), (i + 1, 0)]) for i in range(5)])
    kq = kiem_tra_chuan_3d(_bv({"T": tuong}), {"T": "tuong"})
    nd = " | ".join(k["noi_dung"] for k in kq)
    assert "nét rời" in nd and "layer Cửa" in nd and "cao độ mái" in nd
    assert any(k["muc"] == "canh_bao" for k in kq)


def test_chuan_3d_du_chuan_thi_khong_bao():
    tuong = LayerData("T", hinh_kin=[HinhKin(box(0, 0, 4, 0.2), "w", "LWPOLYLINE")])
    cua = LayerData("D", hinh_kin=[HinhKin(box(1, 0, 2, 0.2), "d", "LWPOLYLINE")])
    chu = LayerData("0", chu=[_chu("+6.800"), _chu("+6.050")])
    assert kiem_tra_chuan_3d(_bv({"T": tuong, "D": cua, "0": chu}), {"T": "tuong", "D": "cua"}) == []


def test_tai_len_qua_lon_bi_tu_choi(monkeypatch):
    monkeypatch.setattr(main.config, "app_config", lambda: {"tai_len_toi_da_mb": 1})
    r = TestClient(main.app).post("/api/tai-len", files={"file": ("to.dxf", io.BytesIO(b"0" * (2 * 1024 ** 2)))})
    assert r.status_code == 413 and "quá lớn" in r.json()["detail"]
    assert not any(p.name == "to.dxf" for p in main.THU_MUC_TAI_LEN.rglob("to.dxf"))   # không để lại file dở
