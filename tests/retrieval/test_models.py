from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.models import FusedResult, SourceEvidence


def _evidence(**overrides: object) -> SourceEvidence:
    values: dict[str, object] = {
        "chunk_id": "a" * 24,
        "source_id": "a" * 24,
        "document_id": "jan-2025",
        "filename": "swk501.pdf",
        "title": "SWK501",
        "semester": "January 2025",
        "page": 1,
        "excerpt": "Evidence excerpt",
        "score": 0.5,
        "download_url": "/documents/swk501.pdf",
    }
    values.update(overrides)
    return SourceEvidence(**values)


def test_source_evidence_is_frozen_and_uses_only_exact_safe_source_metadata() -> None:
    evidence = _evidence()

    assert evidence.model_dump()["download_url"] == "/documents/swk501.pdf"
    with pytest.raises(ValidationError):
        _evidence(filename="../unsafe.pdf")
    with pytest.raises(ValidationError):
        _evidence(source_id="other")
    with pytest.raises(ValidationError):
        _evidence(title=" ")
    with pytest.raises(ValidationError):
        _evidence(score=float("inf"))
    with pytest.raises(ValidationError):
        _evidence(download_url="/documents/other.pdf")
    with pytest.raises(ValidationError):
        SourceEvidence(**_evidence().model_dump(), unexpected=True)
    with pytest.raises(ValidationError):
        evidence.page = 2


def test_rank_models_require_positive_finite_scores() -> None:
    assert FusedResult(chunk_id="a", score=0.1).score == 0.1
    for score in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            FusedResult(chunk_id="a", score=score)
