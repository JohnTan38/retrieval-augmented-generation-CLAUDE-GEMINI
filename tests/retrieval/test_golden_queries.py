from __future__ import annotations

import json
from pathlib import Path
import time

from backend.retrieval import HybridRetriever
from ingestion.manifest import load_manifest

from .conftest import HashEmbedder


ROOT = Path(__file__).resolve().parents[2]
REQUIRED_GOLDEN_IDS = {
    "max-ppct",
    "tan-arnett",
    "multiple-intelligence",
    "emotion-coaching",
    "marcia",
    "cognitive-ageing",
    "baltes-soc",
}


def _golden_records() -> list[dict[str, object]]:
    return json.loads((ROOT / "evaluation" / "golden-queries.json").read_text(encoding="utf-8"))


def test_golden_query_file_has_exact_manifest_backed_contract() -> None:
    records = _golden_records()
    manifest = load_manifest(ROOT / "data" / "corpus-manifest.json", ROOT / "public" / "documents")
    documents = {document.document_id: document for document in manifest.documents}

    assert {record["id"] for record in records} == REQUIRED_GOLDEN_IDS
    assert len(records) == len(REQUIRED_GOLDEN_IDS)
    for record in records:
        assert set(record) == {"id", "query", "expected_documents", "expected_topic", "expected_page_range"}
        assert isinstance(record["query"], str) and record["query"].strip()
        assert isinstance(record["expected_topic"], str) and record["expected_topic"].strip()
        assert record["expected_documents"] and all(document_id in documents for document_id in record["expected_documents"])
        assert all(record["expected_topic"] in documents[document_id].topics for document_id in record["expected_documents"])
        start, end = record["expected_page_range"]
        assert isinstance(start, int) and isinstance(end, int) and 1 <= start <= end
        assert all(end <= documents[document_id].pages for document_id in record["expected_documents"])


def test_golden_queries_retrieve_the_expected_document_and_page_group(index_store) -> None:
    records = _golden_records()
    retriever = HybridRetriever(index_store)

    for record in records:
        results = retriever.search(record["query"], HashEmbedder.vector_for(record["query"]), top_k=3)
        assert any(result.document_id in record["expected_documents"] for result in results), record["id"]
        start, end = record["expected_page_range"]
        matching = next((result for result in results if result.document_id == record["expected_documents"][0] and start <= result.page <= end), None)
        assert matching is not None, record["id"]
        assert record["expected_topic"] in index_store.chunks_by_id[matching.chunk_id].topics


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
