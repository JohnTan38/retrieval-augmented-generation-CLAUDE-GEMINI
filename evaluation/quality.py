"""Dependency-light quality score validation shared by live evaluation tooling."""

from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QualityReport(BaseModel):
    """Aggregate quality scores normalized to the inclusive range zero to one."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    faithfulness: float = Field(ge=0.0, le=1.0)
    answer_relevance: float = Field(ge=0.0, le=1.0)
    context_precision: float = Field(ge=0.0, le=1.0)
    citation_validity: float = Field(ge=0.0, le=1.0)
    retrieval_hit_rate: float = Field(ge=0.0, le=1.0)
    successful_completion_rate: float = Field(ge=0.0, le=1.0)

    @field_validator("faithfulness", "answer_relevance", "context_precision", "citation_validity", "retrieval_hit_rate", "successful_completion_rate", mode="before")
    @classmethod
    def score_must_be_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("quality scores must be finite")
        return value


class LatencyReport(BaseModel):
    """Nearest-rank p95 timings for the live sources-first stream."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sources_p95_ms: float = Field(ge=0.0)
    first_token_p95_ms: float = Field(ge=0.0)
    complete_p95_ms: float = Field(ge=0.0)

    @field_validator("sources_p95_ms", "first_token_p95_ms", "complete_p95_ms", mode="before")
    @classmethod
    def latency_must_be_finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("latencies must be finite")
        return value


QUALITY_FLOORS = {
    "faithfulness": 0.85,
    "answer_relevance": 0.80,
    "context_precision": 0.80,
    "citation_validity": 1.00,
    "retrieval_hit_rate": 1.00,
    "successful_completion_rate": 1.00,
}

LATENCY_CEILINGS_MS = {
    "sources_p95_ms": 1500.0,
    "first_token_p95_ms": 3000.0,
    "complete_p95_ms": 15000.0,
}


def assert_quality_thresholds(report: QualityReport) -> None:
    """Raise when an aggregate score does not meet its required floor."""

    for field, floor in QUALITY_FLOORS.items():
        score = getattr(report, field)
        if score < floor:
            raise AssertionError(f"{field} score {score:.3f} is below required floor {floor:.2f}")


def assert_latency_thresholds(report: LatencyReport) -> None:
    """Raise when a p95 stream milestone exceeds its production ceiling."""

    for field, ceiling in LATENCY_CEILINGS_MS.items():
        latency = getattr(report, field)
        if latency > ceiling:
            raise AssertionError(f"{field} latency {latency:.0f}ms exceeds ceiling {ceiling:.0f}ms")
