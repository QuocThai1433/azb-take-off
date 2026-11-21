# Quy trình sử dụng AZB Take-off: từ bản vẽ DWG đến khối lượng và mô hình 3D

Tài liệu để trình bày cho các phòng ban (viết 21/11/2026, theo bản vẽ mẫu `LH-NOTT-CD-SH1.dwg`). Chi tiết kỹ thuật từng chức năng xem `README.md`.

## 1. Công cụ làm được gì

Từ một file bản vẽ kết cấu (DWG/DXF/PDF vector), công cụ giúp:

1. Lấy **lưới trục**, **cao độ từng tầng**.
2. Nhận ra **móng, cột, dầm, sàn** từng tầng: tên, kích thước, diện tích, thể tích.
3. Tổng hợp khối lượng theo **Tầng → Loại cấu kiện → Từng cấu kiện**, xuất Excel.
4. Dựng **mô hình 3D** để xem và kiểm tra bằng mắt.

Nguyên tắc chung: **máy đề xuất, người xác nhận.** Mọi chỗ máy đoán đều có cảnh báo hoặc ô "Đã xác nhận" để người có chuyên môn kiểm.

## 2. Chuẩn bị

| Việc | Ai làm | Ghi chú |
|---|---|---|
| Cài đặt một lần (`CAI_DAT.bat`) | IT hoặc người phụ trách | Cần Python 3.10+, ODA File Converter (để đọc DWG) |
| Mỗi lần dùng: bấm đúp `CHAY_AZB.bat` | Người dùng | Tự mở trình duyệt |
| File bản vẽ kết cấu | Phòng thiết kế | Mỗi file có thể chứa nhiều mặt bằng |
| Biết trước cao độ từng tầng | Kỹ sư kết cấu | Dùng cho bước 3 |

Mẹo: file DWG nặng thì **lần đầu tải lên chậm** (file mẫu khoảng 1 phút), các lần sau gần như tức thì. Trong lúc đó máy tự tách mặt bằng ngầm.

## 3. Quy trình 8 bước

### Bước 1. Tải bản vẽ lên
Kéo file vào, hoặc bấm tải lên. Chờ đến khi bản vẽ hiện ra.
**Kết quả:** thấy bản vẽ trên màn hình.

### Bước 2. Tách các mặt bằng (tab "Tách mặt bằng")
Một file thường chứa nhiều mặt bằng (móng, tầng 1, tầng 2, mái...). Máy dò và vẽ khung từng mặt bằng.
- Tick các khung cần dùng, bấm **Tạo mục**: mỗi mặt bằng thành một mục trong "Bản vẽ trong dự án".
- Khung sai (cắt đôi, dính nhau): chỉnh ngưỡng rồi *Dò lại*, hoặc sửa tay ô vùng.
- Mặt bằng dùng cho nhiều tầng giống nhau thì bấm nút nhân bản ⧉; **mục nhân bản phải gán lại layer và tầng**, đừng để nguyên của mục gốc.

**Kết quả:** mỗi mặt bằng là một mục riêng, bấm vào thì bản vẽ phóng tới đúng vùng đó.

### Bước 3. Gán layer (tab "Gán layer")
Mỗi mặt bằng, chỉ cho máy biết layer nào là cột, dầm (khung dầm), sàn, móng, cọc. Máy tự đoán theo tên layer, người dùng sửa lại nếu sai. Layer không liên quan chọn **Bỏ qua**.
- Mặt bằng chỉ có khung dầm, không có layer sàn: máy **tự suy ra dầm và sàn** (sàn = ô trống giữa các dầm). Ô có **dấu X** là lỗ mở, máy bỏ ra khỏi sàn.
- Nhãn dầm dạng `3X2`, `1HR`... máy đọc được kích thước và số tầng.

**Kết quả:** mỗi mặt bằng có danh sách cấu kiện kèm cảnh báo.

### Bước 4. Lập hệ quy chiếu (tab "Hệ quy chiếu") — làm **một lần** cho cả dự án
Đây là bước quan trọng nhất: đặt mọi mặt bằng vào **cùng một hệ toạ độ**.

1. **Lưới trục:** dùng *Chọn đường trục trên bản vẽ*, bấm vào các đường tim trục (hoặc *Dò trục từ bản vẽ này*). Kiểm tra tên trục (A, B, 1, 2...) đúng.
2. **Điểm gốc:** chọn giao của một trục dọc và một trục ngang (ví dụ A-1).
3. **Bảng tầng:** nhập tên tầng, cao độ kết cấu (ví dụ `+3.600`), chiều cao tầng tự tính. Có tầng mái và đỉnh mái nếu có.

**Kết quả:** khung toạ độ chung. Người kiểm: kỹ sư kết cấu, đối chiếu cao độ với bản vẽ.

