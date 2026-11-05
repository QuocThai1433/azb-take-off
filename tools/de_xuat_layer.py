"""Prototype bot chuẩn hóa: đề xuất loại cấu kiện cho từng layer (docs/THIET_KE_CHUAN_HOA.md, mục 3.3).

Nguyên tắc: AI chỉ ĐỀ XUẤT. Hàm này không ghi gì vào kết quả bóc, không sửa file cấu hình.
Thứ tự ưu tiên: hồ sơ đã học -> luật cứng (layer_map.yaml) -> bộ đề xuất (AI) -> hỏi người.

Bản này chạy OFFLINE: bộ đề xuất mặc định là luật heuristic nội bộ, KHÔNG gọi mạng.
Chính sách gửi dữ liệu ra ngoài chưa chốt nên chưa nối API. Khi chốt, chỉ cần viết một hàm
cùng khuôn dạng với `de_xuat_ngoai_tuyen` (nhận `tao_yeu_cau_ai(...)`, trả (loai, tin_cay, ly_do)).

Chạy thử:  python -m tools.de_xuat_layer ban_ve.dxf [ho_so.yaml]
"""
import re
import statistics
import sys
from dataclasses import dataclass, field

import yaml

from app.config import _load

NGUONG_CAO = 0.9   # từ mức này trở lên: tự điền (vẫn là đề xuất)
NGUONG_THAP = 0.6  # dưới mức này: không điền, hỏi người
# Giả định chưa kiểm chứng, chỉnh theo kết quả đo trên bản vẽ mẫu:
COT_CANH_NGAN = (0.15, 2.0)  # m
DAM_TY_LE_TOI_THIEU = 3.0    # dài / rộng
HE_SO_HA = 0.7               # nhân vào tin cậy khi kiểm tra chéo không đạt

NHAN_CAU_KIEN = re.compile(r"^(C|COT|D|B|DAM|S|M|F|FM)\s*\d+|t\s*=\s*\d+|\d+\s*[xX*]\s*\d+")


@dataclass
class ThongTinLayer:
    ten: str
    so_hinh_kin: int = 0
    so_net_ho: int = 0
    so_chu: int = 0
    canh_ngan: float = 0.0   # trung vị cạnh ngắn của hình bao chữ nhật xoay (m); 0 = không có hình
    ty_le: float = 0.0       # trung vị dài/rộng
    mau_chu: list = field(default_factory=list)
    phieu: dict = field(default_factory=dict)   # loại -> số hình kín có nhãn gần đó cho biết loại ấy
    so_mau: int = 0                             # số hình kín đã lấy mẫu để bỏ phiếu


@dataclass
class DeXuat:
    ten: str
    loai: object      # None khi phải hỏi người
    tin_cay: float
    nguon: str        # "hồ sơ" | "luật tên" | "nhãn" | "luật tên + nhãn" | "gợi ý hình học" | "không rõ"
    ly_do: str
    hanh_dong: str    # tu_dien | xac_nhan | hoi_nguoi
    lan: bool = False                              # layer chứa lẫn nhiều loại cấu kiện
    phan_bo: dict = field(default_factory=dict)    # loại -> số hình có nhãn (bằng chứng từ chữ)
    so_hinh: int = 0


MAX_MAU_PHIEU = 300      # mỗi layer chỉ lấy tối đa chừng này hình để bỏ phiếu (đủ tin cậy, giữ app nhanh)
KC_NHAN_TOI_DA = 1.5     # m, nhãn xa hình hơn mức này thì không tính là của hình


def _bo_phieu_theo_nhan(ban_ve):
    """Bằng chứng mạnh nhất để biết một layer là gì: các hình kín của nó đang được gọi tên gì.

    Với mỗi hình kín, lấy nhãn chữ gần nhất (C1, D2, M3, S1...) và đọc loại từ tiền tố nhãn.
    Trả {tên layer: Counter(loại)}. Layer chữ chỉ có nhãn, không có hình, thì không có phiếu.
    """
    import math
    from collections import Counter

    from shapely import STRtree

    from app.takeoff import doc_nhan
    diem, loai_nhan = [], []
    for ld in ban_ve.layers.values():
        for c in ld.chu:
            loai = doc_nhan(c.noi_dung)["loai"]
            if loai:
                diem.append(c.diem)
                loai_nhan.append(loai)
    ket = {}
    if not diem:
        return ket
    cay = STRtree(diem)
    for ld in ban_ve.layers.values():
        if not ld.hinh_kin:
            continue
        hop_le = [h for h in ld.hinh_kin if 0.0004 <= h.geom.area <= 200.0]
        hinh = [h for h in hop_le if h.nguon != "GHEP_NET"] or hop_le
        buoc = max(1, math.ceil(len(hinh) / MAX_MAU_PHIEU))
        dem = Counter()
        for h in hinh[::buoc]:
            idx = cay.query_nearest(h.geom, max_distance=KC_NHAN_TOI_DA, all_matches=False)
            if len(idx):
                dem[loai_nhan[int(idx[0])]] += 1
        if hinh:
            ket[ld.ten] = (dem, len(hinh[::buoc]))
    return ket


