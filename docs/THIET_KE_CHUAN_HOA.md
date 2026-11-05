# Thiết kế: chuẩn hóa đầu vào, tự động hóa phía sau

Tài liệu thiết kế cho giai đoạn tiếp theo của `azb-take-off`. Bám theo mô hình 3 tầng của phần mềm shop drawing thép đã tham khảo:

1. Có **chuẩn riêng** (template, quy tắc).
2. **AI chuẩn hóa** mọi bản vẽ đầu vào về chuẩn đó.
3. **Bộ công cụ tính toán** chạy trên dữ liệu chuẩn. Người chỉ ra lệnh và duyệt.

> Nguyên tắc xuyên suốt: **AI đề xuất, công cụ tính, người duyệt.** AI không bao giờ tự ghi con số vào kết quả. Mọi giá trị AI đưa ra phải ở dạng "đề xuất kèm độ tin cậy và nguồn", người xác nhận thì mới thành dữ liệu chuẩn.

---

## 1. Hiện trạng (đã đọc code, 11/11 test đang đạt)

Luồng hiện tại:

```
DWG/DXF --dxf_reader--> BanVe (layer thô) --layer_map + người gán--> takeoff / thong_ke / ong_gio --> Excel
```

| Thành phần | File | Vai trò |
|---|---|---|
| Đọc CAD | `app/dxf_reader.py` | Gom hình kín, nét hở, chữ theo layer; đổi đơn vị ra mét |
| Suy luận | `app/dam_suy_ra.py` | Suy dầm = khung trừ ô trống |
| Đọc nhãn | `app/takeoff.py` (`doc_nhan`) | Regex tách tên, kích thước, chiều dày |
| Tính | `app/takeoff.py` (`_BoTinh`) | Bê tông, ván khuôn, chống trùng |
| Thống kê | `app/thong_ke.py` | Đếm cấu kiện, đối chiếu mặt bằng với chi tiết, đọc ghi chú |
| Ống gió | `app/ong_gio.py` | Diện tích tôn từ MLINE và block |
| Cấu hình | `config/*.yaml` | Mẫu layer, công tác, ngưỡng |

**Điểm mạnh nên giữ:** phần tính đã là code xác định, có test so với đáp số tay, mỗi con số là công thức Excel dò lại được, có cảnh báo từng cấu kiện.

### Khoảng trống so với mô hình mục tiêu

| # | Khoảng trống | Biểu hiện trong code | Hậu quả |
|---|---|---|---|
| G1 | **Chưa có mô hình dữ liệu chuẩn độc lập.** Bước "chuẩn hóa" nằm lẫn trong bước tính | `_BoTinh` vừa gom hình, gán nhãn, đọc thông số, vừa tính (`takeoff.py:104-420`) | Muốn thêm công cụ mới phải đọc lại bản vẽ thô |
| G2 | **Các module chạy lại bước chuẩn hóa riêng và gọi hàm nội bộ của nhau** | `thong_ke.py:21` import `_BoTinh`, `_hcn` | Sửa một nơi, nơi kia lệch |
| G3 | **Chuẩn hóa dựa vào tên layer + regex**, không nhớ gì giữa các lần | `config/layer_map.yaml`, `TIEN_TO_NHAN` | Mỗi đơn vị thiết kế đặt tên khác, người gán lại từ đầu mỗi file |
| G4 | **Thông số không mang nguồn và độ tin cậy** (trừ `nguon_h`, `nguon_t` cho vài trường) | `lay_thong_so`, `takeoff.py:223-279` | Khó biết con số nào là đọc từ nhãn, con số nào là mặc định |
| G5 | **Phiên làm việc chỉ nằm trong RAM** | `PHIEN = {}` ở `main.py:26` | Tắt server là mất. Không lưu được "bản đã duyệt" |
| G6 | **Chưa có bước duyệt dữ liệu chuẩn trước khi tính** | Người chỉnh `dieu_chinh` rồi tính lại, không có trạng thái "đã xác nhận" | Không phân biệt dữ liệu máy đoán và dữ liệu người đã xem |
| G7 | **Mỗi file một mặt bằng**, chưa tách nhiều mặt bằng trong một file | README mục 8 | Phải tách tay trước khi tải |
| G8 | **Chưa có cốt thép** | README mục 8 | Phần khối lượng lớn nhất sau bê tông |

---

## 2. Kiến trúc đề xuất

