"""Chia văn bản tiếng Việt thành các chunk theo ranh giới câu / đoạn / mục.

Không phụ thuộc framework: sau này có thể bọc lại thành TextSplitter của
LangChain hoặc NodeParser của LlamaIndex mà không phải viết lại logic.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import List, Optional

from .models import Chunk

# Viết tắt thường gặp có dấu chấm -> không cắt câu sau chúng
_ABBREV_RE = re.compile(
    r"(?:^|\s)(?:TP|Tp|PGS|GS|TS|ThS|BS|KS|CN|Mr|Mrs|Ms|Dr|St|vs|TT|ĐH|Q|P|Tr|No|tr|v\.v|Nxb|NXB)\.$"
)
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?…])\s+")
_HEADING_RE = re.compile(
    r"^(?:(?:chương|phần|mục|điều|phụ lục|bài|chuyên đề)\s+[\dIVXLC]+\b"
    r"|\d{1,2}(?:\.\d{1,2}){0,3}[.)]?\s+[A-ZÀ-Ỹ])",
    re.IGNORECASE,
)


@dataclass
class ChunkConfig:
    chunk_size: int = 800          # số ký tự tối đa mỗi chunk
    chunk_overlap: int = 100       # số ký tự chồng lấp giữa 2 chunk liên tiếp
    min_chunk_size: int = 200      # gặp heading mới mà chunk hiện tại >= ngưỡng này thì cắt luôn
    prepend_section: bool = False  # thêm "[Tên mục]" vào đầu chunk (giúp retrieval)

    def __post_init__(self):
        if self.chunk_size <= 0:
            raise ValueError("chunk_size phải > 0")
        if not 0 <= self.chunk_overlap < self.chunk_size:
            raise ValueError("chunk_overlap phải nằm trong [0, chunk_size)")


@dataclass
class Block:
    """Một đoạn văn / heading / bảng sau khi làm sạch, kèm số trang."""
    text: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    is_heading: bool = False


@dataclass
class _Unit:
    text: str
    sep: str                 # chuỗi nối với unit đứng trước
    page_start: Optional[int]
    page_end: Optional[int]
    section: Optional[str]
    is_heading: bool = False


# ------------------------------------------------------------------ helpers
def is_heading_line(line: str) -> bool:
    s = line.strip()
    if s.startswith("#"):
        return True
    if not s or len(s) > 120 or "\n" in s or re.search(r"[.!?;,]$", s):
        return False
    if _HEADING_RE.match(s):
        return True
    letters = [c for c in s if c.isalpha()]
    return len(letters) >= 3 and s.isupper() and len(s.split()) <= 15


def split_sentences(text: str) -> List[str]:
    """Tách câu, không cắt sau các từ viết tắt như TP., PGS., TS., v.v."""
    pieces = [p for p in _SENT_SPLIT_RE.split(text.strip()) if p]
    out: List[str] = []
    for p in pieces:
        if out and (_ABBREV_RE.search(out[-1]) or p[:1].islower()):
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def _split_long(text: str, size: int) -> List[str]:
    """Cắt câu quá dài theo từ (không bao giờ cắt giữa 1 âm tiết)."""
    parts, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > size:
            parts.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        parts.append(cur)
    return parts


def build_blocks(pages: List[str], has_pages: bool) -> List[Block]:
    """Từ các trang đã làm sạch -> Block; nhận diện heading kể cả khi cùng đoạn."""
    blocks: List[Block] = []

    def add_body(text: str, page_no: Optional[int]) -> None:
        text = text.strip()
        if not text:
            return
        if (
            blocks and has_pages and page_no is not None and page_no > 1
            and not blocks[-1].is_heading and blocks[-1].page_end == page_no - 1
            and not re.search(r"[.!?…:;]$", blocks[-1].text)
            and text[:1].islower() and "\n" not in blocks[-1].text
        ):
            blocks[-1].text += " " + text
            blocks[-1].page_end = page_no
        else:
            blocks.append(Block(text, page_no, page_no, False))

    for idx, page in enumerate(pages):
        pno = idx + 1 if has_pages else None
        for para in re.split(r"\n{2,}", page):
            lines = [line.strip() for line in para.splitlines() if line.strip()]
            body_lines: List[str] = []

            def flush_body() -> None:
                if body_lines:
                    add_body("\n".join(body_lines), pno)
                    body_lines.clear()

            for line in lines:
                if is_heading_line(line):
                    flush_body()
                    blocks.append(Block(line, pno, pno, True))
                else:
                    body_lines.append(line)
            flush_body()
    return blocks

def _blocks_to_units(blocks: List[Block], size: int) -> List[_Unit]:
    units: List[_Unit] = []
    section: Optional[str] = None
    for b in blocks:
        if b.is_heading:
            section = b.text.lstrip("#").strip()
            units.append(_Unit(section, "\n\n", b.page_start, b.page_end, section, True))
            continue
        first_in_block = True
        for line in b.text.split("\n"):
            line = line.strip()
            if not line:
                continue
            sents = split_sentences(line)
            for j, s in enumerate(sents):
                for k, piece in enumerate(_split_long(s, size) if len(s) > size else [s]):
                    if first_in_block:
                        sep = "\n\n"
                    elif j == 0 and k == 0:
                        sep = "\n"      # dòng mới trong cùng khối (vd. hàng bảng, gạch đầu dòng)
                    else:
                        sep = " "
                    first_in_block = False
                    units.append(_Unit(piece, sep, b.page_start, b.page_end, section))
    return units


def _stable_id(source: str, index: int, text: str) -> str:
    return hashlib.sha1(f"{source}|{index}|{text}".encode("utf-8")).hexdigest()[:16]


# ------------------------------------------------------------------ chunker
class VietnameseChunker:
    def __init__(self, config: Optional[ChunkConfig] = None):
        self.config = config or ChunkConfig()

    def split(self, blocks: List[Block], source: str = "", base_metadata: Optional[dict] = None) -> List[Chunk]:
        cfg = self.config
        units = _blocks_to_units(blocks, cfg.chunk_size)
        groups: List[List[_Unit]] = []
        cur: List[_Unit] = []
        cur_len = 0
        fresh = 0  # số unit mới (không tính phần overlap) trong cur

        def length(us: List[_Unit]) -> int:
            return sum(len(u.text) + (len(u.sep) if i else 0) for i, u in enumerate(us))

        def flush(carry: bool):
            nonlocal cur, cur_len, fresh
            if fresh > 0:
                groups.append(cur)
            tail: List[_Unit] = []
            if carry and cfg.chunk_overlap > 0 and fresh > 0:
                acc = 0
                for u in reversed(cur):
                    if u.is_heading:
                        break
                    acc += len(u.text) + len(u.sep)
                    if acc > cfg.chunk_overlap:
                        break
                    tail.insert(0, u)
            cur, fresh = tail, 0
            cur_len = length(cur)

        for u in units:
            add = len(u.text) + (len(u.sep) if cur else 0)
            if u.is_heading and fresh > 0 and cur_len >= cfg.min_chunk_size:
                flush(carry=False)
                add = len(u.text)
            if cur and cur_len + add > cfg.chunk_size:
                flush(carry=True)
                if cur and cur_len + len(u.text) + len(u.sep) > cfg.chunk_size:
                    cur, cur_len = [], 0  # overlap làm tràn -> bỏ overlap
                add = len(u.text) + (len(u.sep) if cur else 0)
            cur.append(u)
            cur_len += add
            fresh += 1
        flush(carry=False)

        return self._to_chunks(groups, source, base_metadata or {})

    def _to_chunks(self, groups: List[List[_Unit]], source: str, base: dict) -> List[Chunk]:
        chunks: List[Chunk] = []
        total = len(groups)
        for i, g in enumerate(groups):
            text = "".join((u.sep if j else "") + u.text for j, u in enumerate(g)).strip()
            section = g[0].section
            if self.config.prepend_section and section and not g[0].is_heading:
                text = f"[{section}]\n{text}"
            starts = [u.page_start for u in g if u.page_start is not None]
            ends = [u.page_end for u in g if u.page_end is not None]
            meta = dict(base)
            meta.update({
                "source": source,
                "filename": os.path.basename(source) if source else None,
                "chunk_index": i,
                "total_chunks": total,
                "section": section,
                "page_start": min(starts) if starts else None,
                "page_end": max(ends) if ends else None,
                "char_count": len(text),
                "word_count": len(text.split()),
            })
            chunks.append(Chunk(id=_stable_id(source, i, text), text=text, metadata=meta))
        return chunks

