# vi_doc_rag — Module thu thập & xử lý tài liệu tiếng Việt

## Cài đặt và chạy thử (Windows PowerShell)

Mở terminal tại thư mục cha chứa thư mục `vi_doc_rag/`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r vi_doc_rag\requirements.txt
python -m vi_doc_rag --help
python -m vi_doc_rag vi_doc_rag\samples\mau_tieng_viet.txt --out vi_doc_rag\ket_qua_mau.jsonl --chunk-size 450 --overlap 80 --preview 3
python -m unittest discover -s vi_doc_rag -p "test_*.py" -v
```

Nếu chỉ chạy `.txt` hoặc `.md`, không cần cài thêm thư viện ngoài. Để đọc PDF/DOCX, cài `requirements.txt`. Để mở hộp thoại chọn file hoặc thư mục, chạy `python -m vi_doc_rag` không kèm đường dẫn.

## Đầu ra cần kiểm tra

- Terminal: preview của tối đa 3 chunk, gồm nội dung và metadata.
- `vi_doc_rag/ket_qua_mau.jsonl`: toàn bộ chunk, mỗi dòng là một JSON object có `id`, `text`, `metadata`.
- Metadata có tên file nguồn, mục, khoảng trang (nếu có), số ký tự và số từ.

Có thể mở JSONL bằng VS Code hoặc đọc từng dòng trong Python:

```python
import json
with open("vi_doc_rag/ket_qua_mau.jsonl", encoding="utf-8") as f:
    for line in f:
        chunk = json.loads(line)
        print(chunk["metadata"]["chunk_index"], chunk["metadata"]["section"])
        print(chunk["text"])
```

## Dùng trong Python

```python
from vi_doc_rag import IngestionPipeline, ChunkConfig

pipeline = IngestionPipeline(ChunkConfig(chunk_size=800, chunk_overlap=100))
chunks = pipeline.process_file("tai_lieu.docx")
print(chunks[0].text, chunks[0].metadata)
```

## Giới hạn hiện tại

PDF scan cần OCR; PDF nhiều cột hoặc bảng phức tạp có thể sai thứ tự đọc; PDF dùng bảng mã tiếng Việt cũ mới được cảnh báo, chưa tự chuyển mã. Chunk size đang tính theo ký tự, chưa theo token của mô hình embedding. Cần đối chiếu ngẫu nhiên nội dung trích xuất với file gốc trước khi đưa vào RAG.

## Module embedding và lưu trữ vector

Sau khi tạo `ket_qua_mau.jsonl`, cài thêm `python -m pip install -r vi_doc_rag\requirements-embedding.txt`, rồi chạy `python -m vi_doc_rag.vector_store --db-path vi_doc_rag\vector_db --batch-size 4 index vi_doc_rag\ket_qua_mau.jsonl`. Chạy file show_vector_db.py để kiểm tra các chunk đã được embedding sang vector.
