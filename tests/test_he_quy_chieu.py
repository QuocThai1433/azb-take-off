"""Hệ quy chiếu dự án: dò lưới trục + tên, điểm gốc / điểm hướng, bảng tầng, API."""
import ezdxf
import pytest
from fastapi.testclient import TestClient

from app import he_quy_chieu as hq
from app.dxf_reader import doc_ban_ve
from app.main import app

XS = [0, 6000, 12000]           # trục số 1, 2, 3 (mm)
YS = [0, 4500]                  # trục chữ A, B


def _tao(tmp_path, co_ten=True):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    for l in ("TRUC", "CHU", "KT"):
        doc.layers.add(l)
    msp = doc.modelspace()
    for x in XS:
        msp.add_line((x + 20000, -1500), (x + 20000, 6000), dxfattribs={"layer": "TRUC"})
    for y in YS:
        msp.add_line((18500, y), (33500, y), dxfattribs={"layer": "TRUC"})
    msp.add_line((20000, 0), (20000, 300), dxfattribs={"layer": "TRUC"})   # vạch ngắn: không phải trục
    if co_ten:
        for i, x in enumerate(XS):   # bong bóng + chữ ở đầu dưới trục số
            msp.add_circle((x + 20000, -1800), 300, dxfattribs={"layer": "KT"})
            msp.add_text(str(i + 1), dxfattribs={"layer": "CHU", "height": 250, "insert": (x + 20000 - 70, -1900)})
        for ten, y in zip("AB", YS):
            msp.add_circle((18200, y), 300, dxfattribs={"layer": "KT"})
            msp.add_text(ten, dxfattribs={"layer": "CHU", "height": 250, "insert": (18200 - 80, y - 100)})
    msp.add_text("+3.600", dxfattribs={"layer": "CHU", "height": 150, "insert": (21000, 2000)})
    msp.add_text("±0.000", dxfattribs={"layer": "CHU", "height": 150, "insert": (21000, 2500)})
    msp.add_text("-1.500", dxfattribs={"layer": "CHU", "height": 150, "insert": (21000, 3000)})
    f = tmp_path / "truc.dxf"
    doc.saveas(f)
    return doc_ban_ve(f)


def test_do_luoi_truc_va_ten(tmp_path):
    kq = hq.do_luoi_truc(_tao(tmp_path))
    assert [t["v"] for t in kq["doc"]] == pytest.approx([20, 26, 32])
    assert [t["ten"] for t in kq["doc"]] == ["1", "2", "3"]
    assert [t["ten"] for t in kq["ngang"]] == ["A", "B"]
    assert all(t["nguon_ten"] == "bong bóng" for t in kq["doc"] + kq["ngang"])
    assert not any("tên" in c for c in kq["canh_bao"])


def test_khong_co_ten_thi_dat_tam_va_canh_bao(tmp_path):
    kq = hq.do_luoi_truc(_tao(tmp_path, co_ten=False))
    assert [t["ten"] for t in kq["doc"]] == ["1", "2", "3"]
    assert [t["ten"] for t in kq["ngang"]] == ["A", "B"]
    assert all(t["nguon_ten"] == "tự đặt" for t in kq["doc"])
    assert any("tên tạm" in c for c in kq["canh_bao"])


def test_dat_ten_truc_chon_tay(tmp_path):
    """Trục chọn tay (tên rỗng) được đặt tên từ bong bóng; trục đã có tên giữ nguyên."""
    bv = _tao(tmp_path)
    luoi = {"doc": [{"ten": "", "v": 20, "tu": -1.5, "den": 6}, {"ten": "", "v": 26, "tu": -1.5, "den": 6},
                    {"ten": "X9", "v": 32, "tu": -1.5, "den": 6}],
            "ngang": [{"ten": "", "v": 0, "tu": 18.5, "den": 33.5}]}
    kq = hq.dat_ten_luoi(bv, luoi)
    assert [t["ten"] for t in kq["doc"]] == ["1", "2", "X9"]
    assert kq["ngang"][0]["ten"] == "A" and kq["ngang"][0]["nguon_ten"] == "bong bóng"
    assert luoi["doc"][0]["ten"] == ""   # không sửa dữ liệu vào


