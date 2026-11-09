"""Đọc các file cấu hình trong thư mục config/."""
import os
import re
import unicodedata
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
# Mặc định data/ trong thư mục app. Đặt biến AZB_DATA_DIR để dùng thư mục dữ liệu riêng (vd: bản dùng thử qua tunnel).
DATA_DIR = Path(os.environ.get("AZB_DATA_DIR") or ROOT / "data")

LOAI_CAU_KIEN = ["cot", "dam", "san", "lo_san", "mong", "coc", "vach", "khung_dam", "o_dam", "nhan", "ong_gio", "ong_nuoc", "ong_pccc", "khay_cap", "tuong", "cua", "bo_qua"]
LOAI_MEP = {"ong_gio", "ong_nuoc", "ong_pccc", "khay_cap"}   # hệ thống cơ điện: không tính bê tông, chỉ dựng 3D / bóc riêng


def _load(name):
    with open(CONFIG_DIR / name, encoding="utf-8") as f:
        return yaml.safe_load(f)


def app_config():
    return _load("app.yaml")


def ong_gio():
    return _load("ong_gio.yaml")


def mep():
    return _load("mep.yaml")


def cong_tac():
    return _load("cong_tac.yaml")


_XREF = re.compile(r"\$\d+\$|\|")
NGUONG_TU_GAN = 0.7   # từ mức này trở lên, loại đoán theo tên được gán sẵn; dưới mức: chỉ là gợi ý
HE_SO_XREF = 0.6      # layer trong xref (bản vẽ tham chiếu, thường là kiến trúc): hạ tin cậy loại kết cấu
LOAI_KET_CAU = {"cot", "dam", "san", "mong", "coc", "vach"}


def chuan_hoa_ten(ten):
    """'X - NHA BAO VE 2-1$0$A-Wall' -> ('a wall', True). Trả (tên sạch, có phải layer của xref)."""
    ten = str(ten)
    phan = _XREF.split(ten)
    la_xref = len(phan) > 1
    s = unicodedata.normalize("NFD", phan[-1].replace("đ", "d").replace("Đ", "D"))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").lower()
    s = re.sub(r"[_\-.]+", " ", s)
    return re.sub(r"\s+", " ", s).strip(), la_xref


def phan_tich_ten(ten, layer_map=None, ho_so=None):
    """Đoán loại theo tên. Trả (loai, tin_cay, ly_do, nguon); loai None = tên không cho biết gì.

    Thứ tự: hồ sơ người dùng đã nhớ -> luật trong layer_map.yaml (đã chuẩn hóa tên, hạ tin cậy nếu là xref).
    """
    if ho_so is None:
        from . import ho_so_layer
        ho_so = ho_so_layer.doc()
    sach, la_xref = chuan_hoa_ten(ten)
    if sach in ho_so:
        return ho_so[sach], 1.0, "Bạn đã chọn tay và ghi nhớ ở lần trước", "hồ sơ"
    layer_map = layer_map or _load("layer_map.yaml")
    for rule in layer_map["rules"]:
        if re.search(rule["pattern"], sach):
            conf = float(rule.get("conf", 0.9))
            ly_do = rule.get("ly_do") or f"Khớp luật '{rule['pattern'][:30]}'"
            if la_xref and rule["type"] in LOAI_KET_CAU:
                conf *= HE_SO_XREF
                ly_do += "; layer nằm trong bản vẽ tham chiếu ngoài (xref), thường là bản kiến trúc nên hạ tin cậy"
            return rule["type"], round(conf, 2), ly_do, "luật tên"
    return None, 0.0, "Tên layer không cho biết loại", "không rõ"


def goi_y_loai_layer(ten_layer, layer_map=None):
    """Loại gán sẵn cho layer: chỉ khi tin cậy theo tên đủ cao, còn lại 'bo_qua' (an toàn, không tính nhầm)."""
    loai, tin_cay, _, nguon = phan_tich_ten(ten_layer, layer_map)
    if loai and tin_cay >= NGUONG_TU_GAN:
        return loai
    return (layer_map or _load("layer_map.yaml")).get("default", "bo_qua")
