"""Tạo bản vẽ DXF mẫu (đơn vị mm) có đáp số tính tay, dùng để kiểm thử.

Khung 2 nhịp x 1 nhịp: lưới trục X = 0, 6000, 12000; Y = 0, 5000.
- 6 cột C1 300x300 tại giao trục
- Dầm D1 220x500 theo phương X, dầm D2 220x400 theo phương Y, vẽ từ tim cột đến tim cột
- 1 ô sàn S1 t=120 bao ngoài mép cột, có 1 lỗ mở 1000x1000
- 6 móng M1 1200x1200x700
- Cố ý vẽ trùng 1 cột và 1 nét hở để kiểm tra cảnh báo

Chạy: .venv\\Scripts\\python tools\\tao_ban_ve_mau.py
"""
from pathlib import Path

import ezdxf


def hcn(msp, x0, y0, x1, y1, layer):
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": layer})


def tao(duong_dan):
    doc = ezdxf.new("R2018", units=4)  # 4 = mm
    for ten, mau in [("S-COT", 1), ("S-DAM", 3), ("S-SAN", 5), ("S-LO_SAN", 6), ("S-MONG", 2), ("S-TEXT", 7)]:
        doc.layers.add(ten, color=mau)
    msp = doc.modelspace()
    X, Y = [0, 6000, 12000], [0, 5000]

    for x in X:
        for y in Y:
            hcn(msp, x - 150, y - 150, x + 150, y + 150, "S-COT")
            msp.add_text("C1 300x300", height=150, dxfattribs={"layer": "S-TEXT", "insert": (x + 250, y + 250)})
            hcn(msp, x - 600, y - 600, x + 600, y + 600, "S-MONG")
            msp.add_text("M1 1200x1200x700", height=150, dxfattribs={"layer": "S-TEXT", "insert": (x + 650, y - 650)})
    hcn(msp, -150, -150, 150, 150, "S-COT")  # vẽ trùng cột tại (0,0)

    for y in Y:
        for x0, x1 in [(0, 6000), (6000, 12000)]:
            hcn(msp, x0, y - 110, x1, y + 110, "S-DAM")
            msp.add_text("D1 220x500", height=150, dxfattribs={"layer": "S-TEXT", "insert": ((x0 + x1) / 2, y + 300)})
    for x in X:
        hcn(msp, x - 110, 0, x + 110, 5000, "S-DAM")
        msp.add_text("D2 220x400", height=150, dxfattribs={"layer": "S-TEXT", "insert": (x + 300, 2500)})
    msp.add_lwpolyline([(20000, 0), (21000, 0), (21000, 500)], dxfattribs={"layer": "S-DAM"})  # nét hở

    hcn(msp, -150, -150, 12150, 5150, "S-SAN")
    msp.add_text("S1 t=120", height=200, dxfattribs={"layer": "S-TEXT", "insert": (9000, 2500)})
    hcn(msp, 2000, 2000, 3000, 3000, "S-LO_SAN")

    doc.saveas(duong_dan)


if __name__ == "__main__":
    ra = Path(__file__).resolve().parent.parent / "data" / "mau" / "khung_mau.dxf"
    ra.parent.mkdir(parents=True, exist_ok=True)
    tao(ra)
    print("Đã tạo", ra)
