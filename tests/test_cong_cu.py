"""Công cụ tính theo cấu kiện: công thức, Excel, quét chọn mặt bằng móng (không nhầm cột) và chi tiết móng."""
import re
from io import BytesIO

import ezdxf
import pytest
import yaml
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import cong_cu
from app.bang_boc import xuat_excel
from app.dxf_reader import doc_ban_ve
from app.main import app
from app.quet_chon import doc_ky_hieu, quet_chi_tiet, quet_mat_bang


def _rect(msp, x0, y0, x1, y1, layer):
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": layer})


def _chon_het(bv, layers=None):
    return {t: {"h": list(range(len(ld.hinh_kin))), "n": list(range(len(ld.net_ho)))}
            for t, ld in bv.layers.items() if (layers is None or t in layers) and (ld.hinh_kin or ld.net_ho)}


def _mat_bang_mong(tmp_path, co_nhan_cot=False, co_nhan_mong=True, layer_mong="S-COT", ten="mb.dxf"):
    """4 móng M1 1500x1500 (mỗi móng một cột 300x300 bên trong) và 2 móng M2 2000x1200. Mọi hình vẽ trên cùng layer
    layer_mong (cố ý trùng layer với cột) để kiểm tra phân loại không dựa vào tên layer."""
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    for i, x in enumerate((0, 6000, 12000, 18000)):
        _rect(msp, x - 750, -750, x + 750, 750, layer_mong)
        _rect(msp, x - 150, -150, x + 150, 150, layer_mong)
        if co_nhan_mong and i == 0:
            msp.add_text("M1", dxfattribs={"layer": "S-TEXT", "insert": (x + 800, 800), "height": 150})
        if co_nhan_cot and i == 0:
            msp.add_text("C1", dxfattribs={"layer": "S-TEXT", "insert": (x + 50, 0), "height": 100})
    for x in (0, 6000):
        _rect(msp, x - 1000, 5000 - 600, x + 1000, 5000 + 600, layer_mong)
        _rect(msp, x - 150, 5000 - 150, x + 150, 5000 + 150, layer_mong)
        if co_nhan_mong and x == 0:
            msp.add_text("M2", dxfattribs={"layer": "S-TEXT", "insert": (x + 1050, 5700), "height": 150})
    f = tmp_path / ten
    doc.saveas(f)
    return doc_ban_ve(f)


# ---------- Công thức ----------
def test_bieu_thuc_tinh_va_tu_choi_ma_doc():
    bien = {"n": 4, "a": 1.5, "b": 1.5, "h": 0.4, "S": 2.25, "P": 6.0, "L": 1.5, "c": 0.3}
    assert cong_cu.tinh_bt("n*(a+2*c)*(b+2*c)*h", bien) == pytest.approx(4 * 2.1 * 2.1 * 0.4)
    assert cong_cu.tinh_bt("max(a,b)**2 - sqrt(4)", bien) == pytest.approx(2.25 - 2)
    for xau in ("__import__('os').system('x')", "a.__class__", "[1][0]", "lambda: 1", "a if b else c", "zz+1", "open('f')", "1;2"):
        with pytest.raises(ValueError):
            cong_cu.kiem_tra_bt(xau, list(bien))
    with pytest.raises(cong_cu.ThieuBien):
        cong_cu.tinh_bt("n*h", {**bien, "h": None})


def test_cong_thuc_mac_dinh_hop_le_va_tinh():
    ds = {d["ma"]: d for d in cong_cu.danh_sach()}
    assert {"dao_dat", "mong", "da_kieng", "cot", "khac"} <= set(ds)
    nhom = [{"ky_hieu": "M1", "n": 4, "a": 1.5, "b": 1.5, "h": 0.4, "S": 2.25, "P": 6.0, "L": 1.5}]
    kq = cong_cu.tinh(ds["mong"]["tham_so"], ds["mong"]["cong_thuc"], nhom)
    gia_tri = {d["ten"]: d["gia_tri"] for d in kq["dong"]}
    assert gia_tri["Bê tông lót móng"] == pytest.approx(4 * 1.7 * 1.7 * 0.1)
    assert gia_tri["Bê tông móng"] == pytest.approx(4 * 2.25 * 0.4)
    assert gia_tri["Ván khuôn móng"] == pytest.approx(4 * 6.0 * 0.4)
    kq = cong_cu.tinh(ds["dao_dat"]["tham_so"], ds["dao_dat"]["cong_thuc"], nhom)
    assert kq["dong"][0]["loi"] == "Chưa có giá trị 'b'" or kq["dong"][0]["gia_tri"] == pytest.approx(4 * 2.1 * 2.1 * 1.5)
    # Thiếu chiều cao thì dòng báo lỗi rõ, không ra số
    kq = cong_cu.tinh(ds["mong"]["tham_so"], ds["mong"]["cong_thuc"], [{**nhom[0], "h": None}])
    assert [d["loi"] for d in kq["dong"]] == [None, "Chưa có giá trị 'h'", "Chưa có giá trị 'h'", "Chưa có giá trị 'h'"]


