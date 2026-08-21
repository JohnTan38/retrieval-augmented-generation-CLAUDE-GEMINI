from __future__ import annotations

from pathlib import Path
import threading

import pytest

from ingestion.artifact import read_artifact, write_artifact

from backend.index_store import IndexStore


def test_loads_validated_artifact_once_and_exposes_precomputed_lookups(artifact_path: Path) -> None:
    first = IndexStore.load(artifact_path)
    second = IndexStore.load(artifact_path)

    assert first is second
    assert len(first.chunks_by_id) == 137
    assert len(first.documents_by_id) == 6
    assert len(first.vectors) == len(first.bm25_term_frequencies) == 137
    assert len(first.fingerprint) == 64


def test_load_cache_is_thread_safe(artifact_path: Path) -> None:
    stores = []
    errors = []

    def load() -> None:
        try:
            stores.append(IndexStore.load(artifact_path))
        except Exception as error:  # pragma: no cover - asserted after joining
            errors.append(error)

    threads = [threading.Thread(target=load) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert not errors
    assert len({id(store) for store in stores}) == 1


def test_detects_changed_or_corrupt_artifact_at_the_same_path(artifact_path: Path) -> None:
    original = IndexStore.load(artifact_path)
    artifact = read_artifact(artifact_path)
    changed = artifact.model_copy(update={"built_at": 42})
    write_artifact(artifact_path, changed)

    replacement = IndexStore.load(artifact_path)
    assert replacement is not original
    assert replacement.corpus_version == "swk501-2026-01-v2"

    artifact_path.write_bytes(b"not a gzip artifact")
    with pytest.raises(ValueError, match="index artifact"):
        IndexStore.load(artifact_path)


def test_rejects_missing_artifact_and_has_a_test_only_reset_hook(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unavailable"):
        IndexStore.load(tmp_path)

    IndexStore.reset_cache_for_tests()
    assert IndexStore.cache_size_for_tests() == 0


def test_cache_is_bounded(artifact_path: Path, tmp_path: Path) -> None:
    original_bytes = artifact_path.read_bytes()
    for index in range(9):
        path = tmp_path / f"copy-{index}.json.gz"
        path.write_bytes(original_bytes)
        IndexStore.load(path)
    assert IndexStore.cache_size_for_tests() == 8



def test_cache_hit_uses_one_snapshot_when_path_is_replaced_after_read(artifact_path: Path, monkeypatch) -> None:
    from backend import index_store as module

    first = IndexStore.load(artifact_path)
    original_read = module._read_snapshot
    replacement = read_artifact(artifact_path).model_copy(update={"built_at": 99})

    def snapshot_then_replace(path: Path) -> bytes:
        snapshot = original_read(path)
        write_artifact(path, replacement)
        return snapshot

    monkeypatch.setattr(module, "_read_snapshot", snapshot_then_replace)
    assert IndexStore.load(artifact_path) is first
    monkeypatch.setattr(module, "_read_snapshot", original_read)
    assert IndexStore.load(artifact_path).artifact.built_at == 99


def test_rejects_nonproduction_dense_metadata_and_manifest_drift(artifact_path: Path) -> None:
    artifact = read_artifact(artifact_path)
    invalid_cases = [
        artifact.model_copy(update={"embedding_model": "test-hash-768"}),
        artifact.model_copy(update={"corpus_version": "swk501-2026-01-v1"}),
        artifact.model_copy(update={"documents": (artifact.documents[0].model_copy(update={"sha256": "f" * 64}),) + artifact.documents[1:]}),
        artifact.model_copy(update={"chunks": artifact.chunks[:-1]}),
    ]
    for invalid in invalid_cases:
        write_artifact(artifact_path, invalid)
        with pytest.raises(ValueError, match="index artifact"):
            IndexStore.load(artifact_path)
    write_artifact(artifact_path, artifact)


def test_rejects_a_corrupt_snapshot_without_reopening_the_path(artifact_path: Path, monkeypatch) -> None:
    from backend import index_store as module

    monkeypatch.setattr(module, "_read_snapshot", lambda _: b"not a gzip artifact")
    with pytest.raises(ValueError, match="invalid"):
        IndexStore.load(artifact_path)


def test_load_wraps_a_truncated_gzip_snapshot_as_an_invalid_index(tmp_path: Path) -> None:
    path = tmp_path / "truncated.json.gz"
    path.write_bytes(bytes.fromhex("1f8b0800"))

    with pytest.raises(ValueError, match="index artifact is invalid") as error:
        IndexStore.load(path)

    assert isinstance(error.value.__cause__, ValueError)
    assert "gzip JSON" in str(error.value.__cause__)


def test_store_rejects_constructed_artifact_integrity_corruption(artifact_path: Path) -> None:
    artifact = read_artifact(artifact_path)
    invalid_cases = [
        artifact.model_copy(update={"schema_version": 2}),
        artifact.model_copy(update={"documents": ()}),
        artifact.model_copy(update={"documents": artifact.documents + (artifact.documents[0],)}),
        artifact.model_copy(update={"documents": (artifact.documents[0].model_copy(update={"download_url": "/documents/other.pdf"}),) + artifact.documents[1:]}),
        artifact.model_copy(update={"bm25": artifact.bm25.model_copy(update={"document_lengths": artifact.bm25.document_lengths[:-1]})}),
        artifact.model_copy(update={"chunks": artifact.chunks + (artifact.chunks[0],)}),
        artifact.model_copy(update={"chunks": (artifact.chunks[0].model_copy(update={"document_id": "missing"}),) + artifact.chunks[1:]}),
        artifact.model_copy(update={"chunks": (artifact.chunks[0].model_copy(update={"filename": "other.pdf"}),) + artifact.chunks[1:]}),
    ]
    for invalid in invalid_cases:
        with pytest.raises(ValueError):
            IndexStore._validate_artifact(invalid)


def test_store_rejects_an_artifact_that_omits_one_manifest_page(artifact_path: Path) -> None:
    artifact = read_artifact(artifact_path)
    by_page = {}
    for chunk in artifact.chunks:
        by_page.setdefault((chunk.document_id, chunk.page), []).append(chunk)
    omitted = next(chunks[0] for chunks in by_page.values() if len(chunks) == 1)
    replacement_source = next(chunk for chunk in artifact.chunks if chunk.chunk_id != omitted.chunk_id)
    replacement = replacement_source.model_copy(update={"chunk_id": "e" * 24})
    chunks = tuple(chunk for chunk in artifact.chunks if chunk.chunk_id != omitted.chunk_id) + (replacement,)

    with pytest.raises(ValueError, match="cover every manifest page"):
        IndexStore._validate_artifact(artifact.model_copy(update={"chunks": chunks}))
