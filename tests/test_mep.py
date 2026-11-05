"""Đọc đường ống / khay cáp MEP cho Xem 3D."""
import ezdxf
import pytest

from app import config
from app.dxf_reader import doc_ban_ve
from app.mep import doc_mep, kich_thuoc_tu_ten


def test_kich_thuoc_tu_ten_layer():
    cfg = config.mep()
    assert kich_thuoc_tu_ten("P-WATER-D150", cfg["ong_nuoc"])[:3] == (150.0, 150.0, True)
    assert kich_thuoc_tu_ten("PCCC DN65", cfg["ong_pccc"])[0] == 65.0
    assert kich_thuoc_tu_ten("E-KHAY CAP 400x100", cfg["khay_cap"])[:3] == (400.0, 100.0, False)
    assert kich_thuoc_tu_ten("P-WATER", cfg["ong_nuoc"])[3] == "mặc định"
    assert kich_thuoc_tu_ten("P-WATER", cfg["ong_nuoc"])[0] == 100.0


def test_layer_map_nhan_ra_mep():
    assert config.phan_tich_ten("P-THOAT NUOC")[0] == "ong_nuoc"
    assert config.phan_tich_ten("PCCC-SPRINKLER")[0] == "ong_pccc"
    assert config.phan_tich_ten("E-KHAY CAP")[0] == "khay_cap"
    assert config.phan_tich_ten("S-BEAM")[0] == "dam"


@pytest.fixture
def bv(tmp_path):
    doc = ezdxf.new("R2010", setup=True)
    doc.header["$INSUNITS"] = 4
    for ten in ("P-WATER-D150", "E-KHAY CAP 400x100", "KHAC"):
        doc.layers.add(ten)
    ms = doc.modelspace()
    ms.add_line((0, 0), (5000, 0), dxfattribs={"layer": "P-WATER-D150"})
    ms.add_lwpolyline([(0, 1000), (3000, 1000), (3000, 4000)], dxfattribs={"layer": "E-KHAY CAP 400x100"})
    ms.add_line((0, 0), (1, 1), dxfattribs={"layer": "KHAC"})
    p = tmp_path / "mep.dxf"
    doc.saveas(p)
    return doc_ban_ve(p)


def test_doc_mep(bv):
    kq = doc_mep(bv, {"P-WATER-D150": "ong_nuoc", "E-KHAY CAP 400x100": "khay_cap", "KHAC": "bo_qua"})
    ds = {d["loai"]: d for d in kq["duong"]}
    assert set(ds) == {"ong_nuoc", "khay_cap"}
    assert ds["ong_nuoc"]["tron"] and ds["ong_nuoc"]["rong"] == pytest.approx(0.15)
    assert ds["ong_nuoc"]["diem"][-1] == [5.0, 0.0]
    assert not ds["khay_cap"]["tron"] and ds["khay_cap"]["cao"] == pytest.approx(0.1)
    assert len(ds["khay_cap"]["diem"]) == 3


def test_khong_co_layer_mep(bv):
    with pytest.raises(ValueError):
        doc_mep(bv, {"KHAC": "bo_qua"})
