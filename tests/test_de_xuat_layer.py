"""Test prototype đề xuất layer: thứ tự ưu tiên, ngưỡng, kiểm tra chéo, dữ liệu gửi AI, đọc từ DXF thật."""
import ezdxf

from app.dxf_reader import doc_ban_ve
from tools.de_xuat_layer import ThongTinLayer, de_xuat_layer, tao_yeu_cau_ai, thong_tin_tu_ban_ve


def _dx(ds, ten):
    return next(d for d in ds if d.ten == ten)


def test_thu_tu_uu_tien_ho_so_roi_luat_cung():
    ds = de_xuat_layer([ThongTinLayer("S-COT"), ThongTinLayer("S-BEAM")], ho_so={"S-COT": "vach"})
    assert (_dx(ds, "S-COT").loai, _dx(ds, "S-COT").nguon) == ("vach", "hồ sơ")
    assert (_dx(ds, "S-BEAM").loai, _dx(ds, "S-BEAM").nguon) == ("dam", "luật tên")


def test_ai_de_xuat_theo_hinh_hoc_va_nguong():
    cot = ThongTinLayer("XYZ_17", so_hinh_kin=40, canh_ngan=0.3, ty_le=1.0)
    ds = de_xuat_layer([cot])
    d = _dx(ds, "XYZ_17")
    assert d.loai == "cot" and d.nguon == "gợi ý hình học"
    assert d.tin_cay < 0.9 and d.hanh_dong == "xac_nhan"  # heuristic không bao giờ tự điền


def test_kiem_tra_cheo_ha_tin_cay_xuong_hoi_nguoi():
    # Giả "AI" tự tin 0.65 là dầm, nhưng hình gần vuông: kiểm tra chéo hạ xuống dưới ngưỡng thấp
    bo = lambda yc: ("dam", 0.65, "giả lập")
    d = de_xuat_layer([ThongTinLayer("Q1", so_hinh_kin=10, canh_ngan=0.3, ty_le=1.2)], bo_de_xuat=bo)[0]
    assert d.loai is None and d.hanh_dong == "hoi_nguoi" and "hạ tin cậy" in d.ly_do


def test_khong_du_can_cu_thi_hoi_nguoi():
    d = de_xuat_layer([ThongTinLayer("ZZZ")])[0]
    assert d.loai is None and d.hanh_dong == "hoi_nguoi"


def test_nhan_chu_giong_nhan_cau_kien_tu_dien():
    tt = ThongTinLayer("QQ", so_chu=3, mau_chu=["C1 300x300", "C2 300x400", "ghi chu"])
    d = de_xuat_layer([tt])[0]
    assert d.loai == "nhan" and d.hanh_dong == "tu_dien"


def test_yeu_cau_ai_khong_chua_toa_do():
    tt = ThongTinLayer("L", so_hinh_kin=3, canh_ngan=0.31234, ty_le=1.0, mau_chu=["x" * 100])
    yc = tao_yeu_cau_ai(tt)
    assert set(yc) == {"ten_layer", "so_hinh_kin", "so_net_ho", "so_chu", "canh_ngan_trung_vi_m",
                       "ty_le_trung_vi", "mau_chu"}
    assert all(len(c) <= 40 for c in yc["mau_chu"])


def test_doc_tu_dxf_that(tmp_path):
    doc = ezdxf.new(units=6)  # mét
    msp = doc.modelspace()
    for i in range(4):  # cột 0.3x0.3 trên layer tên lạ
        x = i * 5.0
        msp.add_lwpolyline([(x, 0), (x + .3, 0), (x + .3, .3), (x, .3)], close=True, dxfattribs={"layer": "XYZ_17"})
    msp.add_lwpolyline([(0, 10), (8, 10), (8, 10.25), (0, 10.25)], close=True, dxfattribs={"layer": "S-BEAM"})
    msp.add_text("C1 300x300", dxfattribs={"layer": "KY_HIEU", "insert": (0, 1), "height": 0.2})
    duong_dan = tmp_path / "mau.dxf"
    doc.saveas(duong_dan)
    ds = de_xuat_layer(thong_tin_tu_ban_ve(doc_ban_ve(str(duong_dan))))
    assert _dx(ds, "XYZ_17").loai == "cot" and _dx(ds, "XYZ_17").nguon == "gợi ý hình học"
    assert _dx(ds, "S-BEAM").nguon == "luật tên"
    assert _dx(ds, "KY_HIEU").loai == "nhan"
