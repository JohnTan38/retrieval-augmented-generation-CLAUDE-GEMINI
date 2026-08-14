def test_gateway_has_no_legacy_or_cors_routes(client):
    assert client.options("/api/query", headers={"origin": "https://attacker.example"}).headers.get("access-control-allow-origin") is None
    assert client.post("/api/save-key", json={"api_key": "leak"}).status_code == 404
    assert client.post("/api/upload-pdfs").status_code == 404


def test_provider_details_are_not_logged(app, caplog):
    from fastapi.testclient import TestClient
    from test_failures import GenerationFails

    app.state.gateway.gemini = GenerationFails()
    with TestClient(app) as client:
        response = client.post("/api/query", json={"query": "Arnett"})
    assert "secret provider payload" not in response.text
    assert "secret provider payload" not in caplog.text
