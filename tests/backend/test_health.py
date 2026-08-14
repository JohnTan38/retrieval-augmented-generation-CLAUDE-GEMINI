def test_health_reports_injected_index(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"ready": True, "schema_version": 1, "corpus_version": "swk501-2026-01-v1", "documents": 1, "pages": 27, "status": "ready"}


def test_default_app_is_safe_without_artifact(monkeypatch):
    monkeypatch.setenv("RAG_INDEX_PATH", "missing.json.gz")
    from backend.app import create_app
    from fastapi.testclient import TestClient

    with TestClient(create_app()) as client:
        assert client.get("/api/health").json()["ready"] is False
        assert client.get("/api/corpus").status_code == 503
        assert client.post("/api/query", json={"query": "Arnett"}).status_code == 503


def test_factory_handles_missing_key_and_invalid_artifact(monkeypatch):
    from backend import app as app_module
    from backend.app import _safe_error, create_app
    from tests.backend.conftest import FakeStore

    monkeypatch.setattr(app_module.IndexStore, "load", lambda path: (_ for _ in ()).throw(ValueError("bad")))
    assert create_app().state.store is None
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert create_app(store=FakeStore()).state.gateway is None
    assert "request_id" not in _safe_error(400, "invalid_request", "safe").body.decode()