```
                         ┌──────────────────────────────┐
 DWG / DXF / PDF  ─────► │ 1. INGEST   đọc thô          │  dxf_reader (giữ nguyên)
                         └──────────────┬───────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │ 2. NORMALIZE  về chuẩn AZB   │  luật cứng trước, AI cho phần mơ hồ
                         │    → "Mô hình chuẩn" (JSON)  │  mọi giá trị có nguồn + độ tin cậy
                         └──────────────┬───────────────┘
                                        ▼
                         ┌──────────────────────────────┐
                         │ 3. VALIDATE + DUYỆT          │  cổng kiểm tra, người xác nhận
                         │    trạng thái: đề_xuất →     │
                         │    đã_xác_nhận               │
                         └──────────────┬───────────────┘
                                        ▼
        ┌───────────────────────────────────────────────────────────┐
        │ 4. CÔNG CỤ (đăng ký theo tên, nhận Mô hình chuẩn)         │
        │  be_tong_van_khuon │ thong_ke │ ong_gio │ thep (sau)      │
        └──────────────┬────────────────────────────────────────────┘
                       ▼
        ┌──────────────────────────────┐
        │ 5. XUẤT  Excel / báo cáo     │  công thức, mã hiệu theo mẫu AZB
        └──────────────────────────────┘
```

Điểm khác với hiện tại: **bước 2 tách ra thành một tầng riêng, sinh ra một tệp dữ liệu chuẩn có thể lưu, mở lại, duyệt**. Bước 4 chỉ đọc tệp đó, không đụng vào bản vẽ thô.

### 2.1. Mô hình chuẩn AZB (`azb-model` v1)

Một dự án là một thư mục chứa `model.json`. Cấu trúc:

```jsonc
{
  "schema": "azb-model/1",
  "du_an": { "ten": "...", "ma": "..." },
  "don_vi_chieu_dai": "m",                       // cố định, mọi tọa độ đã đổi ra mét
  "nguon": [                                      // các file đã nạp
    { "id": "f1", "ten_file": "S-NHA BAO VE 2.dwg", "sha256": "...", "don_vi_goc": "mm" }
  ],
  "tang": [                                       // mỗi mặt bằng gắn với một tầng
    {
      "id": "T1", "ten": "Tầng 1",
      "cao_do_san": { "gia_tri": 0.0, "nguon": "người nhập", "tin_cay": 1.0 },
      "chieu_cao": { "gia_tri": 3.6, "nguon": "mặc định", "tin_cay": 0.3 },
      "so_tang_giong_nhau": 1,
      "vung_cat": [x0, y0, x1, y1],              // vùng cắt trong file nguồn
      "file": "f1"
    }
  ],
  "cau_kien": [
    {
      "id": "T1.cot.007",
      "tang": "T1",
      "loai": "cot",                              // cot|dam|san|lo_san|mong|vach|...
      "ten": "C1",                                // tên theo chuẩn (đã chuẩn hóa)
      "hinh": [[[x,y],...]],                      // đa giác ngoài + lỗ, mét
      "thong_so": {
        "b":  { "gia_tri": 0.30, "nguon": "nhãn",  "tin_cay": 0.95 },
        "h":  { "gia_tri": 0.30, "nguon": "hình vẽ", "tin_cay": 1.0 },
        "cao":{ "gia_tri": 3.6,  "nguon": "mặc định", "tin_cay": 0.3 }
      },
      "tham_chieu": { "file": "f1", "layer": "S-COT", "handle": "2A4F", "nhan": "C1 300x300" },
      "trang_thai": "de_xuat",                    // de_xuat | da_xac_nhan | sua_tay | loai_bo
      "canh_bao": [ { "muc": "canh_bao", "ma": "NHAN_LECH_HINH", "noi_dung": "..." } ]
    }
  ],
  "quy_tac": "azb-rules/1",                       // phiên bản bộ quy tắc đã dùng để chuẩn hóa
  "lich_su": [ { "luc": "...", "ai": "...", "viec": "xác nhận 12 cột" } ]
}
```

Quy ước bắt buộc:

- **Mỗi thông số là một bộ ba** `{gia_tri, nguon, tin_cay}`. `nguon` thuộc tập cố định: `hình vẽ`, `nhãn`, `chi tiết`, `ghi chú`, `suy ra`, `mặc định`, `người nhập`, `AI đề xuất`.
- **Công cụ tính từ chối thông số `nguon = AI đề xuất` chưa xác nhận.** Đây là chốt chặn giữ nguyên tắc "AI không tự ghi số".
- `tham_chieu` luôn trỏ về layer và handle của bản vẽ gốc, để người dò ngược được.
- Đơn vị cố định là mét ngay từ mô hình chuẩn, không còn chuyện mỗi module tự đổi.

