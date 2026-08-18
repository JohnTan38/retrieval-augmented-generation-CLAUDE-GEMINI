"""Minimal async Google GenAI adapter with no public provider controls."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

from backend.prompts import SYSTEM_INSTRUCTION, build_prompt


GENERATION_MODEL = "gemini-3.6-flash"


class GeminiClient:
    def __init__(self, api_key: str, embedding_model: str, *, client: object | None = None) -> None:
        if not api_key or not api_key.strip() or not embedding_model or not embedding_model.strip():
            raise ValueError("Gemini configuration is unavailable")
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client
        self._embedding_model = embedding_model

    async def embed_query(self, query: str) -> list[float]:
        response = await self._client.aio.models.embed_content(
            model=self._embedding_model,
            contents=[query],
            config={"task_type": "RETRIEVAL_QUERY"},
        )
        embeddings = getattr(response, "embeddings", None)
        if not isinstance(embeddings, list) or len(embeddings) != 1:
            raise ValueError("embedding response is unavailable")
        values = getattr(embeddings[0], "values", None)
        if not isinstance(values, list):
            raise ValueError("embedding response is unavailable")
        return values

    async def stream_answer(self, query: str, sources: Sequence[object]) -> AsyncIterator[str]:
        stream = await self._client.aio.models.generate_content_stream(
            model=GENERATION_MODEL,
            contents=build_prompt(query, sources),
            config={"system_instruction": SYSTEM_INSTRUCTION, "max_output_tokens": 1024},
        )
        async for chunk in stream:
            text = getattr(chunk, "text", None)
            if isinstance(text, str) and text:
                yield text
