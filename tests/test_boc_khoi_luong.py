"""Kiểm thử bằng bản vẽ mẫu có đáp số tính tay. Chạy: .venv\\Scripts\\python -m pytest"""
from io import BytesIO

import ezdxf
import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from shapely.geometry import box
from shapely.ops import unary_union

from app.config import goi_y_loai_layer
from app.dxf_reader import doc_ban_ve
from app.excel_io import xuat_excel
from app.main import app
from app.takeoff import boc_khoi_luong, doc_nhan
from tools.tao_ban_ve_mau import tao

# Đáp số tính tay cho khung mẫu (xem tools/tao_ban_ve_mau.py), chiều cao tầng 3,6 m
DAP_SO = {
    "be_tong_lot_mong": 6 * 1.4 * 1.4 * 0.1,                       # 1,176
    "be_tong_mong": 6 * 1.2 * 1.2 * 0.7,                            # 6,048
    "van_khuon_mong": 6 * 4.8 * 0.7,                                # 20,16
    "be_tong_cot": 6 * 0.09 * 3.48,                                 # 1,8792
    # chu vi 1,2 x 3,48 trừ đầu dầm D1 (0,22 x 0,38) và D2 (0,22 x 0,28)
    "van_khuon_cot": 6 * 1.2 * 3.48 - 8 * 0.22 * 0.38 - 6 * 0.22 * 0.28,  # 24,0176
    "be_tong_dam": 4 * 5.7 * 0.22 * 0.38 + 3 * 4.7 * 0.22 * 0.28,   # 2,77464
    "van_khuon_dam": 4 * (11.4 * 0.38 + 5.7 * 0.22) + 3 * (9.4 * 0.28 + 4.7 * 0.22),  # 33,342
    "be_tong_san": (12.3 * 5.3 - 1.0) * 0.12,                       # 7,7028
    "van_khuon_san": (12.3 * 5.3 - 1.0) - 6 * 0.09 - 4 * 5.7 * 0.22 - 3 * 4.7 * 0.22 + (35.2 + 4.0) * 0.12,  # 60,236
}


@pytest.fixture(scope="module")
def ban_ve_mau(tmp_path_factory):
    p = tmp_path_factory.mktemp("mau") / "khung_mau.dxf"
    tao(p)
    return p


def _tinh(duong_dan, **ts):
    bv = doc_ban_ve(duong_dan)
    loai = {l: goi_y_loai_layer(l) for l in bv.layers}
    return boc_khoi_luong(bv, loai, {"chieu_cao_tang": 3.6, **ts})


def test_khop_dap_so_tinh_tay(ban_ve_mau):
    kq = _tinh(ban_ve_mau)
    tong = {t["ma"]: t["khoi_luong"] for t in kq["tong_hop"]}
    assert set(tong) == set(DAP_SO)
    for k, v in DAP_SO.items():
        assert tong[k] == pytest.approx(v, abs=1e-6), k


def test_canh_bao_ve_trung_va_net_ho(ban_ve_mau):
    kq = _tinh(ban_ve_mau)
    chung = " ".join(kq["canh_bao_chung"])
    assert "vẽ trùng" in chung
    assert "polyline hở" in chung
    assert not kq["nhan_khong_gan"]
    assert sum(1 for c in kq["cau_kien"] if c["loai"] == "cot") == 6


def test_so_tang_giong_nhau(ban_ve_mau):
    kq1 = _tinh(ban_ve_mau)
    kq3 = _tinh(ban_ve_mau, so_tang_giong_nhau=3)
    t1 = {t["ma"]: t["khoi_luong"] for t in kq1["tong_hop"]}
    for t in kq3["tong_hop"]:
        assert t["khoi_luong"] == pytest.approx(3 * t1[t["ma"]])


def test_dieu_chinh_va_loai_bo(ban_ve_mau):
    bv = doc_ban_ve(ban_ve_mau)
    loai = {l: goi_y_loai_layer(l) for l in bv.layers}
    goc = boc_khoi_luong(bv, loai, {"chieu_cao_tang": 3.6})
    dam = next(c for c in goc["cau_kien"] if c["loai"] == "dam" and c["ten"] == "D1")
    cot = next(c for c in goc["cau_kien"] if c["loai"] == "cot")
    kq = boc_khoi_luong(bv, loai, {"chieu_cao_tang": 3.6},
                        {dam["id"]: {"h": 0.6}, cot["id"]: {"loai_bo": True}})
    assert next(c for c in kq["cau_kien"] if c["id"] == cot["id"])["loai_bo"]
    tong = {t["ma"]: t["khoi_luong"] for t in kq["tong_hop"]}
    assert tong["be_tong_cot"] == pytest.approx(5 * 0.09 * 3.48)


