# AZB - Công cụ bóc khối lượng kết cấu (Giai đoạn 1)

Công cụ web chạy trên máy cá nhân. Đọc mặt bằng kết cấu DWG/DXF, bóc khối lượng **bê tông và ván khuôn** của cột, dầm, sàn, vách, móng, rồi xuất Excel. Mỗi con số trong Excel là một công thức để kỹ sư dò lại được.

> Kết quả do công cụ tính. Kỹ sư phải kiểm tra, đối chiếu và ký duyệt trước khi dùng cho dự toán hoặc thanh toán.

---

## 0. Cách nhanh nhất (Windows)

1. Bấm đúp **`CAI_DAT.bat`** (một lần): tạo môi trường ảo, cài thư viện, tự dò ODA File Converter và ghi đường dẫn vào `config/app.yaml`.
2. Từ đó chỉ cần bấm đúp **`CHAY_AZB.bat`**: khởi động phần mềm và tự mở trình duyệt. Nếu phần mềm đã chạy sẵn thì chỉ mở trình duyệt. Chưa cài thì tự chạy bước 1.
3. Gặp lỗi: bấm đúp **`XEM_NHAT_KY.bat`** (mở `data/logs/azb.log`) hoặc vào `http://127.0.0.1:8765/api/nhat-ky`. Khi giao diện báo "mã lỗi xxxxxxxx", tìm mã đó trong nhật ký để thấy lỗi chi tiết.

Cần Python 3.10 trở lên (tải tại python.org, nhớ tick *Add python.exe to PATH*). Các mục 1 và 2 bên dưới là cách làm tay, tương đương.

**Vận hành:** nhật ký xoay vòng (tối đa khoảng 6 MB). Thư mục `data/backup` giữ tối đa 10 bản tự động + 20 bản khác, tổng không quá 1 GB (xóa bản cũ nhất trước), và không giữ thêm bản tự động nếu nội dung y hệt bản trước. Mã nguồn nằm trong git (`git log`); dữ liệu người dùng trong `data/` không đưa vào git, trừ bản vẽ mẫu và hai file thiết lập cá nhân (`data/cong_cu_tuy_chinh.yaml`, `data/ho_so_layer.yaml`). Các bản giao diện cũ trước đây ở `backup_ui/` lấy lại bằng `git show 58269c6:backup_ui/<tên file>`.

## 1. Cài đặt (làm một lần)

Mở **PowerShell** tại thư mục `azb-take-off` (trong File Explorer: Shift + chuột phải > Open PowerShell window here).

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

- Dòng 1 tạo "môi trường ảo" `.venv`, tức một bản Python riêng cho dự án, không ảnh hưởng máy.
- Dòng 2 cài các thư viện: `ezdxf` (đọc CAD), `pymupdf` (đọc PDF), `shapely` (tính hình học), `openpyxl` (Excel), `fastapi` + `uvicorn` (web).

**Đọc trực tiếp file DWG (tùy chọn):** cài *ODA File Converter* (miễn phí, Open Design Alliance), sau đó sửa `oda_path` trong `config/app.yaml` cho đúng đường dẫn. Nếu chưa cài, trong AutoCAD dùng lệnh `SAVEAS`, chọn định dạng DXF rồi tải file DXF lên.

## 2. Chạy

```powershell
.venv\Scripts\python -m app.main
```

Mở trình duyệt vào **http://127.0.0.1:8765**. Công cụ chỉ nhận kết nối từ chính máy này. Tắt bằng Ctrl + C.

## 3. Quy trình sử dụng

> Bản trình bày cho các phòng ban (8 bước từ DWG đến 3D, ai kiểm gì): xem [docs/QUY_TRINH_SU_DUNG.md](docs/QUY_TRINH_SU_DUNG.md) (thêm 21/11/2026).

