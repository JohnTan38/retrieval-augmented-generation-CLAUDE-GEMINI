from __future__ import annotations

from pathlib import Path

import pytest

from ingestion.artifact import read_artifact
from ingestion.indexer import _bm25, _build_timestamp, build_index, tokenize


ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIRECTORY = ROOT / "data"


class FakeEmbedder:
    model = "fake-embedding"

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(text)), 1.0] for text in texts]


def test_build_index_writes_the_deterministic_hybrid_artifact() -> None:
    first = OUTPUT_DIRECTORY / "_task4-first.json.gz"
    second = OUTPUT_DIRECTORY / "_task4-second.json.gz"
    try:

        one = build_index(ROOT / "data/corpus-manifest.json", ROOT / "public/documents", first, FakeEmbedder())
        two = build_index(ROOT / "data/corpus-manifest.json", ROOT / "public/documents", second, FakeEmbedder())

        assert one == two
        assert one.corpus_version == "swk501-2026-01-v1"
        assert one.embedding_dimensions == 2
        assert len(one.documents) == 3
        assert sum(document.pages for document in one.documents) == 89
        assert len(one.chunks) == 93
        assert first.read_bytes() == second.read_bytes()
        assert read_artifact(first) == one
    finally:
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)


def test_tokenize_is_unicode_aware_casefolded_and_deterministic() -> None:
    assert tokenize("Straße, CAFÉ — child's 2026!") == ("strasse", "café", "child", "s", "2026")
    with pytest.raises(ValueError, match="string"):
        tokenize(None)  # type: ignore[arg-type]


def test_bm25_rejects_text_without_lexical_terms() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        _bm25(["---"])


def test_build_timestamp_uses_valid_source_date_epoch_or_canonical_mtime(monkeypatch) -> None:
    manifest = type("Manifest", (), {"documents": []})()
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "12")
    assert _build_timestamp(manifest, ROOT / "public" / "documents") == 12
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "-1")
    with pytest.raises(ValueError, match="SOURCE_DATE_EPOCH"):
        _build_timestamp(manifest, ROOT / "public" / "documents")


def test_build_index_rejects_embedder_response_count_mismatch() -> None:
    class BadEmbedder:
        model = "bad"

        def embed_documents(self, texts: list[str]) -> list[list[float]]:
            return [[1.0, 0.0]] if texts else []

    output = OUTPUT_DIRECTORY / "_task4-bad.json.gz"
    try:
        with pytest.raises(ValueError, match="response count"):
            build_index(ROOT / "data/corpus-manifest.json", ROOT / "public/documents", output, BadEmbedder())
    finally:
        output.unlink(missing_ok=True)
