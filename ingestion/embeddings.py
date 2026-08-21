"""Safe, deterministic batching for build-time document embeddings."""

from __future__ import annotations

from collections.abc import Callable, Sequence
import math
import time
from typing import Protocol


DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSIONS = 768
MAX_BATCH_SIZE = 100
MAX_TEXT_LENGTH = 20_000
_TRANSIENT_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class Embedder(Protocol):
    """Minimal build-time embedding interface, deliberately independent of the SDK."""

    model: str

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...


def normalize_embeddings(vectors: Sequence[Sequence[float]]) -> list[list[float]]:
    """Validate and L2-normalize vectors, rejecting non-finite and zero inputs."""
    if not isinstance(vectors, Sequence) or isinstance(vectors, (str, bytes)):
        raise ValueError("embeddings must be a sequence of vectors")
    normalized: list[list[float]] = []
    dimension: int | None = None
    for vector in vectors:
        if not isinstance(vector, Sequence) or isinstance(vector, (str, bytes)) or not vector:
            raise ValueError("embedding vectors must be non-empty sequences")
        values: list[float] = []
        for value in vector:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError("embedding values must be numeric")
            number = float(value)
            if not math.isfinite(number):
                raise ValueError("embedding values must be finite")
            values.append(number)
        if dimension is None:
            dimension = len(values)
        elif len(values) != dimension:
            raise ValueError("embedding dimensions must be consistent")
        length = math.sqrt(sum(value * value for value in values))
        if length == 0:
            raise ValueError("embedding vectors must not be zero")
        normalized.append([value / length for value in values])
    return normalized


class GoogleEmbedder:
    """Official Google GenAI document embedder with bounded, injectable retries."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_EMBEDDING_MODEL,
        client: object | None = None,
        batch_size: int = 32,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("GEMINI_API_KEY must be non-empty")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("embedding model must be non-empty")
        if not isinstance(batch_size, int) or isinstance(batch_size, bool) or not 1 <= batch_size <= MAX_BATCH_SIZE:
            raise ValueError(f"batch size must be between 1 and {MAX_BATCH_SIZE}")
        if not isinstance(max_retries, int) or isinstance(max_retries, bool) or not 0 <= max_retries <= 5:
            raise ValueError("max retries must be between 0 and 5")
        self.model = model
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._sleep = sleep
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        text_list = _validate_texts(texts)
        vectors: list[list[float]] = []
        for start in range(0, len(text_list), self._batch_size):
            batch = text_list[start : start + self._batch_size]
            vectors.extend(self._embed_batch(batch))
        normalize_embeddings(vectors)
        return vectors

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        attempt = 0
        while True:
            try:
                response = self._client.models.embed_content(
                    model=self.model,
                    contents=texts,
                    config={"task_type": "RETRIEVAL_DOCUMENT", "output_dimensionality": EMBEDDING_DIMENSIONS},
                )
                embeddings = getattr(response, "embeddings", None)
                if not isinstance(embeddings, list) or len(embeddings) != len(texts):
                    raise ValueError("embedding response count does not match request")
                values: list[list[float]] = []
                for embedding in embeddings:
                    vector = getattr(embedding, "values", None)
                    if not isinstance(vector, list):
                        raise ValueError("embedding response contains no values")
                    values.append(vector)
                normalize_embeddings(values)
                return values
            except Exception as error:
                if attempt >= self._max_retries or not _is_transient(error):
                    raise
                self._sleep(_backoff_seconds(attempt))
                attempt += 1


def _validate_texts(texts: Sequence[str]) -> list[str]:
    if not isinstance(texts, Sequence) or isinstance(texts, (str, bytes)):
        raise ValueError("texts must be a sequence")
    validated = list(texts)
    for text in validated:
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT_LENGTH:
            raise ValueError("texts must be nonblank and within the maximum length")
    return validated


def _is_transient(error: Exception) -> bool:
    return getattr(error, "code", None) in _TRANSIENT_STATUS_CODES


def _backoff_seconds(attempt: int) -> float:
    return min(0.25 * (2**attempt), 1.0)