def thong_tin_tu_ban_ve(ban_ve):
    """Rút thông tin từng layer từ BanVe (app.dxf_reader.doc_ban_ve)."""
    kq = []
    phieu = _bo_phieu_theo_nhan(ban_ve)
    for ld in ban_ve.layers.values():
        if not (ld.hinh_kin or ld.net_ho or ld.chu):
            continue
        canh, ty = [], []
        for h in ld.hinh_kin:
            hcn = h.geom.minimum_rotated_rectangle
            if hcn.geom_type != "Polygon":
                continue
            xs, ys = hcn.exterior.coords.xy
            d1 = ((xs[0] - xs[1]) ** 2 + (ys[0] - ys[1]) ** 2) ** 0.5
            d2 = ((xs[1] - xs[2]) ** 2 + (ys[1] - ys[2]) ** 2) ** 0.5
            ngan, dai = min(d1, d2), max(d1, d2)
            if ngan > 0:
                canh.append(ngan)
                ty.append(dai / ngan)
        kq.append(ThongTinLayer(
            ten=ld.ten, so_hinh_kin=len(ld.hinh_kin), so_net_ho=len(ld.net_ho), so_chu=len(ld.chu),
            canh_ngan=statistics.median(canh) if canh else 0.0,
            ty_le=statistics.median(ty) if ty else 0.0,
            mau_chu=[c.noi_dung for c in ld.chu[:5]],
            phieu=dict(phieu.get(ld.ten, ({}, 0))[0]), so_mau=phieu.get(ld.ten, ({}, 0))[1],
        ))
    return kq


def tao_yeu_cau_ai(tt):
    """Dữ liệu duy nhất được phép gửi cho bộ đề xuất ngoài: thống kê và mẫu chữ.
    Không có tọa độ, không có tên file, tên dự án hay chủ đầu tư."""
    return {
        "ten_layer": tt.ten, "so_hinh_kin": tt.so_hinh_kin, "so_net_ho": tt.so_net_ho, "so_chu": tt.so_chu,
        "canh_ngan_trung_vi_m": round(tt.canh_ngan, 3), "ty_le_trung_vi": round(tt.ty_le, 2),
        "mau_chu": [c[:40] for c in tt.mau_chu[:5]],
    }


def de_xuat_ngoai_tuyen(yc):
    """Bộ đề xuất heuristic, chạy offline, thay chỗ cho AI. Trả (loai, tin_cay, ly_do).
    Các mức tin cậy là giá trị khởi đầu chưa kiểm chứng."""
    if yc["so_chu"] and not yc["so_hinh_kin"]:
        khop = sum(1 for c in yc["mau_chu"] if NHAN_CAU_KIEN.search(c))
        if khop:
            return "nhan", 0.9, f"Layer chỉ có chữ, {khop}/{len(yc['mau_chu'])} mẫu giống nhãn cấu kiện"
        return "nhan", 0.65, "Layer chỉ có chữ, mẫu không giống nhãn cấu kiện rõ ràng"
    if yc["so_hinh_kin"]:
        canh, ty = yc["canh_ngan_trung_vi_m"], yc["ty_le_trung_vi"]
        if ty >= 4:
            return "dam", 0.6, f"Hình dài và hẹp (dài/rộng ≈ {ty})"
        if ty <= 1.6 and 0.15 <= canh <= 1.2:
            return "cot", 0.6, f"Nhiều hình gần vuông, cạnh ≈ {canh} m"
        if canh > 2.0:
            return "san", 0.55, f"Hình lớn, cạnh ngắn ≈ {canh} m"
    return None, 0.0, "Không đủ căn cứ"


