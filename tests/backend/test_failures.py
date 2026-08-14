from collections.abc import AsyncIterator

from test_streaming import events


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
