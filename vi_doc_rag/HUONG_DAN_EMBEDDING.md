# Hướng dẫn module embedding và ChromaDB

Tài liệu này bổ sung bước sau module `vi_doc_rag` hiện có. Module ingestion vẫn đọc PDF/DOCX/TXT/MD, làm sạch và chia chunk; module mới biến từng chunk thành vector rồi lưu vector, nội dung và metadata vào ChromaDB cục bộ.

## 1. Luồng dữ liệu

```text
tài liệu gốc
  -> vi_doc_rag (loaders.py -> cleaner.py -> chunker.py)
  -> JSONL: {id, text, metadata}
  -> vector_store.py: Sentence Transformers encode(text)
  -> ChromaDB persistent trên ổ đĩa
  -> lúc tìm kiếm: encode(câu hỏi) -> Chroma query -> top-k chunk + metadata
```

Embedding model chỉ biến văn bản thành vector số. ChromaDB giữ vector cùng nội dung chunk và metadata; nó không tạo câu trả lời. Bước sinh câu trả lời bằng LLM được nối sau này.

## 2. Vì sao chọn thiết kế này?

- Model mặc định: `AITeamVN/Vietnamese_Embedding_v2`, chạy bằng Sentence Transformers trên CPU. Model card công bố ngôn ngữ tiếng Việt, vector 1024 chiều, tối đa 2048 token và similarity bằng dot product.
- Vector được chuẩn hóa L2 trước khi lưu. Với vector chuẩn hóa, xếp hạng cosine và dot product tương đương; Chroma được đặt metric cosine.
- Vector của tài liệu và câu hỏi phải dùng cùng model. Mặc định model này không cần tiền tố `passage:` / `query:`.
- Chroma lưu nội dung cùng metadata như file nguồn, số trang, mục và chỉ số chunk. Giá trị `null` được bỏ qua vì metadata Chroma cần kiểu dữ liệu scalar.
- Khi re-index, các chunk cũ của cùng `source` bị xóa trước khi ghi chunk mới, tránh kết quả tìm kiếm trả về nội dung lỗi thời.
- Thay model thì tạo DB/collection mới hoặc xóa và tạo lại chỉ mục; không thể so sánh vector từ hai model khác nhau trong cùng không gian.

## 3. Cài đặt trên Windows PowerShell

Mở PowerShell tại thư mục cha chứa `vi_doc_rag` và bật virtual environment đang dùng cho module ingestion:

```powershell
..venv\Scripts\Activate.ps1
python -m pip install -r vi_doc_rag\requirements-embedding.txt
```

Lần đầu chạy, Sentence Transformers tải model từ Hugging Face. Cần có Internet trong lần tải đầu; trọng số model được cache trên máy để các lần sau chạy local.

## 4. Tạo vector database từ JSONL

Trước tiên xuất chunk JSONL như cũ. Ví dụ:

```powershell
python -m vi_doc_rag vi_doc_rag\samples\mau_tieng_viet.txt `
  --out vi_doc_rag\ket_qua_mau.jsonl `
  --chunk-size 450 --overlap 80 --preview 3
```

Sau đó nhúng và lưu vào ChromaDB:

```powershell
python -m vi_doc_rag.vector_store `
  --db-path vi_doc_rag\vector_db `
  --collection tai_lieu_tieng_viet `
  --batch-size 4 `
  index vi_doc_rag\ket_qua_mau.jsonl
```

`--batch-size 4` giảm mức dùng RAM/tải CPU trên máy phổ thông. Có thể thử tăng sau khi đo thời gian và mức sử dụng RAM. Không cần có GPU NVIDIA; có thể chỉ định `--device cpu` để ép chạy CPU.

## 5. Tìm đoạn liên quan

```powershell
python -m vi_doc_rag.vector_store `
  --db-path vi_doc_rag\vector_db `
  --collection tai_lieu_tieng_viet `
  search "Nội dung nào cần ôn tập về xử lý ngôn ngữ tự nhiên?" `
  --top-k 3
```

Kết quả hiển thị nội dung, nguồn, trang, mục, cosine similarity. Similarity là điểm xếp hạng tương đối trong các kết quả của lần tìm kiếm; không nên coi một ngưỡng cố định là xác suất đúng. So sánh đoạn trả về với tài liệu gốc.

## 6. Kiểm tra và báo cáo tiến độ

Chụp lại các bằng chứng sau:

1. JSONL đầu vào có `id`, `text`, `metadata`.
2. Terminal chạy lệnh `index`, số chunk được lưu và đường dẫn DB.
3. Terminal chạy `search`, câu hỏi và top-k kết quả kèm tên file/trang.
4. Thư mục `vector_db` được tạo và có dữ liệu sau lần index.

Một phép thử tốt nên có vài câu hỏi mà bạn biết trước chunk/trang chứa đáp án. Ghi lại câu hỏi, chunk đúng mong đợi, hạng kết quả đúng (1, 2, ...), và thời gian chạy. Lặp lại cùng bộ câu hỏi khi thay embedding model.

## 7. Giới hạn và lưu ý

- Module này nhận JSONL do ingestion hiện tại xuất ra; nó không đọc PDF/DOCX trực tiếp và chưa xử lý OCR.
- Chunker hiện đếm ký tự. Trước khi chạy embedding, module đếm token bằng tokenizer của model và báo lỗi nếu chunk vượt giới hạn, thay vì cắt nội dung âm thầm.
- Với JSONL thông thường của module, `source` là đường dẫn nguồn. Khi chạy lại cùng tài liệu và cùng `source`, các chunk của tài liệu đó được thay mới.
- Vector dimension hiện là 1024 theo model mặc định. Đổi model thì không tái sử dụng vector cũ.
- Chỉ chạy `index` trên dữ liệu tin cậy; file JSONL có nguồn khác nhau được quản lý theo metadata `source`.
- Để demo tái lập, ghi lại model, phiên bản thư viện, chunk size/overlap, batch size, số chunk và đường dẫn DB.

## 8. Thay model để so sánh

Có thể thử `intfloat/multilingual-e5-large-instruct` bằng tham số `--model`, nhưng hãy dùng DB/collection mới:

```powershell
python -m vi_doc_rag.vector_store `
  --model intfloat/multilingual-e5-large-instruct `
  --db-path vi_doc_rag\vector_db_e5 `
  --collection tai_lieu_e5 `
  index vi_doc_rag\ket_qua_mau.jsonl
```

Trong bước query, model E5 instruct yêu cầu câu truy vấn có chỉ dẫn một câu như:

```text
Instruct: Given a question in Vietnamese, retrieve passages that answer it
Query: Nội dung nào cần ôn tập về xử lý ngôn ngữ tự nhiên?
```

Module tự thêm query instruction cho model E5 instruct; có thể đổi câu chỉ dẫn bằng `--query-instruction`. Tài liệu chunk không thêm instruction. Không so sánh chỉ dựa trên con số cosine giữa hai model; hãy so sánh xem đoạn nguồn đúng có xuất hiện trong top-k hay không.
