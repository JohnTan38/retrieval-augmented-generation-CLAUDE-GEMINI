"""Lightweight lexical, dense, and reciprocal-rank retrieval over IndexStore."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
import math

from backend.index_store import IndexStore
from backend.models import DiverseResult, FusedResult, SourceEvidence
from ingestion.indexer import tokenize


BM25_K1 = 1.2
BM25_B = 0.75
RRF_K = 60


@dataclass(frozen=True)
class _ScoredChunk:
    chunk_id: str
    score: float


def bm25_rank(store: IndexStore, query: str) -> list[_ScoredChunk]:
    """Return non-negative BM25 matches using Task 4's exact tokenizer."""
    terms = tokenize(query)
    if not terms:
        return []
    query_terms = set(terms)
    matches: list[_ScoredChunk] = []
    document_count = len(store.bm25_document_lengths)
    for index, chunk in enumerate(store.artifact.chunks):
        frequency = store.bm25_term_frequencies[index]
        length = store.bm25_document_lengths[index]
        score = 0.0
        for term in query_terms:
            term_count = frequency.get(term, 0)
            if term_count:
                document_frequency = store.bm25_document_frequencies[term]
                inverse_frequency = math.log(1.0 + (document_count - document_frequency + 0.5) / (document_frequency + 0.5))
                denominator = term_count + BM25_K1 * (1.0 - BM25_B + BM25_B * length / store.bm25_average_document_length)
                score += inverse_frequency * term_count * (BM25_K1 + 1.0) / denominator
        if score > 0.0 and math.isfinite(score):
            matches.append(_ScoredChunk(chunk.chunk_id, score))
    return sorted(matches, key=lambda item: (-item.score, item.chunk_id))


def cosine_rank(store: IndexStore, query_vector: Sequence[float]) -> list[_ScoredChunk]:
    """Rank all normalized artifact vectors after validating one query normalization."""
    vector = _normalized_query_vector(query_vector, store.embedding_dimensions)
    matches = [
        _ScoredChunk(chunk.chunk_id, sum(value * stored for value, stored in zip(vector, stored_vector, strict=True)))
        for chunk, stored_vector in zip(store.artifact.chunks, store.vectors, strict=True)
    ]
    return sorted(matches, key=lambda item: (-item.score, item.chunk_id))


def reciprocal_rank_fusion(
    lexical: Sequence[str], dense: Sequence[str], *, k: int = RRF_K
) -> list[FusedResult]:
    """Fuse two rank lists with RRF k=60 and lexicographic deterministic ties."""
    if isinstance(k, bool) or not isinstance(k, int) or k <= 0:
        raise ValueError("RRF k must be positive")
    scores: dict[str, float] = {}
    for ranking in (lexical, dense):
        seen: set[str] = set()
        for rank, chunk_id in enumerate(ranking, start=1):
            if not isinstance(chunk_id, str) or not chunk_id:
                raise ValueError("rankings must contain chunk IDs")
            if chunk_id not in seen:
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
                seen.add(chunk_id)
    return [FusedResult(chunk_id=chunk_id, score=score) for chunk_id, score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))]


def diversity_select(store: IndexStore, ranked: Sequence[FusedResult], *, top_k: int) -> list[DiverseResult]:
    """Keep one chunk per document/page and fill from remaining ranked evidence."""
    selected: list[DiverseResult] = []
    represented_pages: set[tuple[str, int]] = set()
    for result in ranked:
        chunk = store.chunks_by_id.get(result.chunk_id)
        if chunk is None:
            raise ValueError("ranked result is absent from the index")
        page_key = (chunk.document_id, chunk.page)
        if page_key not in represented_pages:
            selected.append(DiverseResult(chunk_id=chunk.chunk_id, score=result.score, document_id=chunk.document_id, page=chunk.page))
            represented_pages.add(page_key)
            if len(selected) == top_k:
                break
    return selected


class HybridRetriever:
    """Safe retrieval only; answer generation intentionally lives elsewhere."""

    def __init__(self, store: IndexStore) -> None:
        self._store = store

    def search(
        self, query: str, query_vector: Sequence[float] | None, top_k: int = 5
    ) -> list[SourceEvidence]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be nonblank")
        if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 5:
            raise ValueError("top_k must be between 1 and 5")
        lexical = bm25_rank(self._store, query)
        dense = [] if query_vector is None else cosine_rank(self._store, query_vector)
        fused = reciprocal_rank_fusion([item.chunk_id for item in lexical], [item.chunk_id for item in dense])
        return [_source_evidence(self._store, item) for item in diversity_select(self._store, fused, top_k=top_k)]


def _normalized_query_vector(query_vector: Sequence[float], dimensions: int) -> tuple[float, ...]:
    if not isinstance(query_vector, Sequence) or isinstance(query_vector, (str, bytes)) or len(query_vector) != dimensions:
        raise ValueError("query vector must have the index dimensions")
    values: list[float] = []
    for value in query_vector:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValueError("query vector values must be finite numbers")
        values.append(float(value))
    length = math.sqrt(sum(value * value for value in values))
    if length == 0.0:
        raise ValueError("query vector must not be zero")
    return tuple(value / length for value in values)


def _source_evidence(store: IndexStore, result: DiverseResult) -> SourceEvidence:
    chunk = store.chunks_by_id[result.chunk_id]
    document = store.documents_by_id[chunk.document_id]
    excerpt = " ".join(chunk.text.split())[:600]
    return SourceEvidence(
        source_id=chunk.chunk_id,
        chunk_id=chunk.chunk_id,
        document_id=chunk.document_id,
        filename=chunk.filename,
        title=document.title,
        semester=chunk.semester,
        page=chunk.page,
        excerpt=excerpt,
        score=result.score,
        download_url=document.download_url,
    )
