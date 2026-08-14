from __future__ import annotations

import json
from pathlib import Path
import time

from backend.retrieval import HybridRetriever

from .conftest import HashEmbedder


ROOT = Path(__file__).resolve().parents[2]


def test_golden_queries_retrieve_the_expected_document_and_page_group(index_store) -> None:
    records = json.loads((ROOT / "evaluation" / "golden-queries.json").read_text(encoding="utf-8"))
    retriever = HybridRetriever(index_store)

    for record in records:
        results = retriever.search(record["query"], HashEmbedder.vector_for(record["query"]), top_k=3)
        assert any(result.document_id in record["expected_documents"] for result in results), record["id"]
        start, end = record["expected_page_range"]
        assert any(result.document_id == record["expected_documents"][0] and start <= result.page <= end for result in results), record["id"]


def test_hybrid_retriever_uses_lexical_results_when_vector_is_unavailable(index_store) -> None:
    results = HybridRetriever(index_store).search("Arnett emerging adulthood", None, top_k=3)

    assert len(results) == 3
    assert all(result.score > 0 for result in results)
    assert all(result.download_url == f"/documents/{result.filename}" for result in results)


def test_search_rejects_invalid_inputs_and_hot_retrieval_stays_within_local_budget(index_store) -> None:
    retriever = HybridRetriever(index_store)
    for query, top_k in (("", 3), ("valid", 0), ("valid", 6)):
        try:
            retriever.search(query, None, top_k=top_k)
        except ValueError:
            pass
        else:  # pragma: no cover - assertion failure branch
            raise AssertionError("invalid search input was accepted")

    query = "Apply Baltes selection optimisation compensation to active ageing"
    vector = HashEmbedder.vector_for(query)
    retriever.search(query, vector)
    samples = []
    for _ in range(30):
        started = time.perf_counter()
        retriever.search(query, vector)
        samples.append((time.perf_counter() - started) * 1_000)
    samples.sort()
    p95 = samples[round((len(samples) - 1) * 0.95)]
    print(f"hot hybrid retrieval p95: {p95:.3f} ms across 30 warmed calls")
    assert p95 < 100
