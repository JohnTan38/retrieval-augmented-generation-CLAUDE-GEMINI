from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf
from pydantic import ValidationError

from ingestion.models import CorpusManifest


def load_manifest(path: Path, documents_dir: Path) -> CorpusManifest:
    """Load a manifest only when every declared PDF exactly matches on disk."""
    try:
        manifest_data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("manifest must be valid JSON") from error

    try:
        manifest = CorpusManifest.model_validate(manifest_data)
    except ValidationError as error:
        raise ValueError(f"invalid corpus manifest: {error}") from error

    if not documents_dir.is_dir():
        raise ValueError("documents directory does not exist")

    expected_filenames = {document.filename for document in manifest.documents}
    actual_filenames = {
        document_path.name
        for document_path in documents_dir.iterdir()
        if document_path.is_file() and document_path.suffix.lower() == ".pdf"
    }
    if actual_filenames != expected_filenames:
        missing_filenames = sorted(expected_filenames - actual_filenames)
        unexpected_filenames = sorted(actual_filenames - expected_filenames)
        raise ValueError(
            f"missing PDFs: {missing_filenames}; unexpected PDFs: {unexpected_filenames}"
        )

    for document in manifest.documents:
        pdf_path = documents_dir / document.filename
        actual_checksum = _sha256(pdf_path)
        if actual_checksum != document.sha256:
            raise ValueError(f"checksum mismatch for {document.filename}")
        try:
            with pymupdf.open(pdf_path) as pdf:
                actual_pages = pdf.page_count
        except pymupdf.FileDataError as error:
            raise ValueError(f"{document.filename} cannot be read as a PDF") from error
        if actual_pages != document.pages:
            raise ValueError(
                f"page count mismatch for {document.filename}: "
                f"expected {document.pages}, found {actual_pages}"
            )

    return manifest


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        while chunk := file_handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