def _kiem_tra_cheo(loai, tt, tin_cay):
    """Hạ tin cậy khi hình học mâu thuẫn với loại được đề xuất. Trả (tin_cay, ghi_chu)."""
    if tt.so_hinh_kin == 0 or tt.canh_ngan == 0:
        return tin_cay, ""
    if loai == "cot" and not (COT_CANH_NGAN[0] <= tt.canh_ngan <= COT_CANH_NGAN[1]):
        return tin_cay * HE_SO_HA, f"; cạnh {tt.canh_ngan:.2f} m ngoài khoảng cột hợp lý, hạ tin cậy"
    if loai == "dam" and tt.ty_le < DAM_TY_LE_TOI_THIEU:
        return tin_cay * HE_SO_HA, f"; dài/rộng {tt.ty_le:.1f} thấp so với dầm, hạ tin cậy"
    return tin_cay, ""


LOAI_VN = {"cot": "cột", "dam": "dầm", "san": "sàn", "mong": "móng", "vach": "vách"}
LOAI_KHONG_TINH = {"bo_qua", "nhan", "ong_gio"}
TIN_CAY_NHAN_TOI_DA = 0.88   # chỉ có nhãn, không có tên layer xác nhận: luôn cần người xác nhận


DO_PHU_TOI_THIEU = 0.3   # tối thiểu 30% hình mẫu phải có nhãn gần, mới dám kết luận cho cả layer


def _bang_chung_nhan(phieu, so_mau=0):
    """-> (loai, tin_cay, lan, phan_bo_text). lan=True khi không loại nào chiếm áp đảo,
    hoặc khi quá ít hình có nhãn (layer lớn mà chỉ vài hình được gọi tên thì không thể gán cả layer)."""
    tong = sum(phieu.values())
    if tong < 3:
        return None, 0.0, False, ""
    if so_mau >= 20 and tong / so_mau < DO_PHU_TOI_THIEU:
        pb = ", ".join(f"{LOAI_VN.get(k, k)} {v}" for k, v in sorted(phieu.items(), key=lambda kv: -kv[1]))
        return None, 0.0, True, f"{pb}; chỉ {tong}/{so_mau} hình mẫu có nhãn gần"
    loai, n = max(phieu.items(), key=lambda kv: kv[1])
    ty = n / tong
    pb = ", ".join(f"{LOAI_VN.get(k, k)} {v}" for k, v in sorted(phieu.items(), key=lambda kv: -kv[1]))
    if ty >= 0.7:
        return loai, round(min(TIN_CAY_NHAN_TOI_DA, 0.6 + 0.3 * ty * min(1.0, tong / 8)), 2), False, pb
    return None, 0.0, True, pb


def _hanh_dong(tin_cay, nguong_cao, nguong_thap):
    if tin_cay >= nguong_cao:
        return "tu_dien"
    return "xac_nhan" if tin_cay >= nguong_thap else "hoi_nguoi"


