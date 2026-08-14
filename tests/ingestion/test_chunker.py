from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from ingestion.chunker import chunk_pages
from ingestion.models import ChunkRecord, CorpusDocument, PageText
from ingestion.parser import extract_pages


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def document() -> CorpusDocument:
    return CorpusDocument(
        document_id="test-document",
        filename="test-document.pdf",
        title="Test document",
        semester="Test semester",
        pages=27,
        sha256="0" * 64,
        download_url="/documents/test-document.pdf",
        topics=("testing", "chunking"),
    )


@pytest.fixture
def jan_2026_document() -> CorpusDocument:
    return CorpusDocument(
        document_id="jan-2026",
        filename="swk501-Jan2026-deep-research-model-answers.pdf",
        title="SWK501 January 2026 Deep-Research Model Answers",
        semester="January 2026",
        pages=27,
        sha256="109601093872bd96a0333386b2e474bd67f3c91331fb873218b560ecdc93e1a7",
        download_url="/documents/swk501-Jan2026-deep-research-model-answers.pdf",
        topics=("emotion coaching",),
    )


@pytest.fixture
def jan_2026_pages() -> list[PageText]:
    return extract_pages(
        ROOT / "public" / "documents" / "swk501-Jan2026-deep-research-model-answers.pdf",
        "jan-2026",
    )


@pytest.fixture
def long_page() -> PageText:
    words = [f"word{number}" for number in range(320)]
    return PageText(document_id="test-document", page=1, text=" ".join(words))


def test_chunks_have_stable_ids_and_never_cross_pages(
    jan_2026_document: CorpusDocument, jan_2026_pages: list[PageText]
):
    first = chunk_pages(jan_2026_document, jan_2026_pages)
    second = chunk_pages(jan_2026_document, jan_2026_pages)

    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]
    assert all(chunk.document_id == "jan-2026" for chunk in first)
    assert all(1 <= chunk.page <= 27 for chunk in first)
    assert all(chunk.text.strip() for chunk in first)
    assert all(chunk.filename == jan_2026_document.filename for chunk in first)
    assert all(chunk.topics == jan_2026_document.topics for chunk in first)


def test_chunk_ids_hash_the_explicit_corpus_version(document: CorpusDocument):
    page = PageText(document_id="test-document", page=1, text="One complete sentence.")

    chunks = chunk_pages(document, [page], corpus_version="corpus-v2")

    expected = hashlib.sha256(
        b"corpus-v2|test-document|1|1|One complete sentence."
    ).hexdigest()[:24]
    assert [chunk.chunk_id for chunk in chunks] == [expected]


def test_chunk_ids_preserve_the_supplied_corpus_version_bytes(document: CorpusDocument):
    page = PageText(document_id="test-document", page=1, text="One complete sentence.")

    chunks = chunk_pages(document, [page], corpus_version=" corpus-v2 ")

    expected = hashlib.sha256(
        b" corpus-v2 |test-document|1|1|One complete sentence."
    ).hexdigest()[:24]
    assert [chunk.chunk_id for chunk in chunks] == [expected]


@pytest.mark.parametrize("corpus_version", ["", " ", 1])
def test_chunking_rejects_a_blank_or_non_string_corpus_version(
    document: CorpusDocument, corpus_version: object
):
    page = PageText(document_id="test-document", page=1, text="source text")

    with pytest.raises(ValueError, match="corpus version"):
        chunk_pages(document, [page], corpus_version=corpus_version)  # type: ignore[arg-type]


def test_adjacent_chunks_overlap_without_being_duplicates(
    document: CorpusDocument, long_page: PageText
):
    chunks = chunk_pages(document, [long_page], target_words=120, overlap_words=20)

    assert len(chunks) > 1
    assert set(chunks[0].text.split()[-20:]) <= set(chunks[1].text.split()[:40])
    assert chunks[0].text != chunks[1].text


