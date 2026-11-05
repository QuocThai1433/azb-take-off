"""Hồ sơ layer: các lựa chọn tay của người dùng được ghi nhớ cho lần sau.

Lưu ở data/ho_so_layer.yaml, xem / sửa / xóa được trên giao diện (không còn ghi vào config/layer_map.yaml).
Khóa là tên layer đã chuẩn hóa (bỏ tiền tố xref, chữ thường, bỏ dấu). Tên mơ hồ như "0", "1", "05", "100"
không bao giờ được nhớ, vì cùng một tên có thể mang nội dung khác nhau ở mỗi bản vẽ.
"""
import re
from pathlib import Path

import yaml

from . import config

DUONG_DAN = config.DATA_DIR / "ho_so_layer.yaml"


def chuan_hoa_khoa(ten):
    from .config import chuan_hoa_ten
    return chuan_hoa_ten(ten)[0]


def ten_mo_ho(ten):
    """Tên không đủ nghĩa để nhớ: chỉ gồm số / dấu, hoặc quá ngắn."""
    k = chuan_hoa_khoa(ten)
    return len(k) <= 1 or not re.search(r"[a-z]", k)


def doc():
    try:
        with open(DUONG_DAN, encoding="utf-8") as f:
            d = (yaml.safe_load(f) or {}).get("layer") or {}
    except FileNotFoundError:
        return {}
    return {str(k): str(v) for k, v in d.items()}


def _ghi(d):
    DUONG_DAN.parent.mkdir(parents=True, exist_ok=True)
    with open(DUONG_DAN, "w", encoding="utf-8") as f:
        f.write("# Hồ sơ layer: lựa chọn tay đã ghi nhớ (tên layer chuẩn hóa -> loại). Sửa / xóa trong giao diện.\n")
        yaml.safe_dump({"layer": dict(sorted(d.items()))}, f, allow_unicode=True, sort_keys=False)


def nho(ds):
    """ds: [{ten, loai}]. Trả (số đã thêm/đổi, danh sách tên bị bỏ qua vì mơ hồ)."""
    from .config import LOAI_CAU_KIEN
    d = doc()
    them, bo = 0, []
    for x in ds:
        ten, loai = str(x.get("ten", "")).strip(), x.get("loai")
        if not ten or loai not in LOAI_CAU_KIEN:
            continue
        if ten_mo_ho(ten):
            bo.append(ten)
            continue
        k = chuan_hoa_khoa(ten)
        if d.get(k) != loai:
            d[k] = loai
            them += 1
    if them:
        _ghi(d)
    return them, bo


def xoa(khoa):
    d = doc()
    if khoa in d:
        del d[khoa]
        _ghi(d)
        return True
    return False


def tra(ten):
    """Loại đã nhớ cho layer này, hoặc None."""
    return doc().get(chuan_hoa_khoa(ten))
