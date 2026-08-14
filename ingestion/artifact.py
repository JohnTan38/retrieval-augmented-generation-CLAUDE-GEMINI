"""Versioned, strict, deterministic on-disk hybrid-index artifact."""

from __future__ import annotations

from collections.abc import Mapping
import gzip
import json
import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, field_validator, model_validator

from ingestion.models import CorpusDocument


class ArtifactChunk(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: StrictStr = Field(pattern=r"[0-9a-f]{24}")
    document_id: StrictStr = Field(min_length=1)
    filename: StrictStr = Field(min_length=1)
    semester: StrictStr = Field(min_length=1)
    page: StrictInt = Field(gt=0)
    text: StrictStr = Field(min_length=1)
    topics: tuple[StrictStr, ...] = Field(min_length=1)
    vector: tuple[StrictFloat, ...] = Field(min_length=1)

    @field_validator("vector")
    @classmethod
    def validate_vector(cls, vector: tuple[float, ...]) -> tuple[float, ...]:
        if not all(math.isfinite(value) for value in vector):
            raise ValueError("vector values must be finite")
        length = math.sqrt(sum(value * value for value in vector))
        if length == 0 or not math.isclose(length, 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("vector must be nonzero and normalized")
        return vector


class BM25Data(BaseModel):
    """Pre-tokenized lexical statistics aligned one-to-one with artifact chunks."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    term_frequencies: tuple[dict[StrictStr, StrictInt], ...] = Field(min_length=1)
    document_frequencies: dict[StrictStr, StrictInt]
    document_lengths: tuple[StrictInt, ...] = Field(min_length=1)
    average_document_length: StrictFloat = Field(gt=0)

    @model_validator(mode="after")
    def validate_statistics(self) -> "BM25Data":
        if len(self.term_frequencies) != len(self.document_lengths):
            raise ValueError("BM25 frequencies and lengths must align")
        if any(length <= 0 for length in self.document_lengths):
            raise ValueError("BM25 document lengths must be positive")
        if any(count <= 0 for frequency in self.term_frequencies for count in frequency.values()):
            raise ValueError("BM25 term frequencies must be positive")
        if any(sum(frequency.values()) != length for frequency, length in zip(self.term_frequencies, self.document_lengths, strict=True)):
            raise ValueError("BM25 term frequencies must match document lengths")
        if any(count <= 0 or count > len(self.document_lengths) for count in self.document_frequencies.values()):
            raise ValueError("BM25 document frequencies are out of range")
        observed = {term: sum(term in frequency for frequency in self.term_frequencies) for term in self.document_frequencies}
        if observed != self.document_frequencies:
            raise ValueError("BM25 document frequencies must match term frequencies")
        if set().union(*(set(frequency) for frequency in self.term_frequencies)) != set(self.document_frequencies):
            raise ValueError("BM25 document frequencies must include every term")
        average = sum(self.document_lengths) / len(self.document_lengths)
        if not math.isclose(self.average_document_length, average, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("BM25 average document length must match lengths")
        return self


class IndexArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: StrictInt = Field(ge=1, le=1)
    corpus_version: StrictStr = Field(min_length=1)
    embedding_model: StrictStr = Field(min_length=1)
    embedding_dimensions: StrictInt = Field(gt=0)
    built_at: StrictInt = Field(ge=0)
    documents: tuple[CorpusDocument, ...] = Field(min_length=1)
    chunks: tuple[ArtifactChunk, ...] = Field(min_length=1)
    bm25: BM25Data

    @model_validator(mode="after")
    def validate_integrity(self) -> "IndexArtifact":
        document_ids = {document.document_id for document in self.documents}
        if len(document_ids) != len(self.documents):
            raise ValueError("artifact document IDs must be unique")
        chunk_ids = [chunk.chunk_id for chunk in self.chunks]
        if len(chunk_ids) != len(set(chunk_ids)):
            raise ValueError("chunk IDs must be unique")
        if len(self.chunks) != len(self.bm25.document_lengths):
            raise ValueError("BM25 data must align with chunks")
        for chunk in self.chunks:
            if chunk.document_id not in document_ids:
                raise ValueError("chunk document is missing from artifact documents")
            document = next(document for document in self.documents if document.document_id == chunk.document_id)
            if chunk.filename != document.filename or chunk.semester != document.semester or chunk.page > document.pages:
                raise ValueError("chunk metadata does not match its document")
            if len(chunk.vector) != self.embedding_dimensions:
                raise ValueError("chunk vector dimensions must match artifact")
        return self


def write_artifact(path: Path, artifact: IndexArtifact) -> None:
    """Write stable UTF-8 JSON into gzip with zero mtime and no filename header."""
    payload = json.dumps(
        artifact.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            compressed.write(payload)


def read_artifact(path: Path) -> IndexArtifact:
    with gzip.open(path, "rt", encoding="utf-8") as compressed:
        try:
            payload: Mapping[str, object] = json.load(compressed)
        except json.JSONDecodeError as error:
            raise ValueError("index artifact must contain JSON") from error
    return IndexArtifact.model_validate(payload)
