"""Minimal async Google GenAI adapter with no public provider controls."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass

from google.genai import types

from backend.prompts import SYSTEM_INSTRUCTION, build_prompt
from ingestion.embeddings import EMBEDDING_DIMENSIONS


@dataclass(frozen=True)
class GenerationDelta:
    """One provider stream update with an optional terminal finish reason."""

    text: str = ""
    finish_reason: str | None = None


class GeminiClient:
    def __init__(self, api_key: str, embedding_model: str, generation_model: str, *, client: object | None = None) -> None:
        if not api_key or not api_key.strip() or not embedding_model or not embedding_model.strip() or not generation_model or not generation_model.strip():
            raise ValueError("Gemini configuration is unavailable")
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client
        self._embedding_model = embedding_model
        self._generation_model = generation_model

    async def embed_query(self, query: str) -> list[float]:
        response = await self._client.aio.models.embed_content(
            model=self._embedding_model,
            contents=[query],
            config={"task_type": "RETRIEVAL_QUERY", "output_dimensionality": EMBEDDING_DIMENSIONS},
        )
        embeddings = getattr(response, "embeddings", None)
        if not isinstance(embeddings, list) or len(embeddings) != 1:
            raise ValueError("embedding response is unavailable")
        values = getattr(embeddings[0], "values", None)
        if not isinstance(values, list):
            raise ValueError("embedding response is unavailable")
        return values

    async def stream_answer(self, query: str, sources: Sequence[object]) -> AsyncIterator[GenerationDelta]:
        stream = await self._client.aio.models.generate_content_stream(
            model=self._generation_model,
            contents=build_prompt(query, sources),
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                max_output_tokens=2048,
                thinking_config=types.ThinkingConfig(thinking_level="LOW"),
            ),
        )
        async for chunk in stream:
            text = getattr(chunk, "text", None)
            finish_reason = _finish_reason(chunk)
            if (isinstance(text, str) and text) or finish_reason is not None:
                yield GenerationDelta(text=text if isinstance(text, str) else "", finish_reason=finish_reason)


def _finish_reason(chunk: object) -> str | None:
    candidates = getattr(chunk, "candidates", None)
    if not isinstance(candidates, list):
        return None
    for candidate in candidates:
        value = getattr(candidate, "finish_reason", None)
        if value is None:
            continue
        raw = getattr(value, "value", value)
        if isinstance(raw, str) and raw:
            return raw
    return None