def doc_ho_so(duong_dan):
    """Đọc hồ sơ đơn vị thiết kế (mục 3.1): {tên layer: loại}."""
    with open(duong_dan, encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("layer", {})


def de_xuat_layer(danh_sach, ho_so=None, bo_de_xuat=de_xuat_ngoai_tuyen, layer_map=None,
                  nguong_cao=NGUONG_CAO, nguong_thap=NGUONG_THAP):
    """Với mỗi ThongTinLayer trả một DeXuat. Không có tác dụng phụ.

    Ba nguồn bằng chứng, kết hợp theo độ tin cậy:
      1. hồ sơ người dùng đã nhớ (thắng tất cả);
      2. tên layer đã chuẩn hóa (bỏ tiền tố xref) theo layer_map.yaml;
      3. nhãn chữ gần các hình kín của layer (C1, D2, M3...). Hai nguồn trùng nhau thì tin cậy tăng,
         mâu thuẫn thì hạ xuống mức phải xác nhận. Layer chứa lẫn nhiều loại thì không gán cả layer.
    """
    from app.config import phan_tich_ten
    ho_so = ho_so or {}
    kq = []
    for tt in danh_sach:
        chung = dict(so_hinh=tt.so_hinh_kin)
        if tt.ten in ho_so:
            kq.append(DeXuat(tt.ten, ho_so[tt.ten], 1.0, "hồ sơ", "Đã duyệt ở lần trước", "tu_dien", **chung))
            continue
        n_loai, n_conf, n_lydo, n_nguon = phan_tich_ten(tt.ten, layer_map)
        if n_nguon == "hồ sơ":
            kq.append(DeXuat(tt.ten, n_loai, 1.0, "hồ sơ", n_lydo, "tu_dien", **chung))
            continue
        c_loai, c_conf, lan, pb = _bang_chung_nhan(tt.phieu, tt.so_mau)
        phan_bo = dict(tt.phieu)

        def xong(loai, tin_cay, nguon, ly_do, **them):
            hd = _hanh_dong(tin_cay, nguong_cao, nguong_thap)
            kq.append(DeXuat(tt.ten, loai if hd != "hoi_nguoi" else None, round(tin_cay, 2), nguon, ly_do, hd,
                             phan_bo=phan_bo, **{**chung, **them}))

        if n_loai in LOAI_KHONG_TINH and n_conf >= 0.8:     # thép, chữ, kiến trúc, hệ thống: tên đủ chắc
            xong(n_loai, n_conf, n_nguon, n_lydo)
        elif n_loai and c_loai:
            if n_loai == c_loai:
                xong(n_loai, min(0.98, max(n_conf, c_conf) + 0.05), "luật tên + nhãn",
                     f"Tên layer và nhãn gần hình cùng chỉ {LOAI_VN.get(n_loai, n_loai)} ({pb})")
            elif c_conf >= 0.8 and n_conf < 0.9:
                xong(c_loai, min(0.85, c_conf * 0.9), "nhãn",
                     f"Nhãn gần hình chỉ {LOAI_VN.get(c_loai, c_loai)} ({pb}), tên layer chỉ yếu hơn: {n_lydo}")
            elif n_loai == "coc" and c_loai == "mong":       # cọc nằm trong đài, nhãn gần cọc là nhãn móng: bình thường
                xong(n_loai, n_conf, n_nguon, n_lydo + "; nhãn gần hình là nhãn đài móng (cọc nằm trong đài)")
            else:
                xong(n_loai, min(0.85, n_conf * 0.9), n_nguon,
                     f"Mâu thuẫn: tên layer chỉ {LOAI_VN.get(n_loai, n_loai)} nhưng nhãn gần hình chỉ {LOAI_VN.get(c_loai, c_loai)} ({pb})")
        elif n_loai:
            if lan and n_loai in LOAI_VN:
                xong(n_loai, min(0.85, n_conf), n_nguon, f"{n_lydo}; nhưng layer chứa lẫn nhiều loại ({pb})", lan=True)
            else:
                xong(n_loai, n_conf, n_nguon, n_lydo)
        elif c_loai:
            xong(c_loai, c_conf, "nhãn", f"Nhãn gần các hình kín của layer chỉ {LOAI_VN.get(c_loai, c_loai)} ({pb})")
        elif lan:
            kq.append(DeXuat(tt.ten, None, 0.0, "nhãn",
                             f"Layer chứa lẫn nhiều loại ({pb}). Đừng gán cả layer: dùng quét chọn theo vùng.",
                             "hoi_nguoi", lan=True, phan_bo=phan_bo, **chung))
        else:
            loai, tin_cay, ly_do = bo_de_xuat(tao_yeu_cau_ai(tt))
            if loai is None:
                kq.append(DeXuat(tt.ten, None, tin_cay, "không rõ", ly_do, "hoi_nguoi", phan_bo=phan_bo, **chung))
                continue
            tin_cay, ghi_chu = _kiem_tra_cheo(loai, tt, tin_cay)
            xong(loai, tin_cay, "gợi ý hình học", ly_do + ghi_chu)
    return kq


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Cách dùng: python -m tools.de_xuat_layer ban_ve.dxf [ho_so.yaml]")
    from app.dxf_reader import doc_ban_ve
    bv = doc_ban_ve(sys.argv[1])
    ho = doc_ho_so(sys.argv[2]) if len(sys.argv) > 2 else None
    for d in de_xuat_layer(thong_tin_tu_ban_ve(bv), ho):
        print(f"{d.ten:<22} {str(d.loai):<8} {d.tin_cay:<5} {d.hanh_dong:<9} [{d.nguon}] {d.ly_do}")
