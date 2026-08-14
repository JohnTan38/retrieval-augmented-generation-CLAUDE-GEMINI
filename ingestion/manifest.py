from __future__ import annotations

import hashlib
import json
from pathlib import Path
import stat

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

    documents_root = _documents_root(documents_dir)

    expected_filenames = {document.filename for document in manifest.documents}
    pdf_entries = sorted(
        (
            entry
            for entry in documents_root.iterdir()
            if entry.suffix.lower() == ".pdf"
        ),
        key=lambda entry: entry.name,
    )
    actual_filenames = {entry.name for entry in pdf_entries}
    if actual_filenames != expected_filenames:
        missing_filenames = sorted(expected_filenames - actual_filenames)
        unexpected_filenames = sorted(actual_filenames - expected_filenames)
        raise ValueError(
            f"missing PDFs: {missing_filenames}; unexpected PDFs: {unexpected_filenames}"
        )

    entries_by_name = {entry.name: entry for entry in pdf_entries}
    for document in manifest.documents:
        pdf_path = entries_by_name[document.filename]
        _validate_pdf_entry(pdf_path, documents_root)
        pdf_snapshot = _read_pdf_snapshot(pdf_path)
        actual_checksum = _sha256(pdf_snapshot)
        if actual_checksum != document.sha256:
            raise ValueError(f"checksum mismatch for {document.filename}")
        try:
            with pymupdf.open(stream=pdf_snapshot, filetype="pdf") as pdf:
                actual_pages = pdf.page_count
        except pymupdf.FileDataError as error:
            raise ValueError(f"{document.filename} cannot be read as a PDF") from error
        if actual_pages != document.pages:
            raise ValueError(
                f"page count mismatch for {document.filename}: "
                f"expected {document.pages}, found {actual_pages}"
            )

    return manifest


def _documents_root(documents_dir: Path) -> Path:
    if not documents_dir.is_dir() or documents_dir.is_symlink() or _is_reparse_point(
        documents_dir
    ):
        raise ValueError("documents directory does not exist")
    return documents_dir.resolve(strict=True)


def _validate_pdf_entry(pdf_path: Path, documents_root: Path) -> None:
    if (
        pdf_path.is_symlink()
        or _is_reparse_point(pdf_path)
        or not stat.S_ISREG(pdf_path.lstat().st_mode)
        or not pdf_path.resolve(strict=True).is_relative_to(documents_root)
    ):
        raise ValueError(f"{pdf_path.name} is not a regular PDF file in documents directory")


def _is_reparse_point(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _read_pdf_snapshot(path: Path) -> bytes:
    return path.read_bytes()


def _sha256(pdf_snapshot: bytes) -> str:
    return hashlib.sha256(pdf_snapshot).hexdigest()
