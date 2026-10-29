## [0.3.0] — 2026-10-25 — Đồng bộ cấu trúc package và hướng dẫn demo
**Loại:** Sửa lỗi / Tài liệu | **Module:** package `vi_doc_rag/`, `README.md`, `test_ingestion.py`

**Lý do:** ZIP thiếu `models.py`; code, test và README không thống nhất cách gọi package nên module không khởi chạy từ bản nén.

**Thay đổi:** thêm `models.py` và `__init__.py`; thống nhất chạy bằng `python -m vi_doc_rag`; sửa đường dẫn import trong test; nhận diện heading ở giữa đoạn; bổ sung tài liệu TXT mẫu và hướng dẫn tạo JSONL; test PDF nhận diện font Windows và tự bỏ qua rõ ràng khi thiếu `reportlab`.

**Kết quả kiểm tra:** 16 test đạt, 1 test PDF được bỏ qua do môi trường hiện tại chưa cài `reportlab`; demo TXT tạo được 4 chunk.

---
# BÁO CÁO THAY ĐỔI (CHANGELOG) — Chatbot RAG tài liệu tiếng Việt

> **Quy ước:** mỗi lần chỉnh sửa code đều thêm 1 mục mới Ở TRÊN CÙNG (mới nhất lên đầu),
> theo mẫu ở cuối file. Đánh số phiên bản theo dạng `0.<giai đoạn>.<lần sửa>`.

---

## [0.2.0] — 2026-10-22 — Chọn file/thư mục bằng hộp thoại + cấu hình chạy trong VS Code
**Loại:** Tính năng mới | **Module:** `ingestion/picker.py` (mới), `ingestion/__main__.py`, `.vscode/launch.json` (mới), `tests/`

**Lý do:** người dùng muốn chọn tài liệu từ máy thay vì gõ đường dẫn; chạy trực tiếp trong VS Code.

**Thay đổi:**
- `picker.py`: cửa sổ nhỏ có 2 nút "Chọn 1 file" / "Chọn cả thư mục" (tkinter). Nếu máy không có tkinter hoặc không có giao diện đồ hoạ thì tự chuyển sang nhập đường dẫn trong terminal.
- `__main__.py`: tham số `path` giờ là tuỳ chọn (bỏ trống → mở hộp thoại); thêm `--preview N` (in N chunk đầu ra màn hình, mặc định 3); in đường dẫn tuyệt đối của file kết quả; báo lỗi rõ khi đường dẫn không tồn tại hoặc không tạo được chunk; ép stdout/stderr UTF-8 (tránh lỗi tiếng Việt trên terminal Windows).
- `.vscode/launch.json`: 2 cấu hình bấm F5 — "Chạy thử (hộp thoại)" và "Chạy test tự động".
- `tests/`: thêm test CLI chạy theo đường dẫn và test chế độ dự phòng của picker.

**Ảnh hưởng:** tương thích ngược — cách gọi có đường dẫn vẫn hoạt động như cũ.

**Kết quả test:** 16/16 đạt (môi trường Linux không có tkinter/màn hình). **Chưa kiểm thử hộp thoại đồ hoạ thật** trên Windows/macOS — cần người dùng xác nhận.

---

## [0.1.1] — 2026-10-21 — Sửa lỗi nhận diện header/footer
**Loại:** Sửa lỗi | **Module:** `ingestion/cleaner.py`, `tests/test_ingestion.py`

**Vấn đề phát hiện khi chạy test:** `remove_headers_footers` xoá nhầm nội dung thân trang khi trang
có ít dòng (toàn bộ trang bị coi là "mép" trang), hoặc khi các trang có dòng chỉ khác nhau chữ số.

**Thay đổi:**
- `scan_lines` mặc định giảm từ 3 → 2 (header/footer thực tế thường 1–2 dòng).
- Trang có ≤ `2 × scan_lines` dòng không tham gia dò header/footer lặp (chỉ áp dụng regex số trang).
- Test: dùng nội dung thân trang khác nhau giữa các trang cho giống thực tế; đóng file đúng cách trong test JSONL.

**Kết quả test:** 14/14 đạt.

---

## [0.1.0] — 2026-10-21 — Khởi tạo module thu thập & xử lý tài liệu
**Loại:** Tính năng mới | **Module:** `vi_doc_rag/ingestion/*`, `tests/`

**Thêm mới:**
| File | Chức năng |
|---|---|
| `ingestion/models.py` | `RawDocument`, `Chunk` (dataclass) |
| `ingestion/loaders.py` | Đọc PDF (pypdf, fallback pdfplumber cho trang trống), DOCX (giữ thứ tự đoạn/bảng, heading → `# `), TXT/MD (thử utf-8 → utf-16 → cp1258) |
| `ingestion/cleaner.py` | Chuẩn hoá Unicode NFC, bỏ ký tự rác/zero-width/ligature, xoá dấu chấm dẫn mục lục, xoá header/footer lặp + số trang, nối dòng bị ngắt cứng, sửa khoảng trắng trước dấu câu, phát hiện lỗi font |
| `ingestion/chunker.py` | Chunk theo câu → đoạn → mục; không cắt sau viết tắt (TS., TP., PGS.…); overlap theo câu; tự cắt theo từ nếu câu quá dài; gắn metadata `section`, `page_start`, `page_end`, … |
| `ingestion/pipeline.py` | `IngestionPipeline`: `process_file`, `process_directory`, `save_jsonl` |
| `ingestion/__main__.py` | CLI: `python -m vi_doc_rag.ingestion <đường dẫn> --out chunks.jsonl` |
| `tests/test_ingestion.py` | 14 test (NFC, header/footer, nối dòng, viết tắt, overlap, DOCX, PDF, JSONL…) |

**Quyết định thiết kế:**
- Module **không phụ thuộc LangChain/LlamaIndex** → dùng được với cả hai (chỉ cần bọc `Chunk` → `Document`/`TextNode`).
- Đơn vị `chunk_size` là **ký tự** (mặc định 800, overlap 100); sẽ đổi sang token khi chọn xong mô hình embedding.
- Chưa có bước tách từ (word segmentation, vd. `underthesea`/`pyvi`) — để dành khi chọn embedding cần tách từ (PhoBERT-based).

**Hạn chế đã biết (chưa xử lý):**
- PDF scan (dạng ảnh) chưa có OCR → chỉ cảnh báo.
- PDF dùng font cũ (TCVN3/VNI) bị lỗi mã hoá → mới phát hiện & cảnh báo, chưa chuyển mã.
- PDF nhiều cột / bảng phức tạp có thể bị lẫn thứ tự dòng.
- Nhận diện heading trong PDF dựa trên heuristic (Chương/Điều/Mục, 1.2…, IN HOA), có thể sót/nhầm.

**Kết quả test:** 14/14 đạt (Python 3.12).

---

## Mẫu cho lần sửa tiếp theo
```
## [x.y.z] — YYYY-MM-DD — Tiêu đề ngắn
**Loại:** Tính năng mới | Sửa lỗi | Tối ưu | Tái cấu trúc | Tài liệu   **Module:** ...
**Lý do:** ...
**Thay đổi:** (file nào, sửa gì)
**Ảnh hưởng / lưu ý tương thích:** ...
**Kết quả test:** ...
```