def test_cong_cu_bo_sung_coc_lanh_to_nen_mai_tuong_va_thep():
    ds = {d["ma"]: d for d in cong_cu.danh_sach()}
    assert {"coc", "lanh_to", "tuong", "nen", "mai"} <= set(ds)
    ten = lambda ma, g: {d["ten"]: d["gia_tri"] for d in cong_cu.tinh(ds[ma]["tham_so"], ds[ma]["cong_thuc"], [g])["dong"]}
    # Mọi công thức của mọi công cụ phải hợp lệ và tính được khi đủ số liệu
    g = {"ky_hieu": "X", "n": 2, "a": 2.0, "b": 1.0, "h": 0.3, "S": 2.0, "P": 6.0, "L": 2.0}
    for ma, d in ds.items():
        assert all(r["loi"] is None for r in cong_cu.tinh(d["tham_so"], d["cong_thuc"], [g])["dong"]), ma
    # Móng: thép = BT móng × hàm lượng 80 kg/m3
    assert ten("mong", g)["Cốt thép móng (ước tính theo hàm lượng)"] == pytest.approx(2 * 2.0 * 0.3 * 80)
    # Đắp đất = đào - móng - lót (c=0.3, H=1.5, d=0.1, tl=0.1)
    dat = ten("dao_dat", g)
    dao = 2 * 2.6 * 1.6 * 1.5
    assert dat["Đào đất hố móng"] == pytest.approx(dao)
    assert dat["Đắp đất hoàn trả hố móng (đào trừ móng và lót; chưa trừ cổ cột)"] == pytest.approx(dao - 2 * 2.0 * 0.3 - 2 * 2.2 * 1.2 * 0.1)
    # Cọc: chiều dài cọc là h (lấy từ nhãn L=16m)
    coc = ten("coc", {**g, "h": 16.0})
    assert coc["Số lượng cọc"] == 2 and coc["Tổng chiều dài cọc"] == pytest.approx(32) and coc["Bê tông cọc"] == pytest.approx(2 * 2.0 * 16)
    # Lanh tô gối 0,2 m mỗi đầu
    assert ten("lanh_to", g)["Bê tông lanh tô"] == pytest.approx(2 * 2.4 * 1.0 * 0.3)
    # Tường cao 3 m, dày 0,2 m
    tuong = ten("tuong", g)
    assert tuong["Xây tường"] == pytest.approx(2 * 2.0 * 3.0 * 0.2) and tuong["Trát tường hai mặt"] == pytest.approx(2 * 2.0 * 3.0 * 2)
    # Nền và mái
    assert ten("nen", g)["Lưới thép nền"] == pytest.approx(2 * 2.0 * 3.95)
    assert ten("mai", g)["Chống thấm mái"] == pytest.approx(2 * (2.0 + 6.0 * 0.3))


def test_sua_va_khoi_phuc_cong_thuc(tmp_path, monkeypatch):
    monkeypatch.setattr(cong_cu, "DUONG_TUY_CHINH", tmp_path / "tuy_chinh.yaml")
    goc = next(d for d in cong_cu.danh_sach() if d["ma"] == "mong")
    ct = [{"ten": "Bê tông móng", "dv": "m3", "bt": "n*a*b*h"}, {"ten": "Ván khuôn móng", "dv": "m2", "bt": "n*P*h*1.05"}]
    moi = cong_cu.luu_tuy_chinh("mong", goc["tham_so"], ct)
    assert moi["da_sua"] and [c["bt"] for c in moi["cong_thuc"]] == ["n*a*b*h", "n*P*h*1.05"]
    assert yaml.safe_load((tmp_path / "tuy_chinh.yaml").read_text(encoding="utf-8"))["mong"]["cong_thuc"][1]["dv"] == "m2"
    with pytest.raises(ValueError):
        cong_cu.luu_tuy_chinh("mong", {}, [{"ten": "x", "dv": "m3", "bt": "n*zz"}])
    with pytest.raises(ValueError):
        cong_cu.luu_tuy_chinh("mong", {}, [{"ten": "x", "dv": "lít", "bt": "n"}])
    with pytest.raises(ValueError):
        cong_cu.luu_tuy_chinh("mong", {"a": {"gia_tri": 1}}, ct)  # trùng tên biến
    ban_goc = cong_cu.khoi_phuc("mong")
    assert not ban_goc["da_sua"] and ban_goc["cong_thuc"][2]["bt"] == "n*P*h"


def test_excel_cong_thuc_khop_python():
    ds = {d["ma"]: d for d in cong_cu.danh_sach()}["dao_dat"]
    nhom = [{"ky_hieu": "M1", "n": 4, "a": 1.5, "b": 1.5, "h": 0.4, "S": 2.25, "P": 6.0, "L": 1.5},
            {"ky_hieu": "M2", "n": 2, "a": 2.0, "b": 1.2, "h": 0.5, "S": 2.4, "P": 6.4, "L": 2.0}]
    kq = cong_cu.tinh(ds["tham_so"], ds["cong_thuc"], nhom)
    dong = [{**d, "cong_cu": "Tính KL đào đất"} for d in kq["dong"]]
    wb = load_workbook(BytesIO(xuat_excel(dong, "Thử")))
    assert wb.sheetnames == ["TH Tính KL đào đất", "CONG CU"]
    ws = wb["CONG CU"]
    dau = [c.value for c in ws[5]]
    cot_kl, cot_bt = dau.index("Khối lượng") + 1, dau.index("Công thức") + 1
    for k, d in enumerate(kq["dong"]):
        r = 6 + k
        ct = ws.cell(r, cot_kl).value
        assert ct.startswith("=") and ws.cell(r, cot_bt).value == d["bt"]
        # Thay địa chỉ ô bằng giá trị trong ô rồi tính lại: phải ra đúng số của Python
        bieu_thuc = re.sub(r"\b([A-Z]{1,2}\d+)\b", lambda m: str(ws[m.group(1)].value or 0), ct[1:]).replace("^", "**")
        assert eval(bieu_thuc) == pytest.approx(d["gia_tri"], rel=1e-9)
    tong = ws.cell(6 + len(kq["dong"]) + 2, cot_kl).value
    assert tong.startswith("=SUMIF(")


