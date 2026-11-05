"""Nhật ký hoạt động: ghi ra data/logs/azb.log để tra cứu khi có lỗi.

- Tự xoay vòng: mỗi file tối đa 1 MB, giữ 5 file (tổng tối đa khoảng 6 MB), không bao giờ đầy ổ đĩa.
- Chỉ ghi khi server chạy thật (sự kiện startup), test không ghi vào data/ thật.
- Không ghi nội dung bản vẽ, chỉ ghi: tên file, thời gian xử lý, lỗi kèm traceback, các thao tác chính.
"""
import logging
import logging.handlers
import platform
import sys
import uuid
from collections import deque
from pathlib import Path

from . import config

THU_MUC = config.ROOT / "data" / "logs"
FILE_LOG = THU_MUC / "azb.log"
DINH_DANG = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
CHAM_GIAY = 5.0     # yêu cầu chậm hơn mức này được ghi lại để biết thao tác nào nặng


def bat(thu_muc=None):
    """Gắn bộ ghi file vào logger 'azb'. Gọi nhiều lần cũng chỉ gắn một lần."""
    thu_muc = Path(thu_muc) if thu_muc else THU_MUC
    log = logging.getLogger("azb")
    log.setLevel(logging.INFO)
    file_log = thu_muc / "azb.log"
    if any(getattr(h, "baseFilename", None) == str(file_log.resolve()) for h in log.handlers):
        return log
    thu_muc.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(file_log, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    h.setFormatter(logging.Formatter(DINH_DANG))
    log.addHandler(h)
    log.propagate = False
    return log


def ghi_khoi_dong():
    log = logging.getLogger("azb")
    oda = config.app_config().get("oda_path")
    log.info("Khởi động AZB. Python %s, %s. ODA File Converter: %s", sys.version.split()[0], platform.platform(),
             "có" if oda and Path(oda).exists() else "KHÔNG THẤY (không đọc được DWG, chỉ đọc DXF/PDF)")


def ma_loi():
    return uuid.uuid4().hex[:8]


def doc_duoi(so_dong=200, file_log=None):
    """Các dòng cuối của nhật ký (cả file xoay vòng gần nhất nếu file hiện tại còn ngắn)."""
    file_log = Path(file_log) if file_log else FILE_LOG
    cac = [file_log] + [file_log.with_name(f"{file_log.name}.{i}") for i in range(1, 6)]
    kq = deque(maxlen=so_dong)
    for p in reversed([p for p in cac if p.is_file()]):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                kq.extend(l.rstrip("\n") for l in f)
        except OSError:
            continue
    return list(kq)
