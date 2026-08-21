from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.models import SourceEvidence


@dataclass
class FakeArtifact:
    schema_version: int = 1
    corpus_version: str = "swk501-2026-01-v2"
    embedding_model: str = "gemini-embedding-001"


class FakeStore:
    artifact = FakeArtifact()
    corpus_version = artifact.corpus_version
    embedding_dimensions = 1

    def __init__(self) -> None:
        self.artifact.documents = (
            type("Document", (), {
                "document_id": "jan-2026", "filename": "swk501-january-2026.pdf",
                "title": "SWK501 January 2026", "semester": "January 2026", "pages": 27,
                "variant": "research",
                "topics": ("development",), "sha256": "a" * 64,
                "download_url": "/documents/swk501-january-2026.pdf",
            })(),
        )


class FakeRetriever:
    def search(self, query: str, vector: list[float] | None, top_k: int = 5) -> list[SourceEvidence]:
        if "nothing" in query:
            return []
        return [
            SourceEvidence(
                chunk_id="a" * 24, source_id="a" * 24, document_id="jan-2026",
                filename="swk501-january-2026.pdf", title="SWK501 January 2026",
                semester="January 2026", variant="research", page=2, excerpt="Arnett describes emerging adulthood as exploratory.",
                score=0.9, lexical_score=1.0, download_url="/documents/swk501-january-2026.pdf",
            )
        ]


class FakeGemini:
    async def embed_query(self, query: str) -> list[float]:
        return [1.0]

    async def stream_answer(self, query: str, sources: list[object]) -> AsyncIterator[str]:
        yield "Arnett describes a period of exploration [S1]."


@pytest.fixture
def app():
    from backend.app import create_app

    return create_app(store=FakeStore(), retriever=FakeRetriever(), gemini=FakeGemini())


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
