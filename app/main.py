"""Web app bóc khối lượng AZB. Chạy: .venv\\Scripts\\python -m app.main  rồi mở http://127.0.0.1:8765"""
import contextlib
import io
import json
import logging
import shutil
import threading
import time
import uuid
import zipfile
from pathlib import Path

from fastapi.middleware.gzip import GZipMiddleware
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, cot_thep, ho_so_layer, kiem_tra_layer, luu_tru, nhat_ky
from .excel_thep import xuat_excel_thep
from .goi_y_hinh_hoc import do_layer_tuong
from .tach_mat_bang import do_mat_bang
from .dxf_reader import _doc_file, cat_vung, doc_ban_ve, doc_ban_ve_cache, hinh_xem, nap_doc, tom_tat_layer, tong_quan
from . import cong_cu, he_quy_chieu
from .bang_boc import xuat_excel as xuat_excel_bang_boc
from .chon_doi_tuong import boc_chon
from .thong_ke import thong_ke, xuat_excel as xuat_excel_thong_ke
from .excel_io import doi_chieu, xuat_excel
from .excel_ong_gio import xuat_excel_ong_gio
from .gan_nhan import gan_nhan, ve_nhan_vao_dxf
from .mep import doc_mep
from .ong_gio import boc_ong_gio
from .pdf_reader import pdf_sang_dxf
from .quet_chon import quet_chi_tiet, quet_mat_bang
from .takeoff import boc_khoi_luong, thong_so_mac_dinh

THU_MUC_TAI_LEN = config.DATA_DIR / "uploads"
STATIC = Path(__file__).parent / "static"

log = logging.getLogger("azb.main")


@contextlib.asynccontextmanager
async def _vong_doi(_app):
    nhat_ky.bat()            # chỉ khi server chạy thật; test không chạy lifespan nên không ghi vào data/ thật
    nhat_ky.ghi_khoi_dong()
    yield


app = FastAPI(title="AZB - Bóc khối lượng", lifespan=_vong_doi)
app.add_middleware(GZipMiddleware, minimum_size=1024, compresslevel=3)  # JSON hình học của bản vẽ nặng rất lớn, nén lại cho tải nhanh (nhất là qua tunnel)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


@app.middleware("http")
async def _khong_nho_dem_giao_dien(request: Request, call_next):
    """Trang và script giao diện luôn tải bản mới, tránh trình duyệt giữ bản cũ sau khi cập nhật."""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.middleware("http")
async def _ghi_nhat_ky(request: Request, call_next):
    """Ghi lại lỗi và yêu cầu chậm. Lỗi không lường trước trả về mã lỗi ngắn để tra trong nhật ký, không lộ traceback ra giao diện."""
    t0 = time.time()
    try:
        r = await call_next(request)
    except Exception:
        ma = nhat_ky.ma_loi()
        log.exception("[%s] Lỗi không lường trước ở %s %s", ma, request.method, request.url.path)
        return JSONResponse({"detail": f"Có lỗi bên trong phần mềm (mã {ma}). Sếp gửi mã này kèm file data/logs/azb.log để tra lỗi."}, status_code=500)
    dt = time.time() - t0
    if request.url.path.startswith("/api/"):
        if r.status_code >= 500:
            log.error("%s %s -> %s (%.1fs)", request.method, request.url.path, r.status_code, dt)
        elif r.status_code >= 400:
            log.warning("%s %s -> %s (%.1fs)", request.method, request.url.path, r.status_code, dt)
        elif dt >= nhat_ky.CHAM_GIAY:
            log.info("Chậm: %s %s mất %.1fs", request.method, request.url.path, dt)
    return r


@app.get("/api/nhat-ky", response_class=PlainTextResponse)
def xem_nhat_ky(dong: int = 200):
    """Các dòng cuối của nhật ký hoạt động (data/logs/azb.log)."""
    return chr(10).join(nhat_ky.doc_duoi(max(1, min(dong, 2000)))) or "Nhật ký trống."

PHIEN = {}  # id -> {"ban_ve": BanVe, "kq": dict}
_khoa_doc = threading.Lock()


class YeuCauTinh(BaseModel):
    id: str
    loai_layer: dict
    thong_so: dict = {}
    dieu_chinh: dict = {}
    du_an: str = ""
    vung: list = []  # [x0, y0, x1, y1] mét; rỗng = lấy cả bản vẽ