### Bước 5. Gán vùng cho từng mặt bằng (cũng trong tab "Hệ quy chiếu")
Với mỗi mặt bằng: chọn **tầng**, **loại cấu kiện**, rồi bấm **Dò + căn tự động**. Máy khớp trục của mặt bằng vào lưới chuẩn (nhiều trục trùng tên thì máy bỏ phiếu chọn trục đúng).
- Xem bảng độ lệch từng trục: **lệch ≤ 50 mm** là đạt. Lệch lớn thì chọn lại điểm căn bằng tay.
- Đạt rồi mới tick **Đã xác nhận**.
- **Không** bấm "Dò trục + căn tự động tất cả" khi đã xác nhận xong, vì nó xoá các ô xác nhận.

**Kết quả:** mỗi mặt bằng nằm đúng chỗ trong toạ độ công trình.

### Bước 6. Tính và tổng hợp
Bấm **Tính và tổng hợp**. Ra cây **Tầng → Cấu kiện → Đối tượng** với toạ độ, cao độ đáy/đỉnh, diện tích, thể tích. Bấm một dòng để thấy cấu kiện sáng lên trên bản vẽ.
- Mục "bỏ qua" ghi lý do (khác loại khai báo, hình dầm rộng hơn 1,2 m là khung ghi chú...).
- Xuất CSV: tick tầng / cấu kiện cần lấy, chỉ các dòng đã tick được xuất. (Nút "Đưa về tim trục" cũ đã bỏ vì chỉ ghi ghi chú, không có tác dụng.)

**Lưu ý:** danh sách tổng hợp không lưu, mở app lại thì bấm tính lại.

### Bước 7. Dựng 3D
Bấm **Dựng 3D theo hệ quy chiếu** (nút cam). Xem mô hình, xoay bằng chuột trái, zoom bằng lăn chuột.
- Phím `1` góc 3D, `2` nhìn từ trên, `3` trước, `4` phải, `F` vừa khung.
- Bấm một khối để xem tên, kích thước, thể tích. Phím `H` ẩn, `I` cô lập, `A` hiện lại.
- Ba kiểu hiển thị: **công nghệ** (mặc định, màu theo loại), **chân thực** (bê tông, cỏ, trời), **phân loại**. Chọn ở tab *Mô hình*.
- Xuất `.glb` mở bằng SketchUp, Blender, Revit; chụp ảnh PNG.

Dùng 3D để **kiểm tra bằng mắt**: cột có thẳng hàng trục, dầm có đúng tầng, có cấu kiện nào lơ lửng hoặc thiếu.

### Bước 8. Kiểm tra và bàn giao
- Kỹ sư kết cấu rà các mục cảnh báo và các giả định (xem mục 5).
- Xuất Excel khối lượng.
- Bấm **Sao lưu** trước khi tắt hoặc khởi động lại app.

## 4. Dữ liệu lưu ở đâu, có sợ mất không

- Số liệu làm việc tự lưu vào `data/du_an/trang_thai.json`; bản sao lưu tự động ở `data/backup/` (zip). Phần mềm cũng tự thử nạp lại nhiều lần khi khởi động.
- Lỡ mất: dùng chức năng khôi phục từ bản sao lưu (nhờ người phụ trách).
- **Trước khi khởi động lại app: bấm Sao lưu.**

## 5. Những điểm phải có người kiểm (chưa chắc chắn)

| Điểm | Vì sao | Ai xác nhận |
|---|---|---|
| Loại cọc từng cọc (dài 26 m hay 12 m) | Bản vẽ chưa đủ để máy biết | Phòng thiết kế |
| Dầm biên rộng 200 mm (T2, T4, đỉnh mái) | Máy giả định khi suy dầm | Kỹ sư kết cấu |
| Dày sàn 120 mm | Lấy theo bảng tầng, cần đối chiếu | Kỹ sư kết cấu |
| Lỗ sàn không có dấu X | Máy không biết là lỗ | Người bóc |
| Khung nhỏ trên mái (4 cột + dầm) | Có thể là chỗ đỡ bể nước, chưa chắc | Phòng thiết kế |
| Tường, cửa | Bản vẽ kết cấu không có; 3D chỉ có khung | Cần bản kiến trúc nếu muốn dựng |

## 6. Gợi ý trình bày với các phòng ban

| Phòng | Họ cần biết |
|---|---|
| Thiết kế / kết cấu | Bước 3, 4, 5 và mục 5: nơi cần xác nhận chuyên môn |
| Dự toán / QS | Bước 6: bảng khối lượng Tầng → Cấu kiện, xuất Excel, đối chiếu sai lệch ≤ 2% với bóc tay |
| Chỉ huy công trường / quản lý | Bước 7: 3D để hình dung công trình, xuất ảnh |
| IT | Mục 2: cài đặt, nhật ký lỗi (`XEM_NHAT_KY.bat`), sao lưu |

Giới hạn cần nói thật khi trình bày: công cụ **đề xuất và hỗ trợ**, không thay kỹ sư kết cấu; khối lượng phải được người có chuyên môn xác nhận trước khi dùng.