1. **Tải bản vẽ** lên (DXF, DWG hoặc **PDF**): mỗi file là 1 mặt bằng của 1 tầng. Bản vẽ có nhiều mặt bằng thì tách ra trước.
   - **PDF** phải xuất từ CAD còn nét vector (PDF scan/ảnh không đọc được, app báo rõ). App đổi từng trang thành DXF (lưu cạnh file PDF gốc trong `data/uploads`) rồi bóc như DXF. Tỷ lệ lấy từ chữ `TL 1/xx` trong trang; không có thì nhập vào ô *Tỷ lệ PDF 1/* trước khi tải. PDF nhiều trang: app mở trang 1 rồi hỏi các trang cần mở thêm. Layer đặt theo lớp (layer) của PDF nếu có, không thì theo màu nét. Kiểm tra lại bằng một kích thước đã biết trước khi bóc.
2. **Gán layer:** công cụ tự đoán loại cấu kiện theo tên layer (`config/layer_map.yaml`), Sếp chỉnh lại nếu sai. Nhập chiều cao tầng.
3. **Tính khối lượng:** xem mặt bằng (cấu kiện viền đỏ là có cảnh báo), bảng tổng hợp và chi tiết từng cấu kiện.
4. **Điều chỉnh:** sửa h dầm, t sàn, cao cột, hoặc tick *Loại bỏ* cho từng cấu kiện, rồi bấm *Tính lại*.
5. **Xuất Excel**, gồm 4 sheet: `BANG KHOI LUONG`, `CHI TIET CAU KIEN`, `CANH BAO`, `DOI CHIEU`.
6. **Đối chiếu:** nhập khối lượng bóc thủ công vào cột F của sheet `DOI CHIEU`, lưu lại rồi tải lên mục 4. Tiêu chí đạt: sai lệch ≤ 2%.

## 3b. Công cụ tính theo cấu kiện (đào đất, móng, đà kiềng, cột, dầm, sàn, cấu kiện khác)

Cột **Công cụ tính** nằm đầu cột trái của giao diện. Mỗi công cụ có **bộ công thức chung** của cấu kiện đó và quy trình quét chọn riêng.

Các công cụ hiện có: đào đất (kèm đắp hoàn trả, đất thừa), móng, đà kiềng (kèm lót, đào rãnh), cột, dầm, sàn, **cọc, lanh tô, tường xây/trát, sàn nền, sàn mái**, cấu kiện khác. Cột, dầm, sàn, móng... đều có thêm dòng **cốt thép ước tính = thể tích bê tông × hàm lượng (kg/m³)**; hàm lượng là tham số mặc định (móng 80, đà kiềng 120, cột/dầm 150, sàn 90...), kỹ sư sửa theo bản vẽ thép hoặc thay bằng khối lượng bóc từ bảng thống kê thép. Các tham số như chiều dài cọc, cao tường, dày lót, thép nền (kg/m²) cũng chỉ là giá trị ban đầu, cần nhập đúng theo hồ sơ.

Ví dụ **Tính KL móng**:

1. **① Quét chọn mặt bằng móng:** bấm nút, kéo khung quanh mặt bằng. Công cụ đọc ký hiệu bên cạnh hoặc bên trong từng hình (M1, F2, MĐ1...), gom thành nhóm theo ký hiệu và hiện lên cả bản vẽ (màu theo loại) lẫn khi rê chuột.
2. **② Quét chọn chi tiết móng:** kéo khung trùm chi tiết (có thể ở bản vẽ khác). Công cụ đọc kích thước theo ký hiệu (`M1 1500x1500x400`, `h=400`). Số rời trong chi tiết hiện thành các nút để bấm chọn chiều cao.
3. Công thức chạy ngay trên các nhóm đã tick, ra khối lượng từng ký hiệu và tổng theo đơn vị. Bấm **Thêm vào bảng bóc** hoặc **Xuất Excel công cụ này** (mỗi con số là công thức Excel, biến nằm cùng dòng).

**Bảng tổng hợp một bảng:** sau hai bước quét chọn, công cụ đếm số lượng theo ký hiệu trên mặt bằng, lấy kích thước từ chi tiết (hoặc từ hình trên mặt bằng, chọn ở ô *Dài × rộng lấy từ*) và gom thành một bảng: STT, tên, đơn vị, SL, D, R, C, CV (chu vi), DT (diện tích), cao độ đáy/mặt, khối lượng bê tông và ván khuôn (mỗi công thức một cột). Cao độ (`-1.700`, `±0.000`...) đọc từ chi tiết; có cao độ đáy và mặt thì hiện nút gợi ý `h = mặt − đáy` để Sếp bấm dùng (không tự áp). Xuất Excel có sheet tổng hợp (khối lượng là công thức, kèm cột vị trí tọa độ) và sheet chi tiết từng công thức.

**Bấm tên để kiểm tra trên bản vẽ:** bấm tên một cấu kiện trong bảng tổng hợp (hoặc nút ⌖ ở bảng nhóm) thì các hình của nó sáng vàng trên bản vẽ và bản vẽ tự phóng tới; bấm lại để tắt. Nút *Lưu ảnh bản vẽ* lưu hình đang hiển thị để đối chiếu hoặc trình bày khi bảo vệ khối lượng.

**Hình thiếu ký hiệu:** nhóm chưa có tên hiện là `(chưa đặt tên) rộng×dài` và sáng dấu `?` trên bản vẽ. Có hai cách xếp vào cấu kiện: (a) gõ tên vào ô *Ký hiệu* của nhóm, nếu trùng tên cấu kiện đã có thì tự gộp; (b) bước **③ Chọn hình trên bản vẽ**: bấm hoặc kéo khung chọn hình (kéo khung chỉ lấy hình thuộc nhóm đang tick, nên cột nằm trong móng không bị lấy nhầm), rồi *Gán vào* một cấu kiện có sẵn hoặc *+ Tên mới*.

**Không nhầm móng với cột:** mỗi hình được phân loại theo thứ tự nhãn chữ gần nhất, rồi quan hệ hình học (hình bao quanh hình nhỏ hơn là móng, hình nhỏ nằm trong nó là cột/cổ cột), rồi tên layer. Nên cột và móng vẽ cùng layer vẫn tách đúng. Hình không đủ căn cứ được đánh dấu "chưa chắc", và Sếp đổi **Loại** của nhóm bằng ô chọn nếu công cụ phân loại sai. Hình rất nhỏ (< 0,02 m², nét chi tiết) không bị tính.

**Sửa công thức:** trong mục *Công thức chung* của từng công cụ, sửa tên hạng mục, đơn vị, biểu thức, tham số (c, H, d, tl...), thêm hoặc xóa công thức. Bấm **Lưu làm mặc định** để giữ (ghi vào `data/cong_cu_tuy_chinh.yaml`), **Khôi phục công thức gốc** để quay về `config/cong_cu.yaml`.

Biến trong biểu thức (số liệu của MỘT cái): `n` số lượng, `a` dài, `b` rộng, `h` cao/dày, `S` diện tích, `P` chu vi, `L` chiều dài; toán tử `+ - * / **`, ngoặc, hàm `min max abs sqrt round`.

## 3c. Tự gán nhãn lên mặt bằng chưa có chữ

Bản vẽ mặt bằng dầm chỉ có nét (chưa có tên dầm, tên trục) thì dùng nhóm **Gán nhãn** trên thanh công cụ:

1. Bấm **Gán nhãn tự động**, kéo khung chọn **một vùng** cần dán nhãn (nên gồm dòng tiêu đề có `TL:1/50`). App **chưa dán gì**.
   Nhân sự chọn loại của vùng đó ở tab **Gán nhãn**: **Móng / Cột / Dầm / Sàn** (có thêm Cọc; Dầm có ô *Dán thêm tên trục*), rồi bấm **Dán nhãn**. App chỉ dán đúng loại đã chọn trong đúng vùng đã chọn, không tự dán những chỗ khác. Muốn dán loại khác thì chọn vùng khác (hoặc đổi loại rồi dán lại).
2. App tự nhận diện dầm (layer đã gán *Dầm*, hoặc *Khung dầm* + *Ô trống giữa dầm*, hoặc tự dò khung chứa ô trống), đo bề rộng b, đặt tên theo hướng và loại: `1.DX1-200X400`, `1.DY1-200X400` (X = dầm chạy ngang, Y = dầm chạy đứng; dầm biên đứng trước dầm giữa), và tên trục `22aX1`, `22aY1` (X từ trái sang phải, Y từ dưới lên).
3. **Đúng tỷ lệ từng phần:** tỷ lệ đọc từ chữ `TL:1/xx` gần vùng nhất (không có thì ước từ cỡ chữ có sẵn, hoặc Sếp nhập tay). Chữ cao = 3 mm trên giấy × mẫu số, nên mặt bằng 1/50 chữ cao 150 mm, mặt bằng 1/25 chữ cao 75 mm. Chữ xoay theo dầm, đặt giữa dầm, né cột, nét và chữ khác.
4. **Chiều cao h** mặt bằng không có. App lấy từ chữ ghi sẵn trong bản vẽ (`1.DX1-200X400` hoặc bảng thống kê, đúng tầng), không có thì ghi `X?` và cảnh báo. Sếp nhập h ở bảng *Loại dầm* của tab **Gán nhãn**, rồi bấm *Gán lại*.
5. **Xuất DXF có nhãn:** tạo bản sao DXF kèm nhãn trên layer `AZB-NHAN` (file gốc không bị sửa; DWG cần ODA File Converter).

Giới hạn: dầm nhận diện theo hình học trên mặt bằng; dầm vẽ lệch tim trục hoặc khung không phải hình chữ nhật có thể cho bề rộng khác thực tế, Sếp đối chiếu bảng *Loại dầm*. Nhãn là đề xuất, kỹ sư kiểm tra trước khi dùng.

**Dầm suy ra khi khung và ô trống chung một layer (20/11/2026):** nhiều mặt bằng dầm sàn (như `MẶT BẰNG DẦM SÀN TẦNG 1` của LH-NOTT-CD-SH1, layer `LH_SH1_BS 1FL$0$S-Beam`) vẽ khung ngoài và các ô sàn trong cùng một layer. Gán layer đó là **Khung dầm (bao ngoài)** là đủ, không cần layer *Ô trống giữa dầm* riêng: hàm `_tach_khung_va_o` (`app/dam_suy_ra.py`) coi hình có tâm nằm trong hình lớn hơn là ô trống, hình ngoài cùng là khung, rồi suy dầm = khung trừ ô trống như bình thường. Hình trùng nhau (hatch + polyline) không coi là chứa nhau. Nếu layer không có hình nào nằm trong hình khác thì báo thiếu *Ô trống giữa dầm*. Test: `test_suy_dam_khung_va_o_trong_cung_mot_layer`, `test_suy_dam_mot_layer_khong_co_o_trong_thi_bao_thieu` trong `tests/test_boc_khoi_luong.py`. Trên mặt bằng dầm sàn tầng 1 mẫu ra 7 dải dầm rộng 200 đến 250 mm và một mảnh lẻ 0,76 m² (kèm cảnh báo, kỹ sư kiểm tra).

**Nhãn dầm có số tầng đứng trước (20/11/2026):** tên như `1Y4 (250x400)`, `1X3-1 (200x400)`, `1HR(200x300)` nay được nhận là dầm (quy tắc `^\d+(X|Y|HR|B)` trong `TIEN_TO_NHAN`, `app/takeoff.py`), lấy tên và h theo nhãn (b x h). Với tên bắt đầu bằng số, kích thước chỉ tìm phần sau tên (tránh đọc `1X3` thành 1 x 3). Dầm suy ra từ khung không có nhãn gần thì lấy h theo dầm cùng bề rộng và có cảnh báo. Test: `test_doc_nhan_dam_co_so_tang_dung_truoc`.

**Sàn suy ra cùng với dầm (20/11/2026):** khi dầm được suy ra từ khung và ô trống mà chưa gán layer *Sàn* nào, mỗi ô trống giữa dầm thành một ô sàn (layer ảo `_SAN_SUY_RA`, `app/dam_suy_ra.py`), dày theo thông số mặc định / bảng tầng. Đã gán layer Sàn rồi thì không tự thêm. Lỗ thang, lỗ kỹ thuật cũng bị coi là ô sàn nên kỹ sư phải loại bỏ tay (có cảnh báo). Test: `test_suy_dam_tao_o_san_tu_o_trong_khi_chua_gan_layer_san`. Mặt bằng dầm sàn tầng 1 mẫu ra 5 ô sàn.

**Nhân bản mục bản vẽ (20/11/2026):** mục mới tạo bằng nút ⧉ nay bắt đầu với hệ quy chiếu trống (chưa gán tầng, chưa căn, `hq:null` trong `nhanBan`, `app/static/cad.html`). Trước đây mục mới dùng chung dữ liệu `hq` với mục gốc nên gán tầng cho mục mới làm đổi luôn tầng của mục gốc.

**Dầm suy ra khi chỉ có các ô sàn (20/11/2026):** mặt bằng dầm sàn tầng 2 mẫu chỉ vẽ các ô, không có hình khung ngoài. Khi layer Khung dầm chỉ có ô (không hình nào chứa hình khác), `suy_dam` lấy khung bao quanh các ô nới `BE_RONG_BAO` = 200 mm mỗi phía làm dầm biên, kèm cảnh báo ước lượng. Test: `test_suy_dam_chi_co_cac_o_trong_khong_co_khung_ngoai`.

**Cao cột khi dựng 3D theo hệ quy chiếu (20/11/2026):** cột, vách của tầng T dựng cao đúng chiều cao tầng trong bảng tầng (cờ `hqCao` trong `ghepMB`, hàm `khoiDoc` của `app/static/xem3d.js`). Trước đây cột lấy `cao` mặc định 3,6 m của cấu kiện nên cột tầng 1 chỉ cao 3,6 m và hở 0,6 m dưới sàn tầng 2 (cao 4,2 m).

**Căn vùng tự động chính xác hơn (20/11/2026):** "Dò trục + căn tự động" (`goi_y_diem_vung`, `app/he_quy_chieu.py`) không còn lấy trục đầu tiên trùng tên. Hàm `_chon_truc_khop` bỏ phiếu: mỗi trục của vùng trùng tên với lưới chuẩn cho một độ dời, độ dời nào được nhiều trục (1, 2, 3, 4, A, B) đồng ý nhất thắng (dung sai `DUNG_SAI_TRUC_BO_PHIEU` 50 mm). Nhờ đó đường trục cùng tên ở mặt cắt / chi tiết không làm lệch cả vùng (trước đây dầm sàn tầng 2 lệch 7213 mm, dầm sàn tầng 3 lệch 8475 mm). Kiểm tra chéo trong `tinh_can_vung` cũng chỉ xét đường khớp nhất khi có nhiều đường cùng tên. Trên 5 mặt bằng của LH-NOTT-CD-SH1 (cột tầng 1, 2, dầm sàn tầng 1, 2, 3) cả 6 trục đều lệch 0 mm. Test: `test_diem_can_bo_phieu_khong_bi_duong_cung_ten_lam_lech`, `test_kiem_tra_cheo_chi_xet_duong_khop_nhat_trong_cac_duong_cung_ten`.

**Sửa lỗi mất mặt bằng khi khởi động lại (20/11/2026):** khi nạp lại dự án mà máy chủ chưa sẵn sàng (vừa khởi động, đọc bản vẽ lớn chậm) và nạp bản vẽ lỗi tạm thời, hàm `nap` (`app/static/cad.html`) chỉ giữ **mục đầu tiên** dùng bản vẽ đó, bỏ cả chục mục mặt bằng còn lại rồi tự lưu đè, nên dự án chỉ còn 1 mục. Nay `nap` thử lại 3 lần (cách 4 giây) và nếu vẫn lỗi tạm thời thì giữ **mọi** mục cùng bản vẽ, báo cách tải lại trang. Lấy lại dự án đã mất: nút *Sao lưu* chọn bản gần nhất, hoặc API `/api/du-an/khoi-phuc`.

**Bảng tổng hợp bỏ hình 'dầm' rộng hơn 1,2 m (20/11/2026):** hình có cạnh ngắn rộng hơn `BE_RONG_DAM_TOI_DA` = 1,2 m trong `tong_hop_cong_trinh` (`app/he_quy_chieu.py`) là khung ghi chú / đường bao khung dầm bị đọc nhầm, không đưa vào tổng hợp (3D vốn đã bỏ), nên không tính sai khối lượng dầm; số bị bỏ hiện ở mục `bo_qua`. Test: `test_tong_hop_bo_dam_rong_hon_1m2_la_khung_ghi_chu`.

**Ô có dấu X là lỗ mở, không có sàn (20/11/2026):** khi suy sàn từ ô trống giữa dầm (`app/dam_suy_ra.py`), hộp chữ nhật có hai đường chéo nối đúng bốn góc (dấu X, ở bất kỳ layer nào) được coi là lỗ thang / lỗ kỹ thuật theo quy ước bản vẽ kết cấu: ô trống là chính hộp đó thì bỏ khỏi sàn (`_co_dau_x`), hộp nằm trong ô sàn lớn thì khoét lỗ (`_lo_co_dau_x`). Dầm xung quanh vẫn được suy ra như cũ. Trên LH-NOTT-CD-SH1: sàn đỉnh mái (2 ô đều có dấu X) không còn tấm sàn nào, chỉ còn khung dầm và 4 cột góc; tầng 2, 3, mái được khoét một lỗ. Lỗ không có dấu X vẫn phải loại tay. Test: `test_suy_dam_bo_o_co_dau_x_khoi_san`, `test_suy_dam_khoet_lo_co_dau_x_nam_trong_o_san`.

## 3d. Gán layer chuẩn (tab "Gán layer")

Gán layer là bước quyết định độ chính xác: layer gán sai thì khối lượng sai mà không có lỗi báo ra. Phần mềm gợi ý loại cho từng layer từ ba nguồn, theo thứ tự:

1. **Hồ sơ layer** (`data/ho_so_layer.yaml`): lựa chọn tay Sếp đã ghi nhớ. Xem và xóa ở cuối tab Gán layer. Tên mơ hồ như `0`, `1`, `100` không bao giờ được nhớ.
2. **Tên layer** (`config/layer_map.yaml`): chuẩn hóa trước (bỏ dấu, bỏ tiền tố xref `X - TÊN$0$`), khớp theo từ nguyên. Layer thép, kiến trúc, hatch, trục lưới, Defpoints luôn bị loại khỏi bê tông. Layer trong xref bị hạ tin cậy vì thường là bản kiến trúc.
3. **Nhãn chữ gần các hình** (C1, D2, M3...): dùng cho layer tên vô nghĩa. Layer chỉ có một phần nhỏ hình được gọi tên, hoặc chứa lẫn nhiều loại (như layer `0`), **không** bị gán cả layer: hiện "chưa đủ căn cứ" để Sếp dùng quét chọn theo vùng.

Tên và nhãn trùng nhau thì tin cậy tăng, mâu thuẫn thì hạ để Sếp xem. Dưới ngưỡng 70% theo tên, layer được để là *Bỏ qua* (an toàn, không tính nhầm) kèm gợi ý.

**Cổng kiểm tra gán layer:** khung cảnh báo ở đầu tab, số cảnh báo hiện cạnh tên tab (⚠n), và cũng được ghi vào mục cảnh báo của kết quả/Excel. Nó báo: layer thép/kiến trúc/xref đang gán là bê tông, layer gán cả layer nhưng chứa lẫn nhiều loại, layer lớn chưa gán nhưng có vẻ là cấu kiện, vách chiếm quá nửa tổng bê tông.

Ở cột trái: ô tìm layer, lọc (chưa gán / đã gán / có hình / có chữ), sắp xếp, nút **◎** chỉ hiện một layer, và **🎯 Hình này thuộc layer nào?** (bấm vào một hình trên bản vẽ để biết layer của nó).

Bản vẽ mở lại giữ nguyên các gán cũ của lần trước; mở tab Gán layer và bấm *Áp dụng tất cả đề xuất tin cậy cao* để cập nhật theo luật mới.

## 3e. Tách nhiều mặt bằng trong một file (tab "Tách mặt bằng")

Mở bản vẽ rồi vào tab **Tách mặt bằng**: phần mềm dò từng tờ vẽ trong file và vẽ khung lên bản vẽ (xanh = đã tick, vàng = đang xem). Mỗi vùng được đọc **tiêu đề** (MẶT BẰNG DẦM SÀN TẦNG 2...), **tầng**, **tỷ lệ** (TL 1/100) và đoán **vai trò** (mặt bằng / chi tiết / ghi chú-bảng).

- Cách dò: nếu file có từ 2 khung giấy lớn trở lên thì mỗi khung là một vùng; không thì gom các nét, hình, chữ nằm gần nhau, hai cụm cách nhau từ ngưỡng *Tách khi cách nhau* trở lên thì tách. Mặt bằng bị cắt đôi thì tăng ngưỡng, hai mặt bằng dính nhau thì giảm, rồi bấm *Dò lại*.
- Bấm một dòng để phóng tới vùng. Sửa tên và vai trò nếu cần, tick các vùng cần dùng, bấm **Tạo mục**: mỗi vùng thành một mục trong "Bản vẽ trong dự án", đã có sẵn vùng cắt, bóc độc lập. Gán layer cho từng mặt bằng rồi tính.
- Chỉ là đề xuất. Vùng chồng lấn nhau được cắt tại khoảng trống rộng nhất giữa nét vẽ của hai tờ (tiêu đề, tầng, tỷ lệ được đọc lại theo khung mới; vùng bị cắt có cảnh báo để kiểm tra ranh giới); vùng chứa nhiều tiêu đề khác nhau (nhiều mặt bằng vẽ đè lên nhau) được cảnh báo và hạ độ tin cậy.
- **Tốc độ (20/11/2026):** hàm dò (`_thu_thap` trong `app/tach_mat_bang.py`) lấy mẫu điểm bằng numpy/shapely theo lô, không lặp từng điểm bằng Python, kết quả y hệt bản cũ (file 7 MB, 30 nghìn hình, 90 nghìn nét: 1,7 s xuống 0,47 s). Kết quả tách được **nhớ trong phiên** (`_tach_co_nho` trong `app/main.py`) và **tách sẵn ngầm ngay sau khi tải lên** (`_tach_san_nen`), nên bấm *Tách mặt bằng* gần như có luôn. Test: `test_tach_co_nho_va_khong_tinh_lai`. Phần chậm nhất là **lần đầu tải một file DWG nặng** (file mẫu khoảng 73 s: ODA đổi DWG, ezdxf nạp, bung hơn 100 nghìn block); các lần mở sau dùng cache `data/uploads/<id>` nên chỉ khoảng 1 s. Nếu muốn nhẹ hơn nữa, tách file thành từng mặt bằng bằng AutoCAD trước khi tải.
- **Làm việc từng mặt bằng:** bấm một mục trong "Bản vẽ trong dự án" thì bản vẽ tự phóng tới vùng của mục đó và làm mờ phần ngoài vùng. Nút **Ngoài vùng** trên thanh công cụ đổi qua lại giữa *Mờ*, *Ẩn* (che hẳn) và *Hiện* (hiện tất cả); lựa chọn được nhớ. Chỉ đổi cách hiển thị: bản vẽ gốc và toạ độ giữ nguyên, khối lượng vẫn chỉ tính trong vùng.

## 3f. Cốt thép theo bảng thống kê thép (tab "Cốt thép")

Khác với dòng *"cốt thép ước tính theo hàm lượng"* ở các công cụ tính (chỉ nhân khối lượng bê tông với kg/m³), tab này tính **từ bảng thống kê thép của hồ sơ thiết kế**: mỗi dòng = số cấu kiện × số thanh × chiều dài × đơn trọng (0,00617 × Ø², khớp bảng tra Ø6 đến Ø32).

- **Nạp bảng:** từ file Excel/CSV (tự nhận dòng tiêu đề tiếng Việt: Cấu kiện, Đường kính/Ø, Số thanh, Chiều dài (mm/m), Tổng chiều dài, Khối lượng), hoặc **kéo khung quanh bảng chữ trong bản vẽ CAD**.
- **Kiểm tra tự động:** bảng có cột khối lượng thì đối chiếu, lệch quá 2% thì cảnh báo dòng đó; tiêu đề không ghi đơn vị thì đoán mm/m theo độ lớn và báo; dòng thiếu dữ liệu bị bỏ qua và báo; có bê tông đã bóc thì đối chiếu hàm lượng kg/m³ (khoảng thường gặp 40–250).
- **Sửa tay** ô đọc sai, bỏ tick dòng không tính, xuất Excel (mỗi con số là công thức, có sheet tổng hợp theo Ø).
- **Giới hạn:** các bản vẽ mẫu hiện có không chứa bảng thép nên bộ đọc mới được thử trên bảng dựng theo các cách trình bày thường gặp, chưa trên bảng thật của đơn vị thiết kế nào. Bảng CAD vẽ bằng chữ lệch cột sẽ đọc sai: luôn xem lại các dòng đã đọc.

## 3g. Xem 3D (nút "Xem 3D" ở thanh công cụ)

Dựng khung kết cấu 3D từ bản vẽ đang mở để kiểm tra nhanh. Bấm nút **❔ Hướng dẫn** (hoặc phím `?`) trong màn hình 3D để xem hướng dẫn đầy đủ.

- **Điều hướng:** chuột trái xoay, chuột phải dịch, lăn để zoom. Phím `1` góc 3D, `2` trên, `3` trước, `4` phải, `F` vừa khung.
- **Chọn / ẩn / cô lập:** bấm một khối để xem tên, layer, kích thước, thể tích, cảnh báo. `H` ẩn, `I` chỉ hiện khối đó, `A` hiện lại tất cả. Nhấp đúp để bay tới.
- **MEP và khoét lỗ tự động:** hiển thị ống gió, ống cấp thoát nước, ống PCCC, khay cáp. Gán layer cho loại *Ống nước / Ống PCCC / Khay cáp* (app đoán theo tên layer). Kích thước đọc từ tên layer (`P-WATER-D100`, `PCCC DN65`, `KHAY CAP 400x100`), không ghi thì lấy mặc định trong `config/mep.yaml` và sửa được ngay trong màn hình 3D.
  - Khoét lỗ thật trên **dầm, sàn, vách** tại chỗ ống đi xuyên, đánh giá từng lỗ (đạt / lỗ lớn / lẹm mép / cắt đứt), chỉnh được cao độ từng hệ thống và khe hở quanh ống. Ngưỡng chỉ để tham khảo, kỹ sư kết cấu quyết định. Sàn / vách hình phức tạp chưa khoét được, app báo tên.
  - Tự báo **va chạm** ống đụng cột, ống giao cắt ống khác, và **cao thông thủy** thấp nhất. Xuất danh sách lỗ và va chạm ra CSV.
- **Vẽ thêm trong 3D** (nút ✏ Vẽ hoặc phím `V`, cập nhật 19/11/2026): công cụ **Móng, Cột, Dầm, Sàn, Cầu thang, Cọc, Trục, Đường, Đường cong, Ghi chú**.
  - Móng: bấm tâm móng, nhập b × l và độ dày (mặt trên móng ở mức vẽ, dày đi xuống). Cầu thang: bấm chân thang rồi điểm cuối, nhập bề rộng, chiều cao lên và chiều cao bậc; số bậc tự chia, bậc dựng đặc từ cao độ chân thang. Đường cong: bấm 3 điểm (đầu, một điểm trên cung, cuối), vẽ thành nét hoặc **dầm cong** (dầm cong là dầm thật, nhưng khoét lỗ MEP trên dầm cong chưa chính xác như dầm thẳng).
  - **Mặt bằng chuẩn**: chọn cao độ mặt bằng ở ô *Mặt bằng chuẩn* (nền, các tầng; khi ghép nhiều mặt bằng thì lấy theo bảng tầng) hoặc nhập *Mức vẽ*; bật *Hiện mặt chuẩn* (tự hiện khi đang vẽ) để thấy mặt phẳng xanh trong 3D, **kéo tay nắm xanh** ở góc để dời mặt chuẩn lên xuống (hít vào cao độ các tầng, bước 50 mm).
  - **Dời phần vẽ thêm**: chọn rồi kéo trên mô hình (hít lưới 50 mm và tim trục; giữ `Shift` để dời lên xuống, `Alt` để không hít), hoặc phím mũi tên / `PgUp` `PgDn` (thêm `Shift` bước 500 mm); cao độ mặt trên (Z) sửa được trong bảng bên phải. **Cấu kiện đọc từ bản vẽ gốc (cột, dầm, tường, móng, cọc...) cũng dời được** (bổ sung 19/11/2026): độ dời lưu ở `sua[id] = {dx, dy, dz}` trong dữ liệu 3D, cộng vào hình học khi dựng (hàm `dichCK`, `dzCua`, `dichGoc` trong `app/static/xem3d.js`), bản vẽ gốc không bị sửa; nút *Về vị trí gốc* trong bảng chọn xóa độ dời. Cọc chỉ dời ngang.
  - Lưu vào bản vẽ thì hiện lại trên 2D và xuất DXF (lớp `AZB-MONG`, `AZB-THANG`...). Test hình học cung: `tests/test_ve_them_3d.py`.
- **Giao diện chân thực (20/11/2026):** mặc định bật (ô *Giao diện chân thực* ở tab *Mô hình*). Cột, dầm, sàn, móng, cọc, tường hiện màu bê tông / vữa có vân hạt (`MAU_THAT`, `taoVanBeTong` trong `app/static/xem3d.js`), ánh sáng bầu trời (đèn bán cầu + mặt trời + đèn bù), tone mapping ACES, nền trời gradient, sương mù ở chân trời, mặt đất mờ ở cao độ chân công trình (móng và cọc nằm dưới, nhìn xuyên qua; tắt bằng ô *Mặt đất mờ*), sàn đặc có đổ bóng (ô *Sàn trong suốt* để nhìn xuyên các tầng), nét cạnh mờ hơn. Tắt ô này để quay về giao diện phân loại màu (cột đỏ, dầm vàng, sàn xanh). Màu: bê tông xám ấm theo loại cấu kiện (`MAU_THAT`), mặt đất là cỏ có vân (`taoVanCo`), trời xanh, nắng ấm, ánh phản xạ xanh lá từ mặt đất. Nhà chỉ có khung kết cấu nên chưa có tường, cửa, kính (xem phần tường cửa). **Đã thử bỏ:** môi trường phản chiếu PMREM làm cả mô hình đen trên trình duyệt thử nghiệm, nên không dùng. Cờ gỡ lỗi: `localStorage['azb-3d-dbg']` chứa `nomap`, `nobump`, `notone`.
- **Hiện tên** cấu kiện (`L`), **xuất .glb** mở bằng SketchUp, Blender, Revit.
- **Mặt cắt** (`C`) theo cao độ, **xuyên thấu** (`X`), **đo khoảng cách** (`M`), **chụp ảnh PNG**, **tự xoay** (`R`).

## 3h. Hệ quy chiếu dự án (tab "Hệ quy chiếu", thêm 16/11/2026)
Chọn **một lần ngay từ đầu** lưới trục chuẩn, điểm gốc và bảng cao độ từng tầng; mọi mặt bằng (móng, cột, dầm sàn...) được căn vào đó rồi mới dựng 3D. Máy chỉ đề xuất, Sếp xem lại và xác nhận. Dữ liệu lưu trong trạng thái dự án (khóa `he_quy_chieu` và trường `hq` của từng mục bản vẽ), đi theo sao lưu và gói .zip.

1. **Lưới trục**: có hai cách. (a) **"Chọn đường trục trên bản vẽ"** (từ 19/11/2026): bật chế độ rồi bấm vào từng đường thẳng dọc / ngang (đường xanh tim trục, kích thước, bất kỳ layer nào đang hiện kể cả layer khoá) hoặc kéo khung quanh nhiều đường; mỗi đường thành một trục, các đoạn cùng toạ độ gộp thành một trục, đoạn ngắn hơn 1 m khi kéo khung bị bỏ qua; bấm lại vào trục đã chọn để bỏ, Esc để thoát. Tên đọc từ bong bóng gần đầu trục, không có thì đặt tạm (`dat_ten_luoi`, API `/api/he-quy-chieu/dat-ten-truc`). (b) "Dò trục từ bản vẽ này" (layer tên TRUC / GRID / AXIS hoặc chọn layer), đọc tên trong bong bóng; trục chưa đọc được tên bị đặt tên tạm và cảnh báo. Module `app/he_quy_chieu.py` (`do_luoi_truc`).
2. **Điểm gốc**: giao một trục dọc và một trục ngang (vd A-1) = (0; 0) công trình; điểm hướng tuỳ chọn để tính góc xoay (`kiem_tra`).
3. **Bảng tầng**: mã, loại, cao độ kết cấu (dựng 3D), cao độ hoàn thiện, dày sàn, cao dầm; chiều cao tầng tự tính (`chuan_hoa_bang_tang`). Gõ cao độ kiểu `+3.600`, `3,6`, `±0.000`.
4. **Gán vùng**: mỗi mặt bằng chọn tầng, cấu kiện, điểm căn A (và B nếu xoay) bằng giao trục; "Dò + căn tự động" dựa trên tên trục trùng lưới chuẩn; kiểm tra chéo độ lệch từng trục (ngưỡng 50 mm); phải tick "đã xác nhận" (`goi_y_diem_vung`, `tinh_can_vung`, `kiem_tra_gan_vung`).
5. **Tổng hợp**: cây Tầng -> Cấu kiện -> Đối tượng, toạ độ theo gốc công trình, cao độ đáy/đỉnh từ bảng tầng, diện tích, thể tích; bấm dòng để tô sáng trên bản vẽ; "Đưa về tim trục" và xuất CSV (`tong_hop_cong_trinh`). Mặt bằng chỉ lấy loại cấu kiện đã khai báo ("Khác" lấy hết).
6. **Dựng 3D theo hệ quy chiếu** (nút cam ở mục 5): vị trí theo phép căn, cao độ theo bảng tầng, lưới trục chuẩn hiện sẵn. Cột, vách, tường, cửa của tầng T dựng từ cao độ T lên tầng trên; dầm, sàn, móng ở cao độ tầng (hàm `zHq` trong `app/static/xem3d.js`).

Giới hạn: danh sách tổng hợp không lưu (bấm "Tính và tổng hợp" lại khi mở app); chưa dựng ống MEP ở chế độ này; lưới trục trong 3D luôn lấy lại từ mục 1 khi dựng lại.
**Mái khi thêm tầng (sửa 16/11/2026)**: ô "Số tầng dựng" trong 3D (chế độ một mặt bằng) nhân cột, dầm, sàn, vách, tường, cửa (`THEM_LOAI`) và **dời mái lên đỉnh tầng trên cùng** (mái không nhân bản; hàm `nhanTang` trong `app/static/xem3d.js`); nút "+ Thêm tầng" trong bảng tầng chèn tầng mới ngay dưới dòng MAI / TUM rồi dời MAI / TUM lên cùng một đoạn, giữ khoảng cách cũ giữa đỉnh tầng và mái (hàm `hqChenTang` trong `app/static/cad.html`). Test: `tests/test_he_quy_chieu.py`.

## 4. Bản vẽ cần như thế nào để bóc chính xác

| Yêu cầu | Lý do |
|---|---|
| Cột, dầm, sàn, vách, móng vẽ bằng **hình kín** (polyline đóng hoặc hatch), mỗi loại một layer riêng | Công cụ lấy diện tích và chu vi từ hình kín. Nét rời được thử ghép, ghép không được thì bỏ qua và cảnh báo |
| Có **nhãn** gần cấu kiện: `C1 300x300`, `D1 220x500`, `S1 t=120`, `M1 1200x1200x700` | Mặt bằng 2D không lưu chiều cao. Thiếu nhãn thì công cụ dùng giá trị mặc định và cảnh báo |
| Lỗ mở sàn vẽ trên layer riêng | Để trừ vào sàn |
| Khai báo đơn vị bản vẽ (`INSUNITS`) | Nếu không khai báo, công cụ hiểu là mm và cảnh báo |

Nhãn: số > 5 được hiểu là mm (220 = 0,22 m). Tên bắt đầu bằng C/K là cột, D/B/GB/DC/DM là dầm, S là sàn, M/F/PC là móng, V/W/LT là vách.

## 5. Quy tắc tính (chống tính trùng)

- **Sàn:** toàn bộ diện tích mặt sàn, kể cả phần trên dầm/cột/vách, trừ lỗ mở, nhân với t.
- **Cột, vách** có sàn phía trên: cao = chiều cao tầng - dày sàn. Không có sàn: cao = chiều cao tầng.
- **Dầm:** dài thông thủy giữa mép cột/vách. Có sàn phía trên: cao = h - dày sàn. Hai dầm giao nhau thì phần giao tính cho dầm cao hơn.
- **Ván khuôn:** trừ mặt tiếp giáp (đầu dầm vào cột, dầm phụ gác vào dầm chính, cột giáp vách). Đáy sàn trừ phần đáy dầm, đầu cột. Có tính thành sàn ở mép ngoài và mép lỗ mở.
- **Móng:** diện tích x chiều cao. Bê tông lót mở rộng mỗi phía theo thông số (mặc định 100 mm, dày 100 mm).
- Hình vẽ trùng (chồng nhau > 98%) chỉ tính một lần. Hình chồng một phần thì phần chồng tính một lần, có cảnh báo.

## 6. Cấu hình

| File | Nội dung |
|---|---|
| `config/layer_map.yaml` | Mẫu tên layer, dùng để đoán loại cấu kiện |
| `config/cong_tac.yaml` | Danh mục công tác, đơn vị, **mã hiệu định mức** (đang để trống, Sếp điền theo mẫu AZB) |
| `config/app.yaml` | Đường dẫn ODA, thông số mặc định, ngưỡng kiểm tra |
| `config/cong_cu.yaml` | Công cụ tính và bộ công thức chung của từng cấu kiện (bản người dùng sửa lưu ở `data/cong_cu_tuy_chinh.yaml`) |

## 7. Kiểm thử

```powershell
.venv\Scripts\python -m pytest
```

Bản vẽ mẫu `data/mau/khung_mau.dxf` (tạo bằng `tools/tao_ban_ve_mau.py`) có đáp số tính tay. Phần kiểm thử gồm: so khớp 9 công tác với đáp số, bảo toàn thể tích khi ô sàn vẽ đến mép dầm, cảnh báo vẽ trùng và nét hở, công thức Excel khớp Python, và toàn bộ luồng web từ tải lên đến đối chiếu.

## 8. Chưa làm ở giai đoạn 1

- Tự bố trí cốt thép từ nội lực (bài toán kết cấu, cần kỹ sư chịu trách nhiệm). Cốt thép từ bảng thống kê: xem mục 3f.
- Đọc BIM (Revit/IFC), bộ môn MEP, hạ tầng/san nền.
- Nhận cao độ từ mặt cắt. (Tách nhiều mặt bằng trong một file: xem mục 3e.)
- Định dạng đúng mẫu Excel AZB: hiện dùng mẫu tạm, sẽ chỉnh khi có mẫu thật.
- Đưa lên máy chủ nội bộ, phân quyền người dùng.

## Cấu trúc thư mục

```
app/
  pdf_reader.py   đổi 1 trang PDF vector thành DXF (mm thực tế, theo tỷ lệ)
  dxf_reader.py   đọc DWG/DXF, gom hình kín và chữ theo layer, đổi đơn vị ra m
  takeoff.py      gán nhãn, tính khối lượng, cảnh báo
  excel_io.py     xuất Excel, đọc sheet đối chiếu
  cong_cu.py      công cụ tính theo cấu kiện: công thức sửa được, tính, xuất Excel có công thức
  gan_nhan.py     tự gán nhãn dầm, trục, cột lên mặt bằng chưa có chữ (đúng tỷ lệ), xuất DXF có nhãn
  quet_chon.py    quét chọn mặt bằng/chi tiết: đọc ký hiệu, tách móng với cột, gom nhóm
  main.py         web API (FastAPI)
  static/index.html  giao diện
config/           cấu hình (sửa được, không cần sửa code)
data/mau/         bản vẽ mẫu và Excel mẫu
data/uploads/     file bản vẽ đã tải lên. Bấm ✕ chỉ đóng bản vẽ, file vẫn ở đây; mở lại ở mục "Bản vẽ đã tải (đã đóng)" bên trái. Chỉ nút 🗑 mới xóa hẳn
tests/            kiểm thử tự động
tools/            công cụ phụ (tạo bản vẽ mẫu)
```
