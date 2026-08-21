from __future__ import annotations

import pytest

from types import SimpleNamespace

from backend.retrieval import _ScoredChunk, _vector_similarity, diversity_select, prioritize_variants, reciprocal_rank_fusion, supported_chunk_ids


def test_rrf_promotes_results_present_in_both_rankings() -> None:
    fused = reciprocal_rank_fusion(
        lexical=["a", "b", "c"],
        dense=["b", "d", "a"],
        k=60,
    )

    assert fused[0].chunk_id == "b"
    assert {item.chunk_id for item in fused[:2]} == {"a", "b"}


def test_rrf_deduplicates_inputs_and_breaks_ties_by_chunk_id() -> None:
    fused = reciprocal_rank_fusion(["b", "b", "a"], ["a", "a", "b"], k=60)

    assert [item.chunk_id for item in fused] == ["a", "b"]
    with pytest.raises(ValueError, match="positive"):
        reciprocal_rank_fusion(["a"], ["b"], k=0)
    with pytest.raises(ValueError, match="chunk IDs"):
        reciprocal_rank_fusion(["a", ""], [])


def test_rrf_deduplicates_before_assigning_default_ranks_and_sums_both_lists() -> None:
    fused = reciprocal_rank_fusion(["a", "a", "b"], ["b", "b", "a"])

    assert [item.chunk_id for item in fused] == ["a", "b"]
    assert fused[0].score == pytest.approx(1 / 61 + 1 / 62)
    assert fused[1].score == pytest.approx(1 / 62 + 1 / 61)
    assert reciprocal_rank_fusion(["a", "a", "b"], [])[1].score == pytest.approx(1 / 62)


def test_diversity_suppresses_extra_chunks_from_one_document_page(index_store) -> None:
    by_page = {}
    for chunk_id, chunk in index_store.chunks_by_id.items():
        by_page.setdefault((chunk.document_id, chunk.page), []).append(chunk_id)
    page_chunks = next(chunk_ids for chunk_ids in by_page.values() if len(chunk_ids) > 1)
    distinct_chunks = [
        next(chunk_id for chunk_id, chunk in index_store.chunks_by_id.items() if chunk.document_id == document_id)
        for document_id in ("jul-2025", "jan-2026")
    ]
    ranked = reciprocal_rank_fusion(page_chunks + distinct_chunks, [])

    selected = diversity_select(index_store, ranked, top_k=2)

    assert len(selected) == 2
    assert len({(item.document_id, item.page) for item in selected}) == 2
    assert len(diversity_select(index_store, ranked, top_k=3)) == 3
    with pytest.raises(ValueError, match="absent"):
        diversity_select(index_store, reciprocal_rank_fusion(["missing"], []), top_k=1)
    for invalid_top_k in (0, -1, True, 6):
        with pytest.raises(ValueError, match="top_k"):
            diversity_select(index_store, ranked, top_k=invalid_top_k)
    assert diversity_select(index_store, [], top_k=1) == []


def test_support_filter_requires_relative_lexical_or_strong_dense_evidence() -> None:
    lexical = [_ScoredChunk("strong", 10.0), _ScoredChunk("boundary", 6.5), _ScoredChunk("weak", 6.49), _ScoredChunk("rescued", 1.0)]
    dense = [_ScoredChunk("rescued", 0.75), _ScoredChunk("weak", 0.749)]

    assert supported_chunk_ids(lexical, dense) == {"strong", "boundary", "rescued"}
    assert supported_chunk_ids([], [_ScoredChunk("semantic", 0.9), _ScoredChunk("noise", 0.74)]) == {"semantic"}


def test_diversity_prefers_research_when_paired_passages_are_near_duplicates() -> None:
    chunks = {
        "claude": SimpleNamespace(chunk_id="claude", document_id="claude-doc", semester="January 2025", variant="claude", page=2, vector=(1.0, 0.0)),
        "research": SimpleNamespace(chunk_id="research", document_id="research-doc", semester="January 2025", variant="research", page=8, vector=(0.99, 0.01)),
        "distinct": SimpleNamespace(chunk_id="distinct", document_id="research-doc", semester="January 2025", variant="research", page=9, vector=(0.0, 1.0)),
    }
    store = SimpleNamespace(chunks_by_id=chunks)
    ranked = reciprocal_rank_fusion(["claude", "distinct", "research"], [])

    selected = diversity_select(store, ranked, top_k=2)

    assert [item.chunk_id for item in selected] == ["research", "distinct"]
    assert [item.chunk_id for item in diversity_select(store, reciprocal_rank_fusion(["research", "claude"], []), top_k=2)] == ["research"]
    assert _vector_similarity((1.0,), (1.0, 0.0)) == -1.0


def test_variant_priority_is_research_first_except_for_explicit_recall_intent() -> None:
    chunks = {
        "claude": SimpleNamespace(variant="claude", semester="January 2026"),
        "research": SimpleNamespace(variant="research", semester="January 2026"),
        "other-research": SimpleNamespace(variant="research", semester="July 2025"),
    }
    store = SimpleNamespace(chunks_by_id=chunks)
    ranked = reciprocal_rank_fusion(["claude", "research", "other-research"], [])

    assert [item.chunk_id for item in prioritize_variants(store, ranked, "Explain Marcia identity status")] == ["research", "claude", "other-research"]
    assert [item.chunk_id for item in prioritize_variants(store, ranked, "Quiz me with active-recall flashcards")] == ["claude", "research", "other-research"]
    assert [item.chunk_id for item in prioritize_variants(store, [], "Explain Marcia")] == []
