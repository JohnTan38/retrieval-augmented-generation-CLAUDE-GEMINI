"""Strict public retrieval models without generation or provider concerns."""

from __future__ import annotations

import math
import re

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt, StrictStr, ValidationInfo, field_validator


_FILENAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\.pdf")


class FusedResult(BaseModel):
    """A positive reciprocal-rank score associated with one unique chunk."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: StrictStr = Field(min_length=1)
    score: StrictFloat = Field(gt=0)

    @field_validator("score")
    @classmethod
    def score_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("score must be finite")
        return value

class DiverseResult(FusedResult):
    """A fused result retained after document/page overlap suppression."""

    document_id: StrictStr = Field(min_length=1)
    page: StrictInt = Field(gt=0)


class SourceEvidence(BaseModel):
    """Safe page-level evidence sent to later API presentation code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: StrictStr = Field(min_length=1)
    source_id: StrictStr = Field(min_length=1)
    document_id: StrictStr = Field(min_length=1)
    filename: StrictStr
    title: StrictStr = Field(min_length=1)
    semester: StrictStr = Field(min_length=1)
    page: StrictInt = Field(gt=0)
    excerpt: StrictStr = Field(min_length=1, max_length=600)
    score: StrictFloat = Field(gt=0)
    lexical_score: StrictFloat = Field(ge=0, default=0.0)
    dense_score: StrictFloat = Field(ge=0, default=0.0)
    download_url: StrictStr

    @field_validator("filename")
    @classmethod
    def filename_is_safe_pdf_basename(cls, value: str) -> str:
        if not _FILENAME_PATTERN.fullmatch(value):
            raise ValueError("filename must be a safe PDF basename")
        return value

    @field_validator("source_id")
    @classmethod
    def source_id_matches_chunk(cls, value: str, info: ValidationInfo) -> str:
        if value != info.data.get("chunk_id"):
            raise ValueError("source ID must match chunk ID")
        return value

    @field_validator("title", "semester", "excerpt")
    @classmethod
    def text_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence text must not be blank")
        return value

    @field_validator("score", "lexical_score", "dense_score")
    @classmethod
    def score_is_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("score must be finite")
        return value

    @field_validator("download_url")
    @classmethod
    def download_url_matches_filename(cls, value: str, info: ValidationInfo) -> str:
        if value != f"/documents/{info.data.get('filename', '')}":
            raise ValueError("download URL must be the exact public PDF path")
        return value
