"""Tính số liệu cho nhóm đối tượng người dùng chọn trên bản vẽ (kéo khung, Shift+bấm, chọn cả layer).

Đầu vào: {tên layer: {"h": [chỉ số hình kín], "n": [chỉ số đường hở]}}; chỉ số theo đúng thứ tự trong
hinh_xem (hinh_kin và net_ho của từng layer).

Diện tích và chu vi tính trên hợp các hình (unary_union) nên hình chồng lên nhau không bị cộng hai lần;
phần chồng được báo riêng để người dùng biết.
"""
from shapely.ops import unary_union


def boc_chon(ban_ve, chon):
    nhom = []
    for ten, sel in chon.items():
        ld = ban_ve.layers.get(ten)
        if ld is None:
            continue
        hs = [ld.hinh_kin[i].geom for i in sel.get("h", []) if 0 <= i < len(ld.hinh_kin)]
        ns = [ld.net_ho[i] for i in sel.get("n", []) if 0 <= i < len(ld.net_ho)]
        s_cong = sum(g.area for g in hs)
        hop = unary_union(hs) if hs else None
        s_hop = hop.area if hop is not None else 0.0
        nhom.append({
            "ten": ten, "so_hinh": len(hs), "so_net": len(ns),
            "s_cong": round(s_cong, 4), "s_hop": round(s_hop, 4), "chong": round(max(s_cong - s_hop, 0.0), 4),
            "p_cong": round(sum(g.length for g in hs), 3),
            "p_hop": round(hop.length, 3) if hop is not None else 0.0,
            "dai_net": round(sum(n.length for n in ns), 3),
        })
    nhom.sort(key=lambda x: -x["s_hop"])
    return {"nhom": nhom}