def test_bao_toan_khi_san_ve_den_mep_dam(tmp_path):
    """Ô sàn vẽ đến mép dầm (không phủ dầm): tổng bê tông vẫn phải bằng thể tích thực, không hụt, không trùng."""
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()

    def hcn(x0, y0, x1, y1, layer):
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": layer})

    cot, dam, san = [], [], []
    for x in (0, 6000):
        for y in (0, 5000):
            hcn(x - 150, y - 150, x + 150, y + 150, "COT"); cot.append(box(x - 150, y - 150, x + 150, y + 150))
            msp.add_text("C1 300x300", dxfattribs={"layer": "TEXT", "insert": (x + 250, y + 250)})
    for y in (0, 5000):
        hcn(0, y - 110, 6000, y + 110, "DAM"); dam.append(box(0, y - 110, 6000, y + 110))
        msp.add_text("D1 220x500", dxfattribs={"layer": "TEXT", "insert": (3000, y + 300)})
    for x in (0, 6000):
        hcn(x - 110, 0, x + 110, 5000, "DAM"); dam.append(box(x - 110, 0, x + 110, 5000))
        msp.add_text("D2 220x400", dxfattribs={"layer": "TEXT", "insert": (x + 300, 2500)})
    hcn(110, 110, 5890, 4890, "SAN"); san.append(box(110, 110, 5890, 4890))
    msp.add_text("S1 t=150", dxfattribs={"layer": "TEXT", "insert": (3000, 2500)})
    p = tmp_path / "san_mep_dam.dxf"
    doc.saveas(p)

    kq = _tinh(p)
    tong = {t["ma"]: t["khoi_luong"] for t in kq["tong_hop"]}
    bt = tong["be_tong_cot"] + tong["be_tong_dam"] + tong["be_tong_san"]

    # Thể tích thực: mặt bằng bê tông chia 3 lớp theo chiều cao (đơn vị mm -> m)
    k = 1e-6
    vung_tren = unary_union(cot + dam + san).area * k            # lớp sàn dày 0,15
    v_cot = unary_union(cot).area * k * (3.6 - 0.15)
    dam_x = unary_union(dam[:2]).difference(unary_union(cot))
    dam_y = unary_union(dam[2:]).difference(unary_union(cot)).difference(dam_x)
    v_dam = dam_x.area * k * (0.5 - 0.15) + dam_y.area * k * (0.4 - 0.15)
    assert bt == pytest.approx(vung_tren * 0.15 + v_cot + v_dam, rel=1e-9)


def test_doc_nhan():
    assert doc_nhan("D1 220x500") | {} == {"ten": "D1", "loai": "dam", "kt": [0.22, 0.5], "day": None, "noi_dung": "D1 220x500"}
    assert doc_nhan("S2 (t=150)")["day"] == 0.15
    assert doc_nhan("M1 1500x1500x800")["kt"] == [1.5, 1.5, 0.8]
    assert doc_nhan("C3")["loai"] == "cot"
    assert doc_nhan("C")["loai"] is None  # tên trục, không phải nhãn
    assert doc_nhan("DM1 300x600")["loai"] == "dam"


def test_excel_cong_thuc_khop_python(ban_ve_mau):
    kq = _tinh(ban_ve_mau)
    wb = load_workbook(BytesIO(xuat_excel(kq, "Thử nghiệm")))
    ws = wb["BANG KHOI LUONG"]
    tong_excel, nhom = {}, None
    ten_ma = {t["ten"]: t["ma"] for t in kq["tong_hop"]}
    for r in range(7, ws.max_row + 1):
        if ws.cell(r, 1).value is not None:
            nhom = ten_ma[ws.cell(r, 3).value]
            continue
        n = ws.cell(r, 5).value
        tich = 1.0
        for c in range(6, 10):
            v = ws.cell(r, c).value
            if v is not None:
                tich *= v
        assert str(ws.cell(r, 10).value).startswith(f"=E{r}*PRODUCT(")
        tong_excel[nhom] = tong_excel.get(nhom, 0) + n * tich
    for t in kq["tong_hop"]:
        assert tong_excel[t["ma"]] == pytest.approx(t["khoi_luong"], abs=1e-9)
    assert "DOI CHIEU" in wb.sheetnames


