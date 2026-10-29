"""Pipeline: đọc file -> làm sạch -> chia chunk."""
from __future__ import annotations

import json
import logging
import os
from typing import Iterable, List, Optional

from .chunker import ChunkConfig, VietnameseChunker, build_blocks
from .cleaner import clean_pages, looks_garbled
from .loaders import SUPPORTED_EXTENSIONS, load_document
from .models import Chunk

logger = logging.getLogger(__name__)


class IngestionPipeline:
    def __init__(self, chunk_config: Optional[ChunkConfig] = None, remove_headers_footers: bool = True):
        self.chunker = VietnameseChunker(chunk_config)
        self.remove_hf = remove_headers_footers

    def process_file(self, path: str) -> List[Chunk]:
        raw = load_document(path)
        if any(looks_garbled(p) for p in raw.pages):
            logger.warning("%s: nghi ngờ lỗi font/encoding (ký tự lạ) - kiểm tra lại file gốc.", path)
        pages = clean_pages(raw.pages, remove_hf=self.remove_hf and raw.has_pages)
        blocks = build_blocks(pages, raw.has_pages)
        if not blocks:
            logger.warning("%s: không có nội dung sau khi làm sạch.", path)
            return []
        base = {k: v for k, v in raw.metadata.items() if k != "empty_pages"}
        chunks = self.chunker.split(blocks, source=path, base_metadata=base)
        logger.info("%s -> %d chunk", path, len(chunks))
        return chunks

    def process_directory(self, directory: str, recursive: bool = True) -> List[Chunk]:
        chunks: List[Chunk] = []
        for path in self._iter_files(directory, recursive):
            try:
                chunks.extend(self.process_file(path))
            except Exception as exc:  # noqa: BLE001  (1 file lỗi không làm hỏng cả lô)
                logger.error("Bỏ qua %s do lỗi: %s", path, exc)
        return chunks

    @staticmethod
    def _iter_files(directory: str, recursive: bool) -> Iterable[str]:
        for root, _, files in os.walk(directory):
            for f in sorted(files):
                if os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS:
                    yield os.path.join(root, f)
            if not recursive:
                break

    @staticmethod
    def save_jsonl(chunks: List[Chunk], out_path: str) -> None:
        with open(out_path, "w", encoding="utf-8") as f:
            for c in chunks:
                f.write(json.dumps(c.to_dict(), ensure_ascii=False) + "\n")
