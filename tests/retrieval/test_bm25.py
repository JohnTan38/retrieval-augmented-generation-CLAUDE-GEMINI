from __future__ import annotations

import math

import pytest

from backend.retrieval import bm25_rank, cosine_rank


def test_bm25_reuses_deterministic_tokenization_and_handles_oov_or_blank_queries(index_store) -> None:
    ranked = bm25_rank(index_store, "Arnett emerging adulthood")

    assert ranked[0].chunk_id in index_store.chunks_by_id
    assert all(math.isfinite(item.score) and item.score >= 0 for item in ranked)
    assert bm25_rank(index_store, " ") == []
    assert bm25_rank(index_store, "unfindableterm") == []


def test_cosine_normalizes_the_query_once_and_rejects_bad_vectors(index_store) -> None:
    ranked = cosine_rank(index_store, [value * 2.0 for value in index_store.vectors[0]])

    assert len(ranked) == len(index_store.chunks_by_id)
    assert ranked[0].score == pytest.approx(1.0)
    for bad in ([], [0.0] * index_store.embedding_dimensions, [float("nan")] * index_store.embedding_dimensions, [1.0]):
        with pytest.raises(ValueError, match="query vector"):
            cosine_rank(index_store, bad)
