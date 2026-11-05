"""Kiểm tra môi trường trước khi chạy app và tự sửa những gì sửa được. Dùng bởi CHAY_AZB.bat / CAI_DAT.bat.

  python tools/kiem_cai_dat.py            kiểm tra + tự dò ODA File Converter, ghi vào config/app.yaml nếu tìm thấy
  python tools/kiem_cai_dat.py --cong     chỉ kiểm tra cổng 8765: thoát với mã 2 nếu đã có app đang chạy
"""
import glob
import re
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "app.yaml"
CONG = 8765


def cong_dang_ban(cong=CONG):
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", cong)) == 0


def doc_oda(noi_dung):
    m = re.search(r'^oda_path:\s*"?([^"\n#]*?)"?\s*(?:#.*)?$', noi_dung, re.M)
    return m.group(1).strip() if m else ""


def tim_oda():
    """Tìm ODAFileConverter.exe ở các chỗ cài mặc định. Chọn phiên bản mới nhất."""
    mau = [r"C:\Program Files\ODA\*\ODAFileConverter.exe", r"C:\Program Files (x86)\ODA\*\ODAFileConverter.exe",
           r"C:\Program Files\ODA\ODAFileConverter*\ODAFileConverter.exe"]
    kq = sorted({p for m in mau for p in glob.glob(m)})
    return kq[-1].replace("\\", "/") if kq else None


def sua_oda(noi_dung, duong_dan):
    moi = f'oda_path: "{duong_dan}"'
    if re.search(r"^oda_path:", noi_dung, re.M):
        return re.sub(r"^oda_path:.*$", lambda _: moi, noi_dung, count=1, flags=re.M)
    return moi + "\n" + noi_dung


def kiem_tra(config=CONFIG):
    """Trả danh sách (muc, noi_dung) với muc = 'ok' | 'sua' | 'canh_bao'."""
    kq = []
    if sys.version_info < (3, 10):
        kq.append(("canh_bao", f"Python {sys.version.split()[0]} quá cũ, cần Python 3.10 trở lên."))
    nd = config.read_text(encoding="utf-8")
    hien = doc_oda(nd)
    if hien and Path(hien).is_file():
        kq.append(("ok", f"ODA File Converter: {hien}"))
    else:
        tim = tim_oda()
        if tim:
            config.write_text(sua_oda(nd, tim), encoding="utf-8")
            kq.append(("sua", f"Đã tự dò thấy ODA File Converter và ghi vào config/app.yaml: {tim}"))
        else:
            kq.append(("canh_bao", "Chưa thấy ODA File Converter: app vẫn chạy, đọc được DXF và PDF nhưng chưa đọc được DWG. "
                                   "Cài ODA File Converter (miễn phí, Open Design Alliance) rồi chạy lại, hoặc lưu bản vẽ thành DXF."))
    return kq


if __name__ == "__main__":
    if "--cong" in sys.argv:
        sys.exit(2 if cong_dang_ban() else 0)
    ma = 0
    for muc, nd in kiem_tra():
        print(("[OK]    " if muc == "ok" else "[DA SUA] " if muc == "sua" else "[CHU Y] ") + nd)
        ma = max(ma, 1 if muc == "canh_bao" and "Python" in nd else 0)
    sys.exit(ma)
