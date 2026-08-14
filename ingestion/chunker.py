"""Deterministic semantic, page-local chunking for the fixed corpus."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import hashlib
import re

from ingestion.models import ChunkRecord, CorpusDocument, PageText


DEFAULT_CORPUS_VERSION = "swk501-2026-01-v1"
_WORD_PATTERN = re.compile(r"\S+")
_PARAGRAPH_BREAK_PATTERN = re.compile(r"\n[^\S\r\n]*\n+")
_SENTENCE_ENDING_PATTERN = re.compile(r"[.!?][)\]}\"'”’]*$")


@dataclass(frozen=True)
class _ChunkSpan:
    start: int
    end: int


def chunk_pages(
    document: CorpusDocument,
    pages: Sequence[PageText],
    target_words: int = 650,
    overlap_words: int = 90,
    *,
    corpus_version: str = DEFAULT_CORPUS_VERSION,
) -> list[ChunkRecord]:
    """Return stable semantic chunks without crossing a PDF page boundary."""
    _validate_document(document)
    _validate_parameters(target_words, overlap_words, corpus_version)
    page_list = _validate_pages(document, pages)
    effective_overlap = min(overlap_words, target_words // 2)

    chunks: list[ChunkRecord] = []
    for page in page_list:
        chunks.extend(
            _chunk_page(
                document,
                page,
                target_words=target_words,
                overlap_words=effective_overlap,
                corpus_version=corpus_version,
            )
        )
    return chunks


def _validate_document(document: object) -> None:
    if not isinstance(document, CorpusDocument):
        raise ValueError("document must be a CorpusDocument")


def _validate_parameters(
    target_words: int, overlap_words: int, corpus_version: str
) -> None:
    if (
        isinstance(target_words, bool)
        or not isinstance(target_words, int)
        or isinstance(overlap_words, bool)
        or not isinstance(overlap_words, int)
        or target_words <= 0
        or overlap_words < 0
        or overlap_words >= target_words
    ):
        raise ValueError("word parameters require positive target and smaller overlap")
    if not isinstance(corpus_version, str) or not corpus_version.strip():
        raise ValueError("corpus version must not be blank")


def _validate_pages(document: CorpusDocument, pages: Sequence[PageText]) -> list[PageText]:
    if not isinstance(pages, Sequence) or isinstance(pages, (str, bytes)):
        raise ValueError("pages must be a non-empty ordered page sequence")
    page_list = list(pages)
    if not page_list:
        raise ValueError("pages must not be empty")

    previous_page = 0
    expected_page = 1
    for page in page_list:
        if not isinstance(page, PageText):
            raise ValueError("pages must contain PageText values")
        if (
            not isinstance(page.page, int)
            or isinstance(page.page, bool)
            or page.page <= previous_page
        ):
            raise ValueError("pages must have unique, ordered positive page numbers")
        if page.page > document.pages or page.document_id != document.document_id:
            raise ValueError("pages must belong to the document")
        if page.page != expected_page:
            raise ValueError("pages must be contiguous from 1 through document.pages")
        if not isinstance(page.text, str) or not page.text.strip():
            raise ValueError("pages must contain nonblank text")
        previous_page = page.page
        expected_page += 1
    if expected_page != document.pages + 1:
        raise ValueError("pages must be contiguous from 1 through document.pages")
    return page_list


def _chunk_page(
    document: CorpusDocument,
    page: PageText,
    *,
    target_words: int,
    overlap_words: int,
    corpus_version: str,
) -> list[ChunkRecord]:
    words = _words(page.text)
    spans = _chunk_page_spans(page.text, target_words, overlap_words)
    return [
        ChunkRecord(
            chunk_id=_chunk_id(
                corpus_version,
                document.document_id,
                page.page,
                ordinal,
                _span_text(words, span),
            ),
            document_id=document.document_id,
            filename=document.filename,
            semester=document.semester,
            page=page.page,
            text=_span_text(words, span),
            topics=document.topics,
        )
        for ordinal, span in enumerate(spans, start=1)
    ]


def _chunk_page_spans(
    text: str, target_words: int, overlap_words: int
) -> list[_ChunkSpan]:
    word_matches = list(_WORD_PATTERN.finditer(text))
    words = [match.group() for match in word_matches]
    paragraph_boundaries = _paragraph_boundaries(text, word_matches)
    sentence_boundaries = [
        position
        for position, word in enumerate(words, start=1)
        if _SENTENCE_ENDING_PATTERN.search(word)
    ]
    spans: list[_ChunkSpan] = []
    start = 0

    while start < len(words):
        end = _choose_chunk_end(
            start,
            len(words),
            target_words,
            overlap_words,
            paragraph_boundaries,
            sentence_boundaries,
        )
        next_overlap = min(overlap_words, (end - start) // 2)
        if end < len(words) and len(words) - end <= next_overlap:
            end = len(words)
        candidate = _ChunkSpan(start, end)
        if spans and _span_text(words, candidate) == _span_text(words, spans[-1]):
            if candidate.end < len(words):
                candidate = _ChunkSpan(candidate.start, candidate.end + 1)
                spans.append(candidate)
            else:
                spans[-1] = _ChunkSpan(spans[-1].start, candidate.end)
                _coalesce_equal_tail(spans, words)
        else:
            spans.append(candidate)
        emitted = spans[-1]
        next_overlap = min(overlap_words, (emitted.end - emitted.start) // 2)
        start = emitted.end if emitted.end == len(words) else emitted.end - next_overlap
    return spans


def _words(text: str) -> list[str]:
    return [match.group() for match in _WORD_PATTERN.finditer(text)]


def _span_text(words: list[str], span: _ChunkSpan) -> str:
    return " ".join(words[span.start : span.end])


def _coalesce_equal_tail(spans: list[_ChunkSpan], words: list[str]) -> None:
    while len(spans) > 1 and _span_text(words, spans[-2]) == _span_text(words, spans[-1]):
        spans[-2] = _ChunkSpan(spans[-2].start, spans[-1].end)
        spans.pop()


def _paragraph_boundaries(text: str, word_matches: list[re.Match[str]]) -> list[int]:
    boundaries: list[int] = []
    for paragraph_break in _PARAGRAPH_BREAK_PATTERN.finditer(text):
        word_count = sum(match.end() <= paragraph_break.start() for match in word_matches)
        boundaries.append(word_count)
    return boundaries


def _choose_chunk_end(
    start: int,
    word_count: int,
    target_words: int,
    overlap_words: int,
    paragraph_boundaries: list[int],
    sentence_boundaries: list[int],
) -> int:
    requested_end = min(start + target_words, word_count)
    minimum_end = start + overlap_words
    for boundaries in (paragraph_boundaries, sentence_boundaries):
        candidates = [
            boundary
            for boundary in boundaries
            if minimum_end < boundary <= requested_end
        ]
        if candidates:
            return candidates[-1]
    return requested_end


def _chunk_id(
    corpus_version: str, document_id: str, page: int, ordinal: int, text: str
) -> str:
    source = f"{corpus_version}|{document_id}|{page}|{ordinal}|{text}".encode("utf-8")
    return hashlib.sha256(source).hexdigest()[:24]
