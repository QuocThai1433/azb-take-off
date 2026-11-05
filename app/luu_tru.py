"""Lưu trữ dự án: trạng thái làm việc, nạp lại bản vẽ, sao lưu tự động và gói dự án (.zip).

Cấu trúc thư mục (đều nằm trong data/):
  uploads/<mã 12 ký tự>/<file bản vẽ>, _meta.json   file Sếp đã tải lên (đóng bản vẽ thì vẫn giữ, chỉ mất khi Sếp xóa hẳn)
  du_an/trang_thai.json                               trạng thái làm việc (danh sách bản vẽ, layer, vùng...)
  backup/AZB_<ngày>_<giờ>_<loại>.zip                  bản sao lưu (trạng thái + file bản vẽ)
"""
import io
import json
import logging
import re
import shutil
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from . import config

log = logging.getLogger("azb.luu_tru")

DATA = config.DATA_DIR
THU_MUC_TAI_LEN = DATA / "uploads"
FILE_TRANG_THAI = DATA / "du_an" / "trang_thai.json"
THU_MUC_BACKUP = DATA / "backup"

MAU_PID = re.compile(r"^[0-9a-f]{12}$")
MAU_TEN_BACKUP = re.compile(r"^AZB_\d{8}_\d{6}(_\d+)?_[a-z_]+\.zip$")
DUOI_HOP_LE = (".dxf", ".dwg")
DUOI_TRONG_GOI = DUOI_HOP_LE + (".pdf",)  # gói zip còn chứa PDF gốc của bản vẽ đổi từ PDF
TEN_META = "_meta.json"

SO_BACKUP_TU_DONG = 10      # giữ bao nhiêu bản tự động gần nhất
SO_BACKUP_KHAC = 20         # giữ bao nhiêu bản bấm tay / trước khi xóa / trước khi khôi phục
DUNG_LUONG_BACKUP_TOI_DA = 1024 ** 3   # tổng dung lượng thư mục backup: vượt mức này thì xóa bản cũ nhất (tự động trước)
GIAN_CACH_TU_DONG = 600     # giây: tối thiểu giữa hai lần tự sao lưu khi chỉ đổi thiết lập
DUNG_LUONG_TOI_DA = 2 * 1024 ** 3  # chặn gói zip giải nén quá 2 GB

NHAN_LOAI = {"tu_dong": "tự động", "thu_cong": "bấm tay", "truoc_xoa": "trước khi xóa",
             "truoc_khoi_phuc": "trước khi khôi phục"}


# ---------- Thư mục bản vẽ ----------
def thu_muc_ban_ve(pid):
    if not isinstance(pid, str) or not MAU_PID.fullmatch(pid):
        raise ValueError("Mã bản vẽ không hợp lệ.")
    return THU_MUC_TAI_LEN / pid


def _ghi_json(duong_dan, doi_tuong):
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    tam = duong_dan.with_name(duong_dan.name + ".tmp")
    tam.write_text(json.dumps(doi_tuong, ensure_ascii=False), encoding="utf-8")
    tam.replace(duong_dan)


def ghi_meta(pid, ten, don_vi, **them):
    """them: thông tin phụ (vd bản vẽ lấy từ PDF: nguon_pdf, canh_bao_nguon)."""
    _ghi_json(thu_muc_ban_ve(pid) / TEN_META, {"ten": ten, "don_vi": don_vi, "mo_luc": time.time(), **them})


def danh_dau_da_mo(pid):
    """Ghi lại thời điểm mở bản vẽ này, để danh sách 'Bản vẽ đã tải' xếp file mở gần nhất lên đầu."""
    meta = doc_meta(pid)
    if not meta or not tim_file(pid):
        return
    meta["mo_luc"] = time.time()
    _ghi_json(thu_muc_ban_ve(pid) / TEN_META, meta)


