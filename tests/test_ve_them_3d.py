"""Vẽ thêm trong 3D: hình học đường cong (cung qua 3 điểm, dầm cong) kiểm bằng node, không cần trình duyệt."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

XEM3D = Path(__file__).resolve().parent.parent / "app" / "static" / "xem3d.js"
NODE = shutil.which("node")


def _chay(bieu_thuc: str):
    """Nạp xem3d.js với window giả rồi tính biểu thức JS dùng window.xem3D.hinhHoc (cungDiem, vongDamCong)."""
    ma = (
        "global.window = {}; require(process.argv[1]);"
        "const {cungDiem, vongDamCong} = window.xem3D.hinhHoc;"
        f"console.log(JSON.stringify({bieu_thuc}));"
    )
    kq = subprocess.run([NODE, "-e", ma, str(XEM3D)], capture_output=True, text=True, timeout=30)
    assert kq.returncode == 0, kq.stderr
    return json.loads(kq.stdout)


pytestmark = pytest.mark.skipif(NODE is None, reason="không có node để chạy test JS")


def test_cung_di_qua_ba_diem_va_cung_ban_kinh():
    # nửa đường tròn tâm (0,0) bán kính 5: đầu (5,0), giữa (0,5), cuối (-5,0)
    p = _chay("cungDiem([5,0],[0,5],[-5,0])")
    assert p[0] == [5, 0] and p[-1] == [-5, 0]
    assert len(p) > 10
    assert all(abs((x * x + y * y) ** 0.5 - 5) < 1e-6 for x, y in p)
    assert all(y >= -1e-9 for _, y in p)  # cung đi qua điểm giữa phía trên, không vòng ra phía dưới


def test_cung_di_chieu_kim_dong_ho_khi_diem_giua_o_phia_kia():
    p = _chay("cungDiem([5,0],[0,-5],[-5,0])")
    assert all(y <= 1e-9 for _, y in p)


def test_ba_diem_thang_hang_thanh_doan_thang():
    assert _chay("cungDiem([0,0],[1,0],[4,0])") == [[0, 0], [4, 0]]


def test_dam_cong_rong_dung_be_rong():
    # dầm thẳng (hai điểm) rộng 0,2: vòng 4 điểm, cạnh ngang cách nhau đúng 0,2
    v = _chay("vongDamCong([[0,0],[4,0]],0.2)")
    assert len(v) == 4
    assert sorted(round(abs(y), 6) for _, y in v) == [0.1, 0.1, 0.1, 0.1]
    # dầm cong: vòng có 2 lần số điểm của đường tim, mọi điểm cách đường tim đúng nửa bề rộng
    tim = _chay("cungDiem([5,0],[0,5],[-5,0])")
    v = _chay("vongDamCong(cungDiem([5,0],[0,5],[-5,0]),0.4)")
    assert len(v) == 2 * len(tim)
    assert all(abs(abs((x * x + y * y) ** 0.5 - 5) - 0.2) < 1e-2 for x, y in v)
