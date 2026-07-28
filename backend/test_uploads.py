import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(__file__))

import main  # noqa: E402
from main import app  # noqa: E402


client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_api_key_env(monkeypatch):
    real_exists = os.path.exists
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.setattr(
        main.os.path,
        "exists",
        lambda path: False if path.endswith(".env.local") else real_exists(path),
    )


def upload_aap(session_id="test-session-aap"):
    pdf_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "public", "assets", "aap.pdf")
    )
    with open(pdf_path, "rb") as pdf:
        return client.post(
            "/api/upload-pdfs",
            data={"session_id": session_id},
            files={"files": ("aap.pdf", pdf, "application/pdf")},
        )


def test_upload_rejects_non_pdf_file():
    response = client.post(
        "/api/upload-pdfs",
        data={"session_id": "test-session-invalid"},
        files={"files": ("notes.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 400
    assert "PDF" in response.json()["detail"]


def test_upload_indexes_pdf_and_status_includes_session_file():
    response = upload_aap()

    assert response.status_code == 200
    payload = response.json()
    assert payload["indexed"] is True
    assert payload["uploaded_files"][0]["name"] == "aap.pdf"

    status = client.get("/api/index-status", params={"session_id": "test-session-aap"})
    assert status.status_code == 200
    file_names = [file["name"] for file in status.json()["files"]]
    assert "aap.pdf" in file_names


def test_query_with_session_id_retrieves_uploaded_pdf_context_without_api_key():
    upload_aap("test-session-query")

    response = client.post(
        "/api/query",
        json={
            "session_id": "test-session-query",
            "query": "AAP",
            "top_k": 3,
            "use_filter": False,
            "use_expansion": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["api_key_required"] is True
    assert any(context["source"] == "aap.pdf" for context in payload["context"])


def test_sample_questions_include_uploaded_pdf_names_for_session():
    upload_aap("test-session-samples")

    response = client.get("/api/sample-questions", params={"session_id": "test-session-samples"})

    assert response.status_code == 200
    questions = response.json()
    assert any("aap.pdf" in item["question"] for item in questions)