def _phien(pid):
    """Lấy bản vẽ đang mở. Nếu server vừa khởi động lại thì đọc lại từ file đã lưu trong data/uploads."""
    if pid not in PHIEN:
        try:
            duong_dan = luu_tru.tim_file(pid)
        except ValueError:
            raise HTTPException(404, "Mã bản vẽ không hợp lệ.")
        if duong_dan is None:
            raise HTTPException(404, "Không còn file bản vẽ này trên máy, Sếp tải lên lại.")
        don_vi = luu_tru.doc_meta(pid).get("don_vi", "auto")
        with _khoa_doc:  # 2 request cùng lúc (thông tin + hình) chỉ đọc file 1 lần
            if pid not in PHIEN:
                try:
                    bv = doc_ban_ve_cache(duong_dan, config.app_config().get("oda_path"), don_vi,
                                          luu_tru.file_cache(pid))
                except RuntimeError as ex:
                    raise HTTPException(400, str(ex))
                except Exception as ex:
                    log.exception("Lỗi khi đọc lại bản vẽ %s", pid)
                    raise HTTPException(400, f"Không đọc lại được bản vẽ: {ex}")
                PHIEN[pid] = {"ban_ve": bv, "kq": None}
    return PHIEN[pid]


def _thong_tin_ban_ve(pid, ten, bv):
    layers = tom_tat_layer(bv)
    for l in layers:
        l["goi_y"] = config.goi_y_loai_layer(l["ten"])
        l["goi_y_ly_do"] = config.phan_tich_ten(l["ten"])[2]
    # Tên layer không cho biết gì: dò theo hình học (cặp nét song song = hai mặt tường)
    chua_ro = {l["ten"] for l in layers if config.phan_tich_ten(l["ten"])[0] is None}
    da_co_tuong = any(l["goi_y"] == "tuong" for l in layers)   # đã có layer tường theo tên thì không đoán thêm theo hình học
    for ten, dai in ({} if da_co_tuong else do_layer_tuong(bv, bo_qua={l["ten"] for l in layers} - chua_ro)).items():
        for l in layers:
            if l["ten"] == ten:
                l["goi_y"] = "tuong"
                l["goi_y_ly_do"] = f"Có nhiều cặp nét song song cách nhau 8 đến 45 cm (tổng {dai:.0f} m), thường là hai mặt tường"
    meta = luu_tru.doc_meta(pid)
    return {
        "id": pid, "ten_file": ten, "don_vi": bv.don_vi, "canh_bao": list(meta.get("canh_bao_nguon", [])) + list(bv.canh_bao),
        "so_trang_pdf": meta.get("so_trang_pdf", 0), "trang_pdf": meta.get("trang_pdf", 0), "layers": layers,
        "mac_dinh": thong_so_mac_dinh(), "loai_hop_le": config.LOAI_CAU_KIEN,
    }


class FileThongKe(BaseModel):
    id: str
    vai_tro: str = "mat_bang"  # mat_bang | chi_tiet | ghi_chu
    loai_layer: dict = {}
    vung: list = []


class YeuCauThongKe(BaseModel):
    files: list[FileThongKe]
    du_an: str = ""


@app.get("/")
def trang_chu():
    return FileResponse(STATIC / "cad.html")


@app.get("/cu")
def trang_cu():
    """Giao diện cũ (một bản vẽ một lần)."""
    return FileResponse(STATIC / "index.html")


TAI_LEN_TOI_DA = 300 * 1024 ** 2   # byte: file bản vẽ lớn hơn mức này bị từ chối (tránh treo máy); đổi bằng 'tai_len_toi_da_mb' trong config/app.yaml


def _luu_co_gioi_han(nguon, duong_dan):
    """Ghi từng khối xuống đĩa, quá giới hạn thì dừng và báo lỗi (không đọc cả file vào bộ nhớ)."""
    toi_da = int(config.app_config().get("tai_len_toi_da_mb") or 0) * 1024 ** 2 or TAI_LEN_TOI_DA
    tong = 0
    with open(duong_dan, "wb") as out:
        while True:
            khoi = nguon.read(1024 * 1024)
            if not khoi:
                break
            tong += len(khoi)
            if tong > toi_da:
                raise HTTPException(413, f"File quá lớn (giới hạn {toi_da // 1024 ** 2} MB). Tách bản vẽ nhỏ hơn, hoặc tăng 'tai_len_toi_da_mb' trong config/app.yaml.")
            out.write(khoi)


