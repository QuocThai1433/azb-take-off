"""Tự tách nhiều mặt bằng / chi tiết nằm trong cùng một file bản vẽ.

Một file CAD thường chứa cả chục tờ (mặt bằng từng tầng, chi tiết, bảng thống kê) bày cạnh nhau trên cùng một
không gian mô hình. Hàm này chỉ ĐỀ XUẤT các vùng (khung chữ nhật, tính bằng mét) để người dùng xem và xác nhận.
Nó không sửa bản vẽ và không ghi gì vào kết quả bóc.

Hai cách tìm vùng, theo thứ tự ưu tiên:
  1. Khung giấy: có từ 2 khung chữ nhật rất lớn (khung tờ vẽ) không lồng nhau thì mỗi khung là một vùng.
  2. Cụm nét vẽ: gom các nét, hình, chữ nằm gần nhau; hai cụm cách nhau quá `khoang_cach` thì tách thành hai vùng.

Với mỗi vùng đọc thêm: tiêu đề (MẶT BẰNG DẦM SÀN TẦNG 2...), tầng, tỷ lệ (TL 1/100), và đoán vai trò
(mặt bằng / chi tiết / ghi chú-bảng).
"""
import math
import re
import unicodedata
from collections import defaultdict, deque

import numpy as np
from shapely.geometry import box

from .dxf_reader import KHUNG_GIAY_M2
from .gan_nhan import RE_TANG, RE_TL
from .takeoff import doc_nhan

TOI_DA_VUNG = 40
MAX_MAU_NET = 20            # số điểm lấy mẫu trên mỗi đường hở
TOI_THIEU_MUC = 6           # cụm có ít mục hơn mức này (và không có tiêu đề) bị coi là rác nét vẽ
TY_LE_HCN = 0.9             # khung giấy: diện tích / diện tích hình chữ nhật bao >= mức này

RE_MAT_BANG = re.compile(r"mat\s*bang|floor\s*plan|\bmb\b")
RE_CHI_TIET = re.compile(r"chi\s*tiet|detail|mat\s*cat|section|\bct\b")
RE_GHI_CHU = re.compile(r"thong\s*ke|bang\s*thep|bang\s*tong|schedule|ghi\s*chu|ghi\s*chu\s*chung|notes?\b|general")


