from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ingestion.manifest import load_manifest
from ingestion.models import CorpusDocument


ROOT = Path(__file__).resolve().parents[2]


def test_manifest_contains_the_exact_approved_corpus():
    manifest = load_manifest(
        ROOT / "data" / "corpus-manifest.json",
        ROOT / "public" / "documents",
    )

    assert [document.document_id for document in manifest.documents] == [
        "jan-2025",
        "jul-2025",
        "jan-2026",
    ]
    assert [document.pages for document in manifest.documents] == [26, 36, 27]
    assert [document.filename for document in manifest.documents] == [
        "swk501-Jan2025-evidence-based-model-answers.pdf",
        "swk501-July2025-deep-research-model-answers.pdf",
        "swk501-Jan2026-deep-research-model-answers.pdf",
    ]
    assert [document.sha256 for document in manifest.documents] == [
        "ce5e335a78d2c2398452643b65eae5aa85e290b37a32dcc28710ae77cc5783b9",
        "57d8a0be84911246c36dafb484534a0b1d9311088969d8afcf1af32aae4babed",
        "109601093872bd96a0333386b2e474bd67f3c91331fb873218b560ecdc93e1a7",
    ]
    assert sum(document.pages for document in manifest.documents) == 89
    assert {document.download_url for document in manifest.documents} == {
        "/documents/swk501-Jan2025-evidence-based-model-answers.pdf",
        "/documents/swk501-July2025-deep-research-model-answers.pdf",
        "/documents/swk501-Jan2026-deep-research-model-answers.pdf",
    }


def test_manifest_rejects_a_checksum_mismatch(tmp_path: Path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        '{"schema_version":1,"corpus_version":"test","documents":['
        '{"document_id":"bad","filename":"bad.pdf","title":"Bad",'
        '"semester":"Test","pages":1,"sha256":"' + "0" * 64 + '",'
        '"download_url":"/documents/bad.pdf","topics":["test"]}]}',
        encoding="utf-8",
    )
    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "bad.pdf").write_bytes(b"%PDF-not-the-expected-file")

    with pytest.raises(ValueError, match="checksum"):
        load_manifest(manifest_path, documents)


def test_manifest_rejects_duplicate_document_ids(write_manifest, write_pdf):
    first = _document("first.pdf", "same")
    second = _document("second.pdf", "same")
    manifest_path, documents_dir = write_manifest([first, second])
    first["sha256"] = write_pdf(documents_dir / "first.pdf")
    second["sha256"] = write_pdf(documents_dir / "second.pdf")
    _rewrite_manifest(manifest_path, [first, second])

    with pytest.raises(ValueError, match="duplicate document IDs"):
        load_manifest(manifest_path, documents_dir)


def test_manifest_rejects_duplicate_filenames(write_manifest, write_pdf):
    first = _document("same.pdf", "one")
    second = _document("same.pdf", "two")
    manifest_path, documents_dir = write_manifest([first, second])
    checksum = write_pdf(documents_dir / "same.pdf")
    first["sha256"] = checksum
    second["sha256"] = checksum
    _rewrite_manifest(manifest_path, [first, second])

    with pytest.raises(ValueError, match="duplicate filenames"):
        load_manifest(manifest_path, documents_dir)


def test_manifest_rejects_missing_or_extra_pdfs(write_manifest, write_pdf):
    document = _document("expected.pdf", "expected")
    manifest_path, documents_dir = write_manifest([document])
    document["sha256"] = hashlib.sha256(b"not-present").hexdigest()
    _rewrite_manifest(manifest_path, [document])

    with pytest.raises(ValueError, match="missing PDFs"):
        load_manifest(manifest_path, documents_dir)

    document["sha256"] = write_pdf(documents_dir / "expected.pdf")
    write_pdf(documents_dir / "unexpected.pdf")
    _rewrite_manifest(manifest_path, [document])

    with pytest.raises(ValueError, match="unexpected PDFs"):
        load_manifest(manifest_path, documents_dir)


def test_manifest_rejects_a_missing_documents_directory(write_manifest):
    document = _document("expected.pdf", "expected")
    manifest_path, documents_dir = write_manifest([document])
    documents_dir.rmdir()

    with pytest.raises(ValueError, match="documents directory"):
        load_manifest(manifest_path, documents_dir)


def test_manifest_rejects_a_page_count_mismatch(write_manifest, write_pdf):
    document = _document("pages.pdf", "pages", pages=2)
    manifest_path, documents_dir = write_manifest([document])
    document["sha256"] = write_pdf(documents_dir / "pages.pdf", pages=1)
    _rewrite_manifest(manifest_path, [document])

    with pytest.raises(ValueError, match="page count"):
        load_manifest(manifest_path, documents_dir)


def test_manifest_rejects_invalid_json(write_manifest):
    manifest_path, documents_dir = write_manifest([])
    manifest_path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="valid JSON"):
        load_manifest(manifest_path, documents_dir)


def test_manifest_rejects_a_non_pdf_after_checksum_validation(write_manifest):
    document = _document("broken.pdf", "broken")
    manifest_path, documents_dir = write_manifest([document])
    contents = b"not a PDF"
    (documents_dir / "broken.pdf").write_bytes(contents)
    document["sha256"] = hashlib.sha256(contents).hexdigest()
    _rewrite_manifest(manifest_path, [document])

    with pytest.raises(ValueError, match="cannot be read as a PDF"):
        load_manifest(manifest_path, documents_dir)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("filename", "../escape.pdf", "filename"),
        ("filename", "not-a-pdf.txt", "filename"),
        ("download_url", "https://example.test/file.pdf", "download URL"),
        ("download_url", "/documents/other.pdf", "download URL"),
        ("topics", [], "topics"),
        ("topics", ["   "], "topics"),
        ("sha256", "abc", "SHA-256"),
    ],
)
def test_document_model_rejects_unsafe_metadata(field: str, value: object, message: str):
    payload = _document("safe.pdf", "safe")
    payload[field] = value

    with pytest.raises(ValidationError, match=message):
        CorpusDocument.model_validate(payload)


def _document(filename: str, document_id: str, pages: int = 1) -> dict[str, object]:
    return {
        "document_id": document_id,
        "filename": filename,
        "title": "Test document",
        "semester": "Test semester",
        "pages": pages,
        "sha256": "0" * 64,
        "download_url": f"/documents/{filename}",
        "topics": ["testing"],
    }


def _rewrite_manifest(manifest_path: Path, documents: list[dict[str, object]]) -> None:
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "corpus_version": "test-corpus",
                "documents": documents,
            }
        ),
        encoding="utf-8",
    )