# ---------- Đọc ký hiệu ----------
@pytest.mark.parametrize("dong,kh,loai", [
    ("M1", "M1", "mong"), ("MÓNG M2 1500x1500x400", "M2", "mong"), ("F3 (2000x2000)", "F3", "mong"), ("MĐ1", "MĐ1", "mong"),
    ("C1 300x300", "C1", "cot"), ("DK1 300x500", "DK1", "da_kieng"), ("D2 220x500", "D2", "dam"), ("1.M1", "M1", "mong"),
])
def test_doc_ky_hieu(dong, kh, loai):
    d = doc_ky_hieu(dong)
    assert d["ky_hieu"] == kh and d["loai"] == loai


def test_doc_ky_hieu_coc():
    d = doc_ky_hieu("P1 D300 L=16m")
    assert d["ky_hieu"] == "P1" and d["loai"] == "coc" and d["d"] == pytest.approx(0.3) and d["dai_coc"] == pytest.approx(16)
    d = doc_ky_hieu("P.2")
    assert d["ky_hieu"] == "P2" and d["loai"] == "coc" and d["d"] is None and d["dai_coc"] is None


def test_mat_bang_coc_doc_d_l_gop_vong_dong_tam_va_bo_bong_bong_truc(tmp_path):
    """4 cọc mỗi cọc vẽ 2 vòng tròn đồng tâm (D300 và D210), nhãn 'P1 D300 L=16m' + nhãn phụ 'P.1'; 4 bong bóng trục D550 không nhãn cọc."""
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    for i, (x, y) in enumerate([(0, 0), (6000, 0), (0, 6000), (6000, 6000)], 1):
        msp.add_circle((x, y), 150, dxfattribs={"layer": "S-THEP DAI"})
        msp.add_circle((x, y), 105, dxfattribs={"layer": "S-THEP DAI"})
        msp.add_text(f"P{i} D300 L=16m", dxfattribs={"layer": "TEXT", "insert": (x + 300, y), "height": 120})
        msp.add_text(f"P.{i}", dxfattribs={"layer": "TEXT", "insert": (x + 160, y + 100), "height": 120})  # nhãn phụ gần vòng tròn hơn nhãn D/L
    for x in (-3000, 9000):
        msp.add_circle((x, 0), 275, dxfattribs={"layer": "2"})
        msp.add_text("22aX1", dxfattribs={"layer": "TEXT", "insert": (x - 150, 0), "height": 120})
    f = tmp_path / "coc.dxf"
    doc.saveas(f)
    bv = doc_ban_ve(f)
    kq = quet_mat_bang(bv, _chon_het(bv), [-4, -2, 10, 8], "coc")
    coc = [g for g in kq["nhom"] if g["loai"] == "coc"]
    assert sorted(g["ky_hieu"] for g in coc) == ["P1", "P2", "P3", "P4"]
    assert sum(g["n"] for g in coc) == 4 and all(g["dung"] for g in coc)  # mỗi cọc đúng một lần
    for g in coc:
        assert g["h"] == pytest.approx(16.0)
        assert g["S"] == pytest.approx(3.141592653589793 * 0.3 ** 2 / 4, abs=1e-5)
    assert not any(g["dung"] for g in kq["nhom"] if g["loai"] != "coc")  # bong bóng trục không tính
    assert any("đồng tâm" in c for c in kq["canh_bao"])


def test_mat_bang_coc_khung_luoi_truc_lon_khong_gianh_nhan_va_lay_dl_tu_bang(tmp_path):
    """Nhãn chỉ có 'P.1'; D và L nằm ở bảng thống kê cọc. Hình vuông lớn (khung trục) chứa các nhãn không được nhận nhãn của cọc."""
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    _rect(msp, 0, 0, 4000, 4000, "S-TRUC")
    for i, (x, y) in enumerate([(0, 0), (4000, 0), (0, 4000), (4000, 4000)], 1):
        msp.add_circle((x + 1000 if x == 0 else x - 1000, y + 1000 if y == 0 else y - 1000), 150, dxfattribs={"layer": "S-THEP DAI"})
        msp.add_text(f"P.{i}", dxfattribs={"layer": "0", "insert": ((x + 1200) if x == 0 else (x - 800), (y + 1200) if y == 0 else (y - 800)), "height": 100})
    msp.add_text("ĐƯỜNG KÍNH CỌC (mm)", dxfattribs={"layer": "TEXT", "insert": (9000, 0), "height": 100})
    msp.add_text("300", dxfattribs={"layer": "TEXT", "insert": (11500, 0), "height": 100})
    msp.add_text("CHIỀU DÀI CỌC (m)", dxfattribs={"layer": "TEXT", "insert": (9000, -300), "height": 100})
    msp.add_text("16", dxfattribs={"layer": "TEXT", "insert": (11500, -300), "height": 100})
    f = tmp_path / "coc2.dxf"
    doc.saveas(f)
    bv = doc_ban_ve(f)
    kq = quet_mat_bang(bv, _chon_het(bv), [-1, -1, 5, 5], "coc")
    coc = [g for g in kq["nhom"] if g["loai"] == "coc"]
    assert sorted(g["ky_hieu"] for g in coc) == ["P1", "P2", "P3", "P4"] and all(g["n"] == 1 and g["dung"] for g in coc)
    assert all(g["h"] == pytest.approx(16.0) and g["a"] == pytest.approx(0.3) for g in coc)
    assert any("bảng thống kê cọc" in c for c in kq["canh_bao"])


