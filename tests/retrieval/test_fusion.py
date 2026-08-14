from __future__ import annotations

import pytest

from backend.retrieval import diversity_select, reciprocal_rank_fusion


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