Phần này tương ứng với `dict` cấu kiện trong `takeoff.py:174-177` (đã có `id`, `loai`, `ten`, `nhan`, `layer`, `handle`, `geom`, `thong_so`, `canh_bao`), chỉ thiếu `nguon/tin_cay` cho mọi thông số, `trang_thai`, và khả năng lưu ra tệp.

### 2.2. Bộ quy tắc chuẩn (`azb-rules`)

Gom những thứ đang rải rác thành một nơi, có phiên bản:

| Nhóm | Hiện ở đâu | Đề xuất |
|---|---|---|
| Quy ước đặt tên cấu kiện (`TIEN_TO_NHAN`) | hằng trong `takeoff.py:27-33` | `config/quy_tac.yaml`, có phiên bản |
| Mẫu layer | `config/layer_map.yaml` | giữ, thêm **hồ sơ theo đơn vị thiết kế** (mục 3.1) |
| Ngưỡng kiểm tra | `config/app.yaml` | giữ |
| Quy tắc tính (chống trùng, ván khuôn trừ giáp) | code trong `_BoTinh.tinh` và README mục 5 | giữ trong code, tài liệu hóa, **ghi phiên bản vào kết quả** |
| Danh mục công tác và mã hiệu | `config/cong_tac.yaml` (mã hiệu đang để trống) | giữ, chờ mẫu AZB |

Mỗi kết quả xuất ra ghi `quy_tac = azb-rules/1` để biết con số tính theo bản quy tắc nào.

### 2.3. Công cụ (tools) đăng ký theo tên

Mỗi công cụ là hàm thuần: `(mo_hinh, tham_so) -> ket_qua`, không đọc file CAD, không có trạng thái.

| Công cụ | Từ code hiện có | Ghi chú |
|---|---|---|
| `be_tong_van_khuon` | `_BoTinh.tinh` | Tách phần tính ra khỏi phần gom và gán nhãn |
| `thong_ke_cau_kien` | `thong_ke.thong_ke` | Thôi import `_BoTinh`, đọc mô hình chuẩn |
| `ong_gio` | `ong_gio.boc_ong_gio` | Có thêm lớp chuẩn hóa riêng (MLINE, block) |
| `boc_chon` | `chon_doi_tuong.boc_chon` | Vẫn làm việc trên hình thô, vì dùng khi người chọn tay |
| `thep` | chưa có | Mục 5 |

Mỗi công cụ khai báo: tên, đầu vào cần (loại cấu kiện, thông số bắt buộc), đầu ra. Nhờ vậy giao diện, API và về sau AI điều phối đều gọi cùng một cửa:

```python
CONG_CU = {"be_tong_van_khuon": ..., "thong_ke_cau_kien": ..., "ong_gio": ...}
```

---

## 3. Chuẩn hóa: chia việc giữa luật cứng và AI

Thứ tự ưu tiên khi chuẩn hóa một giá trị: **luật cứng → hồ sơ đã học → AI đề xuất → hỏi người**.

| Việc | Luật cứng (đã có) | Phần AI hỗ trợ (mới) |
|---|---|---|
| Đổi đơn vị | `$INSUNITS`, mặc định mm + cảnh báo | Gợi ý đơn vị khi không khai báo, dựa vào kích thước điển hình của cột/dầm |
| Phân loại layer | regex `layer_map.yaml` | Đoán loại layer lạ từ tên, hình học (kín/hở, kích thước), và chữ gần đó |
| Đọc nhãn | `doc_nhan` (regex) | Hiểu nhãn viết lạ: `Ø16a200`, `D16@200`, `C1(300x600)`, `200/500` |
| Tách nhiều mặt bằng trong file | chưa có (phải cắt tay) | Đề xuất khung vùng từ tiêu đề bản vẽ và cụm hình |
| Gán tầng cho mặt bằng | người chọn | Đọc tiêu đề "MẶT BẰNG DẦM SÀN TẦNG 2" |
| Đọc ghi chú chung | `doc_ghi_chu` (regex) | Hiểu câu tự do: "sàn dày 120 trừ ô vệ sinh dày 100" |
| Đối chiếu mặt bằng với chi tiết | `thong_ke` | Giữ nguyên, không cần AI |