def test_mat_bang_chi_lay_hinh_trong_vung(tmp_path):
    """Khung quét bao 2 cụm cọc, Vùng chỉ bao cụm đầu: cụm ngoài Vùng bị bỏ."""
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    for i, (x, y) in enumerate([(0, 0), (3000, 0), (50000, 0), (53000, 0)], 1):
        msp.add_circle((x, y), 150, dxfattribs={"layer": "COC"})
        msp.add_text(f"P{i} D300 L=16m", dxfattribs={"layer": "TEXT", "insert": (x + 300, y), "height": 120})
    f = tmp_path / "vung.dxf"
    doc.saveas(f)
    bv = doc_ban_ve(f)
    khung = [-2, -2, 60, 2]
    tat_ca = quet_mat_bang(bv, _chon_het(bv), khung, "coc")
    assert sum(g["n"] for g in tat_ca["nhom"] if g["loai"] == "coc") == 4
    trong = quet_mat_bang(bv, _chon_het(bv), khung, "coc", [-2, -2, 6, 2])
    assert sorted(g["ky_hieu"] for g in trong["nhom"] if g["loai"] == "coc") == ["P1", "P2"]
    assert any("ngoài Vùng" in c for c in trong["canh_bao"])


@pytest.mark.parametrize("dong", ["BÊ TÔNG ĐÁ 10x20, M250", "M20x260", "CHI TIẾT MÓNG", "TL 1/20", "GHI CHÚ:", "±0.000"])
def test_khong_nhan_nham_ky_hieu(dong):
    assert doc_ky_hieu(dong) is None


# ---------- Quét chọn mặt bằng móng ----------
def test_mat_bang_mong_doc_ky_hieu_va_tach_cot(tmp_path):
    """Móng và cột cùng layer S-COT: vẫn phải tách đúng nhờ ký hiệu và quan hệ lồng nhau."""
    bv = _mat_bang_mong(tmp_path)
    kq = quet_mat_bang(bv, _chon_het(bv, ["S-COT"]), [-3000 / 1000, -3, 19, 7], "mong")
    mong = {g["ky_hieu"]: g for g in kq["nhom"] if g["loai"] == "mong"}
    cot = [g for g in kq["nhom"] if g["loai"] == "cot"]
    assert set(mong) == {"M1", "M2"}
    assert mong["M1"]["n"] == 4 and mong["M1"]["a"] == pytest.approx(1.5) and mong["M1"]["b"] == pytest.approx(1.5)
    assert mong["M1"]["S"] == pytest.approx(2.25) and mong["M1"]["P"] == pytest.approx(6.0)
    assert mong["M2"]["n"] == 2 and mong["M2"]["a"] == pytest.approx(2.0) and mong["M2"]["b"] == pytest.approx(1.2)
    assert mong["M2"]["nguon_ten"] == "nhãn, suy ra theo kích thước" and mong["M2"]["chac"]
    assert sum(g["n"] for g in cot) == 6 and all(not g["dung"] for g in cot)  # 6 cột bên trong, không tính vào móng
    assert all(g["dung"] for g in mong.values())


def test_mat_bang_mong_khong_nhan_van_ra_mong_theo_hinh_hoc(tmp_path):
    bv = _mat_bang_mong(tmp_path, co_nhan_mong=False)
    kq = quet_mat_bang(bv, _chon_het(bv), [-3, -3, 19, 7], "mong")
    loai = {g["loai"]: g for g in kq["nhom"]}
    assert loai["mong"]["n"] == 4 + 2 or sum(g["n"] for g in kq["nhom"] if g["loai"] == "mong") == 6
    assert sum(g["n"] for g in kq["nhom"] if g["loai"] == "cot") == 6
    assert any("chưa đọc được ký hiệu" in c or "chưa có" in c for c in kq["canh_bao"] + [g["nguon_ten"] for g in kq["nhom"]])
    assert all(g["ky_hieu"] == "" for g in kq["nhom"])


def test_hinh_co_nhan_cot_van_la_cot(tmp_path):
    bv = _mat_bang_mong(tmp_path, co_nhan_cot=True)
    kq = quet_mat_bang(bv, _chon_het(bv), [-3, -3, 19, 7], "mong")
    c1 = next(g for g in kq["nhom"] if g["ky_hieu"] == "C1")
    assert c1["loai"] == "cot" and c1["n"] == 6  # 5 cột chưa nhãn cùng kích thước lấy tên theo kích thước


def test_hinh_ve_trung_hatch_chong_polyline_chi_tinh_mot_lan(tmp_path):
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    for x in (0, 5000):
        _rect(msp, x, 0, x + 1500, 1500, "MONG")
        _rect(msp, x, 0, x + 1500, 1500, "MONG-HATCH")  # vẽ trùng
    msp.add_text("M1", dxfattribs={"layer": "TEXT", "insert": (200, 1700), "height": 150})
    f = tmp_path / "trung.dxf"
    doc.saveas(f)
    bv = doc_ban_ve(f)
    kq = quet_mat_bang(bv, _chon_het(bv), [-1, -1, 8, 3], "mong")
    assert [(g["ky_hieu"], g["n"]) for g in kq["nhom"]] == [("M1", 2)]
    assert any("vẽ trùng" in c for c in kq["canh_bao"])


