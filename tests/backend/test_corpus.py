def test_corpus_exposes_safe_downloads(client):
    response = client.get("/api/corpus")
    assert response.status_code == 200
    document = response.json()["documents"][0]
    assert document["download_url"].startswith("/documents/")
    assert document["sha256"] == "a" * 64