def test_dat_ten_truc_khong_bong_thi_dat_tam(tmp_path):
    kq = hq.dat_ten_luoi(_tao(tmp_path, co_ten=False), {"doc": [{"ten": "", "v": 20, "tu": 0, "den": 5}, {"ten": "", "v": 26, "tu": 0, "den": 5}], "ngang": []})
    assert [t["ten"] for t in kq["doc"]] == ["1", "2"]
    assert any("tên tạm" in c for c in kq["canh_bao"])


def test_api_dat_ten_truc(tmp_path):
    from app import main
    bv = _tao(tmp_path)
    main.PHIEN["t"] = {"ban_ve": bv, "kq": None}
    r = TestClient(app).post("/api/he-quy-chieu/dat-ten-truc", json={"id": "t", "luoi": {"doc": [{"ten": "", "v": 26, "tu": -1.5, "den": 6}], "ngang": []}})
    assert r.status_code == 200 and r.json()["doc"][0]["ten"] == "2"


def test_khong_co_layer_truc(tmp_path):
    doc = ezdxf.new("R2010")
    doc.modelspace().add_line((0, 0), (5000, 0))
    f = tmp_path / "x.dxf"
    doc.saveas(f)
    kq = hq.do_luoi_truc(doc_ban_ve(f))
    assert kq["doc"] == [] and kq["ngang"] == [] and kq["canh_bao"]


def test_cao_do_goi_y(tmp_path):
    ds = {x["gia_tri"] for x in hq.cao_do_goi_y(_tao(tmp_path))}
    assert {3.6, 0.0, -1.5} <= ds


def test_doc_so_kieu_nguoi_nhap():
    assert hq.doc_so("+3.600") == 3.6
    assert hq.doc_so("3,6") == 3.6
    assert hq.doc_so("-1.500") == -1.5
    assert hq.doc_so("±0.000") == 0.0
    assert hq.doc_so("EL +6,8m") == 6.8
    assert hq.doc_so("") is None and hq.doc_so("abc") is None


def _hqc(**kw):
    luoi = {"doc": [{"ten": "1", "v": 20}, {"ten": "2", "v": 26}, {"ten": "3", "v": 32}],
            "ngang": [{"ten": "A", "v": 0}, {"ten": "B", "v": 4.5}]}
    h = {"luoi": luoi, "goc": {"doc": "1", "ngang": "A"},
         "tang": [{"ma": "MONG", "loai": "mong", "cao_do_kc": "-1.5"},
                  {"ma": "T1", "cao_do_kc": "±0.000", "cao_do_ht": "+0.05", "day_san": 120, "cao_dam": 400},
                  {"ma": "T2", "cao_do_kc": "+3.6"}, {"ma": "MAI", "loai": "mai", "cao_do_kc": "+7.2"}]}
    h.update(kw)
    return h


def test_kiem_tra_day_du_tinh_chieu_cao_tang_va_cach_goc():
    kq = hq.kiem_tra(_hqc())
    assert kq["du"] and kq["canh_bao"] == []
    assert kq["goc"]["ten"] == "A-1" and (kq["goc"]["x"], kq["goc"]["y"]) == (20, 0)
    assert [t["cach_goc"] for t in kq["luoi"]["doc"]] == [0, 6, 12]
    assert {t["ma"]: t["chieu_cao"] for t in kq["tang"]} == {"MONG": 1.5, "T1": 3.6, "T2": 3.6, "MAI": None}


def test_thieu_goc_va_tang_thi_chua_du():
    kq = hq.kiem_tra(_hqc(goc=None, tang=[]))
    assert not kq["du"]
    assert any("điểm gốc" in c for c in kq["canh_bao"]) and any("bảng tầng" in c for c in kq["canh_bao"])


