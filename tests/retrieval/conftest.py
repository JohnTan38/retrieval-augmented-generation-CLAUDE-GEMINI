from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

import pytest

from ingestion.indexer import build_index, tokenize


ROOT = Path(__file__).resolve().parents[2]


class HashEmbedder:
    """Deterministic token-hash vectors used only to exercise hybrid retrieval."""

    model = "test-hash-128"
    dimensions = 128

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.vector_for(text) for text in texts]

    @classmethod
    def vector_for(cls, text: str) -> list[float]:
        vector = [0.0] * cls.dimensions
        for token in tokenize(text):
            value = 0
            for character in token.encode("utf-8"):
                value = (value * 131 + character) % 2_147_483_647
            vector[value % cls.dimensions] += 1.0 if value & 1 else -1.0
        length = math.sqrt(sum(value * value for value in vector))
        if length == 0:
            raise ValueError("test text must contain lexical tokens")
        return [value / length for value in vector]


@pytest.fixture
def artifact_path(tmp_path: Path) -> Path:
    output = tmp_path / "swk501-v1.json.gz"
    artifact = build_index(
        ROOT / "data" / "corpus-manifest.json",
        ROOT / "public" / "documents",
        output,
        HashEmbedder(),
    )
    assert len(artifact.documents) == 3
    assert len(artifact.chunks) == 93
    return output


@pytest.fixture
def index_store(artifact_path: Path):
    from backend.index_store import IndexStore

    IndexStore.reset_cache_for_tests()
    store = IndexStore.load(artifact_path)
    yield store
    IndexStore.reset_cache_for_tests()