@app.post("/api/tai-len")
def tai_len(file: UploadFile = File(...), don_vi: str = Form("auto"), trang: int = Form(1), ty_le: int = Form(0)):
    """Nhận .dxf/.dwg, hoặc .pdf (còn nét vector): PDF được đổi 1 trang thành DXF (mm thực tế) rồi đọc như DXF.
    trang: trang PDF cần lấy (từ 1). ty_le: mẫu số tỷ lệ PDF (100 = 1/100), 0 = tự đọc từ chữ TL trong bản vẽ."""
    ten = Path(file.filename or "").name
    duoi = Path(ten).suffix.lower()
    if duoi not in (".dxf", ".dwg", ".pdf"):
        raise HTTPException(400, "Chỉ nhận file .dxf, .dwg hoặc .pdf")
    pid = uuid.uuid4().hex[:12]
    thu_muc = THU_MUC_TAI_LEN / pid
    thu_muc.mkdir(parents=True, exist_ok=True)
    duong_dan = thu_muc / ten
    try:
        _luu_co_gioi_han(file.file, duong_dan)
    except HTTPException:
        shutil.rmtree(thu_muc, ignore_errors=True)
        raise
    them = {}
    canh_bao_pdf = []
    try:
        if duoi == ".pdf":
            ten_dxf = f"{Path(ten).stem}_t{trang}.dxf" if trang > 1 else f"{Path(ten).stem}.dxf"
            kq_pdf = pdf_sang_dxf(duong_dan, thu_muc / ten_dxf, trang, ty_le or None)
            canh_bao_pdf = kq_pdf["canh_bao"]
            them = {"nguon_pdf": ten, "trang_pdf": trang, "so_trang_pdf": kq_pdf["so_trang"],
                    "ty_le_pdf": kq_pdf["ty_le"], "canh_bao_nguon": canh_bao_pdf}
            ten, duong_dan, don_vi = ten_dxf, thu_muc / ten_dxf, "mm"
        bv = doc_ban_ve_cache(duong_dan, config.app_config().get("oda_path"), don_vi, luu_tru.file_cache(pid))
    except RuntimeError as ex:
        shutil.rmtree(thu_muc, ignore_errors=True)  # file không đọc được thì không giữ lại
        log.warning("Không đọc được %s: %s", ten, ex)
        raise HTTPException(400, str(ex))
    except Exception as ex:
        shutil.rmtree(thu_muc, ignore_errors=True)
        log.exception("Lỗi khi đọc bản vẽ %s", ten)
        raise HTTPException(400, f"Không đọc được bản vẽ: {ex}")
    log.info("Đã tải lên %s (%d layer, đơn vị %s)", ten, len(bv.layers), bv.don_vi)
    luu_tru.ghi_meta(pid, ten, don_vi, **them)  # để nạp lại được sau khi tải lại trang hoặc khởi động lại server
    PHIEN[pid] = {"ban_ve": bv, "kq": None}
    return _thong_tin_ban_ve(pid, ten, bv)


@app.get("/api/ban-ve/{pid}")
def thong_tin_ban_ve(pid: str, mo: int = 0):
    """Thông tin bản vẽ đã tải lên (dùng khi tải lại trang). mo=1: người dùng vừa chủ động mở file này."""
    p = _phien(pid)
    if mo:
        luu_tru.danh_dau_da_mo(pid)
    return _thong_tin_ban_ve(pid, p["ban_ve"].ten_file, p["ban_ve"])


@app.get("/api/ban-ve")
def ds_ban_ve_da_tai():
    """Các bản vẽ đã tải lên và còn trong ổ đĩa (kể cả bản đã đóng), để mở lại mà không phải tải lên."""
    return {"ds": luu_tru.liet_ke_ban_ve()}


@app.get("/api/de-xuat-layer/{pid}")
def de_xuat_loai_layer(pid: str):
    """AI chỉ ĐỀ XUẤT loại cho từng layer. Không ghi gì vào kết quả bóc, người dùng bấm áp dụng mới có hiệu lực."""
    from dataclasses import asdict
    return {"ds": [asdict(d) for d in _de_xuat(_phien(pid))]}


def _de_xuat(p, moi=False):
    """Phân tích layer (tên + nhãn + hình học) một lần cho mỗi phiên; hồ sơ đã nhớ thay đổi thì gọi lại với moi=True."""
    from tools.de_xuat_layer import de_xuat_layer, thong_tin_tu_ban_ve
    if moi or "de_xuat" not in p:
        p["de_xuat"] = de_xuat_layer(thong_tin_tu_ban_ve(p["ban_ve"]))
    return p["de_xuat"]


class TinhThep(BaseModel):
    dong: list[dict]
    loai_bo: list[int] = []
    id: str | None = None          # bản vẽ đã bóc bê tông, để đối chiếu hàm lượng kg/m³
    du_an: str = ""
    nguon: str = ""
    canh_bao_doc: list[str] = []


def _bt_da_boc(pid):
    """Tổng bê tông kết cấu đã bóc (m³) của bản vẽ, không tính lót; None nếu chưa bấm Tính khối lượng."""
    p = PHIEN.get(pid) if pid else None
    if not p or not p.get("kq"):
        return None
    v = sum(t["khoi_luong"] for t in p["kq"].get("tong_hop", []) if t["ma"].startswith("be_tong_") and "lot" not in t["ma"])
    return v or None


@app.post("/api/cot-thep/doc-file")
async def thep_doc_file(file: UploadFile = File(...), sheet: str = Form("")):
    """Đọc bảng thống kê thép từ Excel / CSV. Chỉ đọc, chưa tính."""
    try:
        kq = cot_thep.doc_excel_csv(await file.read(), file.filename or "", sheet or None)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    log.info("Đọc bảng thép từ %s: %d dòng, %d cảnh báo", file.filename, len(kq["dong"]), len(kq["canh_bao"]))
    return kq


