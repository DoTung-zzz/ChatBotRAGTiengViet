"""CLI / chạy thử.

  python -m vi_doc_rag                  -> mở hộp thoại chọn file/thư mục
  python -m vi_doc_rag <file|thư mục>   -> chạy thẳng trên đường dẫn đó
"""
import argparse
import logging
import os
import sys

from .chunker import ChunkConfig
from .pipeline import IngestionPipeline


def _preview(chunks, n: int) -> None:
    for c in chunks[:n]:
        m = c.metadata
        print("=" * 70)
        print(f"chunk {m['chunk_index']}/{m['total_chunks'] - 1} | file: {m.get('filename')} | "
              f"mục: {m['section']} | trang: {m['page_start']}-{m['page_end']} | {m['char_count']} ký tự")
        print("-" * 70)
        print(c.text)
    if len(chunks) > n:
        print("=" * 70)
        print(f"... còn {len(chunks) - n} chunk nữa (xem đầy đủ trong file kết quả)")


def main():
    # Windows: tránh lỗi hiển thị tiếng Việt trong terminal
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass

    ap = argparse.ArgumentParser(description="Đọc, làm sạch và chia chunk tài liệu tiếng Việt")
    ap.add_argument("path", nargs="?", help="File (.pdf/.docx/.txt/.md) hoặc thư mục; bỏ trống để chọn bằng hộp thoại")
    ap.add_argument("--out", default="chunks.jsonl")
    ap.add_argument("--chunk-size", type=int, default=800)
    ap.add_argument("--overlap", type=int, default=100)
    ap.add_argument("--prepend-section", action="store_true")
    ap.add_argument("--keep-headers", action="store_true", help="Không xoá header/footer")
    ap.add_argument("--preview", type=int, default=3, help="Số chunk in ra màn hình (mặc định 3)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    path = args.path
    if not path:
        from .picker import pick_path
        path = pick_path()
        if not path:
            print("Chưa chọn gì, thoát.")
            return
    if not os.path.exists(path):
        sys.exit(f"Không tìm thấy: {path}")

    cfg = ChunkConfig(args.chunk_size, args.overlap, prepend_section=args.prepend_section)
    pipe = IngestionPipeline(cfg, remove_headers_footers=not args.keep_headers)
    chunks = pipe.process_directory(path) if os.path.isdir(path) else pipe.process_file(path)
    if not chunks:
        sys.exit("Không tạo được chunk nào (file trống, sai định dạng hoặc là PDF scan).")

    pipe.save_jsonl(chunks, args.out)
    _preview(chunks, args.preview)
    print(f"\nĐã xử lý: {path}")
    print(f"Tổng {len(chunks)} chunk -> {os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()