def doc_meta(pid):
    try:
        return json.loads((thu_muc_ban_ve(pid) / TEN_META).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def tim_file(pid):
    """Đường dẫn file bản vẽ đã lưu của mã này, hoặc None nếu không còn."""
    thu_muc = thu_muc_ban_ve(pid)
    if not thu_muc.is_dir():
        return None
    ten = doc_meta(pid).get("ten")
    if ten and (thu_muc / ten).is_file():
        return thu_muc / ten
    for p in sorted(thu_muc.iterdir()):
        if p.is_file() and p.suffix.lower() in DUOI_HOP_LE:
            return p
    return None


def file_cache(pid):
    """Cache hình học đã xử lý của bản vẽ; để ngoài thư mục uploads để không lọt vào gói zip/sao lưu."""
    thu_muc_ban_ve(pid)  # kiểm tra mã hợp lệ
    return DATA / "cache" / f"{pid}.pkl"


def xoa_ban_ve(pid):
    thu_muc = thu_muc_ban_ve(pid)
    try:
        file_cache(pid).unlink()
    except OSError:
        pass
    if thu_muc.is_dir():
        shutil.rmtree(thu_muc)
        return True
    return False


# ---------- Trạng thái làm việc ----------
def doc_trang_thai():
    try:
        tt = json.loads(FILE_TRANG_THAI.read_text(encoding="utf-8"))
        return tt if isinstance(tt, dict) else None
    except (OSError, ValueError):
        return None


def ghi_trang_thai(tt):
    _ghi_json(FILE_TRANG_THAI, tt)


def _muc_hop_le(tt, khoa):
    ds = tt.get(khoa, []) if isinstance(tt, dict) else []
    return [f for f in ds if isinstance(f, dict) and isinstance(f.get("id"), str) and MAU_PID.fullmatch(f["id"])]


def ids_trong(tt):
    """Mã các bản vẽ dự án đang giữ: đang mở (files) và đã đóng nhưng còn lưu (da_dong)."""
    if not tt:
        return set()
    return {f["id"] for k in ("files", "da_dong") for f in _muc_hop_le(tt, k)}


def bo_khoi_da_dong(pid):
    """Gỡ bản vẽ khỏi danh sách 'đã đóng' trong trạng thái đã lưu (dùng khi xóa hẳn file)."""
    tt = doc_trang_thai()
    if tt and any(f.get("id") == pid for f in tt.get("da_dong", []) if isinstance(f, dict)):
        tt["da_dong"] = [f for f in tt["da_dong"] if not (isinstance(f, dict) and f.get("id") == pid)]
        ghi_trang_thai(tt)


def liet_ke_ban_ve():
    """Mọi bản vẽ đang nằm trong data/uploads (kể cả bản đã đóng), mở gần nhất xếp trước."""
    ds = []
    if not THU_MUC_TAI_LEN.is_dir():
        return ds
    for thu_muc in THU_MUC_TAI_LEN.iterdir():
        if not (thu_muc.is_dir() and MAU_PID.fullmatch(thu_muc.name)):
            continue
        duong = tim_file(thu_muc.name)
        if duong is None:
            continue
        st = duong.stat()
        mo = doc_meta(thu_muc.name).get("mo_luc")
        mo = mo if isinstance(mo, (int, float)) else st.st_mtime  # file cũ chưa có dấu thời gian mở
        ds.append({"id": thu_muc.name, "ten": duong.name, "mb": round(st.st_size / 1048576, 1), "mtime": mo,
                   "thoi_gian": time.strftime("%d/%m/%Y %H:%M", time.localtime(mo))})
    ds.sort(key=lambda d: d["mtime"], reverse=True)
    return ds


# ---------- Gói zip / sao lưu ----------
def _ghi_zip(z, tt):
    z.writestr("trang_thai.json", json.dumps(tt, ensure_ascii=False))
    for pid in sorted(ids_trong(tt)):
        thu_muc = THU_MUC_TAI_LEN / pid
        if not thu_muc.is_dir():
            continue
        for p in sorted(thu_muc.iterdir()):
            if p.is_file():
                z.write(p, f"uploads/{pid}/{p.name}")


def dong_goi_bytes():
    """Gói dự án hiện tại (trạng thái đã lưu + các file bản vẽ) dưới dạng bytes, hoặc None nếu chưa có bản vẽ."""
    tt = doc_trang_thai()
    if not ids_trong(tt):
        return None
    bo_nho = io.BytesIO()
    with zipfile.ZipFile(bo_nho, "w", zipfile.ZIP_DEFLATED) as z:
        _ghi_zip(z, tt)
    return bo_nho.getvalue()


def tao_backup(loai="tu_dong"):
    tt = doc_trang_thai()
    if not ids_trong(tt):
        return None
    THU_MUC_BACKUP.mkdir(parents=True, exist_ok=True)
    goc = f"AZB_{time.strftime('%Y%m%d_%H%M%S')}"
    duong, so = THU_MUC_BACKUP / f"{goc}_{loai}.zip", 1
    while duong.exists():
        so += 1
        duong = THU_MUC_BACKUP / f"{goc}_{so}_{loai}.zip"
    tam = duong.with_name(duong.name + ".tmp")
    with zipfile.ZipFile(tam, "w", zipfile.ZIP_DEFLATED) as z:
        _ghi_zip(z, tt)
    tam.replace(duong)
    if loai == "tu_dong" and _trung_ban_truoc(duong):
        duong.unlink()          # không có gì mới so với bản tự động trước: không giữ thêm bản trùng
        log.info("Bỏ bản sao lưu tự động vì giống hệt bản trước (%s)", duong.name)
        gan = max(THU_MUC_BACKUP.glob("AZB_*_tu_dong.zip"), key=lambda p: p.stat().st_mtime)
        return _thong_tin_backup(gan)
    _don_backup()
    log.info("Đã sao lưu %s (%.1f MB)", duong.name, duong.stat().st_size / 1048576)
    return _thong_tin_backup(duong)


def _dau_van_tay(p):
    """Danh sách (tên, CRC, kích thước) trong gói zip: so được hai gói mà không giải nén."""
    with zipfile.ZipFile(p) as z:
        return sorted((i.filename, i.CRC, i.file_size) for i in z.infolist())


def _trung_ban_truoc(moi):
    cu = sorted((p for p in THU_MUC_BACKUP.glob("AZB_*_tu_dong.zip") if p != moi and MAU_TEN_BACKUP.fullmatch(p.name)),
                key=lambda p: p.stat().st_mtime, reverse=True)
    if not cu:
        return False
    try:
        return _dau_van_tay(cu[0]) == _dau_van_tay(moi)
    except (zipfile.BadZipFile, OSError):
        return False


def _loai_cua(ten):
    return re.sub(r"^AZB_\d{8}_\d{6}(_\d+)?_", "", ten)[:-4]


def _don_backup():
    ds = sorted((p for p in THU_MUC_BACKUP.glob("AZB_*.zip") if MAU_TEN_BACKUP.fullmatch(p.name)),
                key=lambda p: p.stat().st_mtime, reverse=True)
    tu_dong = [p for p in ds if _loai_cua(p.name) == "tu_dong"]
    khac = [p for p in ds if _loai_cua(p.name) != "tu_dong"]
    for p in tu_dong[SO_BACKUP_TU_DONG:] + khac[SO_BACKUP_KHAC:]:
        try:
            p.unlink()
        except OSError:
            pass
    # Giới hạn tổng dung lượng: xóa bản cũ nhất, bản tự động trước, luôn giữ bản mới nhất mỗi loại
    con = [p for p in ds if p.exists()]
    tong = sum(p.stat().st_size for p in con)
    if tong <= DUNG_LUONG_BACKUP_TOI_DA:
        return
    giu = {next((p for p in con if _loai_cua(p.name) == "tu_dong"), None), next((p for p in con if _loai_cua(p.name) != "tu_dong"), None)}
    xoa = [p for p in reversed(con) if _loai_cua(p.name) == "tu_dong"] + [p for p in reversed(con) if _loai_cua(p.name) != "tu_dong"]
    for p in xoa:
        if tong <= DUNG_LUONG_BACKUP_TOI_DA:
            break
        if p in giu:
            continue
        try:
            tong -= p.stat().st_size
            p.unlink()
            log.warning("Thư mục sao lưu vượt %d MB, đã xóa bản cũ %s", DUNG_LUONG_BACKUP_TOI_DA // 1048576, p.name)
        except OSError:
            pass


def _thong_tin_backup(p):
    st = p.stat()
    loai = _loai_cua(p.name)
    return {"ten": p.name, "loai": NHAN_LOAI.get(loai, loai), "thoi_gian": time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(st.st_mtime)),
            "mb": round(st.st_size / 1048576, 1)}


def liet_ke_backup():
    if not THU_MUC_BACKUP.is_dir():
        return []
    ds = sorted((p for p in THU_MUC_BACKUP.glob("AZB_*.zip") if MAU_TEN_BACKUP.fullmatch(p.name)),
                key=lambda p: p.stat().st_mtime, reverse=True)
    return [_thong_tin_backup(p) for p in ds]


def duong_dan_backup(ten):
    if not isinstance(ten, str) or not MAU_TEN_BACKUP.fullmatch(ten):
        raise ValueError("Tên bản sao lưu không hợp lệ.")
    p = THU_MUC_BACKUP / ten
    if not p.is_file():
        raise ValueError("Bản sao lưu này không còn nữa.")
    return p


def can_sao_luu_tu_dong(cu, moi):
    """Tự sao lưu khi danh sách bản vẽ đổi, hoặc đã lâu chưa có bản tự động nào."""
    ids_moi = ids_trong(moi)
    if not ids_moi:
        return False
    if ids_trong(cu) != ids_moi:
        return True
    gan_nhat = max((p.stat().st_mtime for p in THU_MUC_BACKUP.glob("AZB_*_tu_dong.zip")), default=0) if THU_MUC_BACKUP.is_dir() else 0
    return time.time() - gan_nhat > GIAN_CACH_TU_DONG


def nap_tu_zip(nguon):
    """Giải gói dự án vào data/uploads, trả về trạng thái (id bản vẽ đã đổi nếu bị trùng mã). Chưa ghi trạng thái."""
    with zipfile.ZipFile(nguon) as z:
        if "trang_thai.json" not in z.namelist():
            raise ValueError("Đây không phải gói dự án AZB (thiếu trang_thai.json).")
        tt = json.loads(z.read("trang_thai.json").decode("utf-8"))
        if not isinstance(tt, dict):
            raise ValueError("trang_thai.json không hợp lệ.")
        if sum(i.file_size for i in z.infolist()) > DUNG_LUONG_TOI_DA:
            raise ValueError("Gói quá lớn (trên 2 GB).")
        nhom = {}
        for i in z.infolist():
            if i.is_dir():
                continue
            phan = PurePosixPath(i.filename).parts
            if len(phan) != 3 or phan[0] != "uploads" or not MAU_PID.fullmatch(phan[1]):
                continue
            ten = phan[2]
            if ten in (".", "..") or "\\" in ten or ":" in ten:
                continue
            if ten != TEN_META and Path(ten).suffix.lower() not in DUOI_TRONG_GOI:
                continue
            nhom.setdefault(phan[1], []).append((ten, i))
        anh_xa = {}
        for pid, ds in nhom.items():
            thu_muc = THU_MUC_TAI_LEN / pid
            if thu_muc.is_dir():
                giong = all((thu_muc / ten).is_file() and (thu_muc / ten).stat().st_size == i.file_size
                            for ten, i in ds if ten != TEN_META)
                if giong:
                    anh_xa[pid] = pid   # đã có đúng file này trên máy, dùng lại
                    continue
                moi = uuid.uuid4().hex[:12]
            else:
                moi = pid
            dich = THU_MUC_TAI_LEN / moi
            dich.mkdir(parents=True, exist_ok=True)
            for ten, i in ds:
                (dich / ten).write_bytes(z.read(i))
            anh_xa[pid] = moi
    for khoa in ("files", "da_dong"):
        tt[khoa] = [dict(f, id=anh_xa[f.get("id")]) for f in tt.get(khoa, [])
                    if isinstance(f, dict) and f.get("id") in anh_xa]
    return tt