def test_mong_co_lot_ve_san_cot_long_nhieu_lop_va_bong_bong_truc(tmp_path):
    """Bản vẽ thật: lót 1000 ⊃ móng 800 ⊃ cổ cột 300 ⊃ cột 200, nhãn "F1" gần lót và "F1 800x800x700" xa hơn,
    thêm bong bóng trục tròn Ø550. Phải ra F1 800x800 h=0,7; lót, cổ cột, bong bóng trục không tính vào móng."""
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    for x in (0, 5000, 10000, 15000):
        _rect(msp, x - 500, -500, x + 500, 500, "S-NET CAT")   # lót
        _rect(msp, x - 400, -400, x + 400, 400, "S-NET CAT")   # móng
        _rect(msp, x - 150, -150, x + 150, 150, "S-HATCH DUT")  # cổ cột
        _rect(msp, x - 100, -100, x + 100, 100, "S-COT")        # cột
        msp.add_circle((x, -1200), 275, dxfattribs={"layer": "2"})  # bong bóng trục
        msp.add_text("F1", dxfattribs={"layer": "S-TEXT", "insert": (x - 100, 650), "height": 100})
        msp.add_text("F1 800x800x700", dxfattribs={"layer": "S-TEXT", "insert": (x + 560, 0), "height": 100})
    f = tmp_path / "lot.dxf"
    doc.saveas(f)
    bv = doc_ban_ve(f)
    kq = quet_mat_bang(bv, _chon_het(bv), [-1.5, -2, 16, 1], "mong")
    tinh = [g for g in kq["nhom"] if g["dung"]]
    assert [(g["ky_hieu"], g["n"]) for g in tinh] == [("F1", 4)]
    f1 = tinh[0]
    assert f1["a"] == pytest.approx(0.8) and f1["b"] == pytest.approx(0.8) and f1["h"] == pytest.approx(0.7)
    assert any("bê tông lót vẽ sẵn" in c for c in kq["canh_bao"])
    khac = {(g["a"] and round(g["a"], 3)): g for g in kq["nhom"] if not g["dung"]}
    assert all(g["loai"] in ("cot", "khac") for g in kq["nhom"] if not g["dung"])
    assert any("bong bóng trục" in " ".join(g["ly_do"]) for g in kq["nhom"])


def test_chi_tiet_bang_thong_ke_moi_o_la_mot_chu_rieng(tmp_path):
    """Bảng móng: 'F1' | '800X800X700' | '-0.800' là ba chữ rời cùng hàng; phải ghép thành F1 800x800x700, h=0,7."""
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    for y, kh, kt in ((0, "F1", "800X800X700"), (-400, "F2", "800X1700X700")):
        msp.add_text(kh, dxfattribs={"layer": "T", "insert": (0, y), "height": 100})
        msp.add_text(kt, dxfattribs={"layer": "T", "insert": (1400, y), "height": 100})
    msp.add_text("-0.800", dxfattribs={"layer": "T", "insert": (2800, 0), "height": 100})
    f = tmp_path / "bang.dxf"
    doc.saveas(f)
    kq = quet_chi_tiet(doc_ban_ve(f), [-1, -1.5, 4, 1])
    ds = {k["ky_hieu"]: k for k in kq["ky_hieu"]}
    assert ds["F1"]["kt"] == [[800, 800, 700]] and ds["F1"]["h"] == pytest.approx(0.7)
    assert ds["F2"]["kt"] == [[800, 1700, 700]] and ds["F2"]["h"] == pytest.approx(0.7)
    assert ds["F1"]["cao_do"] == [-0.8]


def test_da_kieng_dung_duong_hop_lay_dai_tu_ky_hieu(tmp_path):
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (4000, 0)], dxfattribs={"layer": "GIANG"})
    msp.add_lwpolyline([(0, 3000), (6000, 3000)], dxfattribs={"layer": "GIANG"})
    msp.add_text("DK1 300x500", dxfattribs={"layer": "TEXT", "insert": (500, 200), "height": 150})
    msp.add_text("DK1", dxfattribs={"layer": "TEXT", "insert": (500, 3200), "height": 150})
    f = tmp_path / "dk.dxf"
    doc.saveas(f)
    bv = doc_ban_ve(f)
    kq = quet_mat_bang(bv, _chon_het(bv), [-1, -1, 7, 4], "da_kieng")
    g = kq["nhom"][0]
    assert (g["ky_hieu"], g["loai"], g["n"], g["dang"]) == ("DK1", "da_kieng", 2, "Đường")
    assert g["n"] * g["L"] == pytest.approx(10.0) and g["h"] == pytest.approx(0.5)


# ---------- Quét chọn chi tiết ----------
def test_chi_tiet_doc_kich_thuoc_va_so_roi(tmp_path):
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    msp.add_text("M1 1500x1500x400", dxfattribs={"layer": "T", "insert": (0, 0), "height": 100})
    msp.add_text("CHI TIẾT MÓNG M2", dxfattribs={"layer": "T", "insert": (10000, 0), "height": 100})
    for v, p in (("500", (10000, 300)), ("1200", (10300, 300)), ("1/20", (10000, 600)), ("GHI CHÚ", (10000, 900))):
        msp.add_text(v, dxfattribs={"layer": "T", "insert": p, "height": 100})
    msp.add_text("M3 h=600", dxfattribs={"layer": "T", "insert": (30000, 0), "height": 100})  # ngoài khung
    f = tmp_path / "ct.dxf"
    doc.saveas(f)
    kq = quet_chi_tiet(doc_ban_ve(f), [-1, -1, 15, 2])
    theo = {k["ky_hieu"]: k for k in kq["ky_hieu"]}
    assert set(theo) == {"M1", "M2"}
    assert theo["M1"]["h"] == pytest.approx(0.4) and theo["M1"]["kt"] == [[1500, 1500, 400]]
    assert theo["M2"]["h"] is None and theo["M2"]["ung_vien"] == [0.5, 1.2]


