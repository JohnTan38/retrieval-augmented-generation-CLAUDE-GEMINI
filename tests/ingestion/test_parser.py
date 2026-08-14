from __future__ import annotations

from pathlib import Path

import pytest

import ingestion.parser as parser
from ingestion.models import PageText


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def corpus_paths() -> dict[str, Path]:
    documents_dir = ROOT / "public" / "documents"
    return {
        "jan-2026": documents_dir / "swk501-Jan2026-deep-research-model-answers.pdf",
    }


def test_extract_pages_preserves_one_based_page_numbers(corpus_paths: dict[str, Path]):
    pages = parser.extract_pages(corpus_paths["jan-2026"], "jan-2026")

    assert len(pages) == 27
    assert pages[0].page == 1
    assert pages[-1].page == 27
    assert "emotion" in " ".join(page.text.lower() for page in pages)


def test_extract_pages_rejects_an_empty_page(monkeypatch):
    monkeypatch.setattr(parser, "_read_pdf_pages", lambda _: [""])

    with pytest.raises(ValueError, match="extractable text"):
        parser.extract_pages(Path("empty.pdf"), "empty")


def test_extract_pages_rejects_a_pdf_without_pages(monkeypatch):
    monkeypatch.setattr(parser, "_read_pdf_pages", lambda _: [])

    with pytest.raises(ValueError, match="contains no pages"):
        parser.extract_pages(Path("empty.pdf"), "empty")


@pytest.mark.parametrize("raw_text", ["", " \t\n\r "])
def test_extract_pages_rejects_every_blank_page(monkeypatch, raw_text: str):
    monkeypatch.setattr(parser, "_read_pdf_pages", lambda _: [raw_text])

    with pytest.raises(ValueError, match="page 1.*extractable text"):
        parser.extract_pages(Path("ignored.pdf"), "document")


def test_extract_pages_normalizes_unicode_newlines_and_excessive_blank_lines(monkeypatch):
    monkeypatch.setattr(
        parser,
        "_read_pdf_pages",
        lambda _: ["\uff23\uff41\uff46\u00e9\r\nfirst\t  line\n\n\n\nsecond\u00a0line  "],
    )

    pages = parser.extract_pages(Path("ignored.pdf"), "document")

    assert pages == [
        PageText(document_id="document", page=1, text="Caf\u00e9\nfirst line\n\nsecond line")
    ]


def test_page_text_requires_strict_nonblank_page_metadata():
    with pytest.raises(ValueError):
        PageText(document_id=" ", page=1, text="text")

    with pytest.raises(ValueError):
        PageText(document_id="document", page=0, text="text")

    with pytest.raises(ValueError):
        PageText(document_id="document", page=1, text=" \n")

    with pytest.raises(ValueError):
        PageText(document_id="document", page=True, text="text")
