"""Gán layer chuẩn: luật tên (dựng từ các layer THẬT đã gặp), xref, hồ sơ, bằng chứng từ nhãn, cổng kiểm tra."""
import ezdxf
import pytest
from fastapi.testclient import TestClient

from app import config, ho_so_layer, kiem_tra_layer
from app.dxf_reader import doc_ban_ve
from tools.de_xuat_layer import de_xuat_layer, thong_tin_tu_ban_ve

# (tên layer thật trong bản vẽ của người dùng, loại gán sẵn đúng)
LAYER_THAT = [
    ("THEP MONG", "bo_qua"), ("THEP CHU", "bo_qua"), ("S-THEP CHU", "bo_qua"), ("S-THEP DAI", "bo_qua"),
    ("SI-FERRAILLAGE-BARRE", "bo_qua"), ("S-Steel", "bo_qua"),
    ("SI-HACHURE-BETON", "bo_qua"), ("S-NET HATCH", "bo_qua"), ("Defpoints", "bo_qua"), ("DEFPOINTS", "bo_qua"),
    ("San-truc", "bo_qua"), ("S-GRID", "bo_qua"), ("D-TRUC", "bo_qua"),
    ("Mong-sohieu", "nhan"), ("CHU-250", "nhan"), ("CHUTHICH", "nhan"), ("GHICHU", "nhan"),
    ("S-Text250", "nhan"), ("TEXTTHEP", "nhan"), ("S-GHI CHU", "nhan"),
    ("A-Wall", "bo_qua"), ("A-COT", "bo_qua"), ("A-Detl-XFine", "bo_qua"),
    ("X - NHA BAO VE 2-1$0$A-Wall", "bo_qua"),
    ("X - NHA BAO VE 2-1$0$WALL", "tuong"),            # 'wall' là tường kiến trúc (chỉ dựng 3D, không tính khối lượng)
    ("WALL", "tuong"), ("0-WALL", "tuong"),            # 'wall' trần: tường kiến trúc, không bao giờ tự gán thành vách bê tông
    ("0", "bo_qua"), ("1", "bo_qua"), ("05", "bo_qua"), ("100", "bo_qua"), ("COBAN", "bo_qua"), ("BETONG", "bo_qua"),
    ("S-COT", "cot"), ("S-Column", "cot"), ("S-DAM", "dam"), ("S-Beam", "dam"),
    ("S-Foundation", "mong"), ("Mong-netmanh", "mong"), ("PILE", "coc"), ("S-Pile", "coc"), ("coc", "coc"),
    ("S-LO_SAN", "lo_san"), ("S-Wall", "vach"),
]


@pytest.mark.parametrize("ten,mong_doi", LAYER_THAT)
def test_goi_y_tren_layer_that(ten, mong_doi):
    assert config.goi_y_loai_layer(ten) == mong_doi


def test_chuan_hoa_ten_bo_tien_to_xref():
    assert config.chuan_hoa_ten("X - NHA BAO VE 2-1$0$A-Wall") == ("a wall", True)
    assert config.chuan_hoa_ten("XREFF MAT BANG MOI$0$A.V_Line_08")[1] is True
    assert config.chuan_hoa_ten("Mong-sohieu") == ("mong sohieu", False)
    assert config.chuan_hoa_ten("Mật Độ Đài")[0] == "mat do dai"


def test_layer_ket_cau_trong_xref_bi_ha_tin_cay_khong_tu_gan():
    loai, tin_cay, ly_do, _ = config.phan_tich_ten("X - ABC$0$S-Column")
    assert loai == "cot" and tin_cay < config.NGUONG_TU_GAN and "xref" in ly_do
    assert config.goi_y_loai_layer("X - ABC$0$S-Column") == "bo_qua"


def test_khong_khop_chuoi_con():
    # 'chu' không được khớp trong 'hachure'; 'san' không khớp trong 'sanitary'; 'dam' không khớp trong 'damper'
    assert config.phan_tich_ten("sanitary")[0] is None
    assert config.phan_tich_ten("damper")[0] is None
    assert config.phan_tich_ten("SI-HACHURE-BETON")[0] == "bo_qua"


# ---------- hồ sơ ----------
def test_ho_so_nho_tra_xoa_va_khong_nho_ten_mo_ho():
    them, bo = ho_so_layer.nho([{"ten": "Q-KHUNG", "loai": "dam"}, {"ten": "0", "loai": "cot"},
                                {"ten": "100", "loai": "cot"}, {"ten": "x", "loai": "cot"}])
    assert them == 1 and sorted(bo) == ["0", "100", "x"]
    assert config.goi_y_loai_layer("q-khung") == "dam"         # chuẩn hóa: không phân biệt hoa thường
    assert config.goi_y_loai_layer("0") == "bo_qua"
    assert config.phan_tich_ten("Q-KHUNG")[3] == "hồ sơ"
    assert ho_so_layer.xoa("q khung") is True and config.goi_y_loai_layer("Q-KHUNG") == "bo_qua"


def test_ho_so_thang_luat_ten():
    ho_so_layer.nho([{"ten": "S-COT", "loai": "vach"}])
    assert config.goi_y_loai_layer("S-COT") == "vach"


