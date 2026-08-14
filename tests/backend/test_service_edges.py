from __future__ import annotations

import asyncio

from backend.service import RagService
from tests.backend.conftest import FakeRetriever


class NeverProvider:
    async def embed_query(self, query: str):
        return [1.0]

    async def stream_answer(self, query: str, sources):
        try:
            await asyncio.Event().wait()
            yield "unreachable"
        finally:
            self.closed = True


class SlowProvider(NeverProvider):
    async def stream_answer(self, query: str, sources):
        await asyncio.sleep(0.01)
        yield "late"


class BrokenRetriever:
    def search(self, query: str, vector):
        raise RuntimeError("unavailable")


class BlankProvider:
    async def embed_query(self, query: str):
        return [1.0]

    async def stream_answer(self, query: str, sources):
        yield ""
        yield "Claim [S1]."


def test_service_timeout_and_cancellation_close_upstream_iterator():
    async def exercise():
        timeout = RagService(FakeRetriever(), SlowProvider(), generation_timeout_seconds=0.0001)
        timeout_events = [event async for event in timeout.stream_query("Arnett", "req")]
        assert timeout_events[-1].data["code"] == "generation_timeout"

        provider = NeverProvider()
        service = RagService(FakeRetriever(), provider)
        stream = service.stream_query("Arnett", "req")
        first = await anext(stream)
        assert first.name == "sources"
        pending = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        pending.cancel()
        try:
            await pending
        except asyncio.CancelledError:
            pass
        assert provider.closed is True

    asyncio.run(exercise())


def test_service_handles_retrieval_failure_blank_deltas_and_total_budget():
    async def exercise():
        failed = RagService(BrokenRetriever(), BlankProvider())
        failed_events = [event async for event in failed.stream_query("Arnett", "req")]
        assert failed_events[-1].name == "complete"

        blank = RagService(FakeRetriever(), BlankProvider())
        blank_events = [event async for event in blank.stream_query("Arnett", "req")]
        assert [event.name for event in blank_events] == ["sources", "token", "complete"]

        over_budget = RagService(FakeRetriever(), BlankProvider(), total_timeout_seconds=-1)
        budget_events = [event async for event in over_budget.stream_query("Arnett", "req")]
        assert budget_events[-1].data["code"] == "generation_timeout"

        during_stream = RagService(
            FakeRetriever(), BlankProvider(), total_timeout_seconds=1,
            clock=iter((0.0, 0.0, 0.0, 2.0)).__next__,
        )
        stream_budget_events = [event async for event in during_stream.stream_query("Arnett", "req")]
        assert stream_budget_events[-1].data["code"] == "generation_timeout"

    asyncio.run(exercise())


def test_service_propagates_embedding_and_retrieval_cancellation_and_closes_optional_iterator():
    class BlockingEmbedding:
        async def embed_query(self, query: str):
            await asyncio.Event().wait()

    class BlockingRetriever:
        def search(self, query: str, vector):
            import time
            time.sleep(0.05)
            return []

    class FallbackBlockingRetriever:
        def search(self, query: str, vector):
            import time
            if vector is not None:
                raise RuntimeError("dense failed")
            time.sleep(0.05)
            return []

    async def exercise():
        embedding_stream = RagService(FakeRetriever(), BlockingEmbedding()).stream_query("Arnett", "req")
        pending_embedding = asyncio.create_task(anext(embedding_stream))
        await asyncio.sleep(0)
        pending_embedding.cancel()
        with __import__("pytest").raises(asyncio.CancelledError):
            await pending_embedding

        retrieval_stream = RagService(BlockingRetriever(), BlankProvider()).stream_query("Arnett", "req")
        pending_retrieval = asyncio.create_task(anext(retrieval_stream))
        await asyncio.sleep(0)
        pending_retrieval.cancel()
        with __import__("pytest").raises(asyncio.CancelledError):
            await pending_retrieval

        fallback_stream = RagService(FallbackBlockingRetriever(), BlankProvider()).stream_query("Arnett", "req")
        pending_fallback = asyncio.create_task(anext(fallback_stream))
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        pending_fallback.cancel()
        with __import__("pytest").raises(asyncio.CancelledError):
            await pending_fallback

        from backend.service import _close
        await _close(None)
        await _close(object())

    asyncio.run(exercise())
