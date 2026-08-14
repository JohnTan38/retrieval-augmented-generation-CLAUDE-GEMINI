"""CLI for building the immutable corpus index; it never prints credentials or text."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from ingestion.embeddings import GoogleEmbedder
from ingestion.indexer import build_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the SWK501 hybrid index artifact")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--documents", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    api_key = os.environ.get("GEMINI_API_KEY")
    try:
        artifact = build_index(arguments.manifest, arguments.documents, arguments.output, GoogleEmbedder(api_key or ""))
    finally:
        os.environ.pop("GEMINI_API_KEY", None)
    print(f"corpus_version={artifact.corpus_version} model={artifact.embedding_model} dimensions={artifact.embedding_dimensions} documents={len(artifact.documents)} pages={sum(document.pages for document in artifact.documents)} chunks={len(artifact.chunks)}")


if __name__ == "__main__":  # pragma: no cover - exercised by the production CLI
    main()
