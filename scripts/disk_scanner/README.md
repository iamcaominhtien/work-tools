# Disk Scanner — Quét & phân tích dung lượng ổ đĩa (1 file, chạy bằng uv)
 
Script duy nhất `disk_scanner.py` quét đệ quy toàn bộ cây thư mục (folder,
folder con, file...) và hiển thị kết quả trực quan trên console: cây thư
mục theo dung lượng giảm dần, bảng top các mục nặng nhất, tóm tắt tổng
quan và thông tin ổ đĩa vật lý.
 
## Yêu cầu
 
- Đã cài **uv** (https://docs.astral.sh/uv/). Nếu chưa có:
  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh        # Linux/Mac
  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"  # Windows
  ```
- Không cần tạo virtualenv, không cần `pip install` thủ công — **uv tự lo
  hết**. Script có khai báo dependency ngay trong file (chuẩn PEP 723),
  uv đọc thấy và tự tải `cython` + `setuptools` vào môi trường tạm trước
  khi chạy.
- Để có mức tăng tốc tối đa cần có **trình biên dịch C** sẵn trên máy
  (Linux/Mac thường có sẵn `gcc`/`clang`; Windows cần cài "Microsoft C++
  Build Tools"). **Không bắt buộc** — nếu không có, script tự động dùng
  lại lõi quét thuần Python, vẫn chạy đúng chức năng, chỉ không có phần
  tăng tốc bằng C.
 
## Cách chạy
 
```bash
uv run disk_scanner.py                          # quét thư mục hiện tại
uv run disk_scanner.py /đường/dẫn/cần/quét
uv run disk_scanner.py "C:\Users\Ten\Documents"  # Windows
```
 
Lần chạy **đầu tiên** sẽ hơi lâu hơn một chút (vài giây) vì uv tải
`cython` và script tự biên dịch lõi quét C. Các lần chạy **sau** sẽ nhanh
gần như ngay lập tức vì đã cache extension đã build sẵn tại:
 
- Linux/Mac: `~/.cache/disk_scanner_cy/`
- Windows: `%LOCALAPPDATA%\disk_scanner_cy\`
 
Muốn build lại từ đầu (ví dụ sau khi đổi máy hoặc nghi ngờ cache lỗi),
chỉ cần xóa thư mục cache ở trên rồi chạy lại.
 
## Tùy chọn dòng lệnh
 
| Tùy chọn              | Ý nghĩa                                                        |
|------------------------|-----------------------------------------------------------------|
| `path`                 | Đường dẫn thư mục cần quét (mặc định: thư mục hiện tại)         |
| `--top N`              | Số mục hiển thị mỗi cấp trong cây (mặc định 10)                 |
| `--depth N`            | Độ sâu tối đa hiển thị cây (mặc định 3, quét vẫn full depth)    |
| `--min-size SIZE`      | Bỏ qua file nhỏ hơn kích thước này, vd `10MB`, `512KB`, `1GB`    |
| `--top-table N`        | Số dòng trong bảng "Top nặng nhất" (mặc định 15)                |
| `--files-only`         | Bảng top chỉ tính file, không tính thư mục                      |
| `--no-color`           | Tắt màu console (hữu ích khi xuất log ra file)                  |
| `--follow-symlinks`    | Đi theo symlink khi quét (mặc định bỏ qua để tránh vòng lặp)    |
| `--no-progress`        | Không hiển thị dòng tiến trình khi đang quét                    |
| `--no-cython`          | Ép dùng lõi Python thuần, bỏ qua bước build/dùng Cython          |
 
## Ví dụ
 
```bash
uv run disk_scanner.py . --top 20 --depth 4
uv run disk_scanner.py /var/log --min-size 1MB --files-only
uv run disk_scanner.py D:\Projects --no-color > report.txt
```
 
## Cơ chế hoạt động (tóm tắt)
 
- Script **chỉ 1 file** nhưng bên trong nhúng sẵn mã nguồn Cython dưới
  dạng chuỗi. Lần chạy đầu, mã này được ghi ra một `.pyx` tạm trong thư
  mục cache và biên dịch bằng `pyximport` (dùng compiler C trên máy) —
  cho lõi quét gọi thẳng `opendir/readdir/lstat` ở mức hệ điều hành.
- Nếu không biên dịch được (thiếu compiler, môi trường hạn chế...), script
  tự động rơi về lõi quét bằng `os.scandir` thuần Python, không lỗi,
  không cần thao tác gì thêm từ người dùng.
- Dòng "TÓM TẮT QUÉT DUNG LƯỢNG" ở cuối luôn ghi rõ đang chạy bằng lõi
  nào (`Cython/C` hay `Pure Python`) để bạn biết trạng thái thực tế.
 
**Lưu ý về tốc độ:** qua benchmark thực tế, lõi Cython/C chủ yếu có lợi
khi ổ đĩa/khối lượng file rất lớn hoặc cache hệ thống lạnh; với các thư
mục vừa/nhỏ hoặc cache đã "ấm", `os.scandir` của Python (vốn cũng là C
bên trong CPython) đã đủ nhanh, nên chênh lệch có thể không lớn.