def test_api_tron_luong(ban_ve_mau):
    cl = TestClient(app)
    with open(ban_ve_mau, "rb") as f:
        r = cl.post("/api/tai-len", files={"file": ("khung_mau.dxf", f)}, data={"don_vi": "auto"})
    assert r.status_code == 200, r.text
    ph = r.json()
    loai = {l["ten"]: l["goi_y"] for l in ph["layers"]}
    yc = {"id": ph["id"], "loai_layer": loai, "thong_so": {"chieu_cao_tang": 3.6}, "dieu_chinh": {}}
    kq = cl.post("/api/tinh", json=yc).json()
    assert {t["ma"]: round(t["khoi_luong"], 4) for t in kq["tong_hop"]}["be_tong_san"] == 7.7028

    x = cl.post("/api/xuat-excel", json=yc)
    assert x.status_code == 200
    # Giả lập kỹ sư nhập khối lượng thủ công lệch 1% và 3%
    wb = load_workbook(BytesIO(x.content))
    ws = wb["DOI CHIEU"]
    for r in range(5, ws.max_row + 1):
        if ws.cell(r, 1).value == "be_tong_san":
            ws.cell(r, 6, 7.7028 / 1.01)
        if ws.cell(r, 1).value == "be_tong_cot":
            ws.cell(r, 6, 1.8792 / 1.03)
    buf = BytesIO(); wb.save(buf)
    d = cl.post("/api/doi-chieu", data={"id": ph["id"]}, files={"file": ("dc.xlsx", buf.getvalue())}).json()
    kq_dc = {x["ma"]: x for x in d["dong"]}
    assert kq_dc["be_tong_san"]["dat"] and not kq_dc["be_tong_cot"]["dat"]
    assert not d["dat_tat_ca"]


def test_dwg_khong_co_oda_bao_loi_ro(tmp_path, monkeypatch):
    # Máy đã cài ODA thì test này vẫn phải mô phỏng trường hợp chưa cài
    monkeypatch.setattr("app.main.config.app_config", lambda: {"oda_path": ""})
    cl = TestClient(app)
    r = cl.post("/api/tai-len", files={"file": ("a.dwg", b"AC1032")})
    assert r.status_code == 400
    assert "ODA" in r.json()["detail"]


def test_suy_dam_tu_khung_tru_o_trong():
    """Khung 4x4, hai ô trống 3.6x2.3 và 3.6x1.1: dầm còn lại 3.76 m2 gồm 2 dầm ngang biên, 1 dầm ngang giữa, 2 dầm đứng biên."""
    from shapely.geometry import box

    from app.dam_suy_ra import TEN_LAYER_SUY_RA, suy_dam
    from app.dxf_reader import BanVe, HinhKin, LayerData

    layers = {
        "KHUNG": LayerData("KHUNG", hinh_kin=[HinhKin(box(0, 0, 4, 4), "", "LWPOLYLINE")]),
        "O": LayerData("O", hinh_kin=[HinhKin(box(0.2, 0.2, 3.8, 2.5), "", "LWPOLYLINE"),
                                      HinhKin(box(0.2, 2.7, 3.8, 3.8), "", "LWPOLYLINE"),
                                      HinhKin(box(0, 0, 4, 4), "", "LWPOLYLINE")]),  # chính khung nằm lẫn trong layer ô
    }
    bv = BanVe("x.dxf", 1.0, "m", layers, [])
    moi, loai = suy_dam(bv, {"KHUNG": "khung_dam", "O": "o_dam"})
    dai = moi.layers[TEN_LAYER_SUY_RA].hinh_kin
    assert loai[TEN_LAYER_SUY_RA] == "dam"
    assert len(dai) == 5
    hop = unary_union_dien_tich([h.geom for h in dai])
    assert abs(hop - 3.76) < 1e-6


def unary_union_dien_tich(gs):
    from shapely.ops import unary_union
    return unary_union(gs).area