def test_goc_tro_vao_truc_da_xoa():
    kq = hq.kiem_tra(_hqc(goc={"doc": "9", "ngang": "A"}))
    assert not kq["du"] and any("không còn nằm trên lưới" in c for c in kq["canh_bao"])


def test_diem_huong_tinh_goc_quay_va_doi_toa_do():
    kq = hq.kiem_tra(_hqc(diem2={"doc": "1", "ngang": "B"}))   # điểm hướng ở trên: trục X công trình quay 90 độ
    assert kq["goc"]["goc_quay"] == pytest.approx(90)
    x, y = hq.sang_toa_do_cong_trinh(kq, 20, 4.5)
    assert (x, y) == pytest.approx((4.5, 0))


def test_canh_bao_bang_tang_bat_thuong():
    cb = hq.chuan_hoa_bang_tang([
        {"ma": "T1", "cao_do_kc": "0"}, {"ma": "T1", "cao_do_kc": "1"},
        {"ma": "T3", "cao_do_kc": "abc"}, {"ma": "T4", "cao_do_ht": "-0.5", "cao_do_kc": "10"},
        {"ma": "MONG", "loai": "mong", "cao_do_kc": "20"}])["canh_bao"]
    t = " | ".join(cb)
    assert "Trùng mã tầng" in t and "không đọc được" in t and "chiều cao tầng" in t and "móng" in t


def test_lop_phu_trung_ten_truc_va_truc_sat_nhau():
    cb = hq.kiem_tra_luoi({"doc": [{"ten": "1", "v": 0}, {"ten": "1", "v": 0.1}], "ngang": [{"ten": "A", "v": 0}]})
    t = " | ".join(cb)
    assert "trùng tên" in t and "cách nhau" in t


def test_api_kiem_tra_va_do_truc(tmp_path):
    c = TestClient(app)
    r = c.post("/api/he-quy-chieu/kiem-tra", json=_hqc())
    assert r.status_code == 200 and r.json()["du"]
    assert c.post("/api/he-quy-chieu/kiem-tra", json=[1]).status_code == 400
    assert c.post("/api/he-quy-chieu/kiem-tra", json={"luoi": {"doc": [{"ten": "1"}]}}).status_code == 400


def test_trang_thai_du_an_giu_he_quy_chieu():
    c = TestClient(app)
    tt = {"files": [], "he_quy_chieu": _hqc()}
    assert c.post("/api/du-an/trang-thai", json=tt).status_code == 200
    assert c.get("/api/du-an/trang-thai").json()["trang_thai"]["he_quy_chieu"]["goc"] == {"doc": "1", "ngang": "A"}


# ---------- Giai đoạn 2: gán vùng mặt bằng, căn về lưới chuẩn ----------
def _kq():
    return hq.kiem_tra(_hqc())


def test_can_vung_dich_theo_giao_truc():
    # vùng khác vẽ lệch: giao trục 1-A của nó nằm ở (100, 50) thay vì (20, 0)
    can = hq.tinh_can_vung(_kq(), {"doc": "1", "ngang": "A"}, [100, 50])
    assert can["ok"] and can["dich"] == [-80, -50] and can["quay"] == 0
    x, y = hq.ap_phep_vung(can, _kq(), 106, 50)     # điểm cách giao trục 6 m theo X
    assert (x, y) == pytest.approx((6, 0))


def test_can_vung_co_xoay_theo_diem_b():
    # vùng vẽ xoay 90 độ: trục 2 của nó nằm ở trên giao trục 1 (cách 6 m theo Y) thay vì bên phải
    can = hq.tinh_can_vung(_kq(), {"doc": "1", "ngang": "A"}, [0, 0], {"doc": "2", "ngang": "A"}, [0, 6])
    assert can["quay"] == pytest.approx(-90)
    x, y = hq.ap_phep_vung(can, _kq(), 0, 6)
    assert (x, y) == pytest.approx((6, 0), abs=1e-6)


