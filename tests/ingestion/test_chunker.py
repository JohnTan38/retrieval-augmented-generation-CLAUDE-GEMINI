from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import ingestion.chunker as chunker
from ingestion.chunker import chunk_pages
from ingestion.manifest import load_manifest
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
        pages=1,
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


@pytest.mark.parametrize(
    ("target_words", "overlap_words", "word_count"),
    [(10, 9, 30), (120, 90, 275), (120, 20, 320)],
)
def test_adjacent_chunks_never_overlap_more_than_half_the_predecessor(
    document: CorpusDocument, target_words: int, overlap_words: int, word_count: int
):
    page = PageText(
        document_id="test-document",
        page=1,
        text=" ".join(f"word{number}" for number in range(word_count)),
    )

    chunks = chunk_pages(
        document, [page], target_words=target_words, overlap_words=overlap_words
    )

    for previous, current in zip(chunks, chunks[1:]):
        assert _positional_overlap(previous.text, current.text) <= len(
            previous.text.split()
        ) // 2
        assert previous.text != current.text


def test_semantic_boundary_uses_dynamic_overlap_from_the_predecessor(
    document: CorpusDocument,
):
    first_paragraph = " ".join(f"word{number}" for number in range(95))
    second_paragraph = " ".join(f"word{number}" for number in range(95, 275))
    page = PageText(
        document_id="test-document",
        page=1,
        text=f"{first_paragraph}\n\n{second_paragraph}",
    )

    chunks = chunk_pages(document, [page], target_words=120, overlap_words=90)

    assert chunks[0].text.split()[-1] == "word94"
    assert chunks[1].text.split()[0] == "word48"


def test_real_corpus_adjacent_chunks_never_exceed_half_predecessor_overlap():
    manifest = load_manifest(ROOT / "data" / "corpus-manifest.json", ROOT / "public" / "documents")

    for document in manifest.documents:
        pages = extract_pages(ROOT / "public" / "documents" / document.filename, document.document_id)
        chunks = chunk_pages(document, pages, corpus_version=manifest.corpus_version)
        for page in pages:
            spans = chunker._chunk_page_spans(page.text, 650, 90)
            page_chunks = [chunk for chunk in chunks if chunk.page == page.page]

            _assert_source_span_invariants(spans, len(page.text.split()))
            assert [chunk.text for chunk in page_chunks] == [
                " ".join(page.text.split()[span.start : span.end]) for span in spans
            ]
            assert all(
                previous.text != current.text
                for previous, current in zip(page_chunks, page_chunks[1:])
            )


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


