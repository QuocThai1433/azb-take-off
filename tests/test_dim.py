import ezdxf

from app.dxf_reader import doc_ban_ve


def test_doc_duong_dim(tmp_path):
    """Entity DIMENSION phải được bung ra thành nét và chữ trên layer của dim."""
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 4
    doc.modelspace().add_linear_dim(base=(0, 2000), p1=(0, 0), p2=(5000, 0), dxfattribs={"layer": "DIM"}).render()
    f = tmp_path / "dim.dxf"
    doc.saveas(f)
    ld = doc_ban_ve(f).layers["DIM"]
    assert ld.net_ho, "không đọc được đường dim"
    assert any("5000" in c.noi_dung for c in ld.chu)
