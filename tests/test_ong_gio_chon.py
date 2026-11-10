"""Ống gió (độ dày tôn, phụ kiện, bóc MLINE) và bóc theo vùng chọn (chống tính trùng diện tích)."""
import ezdxf
import pytest
from shapely.geometry import LineString, box

from app import ong_gio
from app.chon_doi_tuong import boc_chon
from app.dxf_reader import BanVe, HinhKin, LayerData


def test_day_ton_theo_canh_lon_nhat():
    bang = [(400, 0.58), (1000, 0.75), (999999, 1.15)]
    assert ong_gio.day_ton(400, bang) == 0.58          # đúng ngưỡng thì thuộc mức dưới
    assert ong_gio.day_ton(401, bang) == 0.75
    assert ong_gio.day_ton(5000, bang) == 1.15


def test_lam_tron_nua_len_nhu_excel():
    assert ong_gio._lam_tron(2.675, 2) == 2.68          # round() của Python ra 2.67
    assert ong_gio._lam_tron(0.125, 2) == 0.13


def test_doc_block_con_thu():
    b = ong_gio._doc_block("HTS-CON-Can-250x200-300x250-L350")
    assert b["loai"] == "Côn thu" and b["canh_max"] == 300
    cv1, cv2 = 2 * (250 + 200) / 1000, 2 * (300 + 250) / 1000
    assert b["m2"] == pytest.approx((cv1 + cv2) / 2 * 0.35)


def test_doc_block_cut_va_thiet_bi():
    b = ong_gio._doc_block("HTS-CO-V47-150x150-R75-A90")
    assert b["loai"] == "Cút (co)" and b["canh_max"] == 150 and b["m2"] > 0
    assert ong_gio._doc_block("MIENG-GIO-600x600") is None      # miệng gió chỉ đếm số lượng


def _ban_ve_ong(layer="ONG", rong=500):
    doc = ezdxf.new("R2018")
    doc.layers.add(layer)
    msp = doc.modelspace()
    msp.add_mline([(0, 0), (4000, 0)], dxfattribs={"layer": layer, "scale_factor": rong})   # đơn vị mm, dài 4 m
    msp.add_text("500x300", dxfattribs={"layer": "TEXT", "insert": (2000, 100)})
    return BanVe("ong.dxf", 0.001, "mm", {layer: LayerData(layer)}, [], doc)


def test_boc_ong_gio_mline_theo_nhan_kich_thuoc():
    kq = ong_gio.boc_ong_gio(_ban_ve_ong(), {"ONG": "ong_gio"})
    o = kq["ong_thang"][0]
    assert o["rong"] == 500 and o["cao"] == 300 and o["so_doan"] == 1
    assert o["mat_bang"] == pytest.approx(4.0)
    assert o["dien_tich"] == pytest.approx(4.0 * 2 * (500 + 300) / 1000)      # chu vi x dài = 6,4 m²
    assert o["day"] == 0.75                                                    # cạnh lớn 500 mm


def test_boc_ong_gio_thieu_layer_hoac_thieu_nhan():
    with pytest.raises(ValueError):
        ong_gio.boc_ong_gio(_ban_ve_ong(), {"ONG": "cot"})
    bv = _ban_ve_ong()
    for e in list(bv.doc.modelspace().query("TEXT")):
        bv.doc.modelspace().delete_entity(e)
    kq = ong_gio.boc_ong_gio(bv, {"ONG": "ong_gio"})
    assert kq["ong_thang"][0]["cao"] == 500 and any("không có nhãn" in c for c in kq["canh_bao"])   # tạm tính vuông, có cảnh báo


def test_boc_chon_khong_tinh_trung_hinh_chong_nhau():
    ld = LayerData("C", hinh_kin=[HinhKin(box(0, 0, 2, 2), "a", "LWPOLYLINE"), HinhKin(box(1, 0, 3, 2), "b", "LWPOLYLINE")],
                   net_ho=[LineString([(0, 0), (3, 0)])])
    bv = BanVe("t", 1.0, "m", {"C": ld}, [])
    n = boc_chon(bv, {"C": {"h": [0, 1, 99], "n": [0]}})["nhom"][0]        # chỉ số 99 ngoài phạm vi bị bỏ qua
    assert n["so_hinh"] == 2 and n["s_cong"] == 8.0 and n["s_hop"] == 6.0 and n["chong"] == 2.0
    assert n["dai_net"] == 3.0
    assert boc_chon(bv, {"KHONG_CO": {"h": [0]}}) == {"nhom": []}
