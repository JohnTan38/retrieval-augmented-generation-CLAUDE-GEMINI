from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    ValidationInfo,
    field_validator,
    model_validator,
)


_FILENAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.pdf")
_SHA256_PATTERN = re.compile(r"[0-9a-fA-F]{64}")
_CHUNK_ID_PATTERN = re.compile(r"[0-9a-f]{24}")


def _required_text(value: str, field_name: str) -> str:
    if not value.strip():
        raise ValueError(f"{field_name} must not be blank")
    return value.strip()


class CorpusDocument(BaseModel):
    """Metadata and integrity expectations for one static corpus PDF."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: StrictStr = Field(min_length=1)
    filename: StrictStr
    title: StrictStr = Field(min_length=1)
    semester: StrictStr = Field(min_length=1)
    variant: Literal["research", "claude"] = "research"
    pages: StrictInt = Field(gt=0)
    sha256: StrictStr
    download_url: StrictStr
    topics: tuple[StrictStr, ...] = Field(min_length=1)

    @field_validator("document_id", "title", "semester")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _required_text(value, "required metadata")

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        if Path(value).name != value or not _FILENAME_PATTERN.fullmatch(value):
            raise ValueError("filename must be a safe PDF basename")
        return value

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        if not _SHA256_PATTERN.fullmatch(value):
            raise ValueError("SHA-256 checksum must be a 64-character hexadecimal string")
        return value.lower()

    @field_validator("download_url")
    @classmethod
    def validate_download_url(cls, value: str, info: ValidationInfo) -> str:
        expected_url = f"/documents/{info.data.get('filename', '')}"
        if value != expected_url:
            raise ValueError("download URL must be the document's public PDF path")
        return value

    @field_validator("topics")
    @classmethod
    def validate_topics(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not all(topic.strip() for topic in value):
            raise ValueError("topics must not contain empty values")
        return tuple(topic.strip() for topic in value)


class CorpusManifest(BaseModel):
    """Versioned, extensible manifest for a fixed set of static documents."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: StrictInt = Field(ge=1, le=1)
    corpus_version: StrictStr = Field(min_length=1)
    documents: tuple[CorpusDocument, ...] = Field(min_length=1)

    @field_validator("corpus_version")
    @classmethod
    def validate_corpus_version(cls, value: str) -> str:
        return _required_text(value, "corpus version")

    @model_validator(mode="after")
    def validate_unique_documents(self) -> "CorpusManifest":
        document_ids = [document.document_id for document in self.documents]
        if len(document_ids) != len(set(document_ids)):
            raise ValueError("duplicate document IDs are not allowed")
        filenames = [document.filename.casefold() for document in self.documents]
        if len(filenames) != len(set(filenames)):
            raise ValueError("duplicate filenames are not allowed")
        return self


class PageText(BaseModel):
    """Normalized extractable text from one one-based PDF page."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: StrictStr
    page: StrictInt = Field(gt=0)
    text: StrictStr

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        return _required_text(value, "document ID")

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("page text must not be blank")
        return value


class ChunkRecord(BaseModel):
    """Stable, page-local semantic chunk and its source metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: StrictStr
    document_id: StrictStr
    filename: StrictStr
    semester: StrictStr
    variant: Literal["research", "claude"] = "research"
    page: StrictInt = Field(gt=0)
    text: StrictStr
    topics: tuple[StrictStr, ...] = Field(min_length=1)

    @field_validator("chunk_id")
    @classmethod
    def validate_chunk_id(cls, value: str) -> str:
        if not _CHUNK_ID_PATTERN.fullmatch(value):
            raise ValueError("chunk ID must be a 24-character lowercase hexadecimal string")
        return value

    @field_validator("document_id", "filename", "semester")
    @classmethod
    def validate_source_text(cls, value: str) -> str:
        return _required_text(value, "chunk metadata")

    @field_validator("text")
    @classmethod
    def validate_chunk_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("chunk text must not be blank")
        return value

    @field_validator("topics")
    @classmethod
    def validate_chunk_topics(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not all(topic.strip() for topic in value):
            raise ValueError("chunk topics must not contain empty values")
        return tuple(topic.strip() for topic in value)
