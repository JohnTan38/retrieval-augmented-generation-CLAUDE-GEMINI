"""build_index.py -- prebuild backend/index.json from the public/assets PDFs.

Run this locally (or in CI) BEFORE deploying, then commit the generated
backend/index.json. On Vercel the function hydrates this file at cold start
instead of running pdfplumber over the corpus at request time (which is slow
and would depend on the PDFs being bundled into the function).

Usage:
    cd backend
    python build_index.py
"""

import os

from rag_engine import RAGEngine

HERE = os.path.dirname(os.path.abspath(__file__))
PDF_DIR = os.path.abspath(os.path.join(HERE, "..", "public", "assets"))
INDEX_PATH = os.environ.get("RAG_INDEX_PATH", os.path.join(HERE, "index.json"))


def main():
    print(f"PDF source dir : {PDF_DIR}")
    print(f"Index output   : {INDEX_PATH}")
    if not os.path.isdir(PDF_DIR):
        raise SystemExit(f"ERROR: PDF directory not found: {PDF_DIR}")

    rag = RAGEngine(PDF_DIR)
    if not rag.extract_and_index():
        raise SystemExit("ERROR: indexing produced no documents (no extractable PDF text).")

    rag.save_index(INDEX_PATH)
    print(
        f"OK -- wrote {INDEX_PATH}: "
        f"{len(rag.retriever.documents)} pages across {len(rag.metadata)} file(s)."
    )
    for fname, meta in rag.metadata.items():
        print(f"   - {fname}: {meta['pages']} pages, {meta['size'] / 1024:.1f} KB")


if __name__ == "__main__":
    main()
