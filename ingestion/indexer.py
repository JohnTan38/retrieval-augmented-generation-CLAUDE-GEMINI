"""Deterministic construction of the immutable SWK501 hybrid retrieval artifact."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
import os
from pathlib import Path
import re
import unicodedata

from ingestion.artifact import ArtifactChunk, BM25Data, IndexArtifact, write_artifact
from ingestion.chunker import chunk_pages
from ingestion.embeddings import Embedder, normalize_embeddings
from ingestion.manifest import load_manifest
from ingestion.parser import extract_pages


_LEXICAL_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def tokenize(text: str) -> tuple[str, ...]:
    """NFKC-normalize then Unicode-word tokenize and casefold text for BM25."""
    if not isinstance(text, str):
        raise ValueError("BM25 text must be a string")
    return tuple(match.group().casefold() for match in _LEXICAL_TOKEN.finditer(unicodedata.normalize("NFKC", text)))


def build_index(manifest_path: Path, documents_dir: Path, output_path: Path, embedder: Embedder) -> IndexArtifact:
    """Validate corpus, parse/chunk in manifest order, embed, and persist immutable data."""
    manifest = load_manifest(manifest_path, documents_dir)
    chunks = []
    for document in manifest.documents:
        chunks.extend(chunk_pages(document, extract_pages(documents_dir / document.filename, document.document_id), corpus_version=manifest.corpus_version))
    if not chunks:
        raise ValueError("validated corpus produced no chunks")
    vectors = embedder.embed_documents([chunk.text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise ValueError("embedding response count does not match chunks")
    normalized = normalize_embeddings(vectors)
    artifact_chunks = tuple(
        ArtifactChunk(**chunk.model_dump(), vector=tuple(vector))
        for chunk, vector in zip(chunks, normalized, strict=True)
    )
    artifact = IndexArtifact(
        schema_version=1,
        corpus_version=manifest.corpus_version,
        embedding_model=embedder.model,
        embedding_dimensions=len(normalized[0]),
        built_at=_build_timestamp(manifest, documents_dir),
        documents=manifest.documents,
        chunks=artifact_chunks,
        bm25=_bm25(chunk.text for chunk in chunks),
    )
    write_artifact(output_path, artifact)
    return artifact


def _bm25(texts: Sequence[str] | object) -> BM25Data:
    frequencies = tuple(dict(Counter(tokenize(text))) for text in texts)
    lengths = tuple(sum(frequency.values()) for frequency in frequencies)
    if not frequencies or any(length == 0 for length in lengths):
        raise ValueError("chunks must yield non-empty BM25 token sequences")
    document_frequencies = dict(Counter(term for frequency in frequencies for term in frequency))
    return BM25Data(
        term_frequencies=frequencies,
        document_frequencies=document_frequencies,
        document_lengths=lengths,
        average_document_length=sum(lengths) / len(lengths),
    )


def _build_timestamp(manifest: object, documents_dir: Path) -> int:
    source_date_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_date_epoch is not None:
        if not source_date_epoch.isascii() or not source_date_epoch.isdecimal():
            raise ValueError("SOURCE_DATE_EPOCH must be a non-negative integer")
        return int(source_date_epoch)
    return max(int((documents_dir / document.filename).stat().st_mtime) for document in manifest.documents)
