"""Deterministic, page-aware PDF text extraction."""

from __future__ import annotations

from pathlib import Path
import re
import unicodedata

import pymupdf

from ingestion.models import PageText


_HORIZONTAL_WHITESPACE = re.compile(r"[^\S\r\n]+")
_EXCESSIVE_BLANK_LINES = re.compile(r"\n{3,}")


def extract_pages(pdf_path: Path, document_id: str) -> list[PageText]:
    """Extract every PDF page without changing its page boundary."""
    raw_pages = _read_pdf_pages(pdf_path)
    if not raw_pages:
        raise ValueError("PDF contains no pages")

    pages: list[PageText] = []
    for page_number, raw_text in enumerate(raw_pages, start=1):
        text = _normalize_page_text(raw_text)
        if not text:
            raise ValueError(f"page {page_number} has no extractable text")
        pages.append(PageText(document_id=document_id, page=page_number, text=text))
    return pages


def _read_pdf_pages(pdf_path: Path) -> list[str]:
    with pymupdf.open(pdf_path) as pdf:
        return [page.get_text("text") for page in pdf]


def _normalize_page_text(raw_text: str) -> str:
    normalized = unicodedata.normalize("NFKC", raw_text).replace("\r\n", "\n").replace(
        "\r", "\n"
    )
    lines = [_HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in normalized.split("\n")]
    return _EXCESSIVE_BLANK_LINES.sub("\n\n", "\n".join(lines).strip())
