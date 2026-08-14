from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pymupdf
import pytest


@pytest.fixture
def write_manifest(tmp_path: Path):
    def write(
        documents: list[dict[str, object]], *, schema_version: int = 1
    ) -> tuple[Path, Path]:
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": schema_version,
                    "corpus_version": "test-corpus",
                    "documents": documents,
                }
            ),
            encoding="utf-8",
        )
        documents_dir = tmp_path / "documents"
        documents_dir.mkdir()
        return manifest_path, documents_dir

    return write


@pytest.fixture
def write_pdf():
    def write(path: Path, pages: int = 1) -> str:
        document = pymupdf.open()
        for _ in range(pages):
            document.new_page()
        document.save(path)
        document.close()
        return hashlib.sha256(path.read_bytes()).hexdigest()

    return write
