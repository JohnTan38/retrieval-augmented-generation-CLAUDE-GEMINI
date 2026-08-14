"""Retrieval orchestration and safe, sources-first SSE domain events."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from backend.citation import validate_citations


LOGGER = logging.getLogger(__name__)


class PresentedSource(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_id: StrictStr = Field(pattern=r"^S[1-9][0-9]*$")
    document_id: StrictStr
    filename: StrictStr
    title: StrictStr
    semester: StrictStr
    page: StrictInt = Field(gt=0)
    excerpt: StrictStr = Field(min_length=1, max_length=600)
    score: StrictFloat = Field(gt=0)
    download_url: StrictStr


class ServerSentEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: StrictStr = Field(pattern=r"^(sources|token|complete|error)$")
    data: dict[str, object]


@dataclass
class RagService:
    retriever: object
    gemini: object
    embedding_timeout_seconds: float = 5.0
    generation_timeout_seconds: float = 25.0
    total_timeout_seconds: float = 30.0
    clock: Callable[[], float] = time.monotonic

    async def stream_query(self, query: str, request_id: str) -> AsyncIterator[ServerSentEvent]:
        started = self.clock()
        retrieval_mode = "hybrid"
        vector: list[float] | None = None
        try:
            vector = await asyncio.wait_for(self.gemini.embed_query(query), timeout=self.embedding_timeout_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            retrieval_mode = "lexical_degraded"
        try:
            evidence = await asyncio.wait_for(
                asyncio.to_thread(self.retriever.search, query, vector), timeout=self.embedding_timeout_seconds
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            evidence = []
            retrieval_mode = "lexical_degraded"
        sources = _present(evidence)
        timings = {"retrieval_ms": _milliseconds(started, self.clock())}
        yield ServerSentEvent(name="sources", data={"request_id": request_id, "retrieval_mode": retrieval_mode, "sources": [source.model_dump() for source in sources], "timings": timings})
        if not sources:
            yield ServerSentEvent(name="complete", data={"request_id": request_id, "timings": _timings(started, self.clock()), "cited_source_ids": [], "citation_valid": True})
            return
        answer = ""
        iterator: AsyncIterator[str] | None = None
        try:
            if self.clock() - started > self.total_timeout_seconds:
                raise TimeoutError
            iterator = self.gemini.stream_answer(query, sources)
            async with asyncio.timeout(self.generation_timeout_seconds):
                async for delta in iterator:
                    if self.clock() - started > self.total_timeout_seconds:
                        raise TimeoutError
                    if delta:
                        answer += delta
                        yield ServerSentEvent(name="token", data={"delta": delta})
        except asyncio.CancelledError:
            await _close(iterator)
            raise
        except (TimeoutError, asyncio.TimeoutError):
            LOGGER.info("rag generation timeout request_id=%s sources=%d", request_id, len(sources))
            yield _error("generation_timeout", "Answer generation timed out.", retryable=True)
            return
        except Exception:
            LOGGER.info("rag generation unavailable request_id=%s sources=%d", request_id, len(sources))
            yield _error("generation_unavailable", "Answer generation is temporarily unavailable.", retryable=True)
            return
        citations = validate_citations(answer, {source.source_id for source in sources})
        yield ServerSentEvent(name="complete", data={"request_id": request_id, "timings": _timings(started, self.clock()), "cited_source_ids": citations.cited_source_ids, "citation_valid": citations.valid})


def _present(evidence: Sequence[object]) -> list[PresentedSource]:
    return [PresentedSource(source_id=f"S{position}", document_id=item.document_id, filename=item.filename, title=item.title, semester=item.semester, page=item.page, excerpt=item.excerpt, score=item.score, download_url=item.download_url) for position, item in enumerate(evidence, start=1)]


async def _close(iterator: AsyncIterator[str] | None) -> None:
    if iterator is None:
        return
    closer = getattr(iterator, "aclose", None)
    if closer is not None:
        await closer()


def _milliseconds(started: float, now: float) -> int:
    return max(0, round((now - started) * 1000))


def _timings(started: float, now: float) -> dict[str, int]:
    return {"total_ms": _milliseconds(started, now)}


def _error(code: str, message: str, *, retryable: bool) -> ServerSentEvent:
    return ServerSentEvent(name="error", data={"code": code, "message": message, "retryable": retryable})
