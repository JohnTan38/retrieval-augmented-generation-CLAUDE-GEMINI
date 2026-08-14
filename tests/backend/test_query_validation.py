import pytest


@pytest.mark.parametrize("payload", [
    {"query": "Arnett", "model": "attacker-choice"}, {"query": "   "},
    {"query": "x" * 2001}, {"query": "bad\x00query"},
])
def test_query_rejects_unsafe_schema(client, payload):
    response = client.post("/api/query", json=payload)
    assert response.status_code == 422
    assert "attacker-choice" not in response.text


def test_query_requires_json_and_safe_malformed_json(client):
    assert client.post("/api/query", content="{}", headers={"content-type": "text/plain"}).status_code == 415
    response = client.post("/api/query", content="{", headers={"content-type": "application/json"})
    assert response.status_code == 400
    assert "{" not in response.json()["message"]
