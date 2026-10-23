"""PDF 解析与按版面切块。"""
import os
from pathlib import Path

import pymupdf
import pytest

from app.kb.pdf import PdfError, parse_pdf
from tests.builders import make_pdf


def _save(doc: pymupdf.Document, tmp_path: Path) -> Path:
    path = tmp_path / "x.pdf"
    doc.save(path)
    doc.close()
    return path


def _text(page, x0, y0, x1, y1, text, size=12):
    page.insert_textbox(pymupdf.Rect(x0, y0, x1, y1), text, fontname="china-s", fontsize=size)


def make_spread_pdf(tmp_path: Path) -> Path:
    """横版对开页（1200x800）：右半页左栏 2024 / 商家5500，右栏 2025 / 商家5700（右栏靠上）。"""
    doc = pymupdf.open()
    page = doc.new_page(width=1200, height=800)
    _text(page, 620, 100, 880, 140, "2024")
    _text(page, 620, 300, 880, 340, "商家5500")
    _text(page, 920, 50, 1180, 90, "2025")
    _text(page, 920, 100, 1180, 140, "商家5700")
    return _save(doc, tmp_path)


def make_pdf_blocks(tmp_path: Path, n_blocks: int, chars: int) -> Path:
    """竖版单页，n 个互相分开的文字块，每块 chars 字。"""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    base = "春夏秋冬东南西北上下左右前后"
    for i in range(n_blocks):
        body = (base * (chars // len(base) + 1))[:chars]
        _text(page, 40, 30 + i * 160, 555, 30 + i * 160 + 140, body, size=8)
    return _save(doc, tmp_path)


def make_wrapped_pdf(tmp_path: Path) -> Path:
    """一个块里文字折成两行：「團購」「業務啟動」。"""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _text(page, 50, 50, 300, 120, "團購\n業務啟動", size=14)
    return _save(doc, tmp_path)


def test_spread_page_orders_columns_within_each_half(tmp_path):
    parsed = parse_pdf(make_spread_pdf(tmp_path))
    right = [c for c in parsed.chunks if c.half == "R"][0].text
    assert right.index("2025") < right.index("商家5700")
    assert right.index("商家5500") < right.index("2025")


def test_page_without_text_has_zero_chars_and_no_chunk(tmp_path):
    parsed = parse_pdf(make_pdf(tmp_path, pages=["澳觅上线", None]))
    assert [p.n_chars for p in parsed.pages] == [4, 0]
    assert [c.page_no for c in parsed.chunks] == [1]


def test_long_unit_split_at_block_boundaries(tmp_path):
    parsed = parse_pdf(make_pdf_blocks(tmp_path, n_blocks=5, chars=400), max_chars=1200)
    assert [len(c.text.replace("\n", "")) for c in parsed.chunks] == [1200, 800]
    assert all(c.page_no == 1 and c.half == "" for c in parsed.chunks)
    assert [c.seq for c in parsed.chunks] == [0, 1]


def test_oversized_block_split_at_sentence_end(tmp_path):
    sentence = "澳觅是澳门本地生活平台。"
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    _text(page, 40, 40, 555, 700, sentence * 10, size=8)
    parsed = parse_pdf(_save(doc, tmp_path), max_chars=50)
    assert len(parsed.chunks) > 1
    assert all(len(c.text) <= 50 and c.text.endswith("。") for c in parsed.chunks)


def test_cjk_line_wrap_joined_without_space(tmp_path):
    assert "團購業務啟動" in parse_pdf(make_wrapped_pdf(tmp_path)).chunks[0].text


def test_not_a_pdf_raises(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"hello")
    with pytest.raises(PdfError):
        parse_pdf(p)


@pytest.mark.skipif(not os.environ.get("KB_SAMPLE_PDF"), reason="本机年刊路径，不进仓库")
def test_yearbook_timeline_page():
    parsed = parse_pdf(Path(os.environ["KB_SAMPLE_PDF"]))
    assert len(parsed.pages) == 88
    p5r = " ".join(c.text for c in parsed.chunks if c.page_no == 5 and c.half == "R")
    assert p5r.index("2025") < p5r.index("5,700")
