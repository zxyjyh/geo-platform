"""PDF 解析与按版面切块：对开页按中线拆成左右半页，每个半页内先左栏后右栏。"""
import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf


class PdfError(Exception):
    """打不开 / 不是 PDF。"""


@dataclass
class PageStat:
    page_no: int
    n_chars: int  # 去掉所有空白后的字符数
    n_images: int


@dataclass
class ChunkDraft:
    seq: int
    page_no: int
    half: str  # 对开页 "L" / "R"，普通页 ""
    text: str


@dataclass
class ParsedPdf:
    pages: list[PageStat]
    chunks: list[ChunkDraft]


_CJK = re.compile(r"[⺀-鿿豈-﫿＀-￯]")
_SENTENCE_END = "。！？"


def _join_lines(raw: str) -> str:
    """块内换行：两侧都是 CJK 直接拼接，否则补一个空格。"""
    out = ""
    for line in (ln.strip() for ln in raw.split("\n")):
        if not line:
            continue
        if out and not (_CJK.match(out[-1]) and _CJK.match(line[0])):
            out += " "
        out += line
    return out


def _split_long_block(text: str, max_chars: int) -> list[str]:
    """单个块超长：按句末标点切，仍超长的句子硬切。"""
    sentences: list[str] = []
    start = 0
    for i, ch in enumerate(text):
        if ch in _SENTENCE_END:
            sentences.append(text[start:i + 1])
            start = i + 1
    if start < len(text):
        sentences.append(text[start:])
    pieces: list[str] = []
    cur = ""
    for s in sentences:
        while len(s) > max_chars:
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(s[:max_chars])
            s = s[max_chars:]
        if len(cur) + len(s) > max_chars:
            pieces.append(cur)
            cur = ""
        cur += s
    if cur:
        pieces.append(cur)
    return pieces


def _chunk_blocks(blocks: list[str], max_chars: int) -> list[str]:
    """按块边界贪心装填；max_chars 只算块文字本身，不算块间的换行。"""
    units: list[str] = []
    for b in blocks:
        units.extend([b] if len(b) <= max_chars else _split_long_block(b, max_chars))
    chunks: list[str] = []
    cur: list[str] = []
    size = 0
    for u in units:
        if cur and size + len(u) > max_chars:
            chunks.append("\n".join(cur))
            cur, size = [], 0
        cur.append(u)
        size += len(u)
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def _unit_blocks(page: pymupdf.Page, rect: pymupdf.Rect) -> list[str]:
    mid = (rect.x0 + rect.x1) / 2
    found = []
    for b in page.get_text("blocks", clip=rect):
        if b[6] != 0:
            continue
        text = _join_lines(b[4])
        if text:
            found.append((0 if b[0] < mid else 1, b[1], b[0], text))
    found.sort(key=lambda t: t[:3])
    return [t[3] for t in found]


def parse_pdf(path: Path, max_chars: int = 1200) -> ParsedPdf:
    try:
        doc = pymupdf.open(path)
    except Exception as e:
        raise PdfError(f"打不开 PDF：{e}") from e
    try:
        if not doc.is_pdf:
            raise PdfError("不是 PDF 文件")
        pages: list[PageStat] = []
        chunks: list[ChunkDraft] = []
        for page in doc:
            page_no = page.number + 1
            n_chars = len("".join(page.get_text().split()))
            pages.append(PageStat(page_no, n_chars, len(page.get_images())))
            r = page.rect
            if r.width > r.height:  # 对开页：按中线拆成左右半页
                mid = (r.x0 + r.x1) / 2
                units = [("L", pymupdf.Rect(r.x0, r.y0, mid, r.y1)), ("R", pymupdf.Rect(mid, r.y0, r.x1, r.y1))]
            else:
                units = [("", r)]
            for half, rect in units:
                for text in _chunk_blocks(_unit_blocks(page, rect), max_chars):
                    chunks.append(ChunkDraft(len(chunks), page_no, half, text))
        return ParsedPdf(pages, chunks)
    except PdfError:
        raise
    except Exception as e:
        raise PdfError(f"解析 PDF 失败：{e}") from e
    finally:
        doc.close()
