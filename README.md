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
- Chỉ là đề xuất. Vùng chồng lấn nhau hoặc chứa nhiều tiêu đề khác nhau (nhiều mặt bằng vẽ đè lên nhau) được cảnh báo và hạ độ tin cậy.

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

- Cốt thép (cần bảng thống kê thép, định dạng mỗi đơn vị một kiểu).
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
