"""Suy ra dầm từ bản vẽ không vẽ đường bao dầm.

Nhiều bản vẽ mặt bằng dầm chỉ vẽ khung ngoài và các ô trống (ô sàn) giữa các dầm; dầm là phần
còn lại: dầm = khung ngoài trừ các ô trống.

Cách làm cho từng khung:
1. Phần dầm F = khung - hợp các ô trống nằm trong khung.
2. Cắt khung thành dải theo các cạnh của ô trống. Dải ngang nào (hoặc dải đứng nào) mà F phủ kín
   cả bề rộng (bề cao) của khung thì là một dầm chạy suốt khung.
3. Dầm chạy suốt được trả ra thành hình chữ nhật dài suốt khung; chỗ hai dầm giao nhau do logic
   tính dầm hiện có xử lý (dầm cao hơn giữ phần giao).
4. Phần F còn lại không thuộc dải nào (khung không theo lưới chữ nhật) gom thành một dầm riêng và
   có cảnh báo.

Kích thước và chiều cao dầm lấy từ nhãn chữ gần nhất như các dầm vẽ sẵn.
"""
from dataclasses import replace

from shapely.geometry import box
from shapely.ops import unary_union

from .dxf_reader import HinhKin, LayerData

TEN_LAYER_SUY_RA = "_DAM_SUY_RA"
EPS = 1e-6
PHU_KIN = 0.98      # dải được coi là dầm khi F phủ từ 98% diện tích dải
O_NHO_NHAT = 0.01   # ô trống nhỏ hơn 1% diện tích khung bị bỏ (ký hiệu, nét vẽ nhỏ)
O_LON_NHAT = 0.9    # hình từ 90% diện tích khung trở lên là chính khung, không phải ô trống


def _manh(g):
    if g.is_empty:
        return []
    if g.geom_type == "Polygon":
        return [g]
    return [x for x in getattr(g, "geoms", []) if x.geom_type == "Polygon" and x.area > 0]


def _cat_dai(khung, phan_dam, huong):
    """Trả danh sách hình chữ nhật dầm chạy suốt khung theo hướng 'ngang' hoặc 'dung'."""
    x0, y0, x1, y1 = khung.bounds
    if huong == "ngang":
        moc = sorted({round(v, 6) for g in phan_dam.get("o", []) for v in (g.bounds[1], g.bounds[3])} | {y0, y1})
        dai = [box(x0, a, x1, b) for a, b in zip(moc, moc[1:]) if b - a > EPS]
    else:
        moc = sorted({round(v, 6) for g in phan_dam.get("o", []) for v in (g.bounds[0], g.bounds[2])} | {x0, x1})
        dai = [box(a, y0, b, y1) for a, b in zip(moc, moc[1:]) if b - a > EPS]
    f = phan_dam["f"]
    return [d for d in dai if d.intersection(f).area >= PHU_KIN * d.area]


def suy_dam(ban_ve, loai_layer):
    """Trả (ban_ve mới, loai_layer mới). Không đổi gì nếu không có layer khung dầm / ô trống."""
    ten_khung = [t for t, v in loai_layer.items() if v == "khung_dam"]
    ten_o = [t for t, v in loai_layer.items() if v == "o_dam"]
    if not ten_khung and not ten_o:
        return ban_ve, loai_layer

    canh_bao = list(ban_ve.canh_bao)
    if not ten_khung or not ten_o:
        canh_bao.append('Cần gán cả layer "Khung dầm" và layer "Ô trống giữa dầm" thì mới suy ra được dầm.')
        return replace(ban_ve, canh_bao=canh_bao), loai_layer

    khungs = [h.geom for t in ten_khung for h in ban_ve.layers[t].hinh_kin]
    ods = [h.geom for t in ten_o for h in ban_ve.layers[t].hinh_kin]
    # Bỏ khung trùng nhau (hatch + polyline, ghép nét)
    khung_duy_nhat = []
    for k in sorted(khungs, key=lambda g: -g.area):
        if not any(k.intersection(u).area > 0.95 * k.area for u in khung_duy_nhat):
            khung_duy_nhat.append(k)

    dai_dam = []
    for k in khung_duy_nhat:
        o_trong = [o.intersection(k) for o in ods if k.contains(o.centroid)]
        o_trong = [o for o in o_trong if O_NHO_NHAT * k.area <= o.area < O_LON_NHAT * k.area]
        if not o_trong:
            continue  # khung của mặt bằng khác (móng, định vị cột...) không có ô trống: bỏ qua
        f = k.difference(unary_union(o_trong))
        ctx = {"f": f, "o": o_trong}
        ngang, dung = _cat_dai(k, ctx, "ngang"), _cat_dai(k, ctx, "dung")
        dai_k = ngang + dung
        du = f.difference(unary_union(dai_k)) if dai_k else f
        for g in _manh(du):
            if g.area > 1e-4:
                dai_k.append(g)
                canh_bao.append(
                    f"Khung dầm có phần dầm {g.area:.3f} m² không theo lưới chữ nhật, gom thành một dầm riêng, Sếp kiểm tra.")
        dai_dam.extend(dai_k)

    if not dai_dam:
        canh_bao.append("Không suy ra được dầm: không khung dầm nào chứa ô trống.")
        return replace(ban_ve, canh_bao=canh_bao), loai_layer
    canh_bao.append(
        f"Đã suy ra {len(dai_dam)} dải dầm = khung trừ ô trống. Kích thước dầm lấy từ nhãn gần nhất, Sếp đối chiếu.")

    layers = dict(ban_ve.layers)
    layers[TEN_LAYER_SUY_RA] = LayerData(
        ten=TEN_LAYER_SUY_RA, hinh_kin=[HinhKin(g, "", "SUY_RA") for g in dai_dam])
    loai = dict(loai_layer)
    loai[TEN_LAYER_SUY_RA] = "dam"
    return replace(ban_ve, layers=layers, canh_bao=canh_bao), loai
