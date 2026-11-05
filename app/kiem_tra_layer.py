"""Cổng kiểm tra gán layer: chạy trước khi tính, báo những chỗ gán layer có vẻ sai.

Gán layer sai là nguyên nhân số 1 làm sai khối lượng mà không báo lỗi (ví dụ tường kiến trúc trong xref
bị tính như vách, hoặc layer cốt thép bị tính như bê tông). Hàm này chỉ ĐỌC, không sửa gì.
"""
from . import config

LOAI_TINH = config.LOAI_KET_CAU | {"lo_san"}
TEN_LOAI = {"cot": "Cột", "dam": "Dầm", "san": "Sàn", "mong": "Móng", "coc": "Cọc", "vach": "Vách/lõi",
            "lo_san": "Lỗ mở sàn", "bo_qua": "Bỏ qua", "nhan": "Nhãn"}
HINH_LON = 30          # layer có từ chừng này hình kín trở lên mới đáng báo "chưa gán"
TOI_DA_BAO = 12


def kiem_tra_gan_layer(ban_ve, loai_layer, ds_de_xuat):
    """Trả danh sách {muc, layer, noi_dung}; muc = 'canh_bao' | 'thong_tin'. ds_de_xuat: kết quả de_xuat_layer."""
    dx = {d.ten: d for d in ds_de_xuat}
    kq = []
    for ten, loai in loai_layer.items():
        d = dx.get(ten)
        ld = ban_ve.layers.get(ten)
        n = d.so_hinh if d else (len(ld.hinh_kin) if ld else 0)
        if loai in LOAI_TINH:
            n_loai, n_conf, n_lydo, n_nguon = config.phan_tich_ten(ten)
            if n_nguon != "hồ sơ" and n_loai in ("bo_qua", "nhan", "ong_gio") and n_conf >= 0.8:
                kq.append({"muc": "canh_bao", "layer": ten,
                           "noi_dung": f"Layer '{ten}' đang gán là {TEN_LOAI[loai]} nhưng {n_lydo[0].lower() + n_lydo[1:]}. Dễ tính nhầm vào khối lượng."})
            elif config.chuan_hoa_ten(ten)[1] and n_nguon != "hồ sơ":
                kq.append({"muc": "canh_bao", "layer": ten,
                           "noi_dung": f"Layer '{ten}' nằm trong bản vẽ tham chiếu ngoài (xref), thường là bản kiến trúc, mà đang gán là {TEN_LOAI[loai]}. Nếu đây không phải bản kết cấu thì bỏ gán."})
            elif d and d.lan and loai != "lo_san":
                kq.append({"muc": "canh_bao", "layer": ten,
                           "noi_dung": f"Layer '{ten}' đang gán cả layer là {TEN_LOAI[loai]} nhưng chứa lẫn nhiều loại ({', '.join(f'{k} {v}' for k, v in d.phan_bo.items())}). Nên dùng quét chọn theo vùng."})
        elif loai in ("bo_qua", None, "") and n >= HINH_LON and d:
            if d.loai in LOAI_TINH and d.tin_cay >= 0.8 and d.nguon != "gợi ý hình học":
                kq.append({"muc": "canh_bao", "layer": ten,
                           "noi_dung": f"Layer '{ten}' ({n} hình) chưa gán nhưng có vẻ là {TEN_LOAI[d.loai]} ({d.ly_do}). Nếu bỏ sót sẽ thiếu khối lượng."})
            elif d.lan and n >= 200:
                kq.append({"muc": "thong_tin", "layer": ten,
                           "noi_dung": f"Layer '{ten}' ({n} hình) chưa gán vì chứa lẫn nhiều loại. Nếu mặt bằng nằm trong layer này, dùng quét chọn theo vùng."})
    return kq[:TOI_DA_BAO]


def kiem_tra_ket_qua(kq):
    """Kiểm tra độ hợp lý của kết quả sau khi tính. Trả danh sách câu cảnh báo."""
    bt = {t["ma"]: t["khoi_luong"] for t in kq.get("tong_hop", [])}
    cac = [bt.get(k, 0.0) for k in ("be_tong_cot", "be_tong_dam", "be_tong_vach", "be_tong_mong")]
    tong = sum(cac)
    out = []
    if tong > 0 and bt.get("be_tong_vach", 0.0) / tong > 0.5:
        out.append(f"Vách/lõi chiếm {bt['be_tong_vach'] / tong:.0%} tổng bê tông cột-dầm-vách-móng, bất thường nếu công trình không có nhiều vách. "
                   "Kiểm tra layer đang gán là Vách (tường kiến trúc hay bị gán nhầm).")
    return out
