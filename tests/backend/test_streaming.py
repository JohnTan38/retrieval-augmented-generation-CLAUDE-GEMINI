import json


def events(response):
    blocks = [block for block in response.text.split("\n\n") if block]
    return [(next(line[7:] for line in block.splitlines() if line.startswith("event:")), json.loads(next(line[6:] for line in block.splitlines() if line.startswith("data:")))) for block in blocks]


def test_query_streams_sources_before_tokens_and_valid_citations(client):
    response = client.post("/api/query", json={"query": "Explain Arnett"})
    assert response.headers["content-type"].startswith("text/event-stream")
    stream = events(response)
    assert [name for name, _ in stream] == ["sources", "token", "complete"]
    assert stream[0][1]["sources"][0]["source_id"] == "S1"
    assert stream[-1][1]["cited_source_ids"] == ["S1"]
    assert stream[-1][1]["citation_valid"] is True


def test_empty_evidence_refuses_without_generation(app):
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        stream = events(client.post("/api/query", json={"query": "nothing"}))
    assert [name for name, _ in stream] == ["sources", "complete"]
    assert stream[-1][1]["citation_valid"] is True