def _bo_dau(s):
    s = unicodedata.normalize("NFD", (s or "").replace("đ", "d").replace("Đ", "D"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def _thu_thap(ban_ve):
    """Mẫu điểm của mọi nét vẽ để gom cụm. Trả (X, Y, loai, la_chinh): loai 0 hình, 1 nét, 2 chữ."""
    xs, ys, kind, chinh = [], [], [], []

    def them(x, y, k, c):
        xs.append(x); ys.append(y); kind.append(k); chinh.append(c)

    for ten, ld in ban_ve.layers.items():
        if ld.tat or ten.lower() == "defpoints":
            continue
        for h in ld.hinh_kin:
            if h.geom.area >= KHUNG_GIAY_M2:
                continue
            x0, y0, x1, y1 = h.geom.bounds
            them((x0 + x1) / 2, (y0 + y1) / 2, 0, True)
            for x, y in ((x0, y0), (x1, y1), (x0, y1), (x1, y0)):
                them(x, y, 0, False)
        for n in ld.net_ho:
            cs = list(n.coords)
            buoc = max(1, len(cs) // MAX_MAU_NET)
            for i, (x, y) in enumerate(cs[::buoc]):
                them(x, y, 1, i == 0)
        for c in ld.chu:
            them(c.diem.x, c.diem.y, 2, True)
    return np.array(xs), np.array(ys), np.array(kind), np.array(chinh, dtype=bool)


def _cum(X, Y, khoang_cach):
    """Gom điểm thành cụm: chia lưới ô cạnh R, hai ô có điểm kề nhau (8 hướng) thì cùng cụm. Trả nhãn từng điểm."""
    r = max(khoang_cach / 1.5, 1e-6)
    cx = np.floor((X - X.min()) / r).astype(np.int64)
    cy = np.floor((Y - Y.min()) / r).astype(np.int64)
    o = defaultdict(list)
    for i, k in enumerate(zip(cx.tolist(), cy.tolist())):
        o[k].append(i)
    nhan_o, so_cum = {}, 0
    for k in o:
        if k in nhan_o:
            continue
        nhan_o[k] = so_cum
        dq = deque([k])
        while dq:
            a, b = dq.popleft()
            for da in (-1, 0, 1):
                for db in (-1, 0, 1):
                    q = (a + da, b + db)
                    if q in o and q not in nhan_o:
                        nhan_o[q] = so_cum
                        dq.append(q)
        so_cum += 1
    nhan = np.empty(len(X), dtype=np.int64)
    for k, ids in o.items():
        nhan[ids] = nhan_o[k]
    return nhan


def _khung_giay(ban_ve):
    """Các khung tờ vẽ: hình chữ nhật rất lớn, bỏ khung nằm trong khung khác."""
    ds = []
    for ld in ban_ve.layers.values():
        if ld.tat:
            continue
        for h in ld.hinh_kin:
            g = h.geom
            if g.area < KHUNG_GIAY_M2:
                continue
            hcn = g.minimum_rotated_rectangle
            if hcn.area > 0 and g.area / hcn.area >= TY_LE_HCN:
                ds.append(box(*g.bounds))
    ds.sort(key=lambda b: -b.area)
    giu = []
    for b in ds:
        if any(k.buffer(1e-6).contains(b) for k in giu):
            continue
        if any(k.equals(b) for k in giu):
            continue
        giu.append(b)
    return [b.bounds for b in giu]


def _chu_trong(chu_ds, k, le=0.0):
    x0, y0, x1, y1 = k
    return [c for c in chu_ds if x0 - le <= c.diem.x <= x1 + le and y0 - le <= c.diem.y <= y1 + le]


def _phan_tich_vung(chu_ds, k, le):
    """Tiêu đề, tầng, tỷ lệ, vai trò của một vùng."""
    cs = _chu_trong(chu_ds, k, le)
    tieu_de, diem_tot = None, -1.0
    cac_tieu_de = set()
    ty_le, tang = None, None
    nhan_kc = 0
    for c in cs:
        t = unicodedata.normalize("NFC", c.noi_dung).replace("\n", " ").strip()
        kd = _bo_dau(t)
        m = RE_TL.search(t)
        if m and ty_le is None:
            ty_le = int(m.group(1))
        loai = None
        if RE_CHI_TIET.search(kd):
            loai = "chi_tiet"
        elif RE_GHI_CHU.search(kd):
            loai = "ghi_chu"
        elif RE_MAT_BANG.search(kd):
            loai = "mat_bang"
        if loai and len(t) <= 120:
            cac_tieu_de.add(re.sub(r"\s+", " ", t.upper()))
            diem = (c.cao or 0.0) * 10 + (5 if loai == "mat_bang" else 0) + min(len(t), 60) / 60
            if diem > diem_tot:
                diem_tot, tieu_de = diem, (t, loai)
        if doc_nhan(c.noi_dung)["loai"]:
            nhan_kc += 1
    if tieu_de:
        mt = RE_TANG.search(tieu_de[0])
        tang = mt.group(0).strip() if mt else None
    return {"tieu_de": tieu_de[0] if tieu_de else None, "loai_tieu_de": tieu_de[1] if tieu_de else None,
            "ty_le": ty_le, "tang": tang, "nhan_kc": nhan_kc, "so_tieu_de": len(cac_tieu_de)}


def _sap_doc(vung):
    """Thứ tự đọc: từ trên xuống, trong cùng hàng từ trái sang phải."""
    if not vung:
        return vung
    cao = sorted(v["khung"][3] - v["khung"][1] for v in vung)[len(vung) // 2] or 1.0
    return sorted(vung, key=lambda v: (-round(((v["khung"][1] + v["khung"][3]) / 2) / (0.6 * cao)), v["khung"][0]))


def _vi_tri_cat(P, b0, b1):
    """Đường cắt trong dải [b0, b1]: giữa khoảng trống rộng nhất giữa các điểm vẽ nằm trong dải (không có điểm nào thì giữa dải)."""
    ps = np.unique(np.concatenate(([b0, b1], P[(P > b0) & (P < b1)])))
    if len(ps) < 3:
        return (b0 + b1) / 2
    i = int(np.argmax(np.diff(ps)))
    return float((ps[i] + ps[i + 1]) / 2)


def _cat_chong(vung, X, Y, bien=1e-3):
    """Cắt phần khung đè lên nhau. Mỗi cặp chồng nhau được cắt theo trục có độ chồng nhỏ hơn, tại khoảng trống
    rộng nhất giữa nét vẽ của hai tờ trong dải chồng, nên hai vùng sát nhau thành hai khung liền kề. Khung gần trọn
    nằm trong khung kia thì không cắt được (vẫn để cảnh báo). Vùng bị cắt được ghi cảnh báo để kiểm tra ranh giới."""
    for _ in range(4 * len(vung) + 4):
        da_cat = False
        for i, a in enumerate(vung):
            for b in vung[i + 1:]:
                ka, kb = a["khung"], b["khung"]
                ox = min(ka[2], kb[2]) - max(ka[0], kb[0])
                oy = min(ka[3], kb[3]) - max(ka[1], kb[1])
                if ox <= bien or oy <= bien:
                    continue
                dt_a = (ka[2] - ka[0]) * (ka[3] - ka[1])
                dt_b = (kb[2] - kb[0]) * (kb[3] - kb[1])
                if ox * oy >= 0.9 * min(dt_a, dt_b):
                    continue
                lo, hi = (0, 2) if ox <= oy else (1, 3)     # trục cắt: x nếu chồng theo x ít hơn
                trai, phai = (a, b) if ka[lo] + ka[hi] <= kb[lo] + kb[hi] else (b, a)
                g0, g1 = max(ka[lo], kb[lo]), min(ka[hi], kb[hi])
                trong = (X >= max(ka[0], kb[0])) & (X <= min(ka[2], kb[2])) & (Y >= max(ka[1], kb[1])) & (Y <= min(ka[3], kb[3]))
                cat = round(_vi_tri_cat((X if lo == 0 else Y)[trong], g0, g1), 3)
                if not (trai["khung"][lo] < cat < phai["khung"][hi]):
                    continue
                trai["khung"][hi] = cat
                phai["khung"][lo] = cat
                for v, khac in ((trai, phai), (phai, trai)):
                    v["canh_bao"].append(f"Đã cắt bớt phần khung chồng với vùng #{khac['id']}: kiểm tra ranh giới")
                    v["tin_cay"] = min(v["tin_cay"], 0.6)
                da_cat = True
        if not da_cat:
            break


def do_mat_bang(ban_ve, khoang_cach=None):
    """Đề xuất các vùng (mặt bằng / chi tiết / bảng) trong một bản vẽ. Trả {ds, khoang_cach, cach}."""
    X, Y, K, C = _thu_thap(ban_ve)
    chu_ds = [c for ld in ban_ve.layers.values() if not ld.tat for c in ld.chu]
    if not len(X):
        return {"ds": [], "khoang_cach": 0.0, "cach": "trống"}
    rong = max(X.max() - X.min(), Y.max() - Y.min())
    kc = float(khoang_cach) if khoang_cach else min(60.0, max(2.0, 0.04 * rong))

    khung = _khung_giay(ban_ve)
    if len(khung) >= 2:
        cach = "khung giấy"
        cum = []
        for k in khung:
            trong = (X >= k[0]) & (X <= k[2]) & (Y >= k[1]) & (Y <= k[3])
            cum.append((k, trong))
    else:
        cach = "cụm nét vẽ"
        nhan = _cum(X, Y, kc)
        cum = []
        for n in np.unique(nhan):
            m = nhan == n
            cum.append(((float(X[m].min()), float(Y[m].min()), float(X[m].max()), float(Y[m].max())), m))

    vung = []
    for k, m in cum:
        n_hinh = int(((K == 0) & C & m).sum())
        n_net = int(((K == 1) & C & m).sum())
        n_chu = int(((K == 2) & m).sum())
        pt = _phan_tich_vung(chu_ds, k, kc * 0.5)
        if cach == "cụm nét vẽ" and n_hinh + n_net + n_chu < TOI_THIEU_MUC and not pt["tieu_de"]:
            continue   # vài nét lẻ loi, không phải một tờ vẽ
        lt = pt["loai_tieu_de"]
        if lt:
            vai, tin, ly = lt, 0.9, f'Tiêu đề: "{pt["tieu_de"][:50]}"'
        elif n_chu > 3 * max(n_hinh, 1) and n_chu >= 8:
            vai, tin, ly = "ghi_chu", 0.5, "Nhiều chữ, ít hình: giống bảng hoặc ghi chú"
        elif n_hinh >= 10 and pt["nhan_kc"] >= 3:
            vai, tin, ly = "mat_bang", 0.6, f"{n_hinh} hình kín và {pt['nhan_kc']} nhãn cấu kiện: giống mặt bằng, chưa thấy tiêu đề"
        else:
            vai, tin, ly = "chi_tiet", 0.35, "Không thấy tiêu đề, ít nhãn cấu kiện: chưa chắc là mặt bằng"
        canh_bao = []
        if pt["so_tieu_de"] >= 2:
            tin = min(tin, 0.6)
            canh_bao.append(f"Có {pt['so_tieu_de']} tiêu đề khác nhau trong vùng: nhiều mặt bằng có thể vẽ đè lên nhau, kiểm tra tên")
        le = 0.01 * max(k[2] - k[0], k[3] - k[1])
        vung.append({"canh_bao": canh_bao, "khung": [round(k[0] - le, 3), round(k[1] - le, 3), round(k[2] + le, 3), round(k[3] + le, 3)],
                     "ten": (pt["tieu_de"] or "")[:70], "tang": pt["tang"], "ty_le": pt["ty_le"], "vai_tro": vai,
                     "tin_cay": tin, "ly_do": ly, "so_hinh": n_hinh, "so_net": n_net, "so_chu": n_chu, "nguon": cach})
    vung = _sap_doc(sorted(vung, key=lambda v: -(v["so_hinh"] + v["so_net"] + v["so_chu"]))[:TOI_DA_VUNG])
    for i, v in enumerate(vung, 1):
        v["id"] = i
    khung_cu = [list(v["khung"]) for v in vung]
    _cat_chong(vung, X, Y)
    for v, kc_cu in zip(vung, khung_cu):    # khung đã cắt thì đọc lại tiêu đề, tầng, tỷ lệ theo khung mới (không còn lẫn tiêu đề tờ bên cạnh)
        if v["khung"] == kc_cu:
            continue
        pt = _phan_tich_vung(chu_ds, v["khung"], 0.0)
        if pt["tieu_de"]:
            v["ten"], v["tang"], v["vai_tro"] = pt["tieu_de"][:70], pt["tang"], pt["loai_tieu_de"]
            v["ly_do"] = f'Tiêu đề: "{pt["tieu_de"][:50]}"'
        if pt["ty_le"]:
            v["ty_le"] = pt["ty_le"]
        if pt["so_tieu_de"] < 2:
            v["canh_bao"] = [c for c in v["canh_bao"] if not c.startswith("Có ")]
    for a in vung:       # vùng chồng lấn nhau: dấu hiệu nhiều tờ vẽ đè lên nhau, hoặc khung bị vẽ trùng
        ba = box(*a["khung"])
        for b in vung:
            if a is b:
                continue
            giao = ba.intersection(box(*b["khung"])).area
            if giao > 0.2 * min(ba.area, box(*b["khung"]).area):
                a["canh_bao"].append(f"Chồng lấn vùng #{b['id']} ({giao / min(ba.area, box(*b['khung']).area):.0%}): kiểm tra trước khi tạo")
                a["tin_cay"] = min(a["tin_cay"], 0.6)
    for v in vung:
        if not v["ten"]:
            v["ten"] = f"Vùng {v['id']}"
    return {"ds": vung, "khoang_cach": round(kc, 2), "cach": cach}