def test_can_vung_canh_bao_khac_khoang_cach_va_thieu_diem():
    can = hq.tinh_can_vung(_kq(), {"doc": "1", "ngang": "A"}, [0, 0], {"doc": "2", "ngang": "A"}, [5.5, 0])
    assert any("khác lưới chuẩn" in c for c in can["canh_bao"])
    assert not hq.tinh_can_vung(_kq(), None, None)["ok"]
    assert not hq.tinh_can_vung(_kq(), {"doc": "9", "ngang": "A"}, [0, 0])["ok"]


def test_kiem_tra_cheo_bang_truc_cua_vung():
    loc = {"doc": [{"ten": "1", "v": 100}, {"ten": "2", "v": 106.2}], "ngang": [{"ten": "A", "v": 50}]}
    can = hq.tinh_can_vung(_kq(), {"doc": "1", "ngang": "A"}, [100, 50], luoi_local=loc)
    lech = {t["truc"]: t["lech_mm"] for t in can["kiem_tra_truc"]}
    assert lech["1"] == 0 and lech["2"] == 200
    assert any("Trục 2" in c and "200 mm" in c for c in can["canh_bao"])


def test_goi_y_diem_vung_tim_truc_trung_ten(tmp_path):
    bv = _tao(tmp_path)    # lưới tên 1,2,3 / A,B giống lưới chuẩn nhưng đặt ở toạ độ khác
    kq = hq.goi_y_diem_vung(bv, None, _kq())
    assert kq["diem"] == {"doc": "1", "ngang": "A"}      # ưu tiên trục của điểm gốc chuẩn
    assert kq["goc_local"] == pytest.approx([20, 0])


def test_goi_y_diem_vung_khong_trung_ten(tmp_path):
    h = _hqc()
    h["luoi"] = {"doc": [{"ten": "X1", "v": 0}], "ngang": [{"ten": "Y1", "v": 0}]}
    h["goc"] = {"doc": "X1", "ngang": "Y1"}
    kq = hq.goi_y_diem_vung(_tao(tmp_path), None, hq.kiem_tra(h))
    assert kq["diem"] is None and any("không trùng tên" in c for c in kq["canh_bao"])


def test_kiem_tra_gan_vung():
    can_ok = {"ok": True}
    kq = hq.kiem_tra_gan_vung([
        {"ten": "Móng", "tang": "MONG", "cau_kien": "mong", "xac_nhan": True, "can": can_ok},
        {"ten": "T2 dầm sàn", "tang": "T2", "cau_kien": "dam_san", "xac_nhan": False, "can": can_ok},
        {"ten": "T2 dầm sàn 2", "tang": "T2", "cau_kien": "dam_san", "xac_nhan": True, "can": can_ok},
        {"ten": "T9", "tang": "T9", "cau_kien": "cot_vach", "xac_nhan": True, "can": {}},
        {"ten": "chưa gán"}], _kq())
    t = " | ".join(kq["canh_bao"])
    assert not kq["xong"]
    assert "chưa xác nhận" in t and "cùng tầng T2" in t and "không có trong bảng tầng" in t and "chưa chọn tầng" in t
    assert kq["dong"][0]["xong"]
    ok = hq.kiem_tra_gan_vung([{"ten": "a", "tang": "T1", "cau_kien": "cot_vach", "xac_nhan": True, "can": can_ok}], _kq())
    assert ok["xong"] and ok["canh_bao"] == []


def test_api_gan_vung():
    c = TestClient(app)
    d = {"hqc": _hqc(), "ds": [{"ten": "a", "tang": "T1", "cau_kien": "mong", "xac_nhan": True, "can": {"ok": True}}]}
    assert c.post("/api/he-quy-chieu/kiem-tra-gan-vung", json=d).json()["xong"]
    r = c.post("/api/he-quy-chieu/can-vung", json={"id": "x", "hqc": _hqc(), "diem": {"doc": "1", "ngang": "A"}, "goc_local": [100, 50]})
    assert r.status_code == 200 and r.json()["dich"] == [-80, -50]