def test_nut_ghi_nho_khong_ghi_vao_layer_map_yaml():
    from app.main import app
    truoc = (config.CONFIG_DIR / "layer_map.yaml").read_text(encoding="utf-8")
    c = TestClient(app)
    r = c.post("/api/layer-map/nho", json={"ds": [{"ten": "KHUNG-LA", "loai": "dam"}, {"ten": "3", "loai": "cot"}]}).json()
    assert r["them"] == 1 and r["bo_qua_vi_mo_ho"] == ["3"]
    assert (config.CONFIG_DIR / "layer_map.yaml").read_text(encoding="utf-8") == truoc
    assert c.get("/api/ho-so-layer").json()["ds"] == [{"khoa": "khung la", "loai": "dam"}]
    assert c.delete("/api/ho-so-layer", params={"khoa": "khung la"}).json()["da_xoa"] is True
    assert c.get("/api/ho-so-layer").json()["ds"] == []


# ---------- bằng chứng từ nhãn ----------
def _vuong(msp, x, y, layer, c=0.3):
    msp.add_lwpolyline([(x, y), (x + c, y), (x + c, y + c), (x, y + c)], close=True, dxfattribs={"layer": layer})


def _nhan(msp, noi_dung, x, y):
    msp.add_text(noi_dung, dxfattribs={"layer": "KY_HIEU", "insert": (x, y), "height": 0.1})


def _ban_ve(tmp_path, dung):
    doc = ezdxf.new(units=6)
    dung(doc.modelspace())
    f = tmp_path / "t.dxf"
    doc.saveas(f)
    return doc_ban_ve(str(f))


def _dx(bv, ten):
    return next(d for d in de_xuat_layer(thong_tin_tu_ban_ve(bv)) if d.ten == ten)


def test_layer_ten_so_nhan_biet_qua_nhan_gan_hinh(tmp_path):
    def dung(m):
        for i in range(10):                      # layer '7' (tên vô nghĩa): 10 hình vuông, đều có nhãn C?
            _vuong(m, i * 5, 0, "7")
            _nhan(m, f"C{i + 1} 300x300", i * 5, 0.4)
    d = _dx(_ban_ve(tmp_path, dung), "7")
    assert d.loai == "cot" and d.nguon == "nhãn" and d.hanh_dong == "xac_nhan" and d.tin_cay <= 0.88


def test_layer_lon_chi_vai_hinh_co_nhan_thi_khong_gan_ca_layer(tmp_path):
    def dung(m):
        for i in range(60):                      # layer '0' kiểu bản vẽ thật: 60 hình, chỉ 6 hình có nhãn
            _vuong(m, i * 5, 0, "0")
        for i in range(6):
            _nhan(m, f"M{i + 1}", i * 5, 0.4)
    d = _dx(_ban_ve(tmp_path, dung), "0")
    assert d.loai is None and d.lan and d.hanh_dong == "hoi_nguoi"
    assert "chỉ" in d.ly_do


def test_layer_lan_nhieu_loai_khong_gan_ca_layer(tmp_path):
    def dung(m):
        for i in range(12):
            _vuong(m, i * 5, 0, "X9")
            _nhan(m, ("C" if i % 2 else "D") + f"{i + 1}", i * 5, 0.4)
    d = _dx(_ban_ve(tmp_path, dung), "X9")
    assert d.lan and d.loai is None


def test_ten_va_nhan_trung_nhau_tang_tin_cay_mau_thuan_ha_xuong(tmp_path):
    def dung(m):
        for i in range(10):
            _vuong(m, i * 5, 0, "S-COT")         # tên cột, nhãn cột -> tăng
            _nhan(m, f"C{i + 1}", i * 5, 0.4)
            _vuong(m, i * 5, 20, "S-DAM")        # tên dầm nhưng nhãn lại là cột -> mâu thuẫn
            _nhan(m, f"C{i + 1}", i * 5, 20.4)
    bv = _ban_ve(tmp_path, dung)
    dc, dd = _dx(bv, "S-COT"), _dx(bv, "S-DAM")
    assert dc.nguon == "luật tên + nhãn" and dc.tin_cay > 0.9
    assert dd.hanh_dong == "xac_nhan" and dd.tin_cay < 0.9 and "Mâu thuẫn" in dd.ly_do


# ---------- cổng kiểm tra ----------
def test_cong_kiem_tra_bat_layer_thep_gan_nhu_bo_tong(tmp_path):
    def dung(m):
        for i in range(5):
            _vuong(m, i * 5, 0, "THEP MONG")
            _vuong(m, i * 5, 9, "X - ABC$0$S-Column")
    bv = _ban_ve(tmp_path, dung)
    loai = {"THEP MONG": "mong", "X - ABC$0$S-Column": "cot"}
    ds = kiem_tra_layer.kiem_tra_gan_layer(bv, loai, de_xuat_layer(thong_tin_tu_ban_ve(bv)))
    nd = " | ".join(x["noi_dung"] for x in ds)
    assert "THEP MONG" in nd and "cốt thép" in nd.lower()
    assert "xref" in nd


def test_cong_kiem_tra_ket_qua_vach_bat_thuong():
    kq = {"tong_hop": [{"ma": "be_tong_vach", "khoi_luong": 119.0}, {"ma": "van_khuon_vach", "khoi_luong": 1060.0},
                       {"ma": "be_tong_cot", "khoi_luong": 4.0}, {"ma": "be_tong_dam", "khoi_luong": 37.0}]}
    out = kiem_tra_layer.kiem_tra_ket_qua(kq)
    assert len(out) == 1 and "Vách/lõi chiếm 74%" in out[0]
    assert kiem_tra_layer.kiem_tra_ket_qua({"tong_hop": [{"ma": "be_tong_vach", "khoi_luong": 5}, {"ma": "be_tong_cot", "khoi_luong": 30}]}) == []