# ---------- Luồng API ----------
def test_api_mong_hai_buoc_den_excel(tmp_path):
    bv_f = tmp_path / "mb.dxf"
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    for x in (0, 6000, 12000):
        _rect(msp, x - 750, -750, x + 750, 750, "S-COT")
        _rect(msp, x - 150, -150, x + 150, 150, "S-COT")
    msp.add_text("M1", dxfattribs={"layer": "S-TEXT", "insert": (900, 800), "height": 150})
    msp.add_text("M1 1500x1500x400", dxfattribs={"layer": "S-TEXT", "insert": (0, 20000), "height": 150})
    doc.saveas(bv_f)
    cl = TestClient(app)
    ds = cl.get("/api/cong-cu").json()
    assert [d["ma"] for d in ds["cong_cu"]][:4] == ["dao_dat", "mong", "da_kieng", "cot"]
    pid = cl.post("/api/tai-len", files={"file": ("mb.dxf", bv_f.read_bytes())}, data={"don_vi": "auto"}).json()["id"]
    bv = doc_ban_ve(bv_f)
    r1 = cl.post("/api/cong-cu/mat-bang", json={"id": pid, "cong_cu": "mong", "khung": [-3, -3, 14, 3], "chon": _chon_het(bv, ["S-COT"])})
    assert r1.status_code == 200, r1.text
    m1 = next(g for g in r1.json()["nhom"] if g["ky_hieu"] == "M1")
    assert m1["n"] == 3 and m1["loai"] == "mong"
    r2 = cl.post("/api/cong-cu/chi-tiet", json={"id": pid, "cong_cu": "mong", "khung": [-1, 19, 5, 21]})
    h = r2.json()["ky_hieu"][0]["h"]
    assert h == pytest.approx(0.4)
    mong = next(d for d in ds["cong_cu"] if d["ma"] == "mong")
    nhom = [{k: m1[k] for k in ("ky_hieu", "n", "a", "b", "S", "P", "L")} | {"h": h}]
    t = cl.post("/api/cong-cu/tinh", json={"tham_so": mong["tham_so"], "cong_thuc": mong["cong_thuc"], "nhom": nhom}).json()
    assert t["tong"]["m3"] == pytest.approx(3 * 1.7 * 1.7 * 0.1 + 3 * 2.25 * 0.4)
    assert t["tong"]["m2"] == pytest.approx(3 * 6.0 * 0.4)
    dong = [{**d, "cong_cu": "Tính KL móng", "layer": "", "nguon": ""} for d in t["dong"]]
    x = cl.post("/api/xuat-bang-boc", json={"dong": dong, "du_an": "Thử"})
    assert x.status_code == 200 and "CONG CU" in load_workbook(BytesIO(x.content)).sheetnames
    # Công thức sai bị từ chối rõ ràng
    bad = cl.post("/api/cong-cu/tinh", json={"tham_so": {}, "cong_thuc": [{"ten": "x", "dv": "m3", "bt": "n*zz"}], "nhom": nhom})
    assert bad.status_code == 400 and "zz" in bad.json()["detail"]


def test_hinh_rat_nho_va_nhan_dam_khong_lam_nhieu_cong_cu_mong(tmp_path):
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    _rect(msp, 0, 0, 1500, 1500, "S-MONG")
    _rect(msp, 600, 600, 900, 900, "S-MONG")  # cột trong móng
    for k in range(5):
        _rect(msp, 3000 + k * 200, 0, 3000 + k * 200 + 75, 37, "S-MONG")  # nét chi tiết nhỏ cùng layer móng
    msp.add_text("M1", dxfattribs={"layer": "TEXT", "insert": (100, 1600), "height": 150})
    msp.add_text("D1 220x500", dxfattribs={"layer": "TEXT", "insert": (700, 1000), "height": 150})  # nhãn dầm ngay cạnh
    f = tmp_path / "nhieu.dxf"
    doc.saveas(f)
    bv = doc_ban_ve(f)
    kq = quet_mat_bang(bv, _chon_het(bv), [-1, -1, 5, 2], "mong")
    theo = {(g["loai"], g["ky_hieu"]): g for g in kq["nhom"]}
    assert theo[("mong", "M1")]["n"] == 1 and theo[("mong", "M1")]["dung"]
    assert theo[("cot", "")]["n"] == 1 and not theo[("cot", "")]["dung"]
    nho = theo[("khac", "")]
    assert nho["n"] == 5 and not nho["dung"]
    assert not any(g["loai"] == "dam" for g in kq["nhom"])


def test_chi_tiet_doc_cao_do_theo_ky_hieu(tmp_path):
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    msp.add_text("M1 1500x1500", dxfattribs={"layer": "T", "insert": (0, 0), "height": 100})
    for v, p in (("-1.700", (200, -300)), ("-0.900", (400, -300)), ("±0.000", (600, -300))):
        msp.add_text(v, dxfattribs={"layer": "T", "insert": p, "height": 100})
    msp.add_text("1.500", dxfattribs={"layer": "T", "insert": (0, -600), "height": 100})  # không dấu: kích thước, không phải cao độ
    msp.add_text("M2 h=500", dxfattribs={"layer": "T", "insert": (20000, 0), "height": 100})
    msp.add_text("-2.000", dxfattribs={"layer": "T", "insert": (20100, -300), "height": 100})
    f = tmp_path / "cd.dxf"
    doc.saveas(f)
    kq = quet_chi_tiet(doc_ban_ve(f), [-1, -2, 30, 2])
    theo = {k["ky_hieu"]: k for k in kq["ky_hieu"]}
    assert theo["M1"]["cao_do"] == [-1.7, -0.9, 0.0]
    assert theo["M2"]["cao_do"] == [-2.0] and theo["M2"]["h"] == pytest.approx(0.5)
    assert kq["cao_do_chung"] == []