### 3.1. Hồ sơ đơn vị thiết kế (nhớ giữa các lần)

Hiện người gán layer lại từ đầu cho mỗi file (G3). Đề xuất lưu `data/ho_so/<don_vi_thiet_ke>.yaml`:

```yaml
don_vi_thiet_ke: "VISSAN-STR"
layer:
  "S-COT": cot
  "S-BEAM": dam
  "S-TEXT": nhan
nhan:
  dam: "D\\d+\\s+\\d+x\\d+"
mac_dinh: { day_san: 0.12 }
```

Lần sau gặp bản vẽ cùng nguồn, hồ sơ được áp trước, người chỉ xem lại điểm khác. Mỗi lần người sửa, hồ sơ có thể cập nhật (hỏi trước khi ghi). Đây là cách hệ thống "học" mà vẫn kiểm soát được, không cần huấn luyện mô hình.

### 3.2. Khuôn dạng đề xuất của AI

AI trả về danh sách đề xuất, không phải kết quả:

```json
{ "doi_tuong": "layer:SKT-DAM-01", "de_xuat": {"loai": "dam"},
  "tin_cay": 0.82, "ly_do": "Hình chữ nhật dài, nhãn gần có dạng 'D1 220x500'" }
```

- `tin_cay ≥ 0.9` và không mâu thuẫn luật cứng: tự điền, vẫn đánh dấu `de_xuat`.
- `0.6 – 0.9`: hiện lên giao diện để người xác nhận.
- `< 0.6`: không điền, hỏi người.
- Ngưỡng đặt trong `config/app.yaml`, chỉnh được.

### 3.3. Bot AI chuẩn hóa: mục đích, phạm vi, bản đầu tiên

**Mục đích chuyên sâu:** bot là **trợ lý chuẩn hóa đầu vào**. Nó nhìn dữ liệu thô đã trích từ bản vẽ (tên layer, nhãn chữ, kích thước) và *đề xuất* cách đưa về chuẩn AZB, kèm độ tin cậy và lý do. Người duyệt, công cụ tính. Bot không bóc khối lượng, không ghi con số vào kết quả.

**Vì sao chọn mục đích này:** đánh trúng G3 (mỗi đơn vị thiết kế đặt tên layer một kiểu, người gán lại từ đầu mỗi file). Regex và `layer_map.yaml` chỉ khớp được cái đã biết, còn AI hiểu nghĩa (ví dụ "BEAM", "DAM", "A-BEAM-CONC" đều là dầm). Đầu ra là bảng ánh xạ, không phải con số, nên rủi ro thấp và đo được bằng cách so với bản gán tay.

**Mức tự quyết:** chỉ đề xuất. Dùng đúng ngưỡng ở mục 3.2. Mọi giá trị do bot đưa ra mang `nguon = AI đề xuất` và bị chốt chặn ở mục 2.1 cho đến khi người xác nhận.

**Phạm vi bản đầu tiên (gộp P4 và phần "phân loại layer" của P5):**

| Có làm | Chưa làm (để sau) |
|---|---|
| Đề xuất loại cho layer lạ (cột, dầm, sàn, nhãn...) | Diễn giải nhãn viết lạ (làm sau, cùng cơ chế) |
| Lưu ánh xạ đã duyệt vào hồ sơ đơn vị thiết kế (mục 3.1) | Chat điều khiển ("bóc dầm tầng 3") |
| Kiểm tra chéo bằng ngưỡng sẵn có trong `config/app.yaml` | Tách nhiều mặt bằng, gán tầng |

**Điều kiện tiên quyết:** cần có chỗ đặt "đề xuất" và "xác nhận", tức P1 (mô hình chuẩn) và P3 (lưu dự án, trạng thái duyệt) xong trước. Nếu muốn thử sớm, có thể làm prototype chạy độc lập ngoài luồng chính để đo chất lượng, chưa nối vào phần tính.

**Nguyên tắc tối ưu:**