def test_chunking_recognizes_terminal_punctuation_before_closing_quotes(document: CorpusDocument):
    first_sentence = " ".join(f"first{number}" for number in range(20)) + '.)"'
    second_sentence = " ".join(f"second{number}" for number in range(20)) + "."
    page = PageText(
        document_id="test-document",
        page=1,
        text=f"{first_sentence} {second_sentence}",
    )

    chunks = chunk_pages(document, [page], target_words=30, overlap_words=5)

    assert chunks[0].text.split()[-1] == 'first19.)"'


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
    ("tokens", "target_words", "overlap_words"),
    [
        (["same"] * 30, 10, 0),
        (["same"] * 30, 10, 9),
        (["red", "blue"] * 20, 10, 0),
        (["red", "blue"] * 20, 10, 9),
    ],
)
def test_repeated_content_keeps_distinct_adjacent_spans_and_stable_ids(
    document: CorpusDocument,
    tokens: list[str],
    target_words: int,
    overlap_words: int,
):
    page = PageText(document_id="test-document", page=1, text=" ".join(tokens))

    first = chunk_pages(
        document, [page], target_words=target_words, overlap_words=overlap_words
    )
    second = chunk_pages(
        document, [page], target_words=target_words, overlap_words=overlap_words
    )

    assert all(previous.text != current.text for previous, current in zip(first, first[1:]))
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]

    spans = chunker._chunk_page_spans(
        page.text, target_words, min(overlap_words, target_words // 2)
    )
    _assert_source_span_invariants(spans, len(tokens))
    assert [chunk.text for chunk in first] == [
        " ".join(tokens[span.start : span.end]) for span in spans
    ]


def test_final_repeated_candidate_coalesces_without_dropping_source_positions(
    document: CorpusDocument,
):
    tokens = ["same"] * 20
    page = PageText(document_id="test-document", page=1, text=" ".join(tokens))

    chunks = chunk_pages(document, [page], target_words=10, overlap_words=0)
    spans = chunker._chunk_page_spans(page.text, 10, 0)

    assert [chunk.text for chunk in chunks] == [" ".join(tokens)]
    _assert_source_span_invariants(spans, len(tokens))


def test_repeated_final_tail_coalesces_equal_spans_recursively():
    spans = [
        chunker._ChunkSpan(0, 2),
        chunker._ChunkSpan(2, 3),
        chunker._ChunkSpan(3, 4),
    ]

    chunker._coalesce_equal_tail(spans, ["same"] * 4)

    assert spans == [chunker._ChunkSpan(0, 4)]


@pytest.mark.parametrize("pattern", [("same",), ("red", "blue")])
def test_repeated_content_span_property_preserves_coverage_without_equal_neighbors(
    pattern: tuple[str, ...],
):
    for source_word_count in range(2, 41):
        tokens = (pattern * ((source_word_count + len(pattern) - 1) // len(pattern)))[
            :source_word_count
        ]
        text = " ".join(tokens)
        for target_words in range(1, 11):
            for overlap_words in range(target_words):
                spans = chunker._chunk_page_spans(
                    text, target_words, min(overlap_words, target_words // 2)
                )

                _assert_source_span_invariants(spans, source_word_count)
                assert all(
                    " ".join(tokens[previous.start : previous.end])
                    != " ".join(tokens[current.start : current.end])
                    for previous, current in zip(spans, spans[1:])
                )


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
        [PageText.model_construct(document_id="test-document", page=0, text="zero")],
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


@pytest.mark.parametrize(
    ("pages", "page_count"),
    [
        ([PageText(document_id="test-document", page=2, text="second")], 2),
        (
            [
                PageText(document_id="test-document", page=1, text="first"),
                PageText(document_id="test-document", page=3, text="third"),
            ],
            3,
        ),
        ([PageText(document_id="test-document", page=1, text="first")], 2),
    ],
)
def test_chunking_requires_contiguous_complete_document_pages(
    document: CorpusDocument, pages: list[PageText], page_count: int
):
    incomplete_document = document.model_copy(update={"pages": page_count})

    with pytest.raises(ValueError, match="contiguous"):
        chunk_pages(incomplete_document, pages)


def test_chunking_rejects_a_non_document_at_the_public_boundary():
    page = PageText(document_id="test-document", page=1, text="source text")

    with pytest.raises(ValueError, match="document"):
        chunk_pages("not-a-document", [page])  # type: ignore[arg-type]


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


def _positional_overlap(previous_text: str, current_text: str) -> int:
    previous_words = previous_text.split()
    current_words = current_text.split()
    for overlap in range(min(len(previous_words), len(current_words)), 0, -1):
        if previous_words[-overlap:] == current_words[:overlap]:
            return overlap
    return 0


def _assert_source_span_invariants(spans: list[object], source_word_count: int) -> None:
    assert spans[0].start == 0
    assert spans[-1].end == source_word_count
    covered_positions = set()
    for span in spans:
        covered_positions.update(range(span.start, span.end))
    assert covered_positions == set(range(source_word_count))
    for previous, current in zip(spans, spans[1:]):
        assert current.end > previous.end
        assert previous.end - current.start <= (previous.end - previous.start) // 2