def test_doi_tuong_mang_so_lieu_rieng_de_gop_nhom(tmp_path):
    bv = _mat_bang_mong(tmp_path)
    kq = quet_mat_bang(bv, _chon_het(bv), [-3, -3, 19, 7], "mong")
    for g in kq["nhom"]:
        assert len(g["doi_tuong"]) == g["n"]
        assert g["S"] == pytest.approx(sum(o["S"] for o in g["doi_tuong"]) / g["n"], rel=1e-5)
        assert all(o["rect"] is True and o["a"] >= o["b"] for o in g["doi_tuong"])


def test_cong_thuc_dung_cao_do_va_thieu_cao_do():
    nhom = [{"ky_hieu": "M1", "n": 2, "a": 1.5, "b": 1.5, "h": 0.4, "S": 2.25, "P": 6.0, "L": 1.5, "zd": -1.7, "zm": -0.9}]
    ct = [{"ten": "Sâu đáy móng", "dv": "m", "bt": "n*abs(zd)"}]
    kq = cong_cu.tinh({}, ct, nhom)
    assert kq["dong"][0]["gia_tri"] == pytest.approx(3.4)
    kq = cong_cu.tinh({}, ct, [{**nhom[0], "zd": None}])
    assert kq["dong"][0]["loi"] == "Chưa có giá trị 'zd'"


def test_excel_bang_tong_hop_theo_yeu_cau_chi_van(tmp_path):
    """STT, tên, ĐV, SL, D, R, C, CV, DT, KL bê tông, KL ván khuôn; khối lượng là công thức khớp Python."""
    ds = {d["ma"]: d for d in cong_cu.danh_sach()}["mong"]
    nhom = [{"ky_hieu": "M1", "n": 6, "a": 1.5, "b": 1.5, "h": 0.4, "S": 2.25, "P": 6.0, "L": 1.5, "zd": -1.7, "zm": -0.9},
            {"ky_hieu": "M2", "n": 2, "a": 2.0, "b": 1.4, "h": 0.5, "S": 2.8, "P": 6.8, "L": 2.0}]
    kq = cong_cu.tinh(ds["tham_so"], ds["cong_thuc"], nhom)
    dong = [{**d, "cong_cu": "Tính KL móng", "vi_tri": "(0.0; 0.0)"} for d in kq["dong"]]
    wb = load_workbook(BytesIO(xuat_excel(dong, "Thử")))
    ws = wb["TH Tính KL móng"]
    dau = [c.value for c in ws[5]]
    for ten in ("STT", "Tên", "ĐV", "SL", "Dài D (m)", "Rộng R (m)", "Cao C (m)", "Chu vi CV (m)", "Diện tích DT (m²)", "Cao độ đáy (m)"):
        assert ten in dau, ten
    assert "Bê tông móng (m³)" in dau and "Ván khuôn móng (m²)" in dau and dau[-1].startswith("Vị trí")
    c_bt, c_vk = dau.index("Bê tông móng (m³)") + 1, dau.index("Ván khuôn móng (m²)") + 1
    gt = {(d["ky_hieu"], d["ten"]): d["gia_tri"] for d in kq["dong"]}
    for r, kh in ((6, "M1"), (7, "M2")):
        assert ws.cell(r, 2).value == kh and ws.cell(r, 3).value == "cái"
        for c, ten in ((c_bt, "Bê tông móng"), (c_vk, "Ván khuôn móng")):
            f = ws.cell(r, c).value
            bt = re.sub(r"\b([A-Z]{1,2}\d+)\b", lambda m: str(ws[m.group(1)].value or 0), f[1:]).replace("^", "**")
            assert eval(bt) == pytest.approx(gt[(kh, ten)], rel=1e-9)
    assert ws.cell(8, 2).value == "CỘNG" and ws.cell(8, 4).value.startswith("=SUM(")
    assert ws.cell(6, len(dau)).value == "(0.0; 0.0)"


# ---------- Trường hợp lỗi và biên ----------
def test_da_kieng_duong_lay_b_tu_nhan(tmp_path):
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    msp.add_lwpolyline([(0, 0), (4000, 0)], dxfattribs={"layer": "GIANG"})
    msp.add_text("DK1 300x500", dxfattribs={"layer": "TEXT", "insert": (500, 200), "height": 150})
    f = tmp_path / "dk2.dxf"
    doc.saveas(f)
    bv = doc_ban_ve(f)
    g = quet_mat_bang(bv, _chon_het(bv), [-1, -1, 5, 1], "da_kieng")["nhom"][0]
    assert g["b"] == pytest.approx(0.3) and g["h"] == pytest.approx(0.5)
    kq = cong_cu.tinh({}, [{"ten": "BT", "dv": "m3", "bt": "n*L*b*h"}], [{k: g[k] for k in ("n", "a", "b", "h", "S", "P", "L")} | {"ky_hieu": "DK1"}])
    assert kq["dong"][0]["gia_tri"] == pytest.approx(4.0 * 0.3 * 0.5)


def test_quet_khong_co_hinh_va_khung_rong(tmp_path):
    bv = _mat_bang_mong(tmp_path)
    kq = quet_mat_bang(bv, {}, [0, 0, 1, 1], "mong")
    assert kq["nhom"] == [] and kq["canh_bao"]
    assert quet_mat_bang(bv, {"KHONG_CO_LAYER": {"h": [0, 5], "n": [1]}, "S-COT": {"h": [99999, -1], "n": []}}, [0, 0, 1, 1], "mong")["nhom"] == []
    kq = quet_chi_tiet(bv, [100, 100, 101, 101])
    assert kq["ky_hieu"] == [] and kq["canh_bao"]


