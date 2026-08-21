from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.app import MAX_REQUEST_BYTES, create_app
from backend.retrieval import HybridRetriever
from backend.service import RagService, _within_budget
from tests.retrieval.conftest import HashEmbedder


pytest_plugins = ("tests.retrieval.conftest",)


class TrackingProvider:
    def __init__(self, vector: list[float], *, wait_for_lexical: asyncio.Event | None = None) -> None:
        self.vector = vector
        self.wait_for_lexical = wait_for_lexical
        self.generated = False

    async def embed_query(self, query: str) -> list[float]:
        if self.wait_for_lexical is not None:
            await self.wait_for_lexical.wait()
        return self.vector

    async def stream_answer(self, query: str, sources):
        self.generated = True
        yield "Grounded response [S1]."


def test_real_hybrid_retriever_refuses_unrelated_dense_only_evidence(index_store):
    async def exercise():
        query = "quasar nebula tachyon xylophone"
        provider = TrackingProvider(HashEmbedder.vector_for(query))
        events = [event async for event in RagService(HybridRetriever(index_store), provider, embedding_dimensions=768).stream_query(query, "req")]
        assert [event.name for event in events] == ["sources", "complete"]
        assert events[-1].data["refusal"] is True
        assert provider.generated is False

    asyncio.run(exercise())


def test_real_hybrid_retriever_allows_strong_lexically_supported_domain_query(index_store):
    async def exercise():
        query = "Arnett emerging adulthood Tan family"
        provider = TrackingProvider(HashEmbedder.vector_for(query))
        events = [event async for event in RagService(HybridRetriever(index_store), provider, embedding_dimensions=768).stream_query(query, "req")]
        assert [event.name for event in events] == ["sources", "token", "token", "complete"]
        assert provider.generated is True

    asyncio.run(exercise())


def test_generation_uses_the_same_bounded_evidence_exposed_in_sources():
    from tests.backend.conftest import FakeRetriever

    class CapturingProvider(TrackingProvider):
        def __init__(self) -> None:
            super().__init__([1.0])
            self.grounding_excerpt = ""

        async def stream_answer(self, query: str, sources):
            self.generated = True
            self.grounding_excerpt = sources[0].excerpt
            yield "Grounded response [S1]."

    async def exercise():
        provider = CapturingProvider()
        events = [
            event
            async for event in RagService(FakeRetriever(), provider, embedding_dimensions=1).stream_query(
                "Arnett", "req"
            )
        ]
        public_source = events[0].data["sources"][0]
        assert public_source["excerpt"] == "Arnett describes emerging adulthood as exploratory."
        assert provider.grounding_excerpt == public_source["excerpt"]

    asyncio.run(exercise())


def test_real_hybrid_retriever_allows_high_confidence_semantic_paraphrase(index_store):
    async def exercise():
        retriever = HybridRetriever(index_store)
        anchor = retriever.search("Arnett emerging adulthood", None, top_k=1)[0]
        query = "Liminal individuation provisionality"
        assert retriever.search_lexical(query, top_k=1) == []
        provider = TrackingProvider(list(index_store.chunks_by_id[anchor.chunk_id].vector))
        events = [event async for event in RagService(retriever, provider, embedding_dimensions=768).stream_query(query, "req")]
        assert [event.name for event in events] == ["sources", "token", "token", "complete"]
        assert provider.generated is True

    asyncio.run(exercise())


def test_lexical_search_starts_before_embedding_finishes():
    class ConcurrentRetriever:
        def __init__(self, started: asyncio.Event) -> None:
            self.started = started

        def search_lexical(self, query: str):
            self.started.set()
            from tests.backend.conftest import FakeRetriever
            return FakeRetriever().search(query, None)

        def search(self, query: str, vector):
            from tests.backend.conftest import FakeRetriever
            return FakeRetriever().search(query, vector)

    async def exercise():
        started = asyncio.Event()
        provider = TrackingProvider([1.0], wait_for_lexical=started)
        events = [event async for event in RagService(ConcurrentRetriever(started), provider, embedding_dimensions=1).stream_query("Arnett", "req")]
        assert started.is_set()
        assert provider.generated is True
        assert events[0].name == "sources"

    asyncio.run(exercise())