# ---------- Giai đoạn 3: tổng hợp theo tầng / cấu kiện, đưa về tim trục ----------
def _hcn(x0, y0, x1, y1):
    return [[[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]]


def _ck(id_, loai, ten, hinh, **ts):
    return {"id": id_, "loai": loai, "ten": ten, "layer": "L", "thong_so": ts, "canh_bao": [], "loai_bo": False, "hinh": hinh}


def _vung(fi, ten, tang, ck, ds, can=None, xn=True, coc=None):
    return {"fi": fi, "ten": ten, "tang": tang, "cau_kien": ck, "xac_nhan": xn, "ck": ds, "coc": coc or [],
            "can": can or hq.tinh_can_vung(_kq(), {"doc": "1", "ngang": "A"}, [100, 50])}


def test_tong_hop_theo_tang_cau_kien_va_dua_ve_tim_truc():
    # vùng vẽ lệch (+80, +50): cột 400x400 tâm tại (106, 50) trên bản vẽ = 6 m cách trục 1 theo X, nằm trên trục A
    cot = _ck("c1", "cot", "C1", _hcn(105.8, 49.8, 106.2, 50.2))
    dam = _ck("d1", "dam", "D1", _hcn(100, 49.9, 106, 50.1), h=0.5)
    kq = hq.tong_hop_cong_trinh(_kq(), [_vung(1, "T2 cột", "T2", "cot_vach", [cot, dam])])
    assert kq["tong"]["so_doi_tuong"] == 1            # dầm khác loại khai báo (cột-vách) nên không lấy
    assert kq["bo_qua"] == [{"vung": "T2 cột", "so": 1, "ly_do": "khác loại khai báo (Cột - vách)"}]
    t = kq["tang"][0]
    assert t["ma"] == "T2" and t["cao_do_kc"] == 3.6 and t["nhom"][0]["cau_kien"] == "cot_vach"
    o = t["nhom"][0]["doi_tuong"][0]
    assert o["tam_ct"] == pytest.approx([6, 0]) and o["tam_chuan"] == pytest.approx([26, 0])   # công trình: gốc A-1; chuẩn: bản vẽ chuẩn
    assert (o["z_day"], o["z_dinh"]) == (3.6, 7.2)                                               # từ tầng T2 lên MAI
    assert o["dien_tich"] == pytest.approx(0.16) and o["the_tich"] == pytest.approx(0.16 * 3.6)
    assert sorted(o["kich_thuoc"]) == pytest.approx([0.4, 0.4])
    assert o["hinh_ct"][0][0][0] == pytest.approx([5.8, -0.2])


def test_tong_hop_khac_lay_het_va_cao_do_dam_san_mong():
    ds = [_ck("d1", "dam", "D1", _hcn(0, 0, 4, 0.2), h=0.5), _ck("s1", "san", "S1", _hcn(0, 0, 4, 4), t=0.12),
          _ck("m1", "mong", "M1", _hcn(0, 0, 1, 1), day=0.8), _ck("x", "dam", "D2", _hcn(0, 0, 4, 0.2))]
    can = hq.tinh_can_vung(_kq(), {"doc": "1", "ngang": "A"}, [0, 0])
    kq = hq.tong_hop_cong_trinh(_kq(), [_vung(0, "Tầng 1", "T1", "khac", ds, can)])
    o = {x["ma_goc"]: x for n in kq["tang"][0]["nhom"] for x in n["doi_tuong"]}
    assert (o["d1"]["z_day"], o["d1"]["z_dinh"]) == (-0.5, 0.0)
    assert (o["s1"]["z_day"], o["s1"]["z_dinh"]) == (-0.12, 0.0)
    assert (o["m1"]["z_day"], o["m1"]["z_dinh"]) == (-0.8, 0.0)
    assert o["x"]["z_day"] == -0.4          # dầm không có h: lấy cao dầm mặc định 400 mm của tầng T1
    kq2 = hq.tong_hop_cong_trinh(_kq(), [_vung(0, "Tầng 2", "T2", "khac", [ds[3]], can)])   # T2 không khai báo cao dầm
    o2 = kq2["tang"][0]["nhom"][0]["doi_tuong"][0]
    assert o2["z_day"] is None and o2["the_tich"] is None and "dầm" in o2["ghi_chu_cao_do"]
    assert [n["cau_kien"] for n in kq["tang"][0]["nhom"]] == ["mong", "dam_san"]


def test_tong_hop_tang_tren_cung_va_coc():
    coc = [{"id": "coc-0", "ten": "P1", "x": 0, "y": 0, "d": 0.4}]
    kq = hq.tong_hop_cong_trinh(_kq(), [_vung(0, "Móng", "MONG", "mong", [], hq.tinh_can_vung(_kq(), {"doc": "1", "ngang": "A"}, [20, 0]), coc=coc),
                                         _vung(1, "Mái", "MAI", "cot_vach", [_ck("c", "cot", "C", _hcn(0, 0, 1, 1))])])
    assert kq["tang"][0]["ma"] == "MONG" and kq["tang"][0]["nhom"][0]["doi_tuong"][0]["loai"] == "coc"
    assert kq["tang"][0]["nhom"][0]["doi_tuong"][0]["dien_tich"] == pytest.approx(3.14159 * 0.04, rel=0.03)
    mai = kq["tang"][1]["nhom"][0]["doi_tuong"][0]
    assert mai["z_dinh"] is None and "tầng trên cùng" in mai["ghi_chu_cao_do"]


def test_tong_hop_bo_qua_vung_chua_can_va_canh_bao_trung():
    c = _ck("c1", "cot", "C1", _hcn(0, 0, 1, 1))
    kq = hq.tong_hop_cong_trinh(_kq(), [
        {"fi": 0, "ten": "chưa căn", "tang": "T1", "cau_kien": "khac", "ck": [c], "can": None},
        {"fi": 1, "ten": "tầng lạ", "tang": "T9", "cau_kien": "khac", "ck": [c], "can": {"ok": True, "dich": [0, 0], "quay": 0, "tam": [0, 0]}},
        _vung(2, "A", "T1", "cot_vach", [c], hq.tinh_can_vung(_kq(), {"doc": "1", "ngang": "A"}, [0, 0]), xn=False),
        _vung(3, "B", "T1", "cot_vach", [c], hq.tinh_can_vung(_kq(), {"doc": "1", "ngang": "A"}, [0, 0]))])
    t = " | ".join(kq["canh_bao"])
    assert "chưa căn" in t and "chưa có tầng hợp lệ" in t and "chưa xác nhận" in t and "trùng vị trí" in t
    assert kq["tong"]["so_vung"] == 2 and kq["tong"]["so_doi_tuong"] == 2


def test_tong_hop_khong_co_goc():
    h = _hqc(goc=None)
    kq = hq.tong_hop_cong_trinh(hq.kiem_tra(h), [])
    assert kq["tang"] == [] and "điểm gốc" in kq["canh_bao"][0]


def test_tong_hop_co_xoay():
    can = hq.tinh_can_vung(_kq(), {"doc": "1", "ngang": "A"}, [0, 0], {"doc": "2", "ngang": "A"}, [0, 6])   # vùng quay -90 độ
    c = _ck("c", "cot", "C", _hcn(-0.2, 5.8, 0.2, 6.2))        # trên bản vẽ vùng nằm ở (0, 6) = trục 2 sau khi xoay
    o = hq.tong_hop_cong_trinh(_kq(), [_vung(0, "xoay", "T1", "khac", [c], can)])["tang"][0]["nhom"][0]["doi_tuong"][0]
    assert o["tam_ct"] == pytest.approx([6, 0], abs=1e-3)


def test_api_tong_hop():
    c = TestClient(app)
    d = {"hqc": _hqc(), "ds": [_vung(0, "T1", "T1", "cot_vach", [_ck("c", "cot", "C", _hcn(0, 0, 1, 1))])]}
    r = c.post("/api/he-quy-chieu/tong-hop", json=d)
    assert r.status_code == 200 and r.json()["tong"]["so_doi_tuong"] == 1