class DocThepCad(BaseModel):
    id: str
    khung: list[float]


@app.post("/api/cot-thep/doc-cad")
def thep_doc_cad(yc: DocThepCad):
    """Đọc bảng thép dựng bằng chữ trong bản vẽ, trong khung người dùng kéo."""
    if len(yc.khung) != 4:
        raise HTTPException(400, "Khung phải có 4 số: x0, y0, x1, y1 (mét).")
    kq = cot_thep.doc_bang_cad(_phien(yc.id)["ban_ve"], yc.khung)
    log.info("Đọc bảng thép từ CAD %s: %d dòng", yc.id, len(kq["dong"]))
    return kq


@app.post("/api/cot-thep/tinh")
def thep_tinh(yc: TinhThep):
    return cot_thep.tinh(yc.dong, yc.loai_bo, _bt_da_boc(yc.id))


@app.post("/api/cot-thep/xuat-excel")
def thep_xuat_excel(yc: TinhThep):
    kq = cot_thep.tinh(yc.dong, yc.loai_bo, _bt_da_boc(yc.id))
    kq["canh_bao_doc"] = yc.canh_bao_doc
    if not kq["dong"]:
        raise HTTPException(400, "Chưa có dòng thép nào để xuất.")
    return Response(xuat_excel_thep(kq, yc.du_an, yc.nguon),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="cot_thep_theo_bang_thong_ke.xlsx"'})


class TachMatBang(BaseModel):
    id: str
    khoang_cach: float | None = None


@app.post("/api/tach-mat-bang")
def tach_mat_bang(yc: TachMatBang):
    """Đề xuất các vùng (mặt bằng, chi tiết, bảng) trong một file. Chỉ đề xuất: không sửa gì, người dùng bấm tạo mới có hiệu lực."""
    return do_mat_bang(_phien(yc.id)["ban_ve"], yc.khoang_cach)


class KiemTraLayer(BaseModel):
    id: str
    loai_layer: dict


@app.post("/api/kiem-tra-layer")
def kiem_tra_gan(yc: KiemTraLayer):
    """Cổng kiểm tra gán layer, gọi được bất cứ lúc nào (không cần bấm Tính)."""
    p = _phien(yc.id)
    return {"ds": kiem_tra_layer.kiem_tra_gan_layer(p["ban_ve"], yc.loai_layer, _de_xuat(p)),
            "chuan_3d": kiem_tra_layer.kiem_tra_chuan_3d(p["ban_ve"], yc.loai_layer)}


class NhoLayer(BaseModel):
    ds: list[dict]


@app.post("/api/layer-map/nho")
def nho_loai_layer(yc: NhoLayer):
    """Ghi nhớ loại layer do người dùng chọn tay vào hồ sơ layer (data/ho_so_layer.yaml, xem / xóa được).
    Tên mơ hồ như '0', '1', '100' không được nhớ vì mỗi bản vẽ dùng chúng cho việc khác nhau."""
    them, bo = ho_so_layer.nho(yc.ds)
    for p in PHIEN.values():
        p.pop("de_xuat", None)
    return {"them": them, "bo_qua_vi_mo_ho": bo}


@app.get("/api/ho-so-layer")
def ds_ho_so_layer():
    return {"ds": [{"khoa": k, "loai": v} for k, v in sorted(ho_so_layer.doc().items())]}


@app.delete("/api/ho-so-layer")
def xoa_ho_so_layer(khoa: str):
    ok = ho_so_layer.xoa(khoa)
    for p in PHIEN.values():
        p.pop("de_xuat", None)
    return {"da_xoa": ok}


@app.delete("/api/ban-ve/{pid}")
def xoa_ban_ve(pid: str):
    """Xóa hẳn file bản vẽ khỏi ổ đĩa. Trước khi xóa, tự sao lưu để còn khôi phục được."""
    try:
        luu_tru.thu_muc_ban_ve(pid)
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    if pid in luu_tru.ids_trong(luu_tru.doc_trang_thai()):
        luu_tru.tao_backup("truoc_xoa")
    PHIEN.pop(pid, None)
    da_xoa = luu_tru.xoa_ban_ve(pid)
    luu_tru.bo_khoi_da_dong(pid)
    return {"da_xoa": da_xoa}


# ---------- Dự án: trạng thái làm việc, sao lưu, gói .zip ----------
@app.get("/api/du-an/trang-thai")
def doc_trang_thai():
    return {"trang_thai": luu_tru.doc_trang_thai()}


@app.post("/api/du-an/trang-thai")
async def luu_trang_thai(request: Request, nen: BackgroundTasks):
    try:
        tt = await request.json()
    except Exception:
        raise HTTPException(400, "Trạng thái gửi lên không phải JSON.")
    if not isinstance(tt, dict) or not isinstance(tt.get("files", []), list):
        raise HTTPException(400, "Trạng thái không hợp lệ.")
    cu = luu_tru.doc_trang_thai()
    luu_tru.ghi_trang_thai(tt)
    if luu_tru.can_sao_luu_tu_dong(cu, tt):
        nen.add_task(luu_tru.tao_backup, "tu_dong")
    return {"ok": True, "luc": time.strftime("%H:%M:%S")}


@app.get("/api/du-an/sao-luu")
def ds_sao_luu():
    return {"ds": luu_tru.liet_ke_backup()}


@app.post("/api/du-an/sao-luu")
def sao_luu_ngay():
    kq = luu_tru.tao_backup("thu_cong")
    if kq is None:
        raise HTTPException(400, "Chưa có bản vẽ nào để sao lưu.")
    return kq


@app.get("/api/du-an/xuat-goi")
def xuat_goi():
    du_lieu = luu_tru.dong_goi_bytes()
    if du_lieu is None:
        raise HTTPException(400, "Chưa có bản vẽ nào để xuất gói.")
    ten = time.strftime("AZB_du_an_%Y%m%d_%H%M.zip")
    return Response(du_lieu, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{ten}"'})


def _thay_du_an(nap):
    """Thay dự án hiện tại bằng dự án nạp từ gói. Dự án cũ được sao lưu trước."""
    luu_tru.tao_backup("truoc_khoi_phuc")
    try:
        moi = nap()
    except (ValueError, zipfile.BadZipFile, json.JSONDecodeError, KeyError) as ex:
        raise HTTPException(400, f"Không đọc được gói dự án: {ex}")
    luu_tru.ghi_trang_thai(moi)
    # Không tự xóa file của dự án cũ: chúng vẫn nằm trong data/uploads và mở lại được từ "Bản vẽ đã tải".
    return {"trang_thai": moi}


@app.post("/api/du-an/nhap-goi")
def nhap_goi(file: UploadFile = File(...)):
    du_lieu = file.file.read()
    return _thay_du_an(lambda: luu_tru.nap_tu_zip(io.BytesIO(du_lieu)))


class YeuCauKhoiPhuc(BaseModel):
    ten: str


@app.post("/api/du-an/khoi-phuc")
def khoi_phuc_sao_luu(yc: YeuCauKhoiPhuc):
    try:
        du_lieu = luu_tru.duong_dan_backup(yc.ten).read_bytes()  # đọc trước, phòng khi việc dọn bản cũ xóa mất nó
    except ValueError as ex:
        raise HTTPException(400, str(ex))
    return _thay_du_an(lambda: luu_tru.nap_tu_zip(io.BytesIO(du_lieu)))



# ---------- Hệ quy chiếu dự án: lưới trục chuẩn, điểm gốc, bảng tầng ----------
class YeuCauDoTruc(BaseModel):
    id: str
    vung: list = []        # [x0, y0, x1, y1] mét; rỗng = cả bản vẽ
    layer_truc: list = []  # layer người dùng chọn làm layer trục; rỗng = tự nhận theo tên


@app.post("/api/he-quy-chieu/do-truc")
def do_truc_api(yc: YeuCauDoTruc):
    """Chỉ ĐỀ XUẤT lưới trục (đường + tên đọc từ bong bóng). Người dùng xem lại, sửa rồi mới lưu."""
    bv = _phien(yc.id)["ban_ve"]
    vung = [float(v) for v in yc.vung] if len(yc.vung) == 4 else None
    kq = he_quy_chieu.do_luoi_truc(bv, vung, yc.layer_truc)
    kq["cao_do_goi_y"] = he_quy_chieu.cao_do_goi_y(bv)
    kq["layer_co_san"] = sorted(bv.layers)
    return kq


@app.post("/api/he-quy-chieu/kiem-tra")
async def kiem_tra_hqc_api(request: Request):
    """Chuẩn hoá và kiểm tra hệ quy chiếu đang nhập (đọc số, tính chiều cao tầng, góc quay, cảnh báo)."""
    try:
        hqc = await request.json()
    except Exception:
        raise HTTPException(400, "Dữ liệu gửi lên không phải JSON.")
    if not isinstance(hqc, dict):
        raise HTTPException(400, "Hệ quy chiếu không hợp lệ.")
    try:
        return he_quy_chieu.kiem_tra(hqc)
    except (KeyError, TypeError, ValueError) as ex:
        raise HTTPException(400, f"Hệ quy chiếu không hợp lệ: {ex}")



class YeuCauVung(BaseModel):
    id: str
    vung: list = []            # khung vùng trên bản vẽ (mét); rỗng = cả bản vẽ
    hqc: dict = {}             # hệ quy chiếu đang nhập (lưới, gốc, bảng tầng)
    diem: dict | None = None   # giao trục chuẩn mà điểm A của vùng nằm trên
    goc_local: list | None = None
    diem_b: dict | None = None
    goc_local_b: list | None = None
    luoi_local: dict | None = None


def _hqc_hop_le(hqc):
    try:
        return he_quy_chieu.kiem_tra(hqc)
    except (KeyError, TypeError, ValueError) as ex:
        raise HTTPException(400, f"Hệ quy chiếu không hợp lệ: {ex}")


@app.post("/api/he-quy-chieu/goi-y-vung")
def goi_y_vung_api(yc: YeuCauVung):
    """ĐỀ XUẤT điểm căn của một vùng mặt bằng: dò trục trong vùng, tìm trục trùng tên với lưới chuẩn."""
    bv = _phien(yc.id)["ban_ve"]
    vung = [float(v) for v in yc.vung] if len(yc.vung) == 4 else None
    return he_quy_chieu.goi_y_diem_vung(bv, vung, _hqc_hop_le(yc.hqc))


@app.post("/api/he-quy-chieu/can-vung")
def can_vung_api(yc: YeuCauVung):
    """Tính phép dời (và xoay nếu có điểm B) đưa vùng về lưới chuẩn, kiểm tra chéo bằng vị trí trục."""
    return he_quy_chieu.tinh_can_vung(_hqc_hop_le(yc.hqc), yc.diem, yc.goc_local, yc.diem_b, yc.goc_local_b, yc.luoi_local)


class YeuCauGanVung(BaseModel):
    hqc: dict = {}
    ds: list = []   # mỗi vùng: {ten, tang, cau_kien, xac_nhan, can}


@app.post("/api/he-quy-chieu/kiem-tra-gan-vung")
def kiem_tra_gan_vung_api(yc: YeuCauGanVung):
    return he_quy_chieu.kiem_tra_gan_vung(yc.ds, _hqc_hop_le(yc.hqc))

def _tinh(yc):
    t0 = time.time()
    p = _phien(yc.id)
    bv = p["ban_ve"]
    if len(yc.vung) == 4:
        bv = cat_vung(bv, [float(v) for v in yc.vung])
    kq = boc_khoi_luong(bv, yc.loai_layer, yc.thong_so, yc.dieu_chinh, p["ban_ve"])
    # Cổng kiểm tra gán layer: báo trước những chỗ có vẻ gán sai, vì đây là nguồn sai số lớn nhất mà không tự báo lỗi
    try:
        canh = [f"Gán layer: {x['noi_dung']}" for x in kiem_tra_layer.kiem_tra_gan_layer(p["ban_ve"], yc.loai_layer, _de_xuat(p))
                if x["muc"] == "canh_bao"]
    except Exception:  # phân tích phụ không được làm hỏng việc tính
        canh = []
    kq["canh_bao_chung"] = canh + [f"Kiểm tra số liệu: {x}" for x in kiem_tra_layer.kiem_tra_ket_qua(kq)] + kq["canh_bao_chung"]
    try:  # thông số cọc đọc từ bảng thống kê / ghi chú trên toàn bản vẽ (bảng thường nằm ngoài vùng đang tính), dùng để dựng cọc 3D đúng chiều dài
        from .gan_nhan import _bang_coc
        dk, dai = _bang_coc(p["ban_ve"])
        kq["coc_bang"] = {"d_mm": dk, "l_m": dai}
    except Exception:
        kq["coc_bang"] = {"d_mm": None, "l_m": None}
    p["kq"] = kq
    log.info("Tính %s: %d cấu kiện, %d cảnh báo chung, %.1fs", bv.ten_file, len(kq["cau_kien"]), len(kq["canh_bao_chung"]), time.time() - t0)
    return kq


def _du_lieu_thong_ke(yc):
    kq = []
    for f in yc.files:
        p = _phien(f.id)
        kq.append({"id": f.id, "ten_file": p["ban_ve"].ten_file, "vai_tro": f.vai_tro,
                   "loai_layer": f.loai_layer, "vung": f.vung, "ban_ve": p["ban_ve"]})
    return kq


@app.post("/api/thong-ke")
def thong_ke_api(yc: YeuCauThongKe):
    return thong_ke(_du_lieu_thong_ke(yc))


@app.post("/api/xuat-thong-ke")
def xuat_thong_ke(yc: YeuCauThongKe):
    du_lieu = xuat_excel_thong_ke(thong_ke(_du_lieu_thong_ke(yc)), yc.du_an)
    return Response(
        du_lieu,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="thong_ke_cau_kien.xlsx"'},
    )


class YeuCauBangBoc(BaseModel):
    dong: list
    du_an: str = ""


@app.post("/api/xuat-bang-boc")
def xuat_bang_boc(yc: YeuCauBangBoc):
    try:
        du_lieu = xuat_excel_bang_boc(yc.dong, yc.du_an)
    except (ValueError, KeyError, TypeError) as ex:
        raise HTTPException(400, f"Dữ liệu bảng bóc không hợp lệ: {ex}")
    return Response(
        du_lieu,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="bang_boc_doi_tuong.xlsx"'},
    )


# ---------- Công cụ tính theo cấu kiện (đào đất, móng, đà kiềng, cột...) ----------
class YeuCauQuet(BaseModel):
    id: str
    cong_cu: str = "khac"
    khung: list  # [x0, y0, x1, y1] mét
    chon: dict = {}
    vung: list = []  # Vùng (m) đã chọn ở thanh trên; có thì chỉ lấy hình trong vùng


class YeuCauCongThuc(BaseModel):
    tham_so: dict = {}
    cong_thuc: list


class YeuCauTinhCongCu(YeuCauCongThuc):
    nhom: list


def _cong_cu(ma):
    for d in cong_cu.danh_sach():
        if d["ma"] == ma:
            return d
    raise HTTPException(404, f"Không có công cụ '{ma}'.")


@app.get("/api/cong-cu")
def ds_cong_cu():
    return {"cong_cu": cong_cu.danh_sach(), "don_vi": cong_cu.DON_VI_HOP_LE, "bien": cong_cu.BIEN_CO_BAN}


@app.put("/api/cong-cu/{ma}")
def luu_cong_cu(ma: str, yc: YeuCauCongThuc):
    _cong_cu(ma)
    try:
        return cong_cu.luu_tuy_chinh(ma, yc.tham_so, yc.cong_thuc)
    except ValueError as ex:
        raise HTTPException(400, str(ex))


@app.delete("/api/cong-cu/{ma}")
def khoi_phuc_cong_cu(ma: str):
    _cong_cu(ma)
    return cong_cu.khoi_phuc(ma)


@app.post("/api/cong-cu/tinh")
def tinh_cong_cu(yc: YeuCauTinhCongCu):
    try:
        return cong_cu.tinh(yc.tham_so, yc.cong_thuc, yc.nhom)
    except ValueError as ex:
        raise HTTPException(400, str(ex))


@app.post("/api/cong-cu/mat-bang")
def quet_mat_bang_api(yc: YeuCauQuet):
    if len(yc.khung) != 4:
        raise HTTPException(400, "Thiếu khung quét chọn.")
    cc = _cong_cu(yc.cong_cu)
    return quet_mat_bang(_phien(yc.id)["ban_ve"], yc.chon, [float(v) for v in yc.khung], cc["nguon"],
                         [float(v) for v in yc.vung] if len(yc.vung) == 4 else None)


@app.post("/api/cong-cu/chi-tiet")
def quet_chi_tiet_api(yc: YeuCauQuet):
    if len(yc.khung) != 4:
        raise HTTPException(400, "Thiếu khung quét chọn.")
    return quet_chi_tiet(_phien(yc.id)["ban_ve"], [float(v) for v in yc.khung])


# ---------- Tự gán nhãn lên mặt bằng chưa có chữ ----------
class YeuCauGanNhan(BaseModel):
    id: str
    khung: list  # [x0, y0, x1, y1] mét, vùng một mặt bằng
    loai_layer: dict = {}
    ty_le: int | None = None
    tang: str | None = None
    tien_to: str | None = None
    cao_dam: dict = {}
    sua: dict = {}  # chỉnh sửa tay từng nhãn: {doi, xoa, them}
    kt_mong: dict = {}  # {"M7": {"a": 600, "b": 600, "h": 800}} sếp chỉnh kích thước từng loại móng
    nhan_dam: bool = True
    nhan_truc: bool = True
    nhan_cot: bool = False
    nhan_mong: bool = True
    nhan_coc: bool = True
    nhan_san: bool = True
    ds: list = []  # xuất DXF nhiều mặt bằng: mỗi phần tử {khung, ty_le, tang, tien_to, cao_dam, nhan_*}


def _gan_nhan(yc):
    tc = yc.model_dump(exclude={"id", "khung", "loai_layer", "ds"})
    try:
        return gan_nhan(_phien(yc.id)["ban_ve"], yc.loai_layer, [float(v) for v in yc.khung], tc)
    except ValueError as ex:
        raise HTTPException(400, str(ex))


@app.post("/api/gan-nhan")
def gan_nhan_api(yc: YeuCauGanNhan):
    """Chỉ ĐỀ XUẤT nhãn (tên, vị trí, góc, cỡ chữ theo tỷ lệ). Không sửa file bản vẽ."""
    return _gan_nhan(yc)


@app.post("/api/xuat-dxf-nhan")
def xuat_dxf_nhan(yc: YeuCauGanNhan):
    """Bản sao DXF của bản vẽ gốc kèm nhãn trên layer AZB-NHAN. File gốc trong data/uploads không bị sửa."""
    import tempfile
    p = _phien(yc.id)
    if yc.ds:  # nhiều mặt bằng: gán từng vùng rồi gộp nhãn
        kq = {"nhan": [], "bong": []}
        for d in yc.ds:
            tc = {k: v for k, v in d.items() if k != "khung"}
            try:
                r = gan_nhan(p["ban_ve"], yc.loai_layer, [float(v) for v in d.get("khung", [])], tc)
            except ValueError as ex:
                raise HTTPException(400, str(ex))
            kq["nhan"] += r["nhan"]
            kq["bong"] += r["bong"]
    else:
        kq = _gan_nhan(yc)
    try:
        doc = _doc_file(luu_tru.tim_file(yc.id), config.app_config().get("oda_path"))  # nạp bản mới, không dùng bản đang giữ
    except RuntimeError as ex:
        raise HTTPException(400, str(ex))
    ve_nhan_vao_dxf(doc, p["ban_ve"].he_so, kq)
    with tempfile.TemporaryDirectory() as td:
        tam = Path(td) / "nhan.dxf"
        doc.saveas(tam)
        du_lieu = tam.read_bytes()
    ten = Path(p["ban_ve"].ten_file).stem + "_co_nhan.dxf"
    return Response(du_lieu, media_type="application/dxf",
                    headers={"Content-Disposition": f"attachment; filename*=UTF-8''{__import__('urllib.parse').parse.quote(ten)}"})


class YeuCauChon(BaseModel):
    id: str
    chon: dict


@app.post("/api/boc-chon")
def boc_chon_api(yc: YeuCauChon):
    return boc_chon(_phien(yc.id)["ban_ve"], yc.chon)


@app.get("/api/hinh")
def hinh_ban_ve(id: str):
    # Bản vẽ nặng: dựng và mã hóa JSON hình học mất vài giây, nên giữ lại bản đã mã hóa cho các lần mở/tải lại sau
    p = _phien(id); bv = p["ban_ve"]
    cu = p.get("hinh_json")
    if not cu or cu[0] is not bv:
        cu = p["hinh_json"] = (bv, json.dumps(hinh_xem(bv), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return Response(cu[1], media_type="application/json")


@app.get("/api/tong-quan")
def tong_quan_ban_ve(id: str):
    return tong_quan(_phien(id)["ban_ve"])


@app.post("/api/tinh")
def tinh(yc: YeuCauTinh):
    return _tinh(yc)


@app.post("/api/xuat-excel")
def xuat(yc: YeuCauTinh):
    kq = _tinh(yc)
    du_lieu = xuat_excel(kq, yc.du_an)
    ten = Path(kq["ten_file"]).stem + "_khoi_luong.xlsx"
    return Response(
        du_lieu,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{ten}"'},
    )


def _tinh_ong_gio(yc):
    p = _phien(yc.id)
    try:
        nap_doc(p["ban_ve"], luu_tru.tim_file(yc.id), config.app_config().get("oda_path"))
        return boc_ong_gio(p["ban_ve"], yc.loai_layer)
    except ValueError as ex:
        raise HTTPException(400, str(ex))


@app.post("/api/ong-gio")
def ong_gio(yc: YeuCauTinh):
    return _tinh_ong_gio(yc)


@app.post("/api/mep-3d")
def mep_3d(yc: YeuCauTinh):
    """Đường ống nước, PCCC, khay cáp để dựng 3D và kiểm tra va chạm / khoét lỗ."""
    p = _phien(yc.id)
    try:
        nap_doc(p["ban_ve"], luu_tru.tim_file(yc.id), config.app_config().get("oda_path"))
        return doc_mep(p["ban_ve"], yc.loai_layer)
    except ValueError as ex:
        raise HTTPException(400, str(ex))


@app.post("/api/xuat-excel-ong-gio")
def xuat_ong_gio(yc: YeuCauTinh):
    kq = _tinh_ong_gio(yc)
    du_lieu = xuat_excel_ong_gio(kq, yc.du_an)
    ten = Path(kq["ten_file"]).stem + "_ong_gio.xlsx"
    return Response(
        du_lieu,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{ten}"'},
    )


@app.post("/api/doi-chieu")
def so_sanh(id: str = Form(...), file: UploadFile = File(...)):
    p = _phien(id)
    if not p["kq"]:
        raise HTTPException(400, "Sếp bấm Tính khối lượng trước khi đối chiếu.")
    try:
        return doi_chieu(file.file.read(), p["kq"])
    except ValueError as ex:
        raise HTTPException(400, str(ex))


if __name__ == "__main__":
    import uvicorn

    # Chỉ nghe trên máy này, không mở ra mạng. Đặt AZB_PORT để đổi cổng (bản dùng thử dùng cổng khác).
    import os

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("AZB_PORT") or 8765))
