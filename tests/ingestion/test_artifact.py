from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from ingestion.artifact import ArtifactChunk, BM25Data, IndexArtifact, read_artifact, write_artifact
from ingestion.models import CorpusDocument


OUTPUT_DIRECTORY = Path(__file__).resolve().parents[2] / "data"


def _document() -> CorpusDocument:
    return CorpusDocument(
        document_id="doc",
        filename="doc.pdf",
        title="Document",
        semester="Test",
        pages=1,
        sha256="0" * 64,
        download_url="/documents/doc.pdf",
        topics=("topic",),
    )


def _artifact() -> IndexArtifact:
    return IndexArtifact(
        schema_version=1,
        corpus_version="test-v1",
        embedding_model="fake",
        embedding_dimensions=2,
        built_at=1,
        documents=(_document(),),
        chunks=(
            ArtifactChunk(
                chunk_id="a" * 24,
                document_id="doc",
                filename="doc.pdf",
                semester="Test",
                page=1,
                text="Hello world",
                topics=("topic",),
                vector=(1.0, 0.0),
            ),
        ),
        bm25=BM25Data(term_frequencies=({"hello": 1, "world": 1},), document_frequencies={"hello": 1, "world": 1}, document_lengths=(2,), average_document_length=2.0),
    )


def test_artifact_round_trip_uses_deterministic_gzip() -> None:
    first = OUTPUT_DIRECTORY / "_task4-first.json.gz"
    second = OUTPUT_DIRECTORY / "_task4-second.json.gz"
    artifact = _artifact()
    try:
        write_artifact(first, artifact)
        write_artifact(second, artifact)

        assert first.read_bytes() == second.read_bytes()
        assert read_artifact(first) == artifact
        with gzip.open(first, "rt", encoding="utf-8") as stream:
            assert json.load(stream)["corpus_version"] == "test-v1"
    finally:
        first.unlink(missing_ok=True)
        second.unlink(missing_ok=True)


def test_artifact_rejects_chunk_and_bm25_integrity_mismatches() -> None:
    data = _artifact().model_dump(mode="json")
    data["chunks"].append(data["chunks"][0])
    with pytest.raises(ValueError, match="unique"):
        IndexArtifact.model_validate(data)

    data = _artifact().model_dump(mode="json")
    data["bm25"]["document_lengths"] = [3]
    with pytest.raises(ValueError, match="BM25"):
        IndexArtifact.model_validate(data)


def test_artifact_rejects_vectors_and_invalid_bm25_statistics() -> None:
    data = _artifact().model_dump(mode="json")
    data["chunks"][0]["vector"] = [0.0, 0.0]
    with pytest.raises(ValueError, match="normalized"):
        IndexArtifact.model_validate(data)

    data = _artifact().model_dump(mode="json")
    data["bm25"]["document_frequencies"] = {"hello": 2, "world": 1}
    with pytest.raises(ValueError, match="frequencies"):
        IndexArtifact.model_validate(data)

    data = _artifact().model_dump(mode="json")
    data["bm25"]["document_lengths"] = [1]
    with pytest.raises(ValueError, match="lengths"):
        IndexArtifact.model_validate(data)


def test_read_artifact_rejects_non_json_gzip() -> None:
    output = OUTPUT_DIRECTORY / "_task4-invalid.json.gz"
    try:
        with gzip.open(output, "wt", encoding="utf-8") as stream:
            stream.write("{")
        with pytest.raises(ValueError, match="JSON"):
            read_artifact(output)
    finally:
        output.unlink(missing_ok=True)