def test_thong_ke_hinh_dac_biet_co_chu_vi_dien_tich():
    """Cột chữ nhật chỉ có dài x rộng; cột chữ L (đặc biệt) có thêm chu vi và diện tích."""
    from shapely.geometry import Polygon, box

    from app.dxf_reader import BanVe, HinhKin, LayerData
    from app.thong_ke import thong_ke

    chu_l = Polygon([(0, 0), (0.6, 0), (0.6, 0.2), (0.2, 0.2), (0.2, 0.6), (0, 0.6)])
    layers = {"COT": LayerData("COT", hinh_kin=[HinhKin(box(5, 5, 5.3, 5.3), "", "LWPOLYLINE"),
                                                 HinhKin(chu_l, "", "LWPOLYLINE")])}
    bv = BanVe("x.dxf", 1.0, "m", layers, [])
    kq = thong_ke([{"id": "1", "ten_file": "x.dxf", "vai_tro": "mat_bang", "loai_layer": {"COT": "cot"}, "vung": [], "ban_ve": bv}])
    theo = {h["dang"]: h for h in kq["tong_hop"]}
    assert theo["Chữ nhật"]["dai"] == 300 and theo["Chữ nhật"]["rong"] == 300
    db = theo["Đặc biệt"]
    assert (db["dai"], db["rong"]) == (600, 600)  # hộp bao
    assert abs(db["dien_tich"] - 0.2 * 0.6 - 0.2 * 0.4) < 1e-6 and abs(db["chu_vi"] - 2.4) < 1e-6


# ---------- bản vẽ không hoàn hảo (khe hở, đơn vị khác mm) ----------
def _rect(msp, x0, y0, x1, y1, layer):
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": layer})


def _khung_mot_nhip(tmp_path, khe):
    doc = ezdxf.new(units=4)
    msp = doc.modelspace()
    for x in (0, 6000):
        for y in (0, 5000):
            _rect(msp, x - 150, y - 150, x + 150, y + 150, "COT")
    for y in (0, 5000):
        _rect(msp, 150, y - 110, 5850, y + 110, "DAM")
    for x in (0, 6000):
        _rect(msp, x - 110, 150, x + 110, 4850, "DAM")
    _rect(msp, 110 + khe, 110 + khe, 5890 - khe, 4890 - khe, "SAN")
    for t, p in (("C1 300x300", (300, 300)), ("D1 220x500", (3000, 300)),
                 ("D2 220x500", (400, 2500)), ("S1 t=150", (3000, 2500))):
        msp.add_text(t, dxfattribs={"layer": "TEXT", "insert": p})
    f = tmp_path / f"khung_khe_{khe}.dxf"
    doc.saveas(f)
    return {t["ma"]: t["khoi_luong"] for t in _tinh(f)["tong_hop"]}


@pytest.mark.parametrize("khe", [0.5, 1, 3, 8])
def test_khe_ho_san_dam_khong_lam_lech_van_khuon(tmp_path, khe):
    chuan = _khung_mot_nhip(tmp_path, 0)
    t = _khung_mot_nhip(tmp_path, khe)
    assert t["van_khuon_san"] == pytest.approx(chuan["van_khuon_san"], rel=0.01)
    assert t["van_khuon_dam"] == pytest.approx(chuan["van_khuon_dam"], rel=1e-9)
    assert t["van_khuon_cot"] == pytest.approx(chuan["van_khuon_cot"], rel=1e-9)


@pytest.mark.parametrize("khe_mm", [0.1, 0.5, 1.0])
def test_tiep_xuc_khi_ho_nho(khe_mm):
    from app.takeoff import _tiep_xuc
    cot = box(-0.15, -0.15, 0.15, 0.15)
    dam = box(0.15 + khe_mm / 1000, -0.11, 6, 0.11)
    assert _tiep_xuc(dam, cot) == pytest.approx(0.22, rel=0.01)


@pytest.mark.parametrize("ma,he_so", [(4, 1000), (5, 100), (6, 1)])
def test_cot_tron_dung_o_moi_don_vi(tmp_path, ma, he_so):
    import math
    doc = ezdxf.new(units=ma)
    msp = doc.modelspace()
    msp.add_circle((0, 0), 0.2 * he_so, dxfattribs={"layer": "COT"})
    msp.add_text("C1", dxfattribs={"layer": "TEXT", "insert": (0, 0)})
    f = tmp_path / "tron.dxf"
    doc.saveas(f)
    tong = {t["ma"]: t["khoi_luong"] for t in _tinh(f, chieu_cao_tang=3.0)["tong_hop"]}
    assert tong["be_tong_cot"] == pytest.approx(math.pi * 0.04 * 3.0, rel=0.001)
    assert tong["van_khuon_cot"] == pytest.approx(2 * math.pi * 0.2 * 3.0, rel=0.001)


# ---------- nhóm B: suy luận và cảnh báo ----------
def _tinh_ham(msp_xay, tmp_path, ten="b.dxf", don_vi="auto", **ts):
    doc = ezdxf.new(units=4)
    msp_xay(doc.modelspace())
    f = tmp_path / ten
    doc.saveas(f)
    bv = doc_ban_ve(f, don_vi=don_vi)
    loai = {l: goi_y_loai_layer(l) for l in bv.layers}
    return boc_khoi_luong(bv, loai, {"chieu_cao_tang": 3.6, **ts})