def test_total_deadline_limits_embedding_then_stalled_generation_without_resetting_budget():
    class LexicalRetriever:
        def search_lexical(self, query: str):
            from tests.backend.conftest import FakeRetriever
            return FakeRetriever().search(query, None)

        def search(self, query: str, vector):
            return self.search_lexical(query)

    class StalledProvider(TrackingProvider):
        async def embed_query(self, query: str):
            await asyncio.sleep(0.006)
            return [1.0]

        async def stream_answer(self, query: str, sources):
            self.generated = True
            await asyncio.sleep(0.02)
            yield "late [S1]"

    async def exercise():
        provider = StalledProvider([1.0])
        events = [event async for event in RagService(LexicalRetriever(), provider, embedding_dimensions=1, embedding_timeout_seconds=1, generation_timeout_seconds=1, total_timeout_seconds=0.01).stream_query("Arnett", "req")]
        assert events[-1].data["code"] == "generation_timeout"

    asyncio.run(exercise())


def test_nested_json_and_boundary_exception_are_safe_with_request_id_and_headers(app):
    nested = b'{"query":' + b"[" * 3_995 + b"0" + b"]" * 3_995 + b"}"
    assert len(nested) == 8_001
    with TestClient(app) as client:
        malformed = client.post("/api/query", content=nested, headers={"content-type": "application/json"})
    assert malformed.status_code == 400
    assert malformed.json()["code"] == "invalid_request"
    assert malformed.json()["request_id"]
    assert malformed.headers["x-content-type-options"] == "nosniff"

    boundary = create_app()
    @boundary.get("/boom")
    async def boom():
        raise RuntimeError("do not expose")

    with TestClient(boundary, raise_server_exceptions=False) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert response.json()["request_id"]
    assert response.headers["content-security-policy"]
    assert response.headers["x-request-id"] == response.json()["request_id"]


def test_service_deadline_helper_closes_unstarted_coroutine_and_propagates_cancellation():
    class Closable:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

        def __await__(self):
            return iter(())

    class EmptyRetriever:
        def search_lexical(self, query: str):
            return []

    class BlockingProvider:
        async def embed_query(self, query: str):
            await asyncio.Event().wait()

    async def exercise():
        closable = Closable()
        with pytest.raises(TimeoutError):
            await _within_budget(closable, deadline=0.0, stage_timeout=1, clock=lambda: 0.0)
        assert closable.closed is True

        stream = RagService(EmptyRetriever(), BlockingProvider()).stream_query("unmatched", "req")
        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending

    asyncio.run(exercise())


def test_search_lexical_rejects_invalid_arguments(index_store):
    retriever = HybridRetriever(index_store)
    with pytest.raises(ValueError):
        retriever.search_lexical(" ")
    with pytest.raises(ValueError):
        retriever.search_lexical("Arnett", top_k=0)


def test_middleware_propagates_cancellation_without_losing_boundary_policy():
    from starlette.requests import Request

    app = create_app()
    dispatch = app.user_middleware[0].kwargs["dispatch"]

    async def cancelled(_: Request):
        raise asyncio.CancelledError

    async def exercise():
        request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
        with pytest.raises(asyncio.CancelledError):
            await dispatch(request, cancelled)

    asyncio.run(exercise())


