"""Làm sạch văn bản tiếng Việt trích từ PDF/DOCX."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import List

# ---------- Chuẩn hoá ký tự ----------
_LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl"}
_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")  # giữ \t \n \f
_DOT_LEADER_RE = re.compile(r"(?:\s*[.…·]\s*){4,}")          # "Chương 1 ........ 5"
_SPACE_BEFORE_PUNCT_RE = re.compile(r"[ ]+([,;:.!?%])(?=\s|$)")

# ---------- Header / footer / số trang ----------
_PAGE_NUM_RE = re.compile(
    r"^\s*(?:(?:trang|page)\s*)?\d{1,4}(?:\s*(?:/|of|trên)\s*\d{1,4})?\s*$"
    r"|^\s*[-–—]\s*\d{1,4}\s*[-–—]\s*$",
    re.IGNORECASE,
)

# ---------- Nối dòng ----------
_LIST_START_RE = re.compile(
    r"^\s*(?:[-–—•●○▪+*]\s|\d{1,3}[.)]\s|[a-zđ][.)]\s|[ivxIVX]{1,5}[.)]\s|#{1,6}\s)"
)
_TERMINAL_RE = re.compile(r"[.!?…:;”\"')\]]$")


def looks_garbled(text: str, threshold: float = 0.02) -> bool:
    """Phát hiện text lỗi font (ký tự thay thế U+FFFD / vùng private-use)."""
    if not text:
        return False
    bad = sum(1 for ch in text if ch == "\ufffd" or 0xE000 <= ord(ch) <= 0xF8FF)
    return bad / len(text) > threshold


def normalize_text(text: str) -> str:
    """Chuẩn hoá Unicode về NFC + loại ký tự rác (không đụng cấu trúc dòng)."""
    # NFC rất quan trọng với tiếng Việt: "ệ" có thể là 1 ký tự hoặc "e"+dấu mũ+dấu nặng,
    # nếu không thống nhất thì tìm kiếm / embedding / so khớp chuỗi sẽ sai.
    text = unicodedata.normalize("NFC", text)
    for k, v in _LIGATURES.items():
        text = text.replace(k, v)
    text = text.translate(_ZERO_WIDTH)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\t", " ")
    text = _CONTROL_RE.sub("", text)
    text = _DOT_LEADER_RE.sub(" ", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text


def _edge_key(line: str) -> str:
    return re.sub(r"\d+", "#", line.lower()).strip()


def remove_headers_footers(pages: List[str], scan_lines: int = 2,
                           min_pages: int = 3, ratio: float = 0.5) -> List[str]:
    """Xoá header/footer lặp lại và số trang ở mép trên/dưới mỗi trang."""
    split = [p.split("\n") for p in pages]

    def edge_idx(lines: List[str], for_repeat: bool = False):
        nz = [i for i, l in enumerate(lines) if l.strip()]
        # Trang quá ít dòng: gần như toàn bộ là "mép" -> không dò header/footer lặp
        # (tránh xoá nhầm nội dung); số trang vẫn được xử lý bằng regex.
        if for_repeat and len(nz) <= 2 * scan_lines:
            return [], []
        return nz[:scan_lines], nz[-scan_lines:]

    counter: Counter = Counter()
    for lines in split:
        top, bot = edge_idx(lines, for_repeat=True)
        counter.update({_edge_key(lines[i]) for i in set(top + bot)})

    n = len(pages)
    threshold = max(2, ratio * n)
    repeated = {k for k, c in counter.items() if n >= min_pages and c >= threshold and k}

    out = []
    for lines in split:
        top, bot = edge_idx(lines)
        long_enough = len([l for l in lines if l.strip()]) > 2 * scan_lines
        drop = set()
        for i in set(top + bot):
            if _PAGE_NUM_RE.match(lines[i]) or (long_enough and _edge_key(lines[i]) in repeated):
                drop.add(i)
        out.append("\n".join(l for i, l in enumerate(lines) if i not in drop))
    return out


def reflow_paragraphs(text: str) -> str:
    """Nối các dòng bị ngắt cứng (do PDF) thành đoạn văn liền mạch.

    Giữ nguyên: dòng trống, gạch đầu dòng, đánh số, heading Markdown, hàng bảng ("|").
    Quy tắc nối: dòng sau bắt đầu bằng chữ thường (tiếng Việt câu mới luôn viết hoa),
    hoặc dòng trước dài, chưa kết thúc câu và dòng sau không bắt đầu bằng chữ hoa.
    """
    out_paras: List[str] = []
    for para in re.split(r"\n{2,}", text):
        lines = [l for l in para.split("\n") if l.strip()]
        if not lines:
            continue
        merged = [lines[0]]
        for line in lines[1:]:
            prev = merged[-1]
            is_struct = (
                _LIST_START_RE.match(line) or " | " in line or " | " in prev
                or prev.lstrip().startswith("#")
            )
            first = line.lstrip()[:1]
            continues = first.islower() or (
                not _TERMINAL_RE.search(prev) and len(prev) >= 60 and not first.isupper()
            )
            if not is_struct and continues:
                merged[-1] = prev.rstrip() + " " + line.lstrip()
            else:
                merged.append(line)
        out_paras.append("\n".join(merged))
    return "\n\n".join(out_paras)


def tidy(text: str) -> str:
    text = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_pages(pages: List[str], remove_hf: bool = True) -> List[str]:
    """Pipeline làm sạch theo từng trang (giữ ranh giới trang để còn ghi số trang)."""
    pages = [normalize_text(p) for p in pages]
    if remove_hf:
        pages = remove_headers_footers(pages)
    return [tidy(reflow_paragraphs(p)) for p in pages]


def clean_text(text: str) -> str:
    """Làm sạch 1 khối văn bản (không chia trang)."""
    return clean_pages([text], remove_hf=False)[0]