1. **Luật cứng và hồ sơ đã học trước, AI sau.** Layer đã khớp `layer_map.yaml` hoặc hồ sơ thì không gọi AI. Giảm chi phí, giảm lượng dữ liệu gửi đi.
2. **Chỉ gửi dữ liệu đã trích**, không gửi file DWG: danh sách layer, số thực thể, vài mẫu chữ, kích thước bao. Bỏ tên dự án và chủ đầu tư. Hình học không rời máy.
3. **Đầu ra có cấu trúc** như mục 3.2, `{loại, tin_cậy, lý_do}`.
4. **Kiểm tra chéo:** nếu bot gán "dầm" mà kích thước ngoài `h_dam_hop_ly`, hoặc lệch nhãn quá `lech_kich_thuoc_nhan`, hệ thống tự hạ độ tin cậy.
5. **Vòng học từ người sửa:** mỗi lần người sửa, hỏi trước rồi ghi vào hồ sơ. Lần sau cùng đơn vị thiết kế không cần hỏi AI.

**Cách đo (trên bộ bản vẽ mẫu ẩn danh, có bản gán tay làm đáp án):**

- Tỷ lệ layer gán đúng mà người không phải sửa.
- Tỷ lệ phải hỏi người (nằm dưới ngưỡng).
- Số lần bot gán sai nhưng tin cậy cao (chỉ số quan trọng nhất, phải càng gần 0 càng tốt).
- Thời gian gán layer so với làm tay.

Các ngưỡng 0.9 và 0.6 ở mục 3.2 là giá trị đề xuất ban đầu, **chưa kiểm chứng**, phải chỉnh theo kết quả đo.

**Triển khai (chưa chốt, xem mục 8 câu 2):**

| Phương án | Ưu | Nhược |
|---|---|---|
| A. API đám mây, chỉ gửi dữ liệu đã trích | Chính xác hơn, ít công dựng | Cần IT hoặc người có thẩm quyền duyệt chính sách dữ liệu |
| B. Mô hình chạy trong nội bộ | Dữ liệu không ra ngoài | Tốn máy, chất lượng thấp hơn |

Khuyến nghị: A cho bản đầu tiên sau khi chốt chính sách, B làm dự phòng nếu bị chặn.

---

## 4. Cổng kiểm tra và duyệt (validate)

Chạy trước khi cho công cụ tính. Phần lớn đã có dưới dạng cảnh báo, cần gom lại thành **cổng**:

| Mức | Ví dụ | Hành vi |
|---|---|---|
| **Chặn** | Cấu kiện thiếu thông số bắt buộc; thông số còn `AI đề xuất` chưa xác nhận; chiều cao dầm ≤ dày sàn | Không tính cấu kiện đó, báo rõ |
| **Cảnh báo** | Dùng giá trị mặc định; nhãn lệch hình vẽ > 5%; hai nhãn gần một cấu kiện; chồng lấn | Tính, đánh dấu viền đỏ như hiện nay |
| **Thông tin** | Không có sàn phía trên, tính cao bằng chiều cao tầng | Chỉ ghi chú |

Thêm kiểm tra **chéo** mà hiện chưa có: tổng diện tích sàn so với bao hình, số cột so với chi tiết, tên trùng khác kích thước, cấu kiện bị đếm ở nhiều mặt bằng.

Trạng thái duyệt: người xác nhận theo nhóm ("xác nhận tất cả cột đạt tin cậy ≥ 0.9"), hoặc từng cái. `lich_su` ghi lại ai xác nhận gì lúc nào, phục vụ truy vết và ký duyệt.

---

## 5. Cốt thép: làm sau, có điều kiện

Đây là phần tương ứng với sản phẩm tham khảo (shop drawing thép), nhưng **không nên đưa vào đợt đầu**, vì:

- Mặt bằng 2D không chứa số thanh, đường kính, chiều dài neo. Dữ liệu này nằm ở **bảng thống kê thép, mặt cắt dầm cột, chi tiết bố trí** và mỗi đơn vị trình bày một kiểu (README đã ghi).
- Cần mô hình chuẩn của cấu kiện trước (mục 2.1), nếu không sẽ lặp lại lỗi G1 cho thép.

Đề xuất lộ trình cho thép:

1. Nạp **bảng thống kê thép** (dạng bảng trong CAD hoặc Excel) vào một mục `thep` trong mô hình chuẩn: `{cau_kien, mac_thep, duong_kinh, so_thanh, chieu_dai, hinh_dang}`.
2. Công cụ `thep` tính khối lượng = Σ (số thanh × dài × đơn trọng theo đường kính). Đơn trọng là bảng tra cố định, có test.
3. Đối chiếu tổng với bảng thống kê trên bản vẽ (nếu có) như tiêu chí nghiệm thu.
4. Chỉ sau đó mới nghĩ đến tự bố trí thép từ nội lực, vốn là bài toán kết cấu cần kỹ sư chịu trách nhiệm.

