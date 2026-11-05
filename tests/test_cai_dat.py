"""Công cụ kiểm tra cài đặt: dò ODA File Converter, sửa config, kiểm tra cổng."""
import socket

from tools import kiem_cai_dat as kc


def test_doc_va_sua_oda_path():
    nd = '# ghi chú\noda_path: "C:/cu/ODA.exe"   # ghi chú cuối dòng\nmac_dinh:\n  a: 1\n'
    assert kc.doc_oda(nd) == "C:/cu/ODA.exe"
    moi = kc.sua_oda(nd, "C:/Program Files/ODA/ODAFileConverter 27.1.0/ODAFileConverter.exe")
    assert kc.doc_oda(moi) == "C:/Program Files/ODA/ODAFileConverter 27.1.0/ODAFileConverter.exe"
    assert "mac_dinh:" in moi and "# ghi chú" in moi.splitlines()[0]
    assert kc.sua_oda("x: 1\n", "C:/a.exe").startswith('oda_path: "C:/a.exe"')


def test_kiem_tra_tu_ghi_oda_khi_duong_dan_sai(tmp_path, monkeypatch):
    exe = tmp_path / "ODAFileConverter.exe"
    exe.write_text("x")
    cfg = tmp_path / "app.yaml"
    cfg.write_text('oda_path: "C:/khong/co.exe"\nkhac: 1\n', encoding="utf-8")
    monkeypatch.setattr(kc, "tim_oda", lambda: str(exe).replace("\\", "/"))
    kq = kc.kiem_tra(cfg)
    assert kq[0][0] == "sua" and kc.doc_oda(cfg.read_text(encoding="utf-8")) == str(exe).replace("\\", "/")
    assert "khac: 1" in cfg.read_text(encoding="utf-8")
    assert kc.kiem_tra(cfg)[0][0] == "ok"                   # lần sau đã đúng, không sửa nữa


def test_khong_thay_oda_chi_canh_bao_khong_loi(tmp_path, monkeypatch):
    cfg = tmp_path / "app.yaml"
    cfg.write_text('oda_path: "C:/khong/co.exe"\n', encoding="utf-8")
    monkeypatch.setattr(kc, "tim_oda", lambda: None)
    kq = kc.kiem_tra(cfg)
    assert kq[0][0] == "canh_bao" and "DXF" in kq[0][1]
    assert cfg.read_text(encoding="utf-8") == 'oda_path: "C:/khong/co.exe"\n'      # không đụng file


def test_cong_dang_ban():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    cong = s.getsockname()[1]
    try:
        assert kc.cong_dang_ban(cong) is True
    finally:
        s.close()
    assert kc.cong_dang_ban(cong) is False
