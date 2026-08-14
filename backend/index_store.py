"""Thread-safe immutable in-memory view of one validated index artifact."""

from __future__ import annotations

from collections import OrderedDict
from hashlib import sha256
from pathlib import Path
from threading import RLock
from types import MappingProxyType

from ingestion.artifact import ArtifactChunk, IndexArtifact, read_artifact_bytes
from ingestion.models import CorpusDocument


_MAX_CACHE_ENTRIES = 8


class IndexStore:
    """Precomputed runtime data, cached by resolved file path and raw SHA-256.

    The fingerprint is the SHA-256 of the compressed artifact bytes.  With the
    one-path runtime interface there is no separately supplied expected digest:
    a changed digest is cache drift, so it always causes a fresh validation;
    invalid replacement bytes fail instead of returning the previous store.
    """

    _cache_lock = RLock()
    _cache: "OrderedDict[tuple[Path, str], IndexStore]" = OrderedDict()

    def __init__(self, artifact: IndexArtifact, fingerprint: str) -> None:
        self._validate_artifact(artifact)
        self.artifact = artifact
        self.fingerprint = fingerprint
        self.corpus_version = artifact.corpus_version
        self.embedding_dimensions = artifact.embedding_dimensions
        self.documents_by_id = MappingProxyType(
            {document.document_id: document for document in artifact.documents}
        )
        self.chunks_by_id = MappingProxyType(
            {chunk.chunk_id: chunk for chunk in artifact.chunks}
        )
        self.vectors = tuple(chunk.vector for chunk in artifact.chunks)
        self.bm25_term_frequencies = tuple(
            MappingProxyType(dict(frequency)) for frequency in artifact.bm25.term_frequencies
        )
        self.bm25_document_frequencies = MappingProxyType(dict(artifact.bm25.document_frequencies))
        self.bm25_document_lengths = artifact.bm25.document_lengths
        self.bm25_average_document_length = artifact.bm25.average_document_length

    @classmethod
    def load(cls, path: Path) -> "IndexStore":
        """Return the validated cache entry for the current file bytes only."""
        try:
            resolved = Path(path).resolve(strict=True)
            snapshot = _read_snapshot(resolved)
        except (OSError, ValueError) as error:
            raise ValueError("index artifact is unavailable") from error
        fingerprint = _snapshot_sha256(snapshot)
        key = (resolved, fingerprint)
        with cls._cache_lock:
            cached = cls._cache.get(key)
            if cached is not None:
                cls._cache.move_to_end(key)
                return cached
            try:
                artifact = read_artifact_bytes(snapshot)
            except (OSError, ValueError) as error:
                raise ValueError("index artifact is invalid") from error
            store = cls(artifact, fingerprint)
            for stale_key in [entry for entry in cls._cache if entry[0] == resolved]:
                del cls._cache[stale_key]
            cls._cache[key] = store
            while len(cls._cache) > _MAX_CACHE_ENTRIES:
                cls._cache.popitem(last=False)
            return store

    @classmethod
    def reset_cache_for_tests(cls) -> None:
        """Clear process cache; intentionally exposed only for deterministic tests."""
        with cls._cache_lock:
            cls._cache.clear()

    @classmethod
    def cache_size_for_tests(cls) -> int:
        with cls._cache_lock:
            return len(cls._cache)

    @staticmethod
    def _validate_artifact(artifact: IndexArtifact) -> None:
        if artifact.schema_version != 1 or not artifact.documents or not artifact.chunks:
            raise ValueError("index artifact has an unsupported or empty corpus")
        documents: dict[str, CorpusDocument] = {}
        for document in artifact.documents:
            if document.document_id in documents or document.download_url != f"/documents/{document.filename}":
                raise ValueError("index artifact has unsafe or duplicate documents")
            documents[document.document_id] = document
        chunk_ids: set[str] = set()
        if len(artifact.chunks) != len(artifact.bm25.document_lengths):
            raise ValueError("index artifact BM25 data does not align with chunks")
        for chunk in artifact.chunks:
            _validate_chunk(chunk, documents, artifact.embedding_dimensions, chunk_ids)


def _validate_chunk(
    chunk: ArtifactChunk,
    documents: dict[str, CorpusDocument],
    dimensions: int,
    chunk_ids: set[str],
) -> None:
    if chunk.chunk_id in chunk_ids or chunk.document_id not in documents or len(chunk.vector) != dimensions:
        raise ValueError("index artifact has duplicate, orphaned, or dimension-mismatched chunks")
    document = documents[chunk.document_id]
    if (
        chunk.filename != document.filename
        or chunk.semester != document.semester
        or chunk.page > document.pages
        or chunk.topics != document.topics
    ):
        raise ValueError("index artifact chunk metadata is unsafe")
    chunk_ids.add(chunk.chunk_id)


def _read_snapshot(path: Path) -> bytes:
    return path.read_bytes()


def _snapshot_sha256(snapshot: bytes) -> str:
    return sha256(snapshot).hexdigest()