---

## 6. Lộ trình thực hiện

Mỗi pha độc lập, xong pha nào dùng được pha đó, và **không phá những gì đang chạy** (11 test hiện có phải luôn đạt).

| Pha | Việc | Kết quả kiểm tra được |
|---|---|---|
| **P1** | Định nghĩa mô hình chuẩn (`app/mo_hinh.py`, dataclass + lưu/đọc JSON). Tách `_BoTinh.gom_hinh/gan_nhan/lay_thong_so` thành bước `chuan_hoa()` sinh mô hình. `tinh()` đọc mô hình | Test cũ vẫn đạt; thêm test: chuẩn hóa → lưu → đọc lại → tính ra cùng số |
| **P2** | `thong_ke` và `ong_gio` đọc mô hình chuẩn, bỏ import hàm nội bộ. Đăng ký công cụ | Kết quả thống kê và ống gió không đổi so với trước (so sánh trên các bản vẽ trong `data/uploads`) |
| **P3** | Lưu dự án xuống đĩa (thay `PHIEN` trong RAM), có `trang_thai` và `lich_su`. Giao diện thêm màn duyệt | Tắt bật server không mất dữ liệu; xác nhận theo nhóm |
| **P4** | Hồ sơ đơn vị thiết kế (mục 3.1) | Nạp lại bản vẽ cùng nguồn: không phải gán layer lại |
| **P5** | Lớp đề xuất AI cho layer, nhãn, vùng/tầng (mục 3.2), có ngưỡng tin cậy | Đo trên bộ bản vẽ mẫu: tỷ lệ đề xuất đúng, tỷ lệ phải hỏi người |
| **P6** | Cốt thép theo mục 5 | Khớp bảng thống kê thép trên bản vẽ trong sai lệch cho phép |

Thứ tự khuyến nghị: **P1 → P2 → P3** là nền móng, làm trước. P5 (AI) chỉ có giá trị khi P1 và P3 xong, vì cần chỗ để đặt "đề xuất" và "xác nhận".

### Tiêu chí hoàn thành chung

- Cùng một bản vẽ, kết quả sau khi refactor **trùng khớp từng số** với trước khi refactor.
- Mọi dòng khối lượng truy được về `layer` và `handle` trong bản vẽ gốc.
- Không có đường nào để một giá trị `AI đề xuất` chưa xác nhận đi vào số liệu xuất ra.

---

## 7. Rủi ro và lưu ý

| Rủi ro | Cách giảm |
|---|---|
| Refactor làm lệch số liệu | Chạy so sánh trước/sau trên toàn bộ bản vẽ trong `data/uploads` trước khi gộp từng pha |
| AI đoán sai mà người duyệt lướt qua | Chỉ tự điền khi tin cậy cao; mục có `AI đề xuất` luôn hiện nổi bật; xác nhận hàng loạt có đếm số lượng |
| Dữ liệu bản vẽ khách hàng đưa lên dịch vụ AI bên ngoài | Quyết định chính sách trước P5: dùng mô hình chạy trong nội bộ hay chỉ gửi **mô tả trích xuất** (tên layer, nhãn chữ) mà không gửi hình học. Hiện công cụ chỉ chạy `127.0.0.1` |
| Mô hình chuẩn đổi về sau | Có trường `schema` kèm phiên bản và hàm nâng cấp |
| Tưởng tự động là chính xác tuyệt đối | Giữ lời nhắc "kỹ sư kiểm tra và ký duyệt" như README hiện nay |

## 8. Câu hỏi cần chốt trước khi làm P1

1. **Mẫu Excel AZB thật** và mã hiệu định mức: đang để trống (`config/cong_tac.yaml`). Cần để chốt phần xuất.
2. **Chính sách dùng AI** ở P5: nội bộ hay dịch vụ ngoài, và được gửi những gì.
3. **Ưu tiên thép**: có cần sớm hơn P4/P5 không? Nếu có, cần mẫu bảng thống kê thép của 2–3 đơn vị thiết kế thường gặp.
4. **Một dự án gồm bao nhiêu file** thường gặp (mặt bằng, chi tiết, ghi chú) để chọn cách tổ chức thư mục dự án.
5. **Bộ bản vẽ mẫu để đo bot (mục 3.3):** 2–3 bản vẽ ẩn danh từ các đơn vị thiết kế khác nhau, kèm bản gán layer bằng tay làm đáp án chuẩn.