def test_chunking_prefers_paragraph_then_sentence_boundaries(document: CorpusDocument):
    first_paragraph = " ".join(f"paragraph{number}" for number in range(40))
    second_sentence = " ".join(f"sentence{number}" for number in range(40)) + "."
    third_sentence = " ".join(f"tail{number}" for number in range(40)) + "."
    page = PageText(
        document_id="test-document",
        page=1,
        text=f"{first_paragraph}\n\n{second_sentence} {third_sentence}",
    )

    chunks = chunk_pages(document, [page], target_words=70, overlap_words=10)

    assert chunks[0].text.split()[-1] == "paragraph39"
    assert chunks[1].text.split()[-1] == "sentence39."


def test_chunking_falls_back_to_word_windows(document: CorpusDocument, long_page: PageText):
    chunks = chunk_pages(document, [long_page], target_words=120, overlap_words=20)

    assert len(chunks[0].text.split()) == 120
    assert chunks[0].text.split()[-1] == "word119"


def test_chunking_absorbs_a_tiny_final_tail_to_avoid_near_duplicates(
    document: CorpusDocument,
):
    page = PageText(
        document_id="test-document",
        page=1,
        text=" ".join(f"word{number}" for number in range(121)),
    )

    chunks = chunk_pages(document, [page], target_words=120, overlap_words=90)

    assert [len(chunk.text.split()) for chunk in chunks] == [121]


def test_chunking_caps_extreme_overlap_to_avoid_near_identical_chunks(
    document: CorpusDocument,
):
    page = PageText(
        document_id="test-document",
        page=1,
        text=" ".join(f"word{number}" for number in range(30)),
    )

    chunks = chunk_pages(document, [page], target_words=10, overlap_words=9)

    assert chunks[1].text.split()[0] == "word5"


@pytest.mark.parametrize(
    ("target_words", "overlap_words"),
    [(0, 0), (-1, 0), (True, 0), (1, -1), (1, 1), (10, 10)],
)
def test_chunking_rejects_invalid_window_parameters(
    document: CorpusDocument, target_words: int, overlap_words: int
):
    page = PageText(document_id="test-document", page=1, text="source text")

    with pytest.raises(ValueError, match="word parameters"):
        chunk_pages(document, [page], target_words=target_words, overlap_words=overlap_words)


@pytest.mark.parametrize(
    "pages",
    [
        [],
        [PageText(document_id="other", page=1, text="source text")],
        [
            PageText(document_id="test-document", page=2, text="second"),
            PageText(document_id="test-document", page=1, text="first"),
        ],
        [PageText(document_id="test-document", page=28, text="out of range")],
        [PageText.model_construct(document_id="test-document", page=1, text=" ")],
        ["not-a-page"],  # type: ignore[list-item]
    ],
)
def test_chunking_rejects_malformed_page_sequences(
    document: CorpusDocument, pages: list[PageText]
):
    with pytest.raises(ValueError, match="pages"):
        chunk_pages(document, pages)


def test_chunking_rejects_a_string_instead_of_a_page_sequence(document: CorpusDocument):
    with pytest.raises(ValueError, match="pages"):
        chunk_pages(document, "not-pages")  # type: ignore[arg-type]


@pytest.mark.parametrize("pages", [None, 1])
def test_chunking_rejects_non_sequence_pages(document: CorpusDocument, pages: object):
    with pytest.raises(ValueError, match="pages"):
        chunk_pages(document, pages)  # type: ignore[arg-type]


def test_chunk_record_requires_strict_nonblank_metadata():
    valid = {
        "chunk_id": "a" * 24,
        "document_id": "document",
        "filename": "document.pdf",
        "semester": "semester",
        "page": 1,
        "text": "text",
        "topics": ("topic",),
    }
    assert ChunkRecord(**valid).topics == ("topic",)

    for field, value in [
        ("chunk_id", "A" * 24),
        ("document_id", " "),
        ("filename", " "),
        ("semester", " "),
        ("page", 0),
        ("page", True),
        ("text", " \n"),
        ("topics", (" ",)),
    ]:
        invalid = {**valid, field: value}
        with pytest.raises(ValueError):
            ChunkRecord(**invalid)