def test_service_race_and_retry_cancellation_branches(monkeypatch):
    from tests.backend.conftest import FakeRetriever
    import backend.service as service_module

    class SlowLexical:
        def search_lexical(self, query: str):
            import time
            time.sleep(0.01)
            return []

    class ImmediatelyCancelled:
        async def embed_query(self, query: str):
            raise asyncio.CancelledError

    class GateProvider:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.release = asyncio.Event()

        async def embed_query(self, query: str):
            self.started.set()
            await self.release.wait()
            raise RuntimeError("embedding unavailable")

    class GateSuccess(GateProvider):
        async def embed_query(self, query: str):
            self.started.set()
            await self.release.wait()
            return [1.0]

    class WaitingProvider:
        def __init__(self) -> None:
            self.started = asyncio.Event()

        async def embed_query(self, query: str):
            self.started.set()
            await asyncio.Event().wait()

    class DenseFailure(FakeRetriever):
        def search(self, query: str, vector, top_k: int = 5):
            if vector is not None:
                raise RuntimeError("vector unavailable")
            return super().search(query, vector, top_k)

    class EvidenceRetriever(FakeRetriever):
        def search_lexical(self, query: str, top_k: int = 5):
            return self.search(query, None, top_k)

    async def exercise():
        cancelled = RagService(SlowLexical(), ImmediatelyCancelled()).stream_query("none", "req")
        with pytest.raises(asyncio.CancelledError):
            await anext(cancelled)

        failure = GateProvider()
        pending_failure = asyncio.create_task(anext(RagService(SlowLexical(), failure).stream_query("none", "req")))
        await failure.started.wait()
        await asyncio.sleep(0.02)
        failure.release.set()
        assert (await pending_failure).name == "sources"

        semantic = GateSuccess()
        pending_semantic = asyncio.create_task(anext(RagService(SlowLexical(), semantic).stream_query("none", "req")))
        await semantic.started.wait()
        await asyncio.sleep(0.02)
        semantic.release.set()
        assert (await pending_semantic).name == "sources"

        waiting = WaitingProvider()
        pending_waiting = asyncio.create_task(anext(RagService(SlowLexical(), waiting).stream_query("none", "req")))
        await waiting.started.wait()
        await asyncio.sleep(0.02)
        pending_waiting.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending_waiting

        lexical_source = await anext(RagService(EvidenceRetriever(), WaitingProvider()).stream_query("Arnett", "req"))
        assert lexical_source.data["retrieval_mode"] == "lexical_degraded"

        original = service_module._lexical_search
        calls = 0
        retry_started = asyncio.Event()

        async def retry_search(retriever, query):
            nonlocal calls
            calls += 1
            if calls == 1:
                await asyncio.sleep(0.01)
                return await original(retriever, query)
            retry_started.set()
            await asyncio.Event().wait()

        monkeypatch.setattr(service_module, "_lexical_search", retry_search)
        provider = TrackingProvider([1.0])
        pending_retry = asyncio.create_task(anext(RagService(DenseFailure(), provider).stream_query("Arnett", "req")))
        await retry_started.wait()
        pending_retry.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending_retry

        calls = 0

        async def timeout_retry_search(retriever, query):
            nonlocal calls
            calls += 1
            if calls == 1:
                await asyncio.sleep(0.001)
                return await original(retriever, query)
            raise asyncio.TimeoutError

        monkeypatch.setattr(service_module, "_lexical_search", timeout_retry_search)
        timeout_events = [event async for event in RagService(DenseFailure(), TrackingProvider([1.0]), embedding_timeout_seconds=0.01).stream_query("Arnett", "req")]
        assert timeout_events[-1].data["code"] == "generation_timeout"

        monkeypatch.setattr(service_module, "_lexical_search", original)
        original_budget = service_module._within_budget
        budget_calls = 0

        async def cancelled_embedding(awaitable, *args):
            nonlocal budget_calls
            budget_calls += 1
            if budget_calls == 2:
                raise asyncio.CancelledError
            return await original_budget(awaitable, *args)

        monkeypatch.setattr(service_module, "_within_budget", cancelled_embedding)
        with pytest.raises(asyncio.CancelledError):
            await anext(RagService(SlowLexical(), WaitingProvider()).stream_query("unmatched", "req"))

    asyncio.run(exercise())
