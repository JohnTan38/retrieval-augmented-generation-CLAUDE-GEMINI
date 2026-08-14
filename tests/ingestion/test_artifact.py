from __future__ import annotations

import gzip
import json
import os
from pathlib import Path

import pytest

from ingestion.artifact import ArtifactChunk, BM25Data, IndexArtifact, read_artifact, read_artifact_bytes, write_artifact
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


def test_read_artifact_bytes_validates_one_immutable_snapshot() -> None:
    artifact = _artifact()
    output = OUTPUT_DIRECTORY / "_task4-snapshot.json.gz"
    try:
        write_artifact(output, artifact)
        snapshot = output.read_bytes()
        output.write_bytes(b"not a gzip artifact")
        assert read_artifact_bytes(snapshot) == artifact
        with pytest.raises(ValueError, match="gzip JSON"):
            read_artifact_bytes(output.read_bytes())
    finally:
        output.unlink(missing_ok=True)


def test_snapshot_reading_rejects_missing_paths_and_non_bytes(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="gzip JSON"):
        read_artifact(tmp_path / "missing.json.gz")
    with pytest.raises(ValueError, match="gzip JSON"):
        read_artifact_bytes("not bytes")  # type: ignore[arg-type]


def test_snapshot_reader_wraps_a_truncated_gzip_header_as_a_stable_value_error() -> None:
    with pytest.raises(ValueError, match="gzip JSON"):
        read_artifact_bytes(bytes.fromhex("1f8b0800"))


def test_artifact_rejects_chunk_id_suffix_and_document_metadata_corruption() -> None:
    for field, value in (("chunk_id", "a" * 24 + "x"), ("document_id", "missing"), ("filename", "other.pdf"), ("semester", "Other"), ("page", 2), ("topics", ["other"])):
        data = _artifact().model_dump(mode="json")
        data["chunks"][0][field] = value
        with pytest.raises(ValueError):
            IndexArtifact.model_validate(data)


def test_write_artifact_is_atomic_when_replace_fails(monkeypatch) -> None:
    output = OUTPUT_DIRECTORY / "_task4-atomic.json.gz"
    original = b"existing-valid-artifact"
    output.write_bytes(original)
    try:
        monkeypatch.setattr(os, "replace", lambda *_: (_ for _ in ()).throw(OSError("replace failed")))
        with pytest.raises(OSError, match="replace failed"):
            write_artifact(output, _artifact())
        assert output.read_bytes() == original
    finally:
        output.unlink(missing_ok=True)


@pytest.mark.parametrize("mutate", [
    lambda data: data["chunks"][0].update(vector=[2.0, 0.0]),
    lambda data: data["bm25"].update(document_lengths=[]),
    lambda data: data["bm25"].update(document_lengths=[0]),
    lambda data: data["bm25"].update(term_frequencies=[{"hello": 0}]),
    lambda data: data["bm25"].update(document_frequencies={"hello": 2, "world": 1}),
    lambda data: data["bm25"].update(average_document_length=3.0),
    lambda data: data.update(documents=[data["documents"][0], data["documents"][0]]),
    lambda data: data.update(chunks=[data["chunks"][0], data["chunks"][0]]),
    lambda data: data["chunks"][0].update(vector=[0.6, 0.8, 0.0]),
])
def test_artifact_validation_branches(mutate) -> None:
    data = _artifact().model_dump(mode="json")
    mutate(data)
    with pytest.raises(ValueError):
        IndexArtifact.model_validate(data)


def test_artifact_hits_remaining_schema_integrity_branches() -> None:
    data = _artifact().model_dump(mode="json")
    data["chunks"][0]["vector"] = [float("inf"), 0.0]
    with pytest.raises(ValueError): IndexArtifact.model_validate(data)
    with pytest.raises(ValueError): BM25Data(term_frequencies=({"x": 1}, {"x": 1}), document_frequencies={"x": 1}, document_lengths=(1, 1), average_document_length=1.0)
    with pytest.raises(ValueError): BM25Data(term_frequencies=({"x": 1}, {"y": 1}), document_frequencies={"x": 1}, document_lengths=(1,), average_document_length=1.0)
    with pytest.raises(ValueError): BM25Data(term_frequencies=({"x": 1}, {"y": 1}), document_frequencies={"x": 1}, document_lengths=(1, 1), average_document_length=1.0)
    data = _artifact().model_dump(mode="json")
    extra = data["chunks"][0].copy(); extra["chunk_id"] = "b" * 24
    data["chunks"].append(extra)
    with pytest.raises(ValueError, match="BM25 data"): IndexArtifact.model_validate(data)
    output = OUTPUT_DIRECTORY / "_task4-schema.json.gz"
    try:
        with gzip.open(output, "wt", encoding="utf-8") as stream: json.dump({}, stream)
        with pytest.raises(ValueError, match="schema"): read_artifact(output)
    finally: output.unlink(missing_ok=True)


def test_atomic_write_cleans_up_when_temp_creation_fails(monkeypatch) -> None:
    output = OUTPUT_DIRECTORY / "_task4-temp-fail.json.gz"
    monkeypatch.setattr("ingestion.artifact.tempfile.NamedTemporaryFile", lambda **_: (_ for _ in ()).throw(OSError("temp fail")))
    with pytest.raises(OSError, match="temp fail"):
        write_artifact(output, _artifact())
