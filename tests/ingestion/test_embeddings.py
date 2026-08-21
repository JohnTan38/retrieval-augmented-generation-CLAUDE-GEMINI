from __future__ import annotations

import math
import sys
import types

import pytest

from ingestion.embeddings import GoogleEmbedder, normalize_embeddings


def test_normalize_embeddings_returns_unit_vectors() -> None:
    assert normalize_embeddings([[3.0, 4.0]]) == [[0.6, 0.8]]


@pytest.mark.parametrize("vectors", [[[1.0, 0.0], [1.0]], [[0.0, 0.0]], [[math.inf, 1.0]]])
def test_normalize_embeddings_rejects_invalid_vectors(vectors: list[list[float]]) -> None:
    with pytest.raises(ValueError):
        normalize_embeddings(vectors)


def test_google_embedder_batches_documents_and_uses_retrieval_document_contract() -> None:
    calls: list[dict[str, object]] = []

    class Models:
        def embed_content(self, **kwargs: object):
            calls.append(kwargs)
            return type(
                "Response",
                (),
                {"embeddings": [type("Embedding", (), {"values": [1.0, 0.0]})() for _ in kwargs["contents"]]},
            )()

    client = type("Client", (), {"models": Models()})()
    result = GoogleEmbedder("key", client=client, batch_size=2, sleep=lambda _: None).embed_documents(
        ["one", "two", "three"]
    )

    assert result == [[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]]
    assert [call["contents"] for call in calls] == [["one", "two"], ["three"]]
    assert all(call["config"] == {"task_type": "RETRIEVAL_DOCUMENT", "output_dimensionality": 768} for call in calls)


def test_google_embedder_retries_only_transient_server_failures() -> None:
    attempts = 0
    pauses: list[float] = []

    class ServerFailure(Exception):
        code = 503

    class Models:
        def embed_content(self, **_: object):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise ServerFailure()
            return type("Response", (), {"embeddings": [type("Embedding", (), {"values": [1.0]})()]})()

    client = type("Client", (), {"models": Models()})()
    assert GoogleEmbedder("key", client=client, sleep=pauses.append).embed_documents(["one"]) == [[1.0]]
    assert attempts == 2
    assert pauses == [0.25]


@pytest.mark.parametrize("api_key,batch_size,max_retries", [("", 32, 2), ("key", 0, 2), ("key", 101, 2), ("key", 32, -1)])
def test_google_embedder_rejects_invalid_configuration(api_key: str, batch_size: int, max_retries: int) -> None:
    with pytest.raises(ValueError):
        GoogleEmbedder(api_key, batch_size=batch_size, max_retries=max_retries)


def test_google_embedder_rejects_bad_input_or_provider_response() -> None:
    class Models:
        def embed_content(self, **_: object):
            return type("Response", (), {"embeddings": []})()

    embedder = GoogleEmbedder("key", client=type("Client", (), {"models": Models()})())
    assert embedder.embed_documents([]) == []
    with pytest.raises(ValueError, match="texts"):
        embedder.embed_documents([""])
    with pytest.raises(ValueError, match="response count"):
        embedder.embed_documents(["one"])


def test_google_embedder_does_not_retry_non_transient_failures() -> None:
    calls = 0

    class ClientFailure(Exception):
        code = 400

    class Models:
        def embed_content(self, **_: object):
            nonlocal calls
            calls += 1
            raise ClientFailure()

    with pytest.raises(ClientFailure):
        GoogleEmbedder("key", client=type("Client", (), {"models": Models()})(), sleep=lambda _: None).embed_documents(["one"])
    assert calls == 1


def test_google_embedder_validates_dimensions_across_batches() -> None:
    class Models:
        calls = 0
        def embed_content(self, **_: object):
            self.calls += 1
            values = [1.0, 0.0] if self.calls == 1 else [1.0]
            return type("Response", (), {"embeddings": [type("Embedding", (), {"values": values})()]})()
    with pytest.raises(ValueError, match="dimensions"):
        GoogleEmbedder("key", client=type("Client", (), {"models": Models()})(), batch_size=1).embed_documents(["one", "two"])


@pytest.mark.parametrize("vectors", ["bad", [[True]], [["bad"]]])
def test_normalize_embeddings_rejects_all_invalid_value_shapes(vectors) -> None:
    with pytest.raises(ValueError):
        normalize_embeddings(vectors)


def test_google_embedder_constructs_official_client_without_network(monkeypatch) -> None:
    captured = {}
    class Client:
        def __init__(self, **kwargs): captured.update(kwargs)
    monkeypatch.setitem(sys.modules, "google", types.SimpleNamespace(genai=types.SimpleNamespace(Client=Client)))
    GoogleEmbedder("key")
    assert captured == {"api_key": "key"}


def test_google_embedder_rejects_missing_values_and_long_text() -> None:
    class Models:
        def embed_content(self, **_): return type("Response", (), {"embeddings": [object()]})()
    embedder = GoogleEmbedder("key", client=type("Client", (), {"models": Models()})())
    with pytest.raises(ValueError, match="no values"):
        embedder.embed_documents(["one"])
    with pytest.raises(ValueError, match="maximum"):
        embedder.embed_documents(["x" * 20_001])
    with pytest.raises(ValueError, match="texts"):
        embedder.embed_documents("one")
    with pytest.raises(ValueError, match="model"):
        GoogleEmbedder("key", model=" ")
    with pytest.raises(ValueError, match="vectors"):
        normalize_embeddings([[]])