def test_api_loi_ro_rang(tmp_path):
    cl = TestClient(app)
    assert cl.post("/api/cong-cu/mat-bang", json={"id": "khong-co", "cong_cu": "mong", "khung": [0, 0, 1, 1]}).status_code == 404
    f = tmp_path / "a.dxf"
    ezdxf.new(units=4).saveas(f)
    pid = cl.post("/api/tai-len", files={"file": ("a.dxf", f.read_bytes())}, data={"don_vi": "auto"}).json()["id"]
    assert cl.post("/api/cong-cu/mat-bang", json={"id": pid, "cong_cu": "khong_co", "khung": [0, 0, 1, 1]}).status_code == 404
    assert cl.post("/api/cong-cu/mat-bang", json={"id": pid, "cong_cu": "mong", "khung": [0, 0, 1]}).status_code == 400
    assert cl.post("/api/cong-cu/chi-tiet", json={"id": pid, "cong_cu": "mong", "khung": []}).status_code == 400
    assert cl.put("/api/cong-cu/khong_co", json={"cong_thuc": []}).status_code == 404
    assert cl.put("/api/cong-cu/mong", json={"cong_thuc": []}).status_code == 400
    # Dữ liệu bảng bóc sai không làm máy chủ lỗi 500
    sai = cl.post("/api/xuat-bang-boc", json={"dong": [{"bt": "n*zz", "ten": "x", "dv": "m3", "bien": {"n": 1}}]})
    assert sai.status_code == 400


def test_chia_cho_0_va_gia_tri_la():
    ct = [{"ten": "x", "dv": "m", "bt": "n/b"}, {"ten": "y", "dv": "m", "bt": "-n*a"}, {"ten": "z", "dv": "m", "bt": "n**2"}]
    kq = cong_cu.tinh({}, ct, [{"ky_hieu": "A", "n": 3, "a": 2.0, "b": 0}])
    assert [d["loi"] for d in kq["dong"]] == ["Chia cho 0", None, None]
    assert kq["dong"][1]["gia_tri"] == pytest.approx(-6) and kq["dong"][2]["gia_tri"] == 9
    # Nhóm rỗng, công thức bắt buộc có
    assert cong_cu.tinh({}, ct, [])["dong"] == []
    with pytest.raises(ValueError):
        cong_cu.tinh({}, [], [{"n": 1}])


def test_excel_ten_sheet_ky_tu_la_va_hai_cong_cu(tmp_path):
    ds = {d["ma"]: d for d in cong_cu.danh_sach()}
    nhom = [{"ky_hieu": "M1", "n": 2, "a": 1.5, "b": 1.5, "h": 0.4, "S": 2.25, "P": 6.0, "L": 1.5}]
    dong = []
    for ma, ten in (("mong", "Tính KL móng / [thử]: *?"), ("cot", "Tính KL cột")):
        kq = cong_cu.tinh(ds[ma]["tham_so"], ds[ma]["cong_thuc"], nhom)
        dong += [{**d, "cong_cu": ten} for d in kq["dong"]]
    wb = load_workbook(BytesIO(xuat_excel(dong, "Thử")))
    assert len(wb.sheetnames) == 3 and all(len(n) <= 31 and not re.search(r"[/\*?:\[\]]", n) for n in wb.sheetnames)


def test_hieu_nang_quet_nhieu_hinh(tmp_path):
    import time
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    for i in range(40):
        for j in range(40):
            _rect(msp, i * 4000, j * 4000, i * 4000 + 1500, j * 4000 + 1500, "MONG")
            _rect(msp, i * 4000 + 600, j * 4000 + 600, i * 4000 + 900, j * 4000 + 900, "MONG")
            if i % 5 == 0 and j % 5 == 0:
                msp.add_text("M1", dxfattribs={"layer": "TEXT", "insert": (i * 4000 + 100, j * 4000 + 1600), "height": 150})
    f = tmp_path / "lon.dxf"
    doc.saveas(f)
    bv = doc_ban_ve(f)
    t0 = time.time()
    kq = quet_mat_bang(bv, _chon_het(bv), [-1, -1, 170, 170], "mong")
    assert time.time() - t0 < 20
    assert sum(g["n"] for g in kq["nhom"] if g["loai"] == "mong") == 1600
    assert sum(g["n"] for g in kq["nhom"] if g["loai"] == "cot") == 1600


def test_bang_boc_dong_khoi_luong_co_san():
    """Dòng từ tab Khối lượng: công thức = SL × khối lượng, đơn vị m3/m2 chuẩn hóa để SUMIF cộng đúng."""
    from openpyxl import load_workbook
    from io import BytesIO
    dong = [{"ten": "Bê tông cột", "layer": "a.dwg", "cach": "co_san", "don_vi": "m3", "so_luong": 1, "cao": 0.576, "nguon": "Tab Khối lượng"},
            {"ten": "Ván khuôn cột", "layer": "a.dwg", "cach": "co_san", "don_vi": "m2", "so_luong": 1, "cao": 11.52, "nguon": "Tab Khối lượng"}]
    ws = load_workbook(BytesIO(xuat_excel(dong, "T")))["BANG BOC"]
    assert ws["I6"].value == "=E6*H6" and ws["H6"].value == 0.576
    assert ws["J6"].value == "m³" and ws["J7"].value == "m²"
    assert any(str(c.value).startswith('=SUMIF(J6:J7,"m³"') for row in ws.iter_rows() for c in row)
