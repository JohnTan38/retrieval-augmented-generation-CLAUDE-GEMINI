"""Build the TF-IDF index from PDFs and serialize it to backend/index.json.

Run locally before deploy:  python scripts/build_index.py
The resulting backend/index.json should be committed so the Vercel function
can hydrate the index on cold start without re-parsing PDFs at runtime.
"""
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from rag_engine import RAGEngine

PDF_DIR = os.path.join(ROOT, "public", "assets")
OUT_PATH = os.path.join(ROOT, "backend", "index.json")

def main():
    print(f"PDFs: {PDF_DIR}")
    rag = RAGEngine(PDF_DIR)
    rag.extract_and_index()
    rag.save_index(OUT_PATH)
    print(f"Wrote {OUT_PATH} ({os.path.getsize(OUT_PATH)/1024:.1f} KB)")
    print(f"Pages indexed: {len(rag.retriever.documents)}")

if __name__ == "__main__":
    main()
