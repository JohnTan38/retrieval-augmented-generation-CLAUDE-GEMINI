from collections.abc import AsyncIterator

from test_streaming import events
from backend.gemini_client import GenerationDelta
from backend.service import _safe_error_label


class EmbeddingFails:
    async def embed_query(self, query: str):
        raise RuntimeError("secret provider payload")

    async def stream_answer(self, query: str, sources: list[object]) -> AsyncIterator[str]:
        yield "Grounded response [S1]."


class GenerationFails(EmbeddingFails):
    async def embed_query(self, query: str):
        return [1.0]

    async def stream_answer(self, query: str, sources: list[object]) -> AsyncIterator[str]:
        raise RuntimeError("secret provider payload")
        yield ""


class TruncatedGeneration(EmbeddingFails):
    async def embed_query(self, query: str):
        return [1.0]

    async def stream_answer(self, query: str, sources: list[object]):
        yield GenerationDelta(text="Partial grounded thought [S1].")
        yield GenerationDelta(finish_reason="MAX_TOKENS")


class UncitedGeneration(TruncatedGeneration):
    async def stream_answer(self, query: str, sources: list[object]):
        yield GenerationDelta(text="A factual claim without a citation.")
        yield GenerationDelta(finish_reason="STOP")


def test_embedding_failure_falls_back_to_lexical(app):
    from fastapi.testclient import TestClient
    app.state.gateway.gemini = EmbeddingFails()
    with TestClient(app) as client:
        stream = events(client.post("/api/query", json={"query": "Arnett"}))
    assert stream[0][1]["retrieval_mode"] == "lexical_degraded"
    assert stream[-1][0] == "complete"


def test_generation_failure_is_safe_sse_error(app):
    from fastapi.testclient import TestClient
    app.state.gateway.gemini = GenerationFails()
    with TestClient(app) as client:
        stream = events(client.post("/api/query", json={"query": "Arnett"}))
    assert stream[-1][0] == "error"
    assert stream[-1][1] == {"code": "generation_unavailable", "message": "Answer generation is temporarily unavailable.", "retryable": True}


def test_truncated_and_uncited_generation_are_retryable_errors(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as client:
        app.state.gateway.gemini = TruncatedGeneration()
        truncated = events(client.post("/api/query", json={"query": "Arnett"}))
        app.state.gateway.gemini = UncitedGeneration()
        uncited = events(client.post("/api/query", json={"query": "Arnett"}))

    assert truncated[-1] == ("error", {"code": "generation_incomplete", "message": "Answer generation did not finish. Please retry.", "retryable": True, "partial_text": "Partial grounded thought [S1]."})
    assert uncited[-1] == ("error", {"code": "citation_invalid", "message": "The answer could not be grounded with valid citations. Please retry.", "retryable": True, "partial_text": "A factual claim without a citation."})


def test_provider_error_labels_include_only_structured_safe_fields():
    error = RuntimeError("sensitive payload")
    error.code = 503
    error.status = "PERMISSION_DENIED"
    assert _safe_error_label(error) == "RuntimeError code=503 status=PERMISSION_DENIED"
    error.status = "unsafe free text"
    assert _safe_error_label(error) == "RuntimeError code=503"