def test_dam_khong_nhan_lay_h_theo_dam_cung_be_rong(tmp_path):
    def xay(msp):
        for y in (0, 3000, 6000):
            _rect(msp, 0, y - 110, 5000, y + 110, "DAM")
        msp.add_text("D1 220x600", dxfattribs={"layer": "TEXT", "insert": (2500, 300)})
    kq = _tinh_ham(xay, tmp_path)
    h = sorted((c["thong_so"]["h"], c["thong_so"]["nguon_h"]) for c in kq["cau_kien"] if c["loai"] == "dam")
    assert h == [(0.6, "nhãn"), (0.6, "suy ra theo bề rộng"), (0.6, "suy ra theo bề rộng")]


def test_dam_cung_be_rong_khac_h_khong_tu_suy(tmp_path):
    def xay(msp):
        for y in (0, 3000, 6000):
            _rect(msp, 0, y - 110, 5000, y + 110, "DAM")
        msp.add_text("D1 220x600", dxfattribs={"layer": "TEXT", "insert": (2500, 300)})
        msp.add_text("D2 220x400", dxfattribs={"layer": "TEXT", "insert": (2500, 3300)})
    kq = _tinh_ham(xay, tmp_path)
    mac_dinh = [c for c in kq["cau_kien"] if c["loai"] == "dam" and c["thong_so"]["nguon_h"] == "mặc định"]
    assert len(mac_dinh) == 1 and "khác nhau" in mac_dinh[0]["canh_bao"][0]["noi_dung"]


def test_cot_cham_dam_co_san_tinh_cao_den_day_san(tmp_path):
    def xay(msp):
        for x in (0, 6000):
            for y in (0, 5000):
                _rect(msp, x - 125, y - 125, x + 125, y + 125, "COT")
        for y in (0, 5000):
            _rect(msp, 125, y - 150, 5875, y + 150, "DAM")
        for x in (0, 6000):
            _rect(msp, x - 150, 125, x + 150, 4875, "DAM")  # dầm rộng hơn cột, ô sàn không chạm cột
        _rect(msp, 150, 150, 5850, 4850, "SAN")
        for t, p in (("C1 250x250", (300, 300)), ("D1 300x500", (3000, 300)), ("S1 t=150", (3000, 2500))):
            msp.add_text(t, dxfattribs={"layer": "TEXT", "insert": p})
    kq = _tinh_ham(xay, tmp_path)
    assert all(c["thong_so"]["cao"] == pytest.approx(3.45) for c in kq["cau_kien"] if c["loai"] == "cot")


def test_canh_bao_ngoai_khoang_hop_ly(tmp_path):
    def xay(msp):
        _rect(msp, 0, 0, 4000, 4000, "SAN")
        msp.add_text("S1 t=12", dxfattribs={"layer": "TEXT", "insert": (2000, 2000)})
    kq = _tinh_ham(xay, tmp_path)
    san = next(c for c in kq["cau_kien"] if c["loai"] == "san")
    assert any("ngoài khoảng hợp lý" in w["noi_dung"] for w in san["canh_bao"])


def test_phat_hien_sai_don_vi_tu_nhan(tmp_path):
    def xay(msp):
        for x in (0, 6000, 12000):
            _rect(msp, x - 150, -150, x + 150, 150, "COT")
            msp.add_text("C1 300x300", dxfattribs={"layer": "TEXT", "insert": (x + 250, 250)})
    kq_dung = _tinh_ham(xay, tmp_path, "dung.dxf")
    kq_sai = _tinh_ham(xay, tmp_path, "sai.dxf", don_vi="m")  # bản vẽ mm bị chọn nhầm là m
    assert not any("SAI ĐƠN VỊ" in w for w in kq_dung["canh_bao_chung"])
    assert any("SAI ĐƠN VỊ" in w for w in kq_sai["canh_bao_chung"])


def test_canh_bao_layer_bo_qua_co_hinh(ban_ve_mau):
    bv = doc_ban_ve(ban_ve_mau)
    loai = {l: goi_y_loai_layer(l) for l in bv.layers}
    ten_cot = next(l for l, v in loai.items() if v == "cot")
    loai[ten_cot] = "bo_qua"
    kq = boc_khoi_luong(bv, loai, {"chieu_cao_tang": 3.6})
    chung = " ".join(kq["canh_bao_chung"])
    assert "đang gán 'Bỏ qua'" in chung and ten_cot in chung
