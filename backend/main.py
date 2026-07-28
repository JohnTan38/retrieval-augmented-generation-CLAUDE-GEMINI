import os
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import session_store
from rag_engine import RAGEngine

load_dotenv()

app = FastAPI(title="Singapore Social Services Document RAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PDF_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "public", "assets"))
# Env-overridable so the committed prebuilt index is found regardless of layout.
INDEX_PATH = os.environ.get(
    "RAG_INDEX_PATH", os.path.join(os.path.dirname(__file__), "index.json")
)
MAX_UPLOAD_FILES = 5
MAX_UPLOAD_BYTES = 10 * 1024 * 1024

rag = RAGEngine(PDF_DIR)
# Per-instance cache of hydrated upload sessions; durability comes from session_store.
uploaded_sessions: dict[str, RAGEngine] = {}


def _corpus_pdfs_available() -> bool:
    """True only when the base-corpus PDFs are actually on disk (local/dev).

    On Vercel the PDFs are excluded from the function bundle, so this is False
    and we rely solely on the committed index.json -- never live extraction.
    """
    return os.path.isdir(PDF_DIR)


def _ensure_base_index() -> bool:
    """Make sure the base corpus is indexed, WITHOUT ever running heavy
    extraction at request time in production. Returns rag.indexed."""
    if rag.indexed:
        return True
    if _corpus_pdfs_available():
        try:
            rag.extract_and_index()
        except Exception as e:
            print(f"Base indexing failed: {e}")
    return rag.indexed


# ---- Startup: prefer the committed prebuilt index; only extract if PDFs present ----
try:
    if os.path.exists(INDEX_PATH):
        rag.load_index(INDEX_PATH)
        print(f"Loaded prebuilt index: {len(rag.retriever.documents)} pages")
    elif _corpus_pdfs_available():
        rag.extract_and_index()
        print(f"Built index from PDFs: {len(rag.retriever.documents)} pages")
    else:
        print(
            "WARNING: no index.json found and no PDFs bundled. "
            "Run backend/build_index.py and commit backend/index.json before deploy."
        )
except Exception as e:
    print(f"Startup indexing failed: {e}")


class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    model: Optional[str] = "gemini-2.5-flash"
    mode: Optional[str] = "classic"
    top_k: Optional[int] = 5
    use_filter: Optional[bool] = True
    use_expansion: Optional[bool] = True
    api_key: Optional[str] = None


class SaveKeyRequest(BaseModel):
    api_key: str


def _format_file_meta(filename, meta, uploaded=False):
    payload = {
        "name": filename,
        "pages": meta["pages"],
        "size": f"{meta['size'] / 1024:.1f} KB",
    }
    if uploaded:
        payload["uploaded"] = True
    return payload


def _hydrate_engine_from_payload(payload):
    engine = RAGEngine(PDF_DIR)
    engine.hydrate(payload)
    return engine


def _session_engine(session_id: Optional[str]):
    """Return the RAGEngine for a session, loading it from the durable store
    on a local cache miss (this is the fix for uploads vanishing across
    serverless instances)."""
    if not session_id:
        return None
    engine = uploaded_sessions.get(session_id)
    if engine:
        return engine
    payload = session_store.load_session(session_id)
    if payload:
        engine = _hydrate_engine_from_payload(payload)
        uploaded_sessions[session_id] = engine
        return engine
    return None


def _session_retrievers(session_id: Optional[str]):
    engine = _session_engine(session_id)
    if engine and engine.indexed:
        return [engine.retriever]
    return []


def _base_sample_questions():
    return [
        {
            "id": "q1",
            "question": "What are the eligibility criteria for Befriending and Buddying services?",
            "category": "Client Management",
            "description": "Checks age, status (PR/Citizen), boundary rules and risk factors.",
        },
        {
            "id": "q2",
            "question": "How often does an AAC need to conduct Communal Dining, and what is the recommended group size?",
            "category": "Active Ageing Programmes",
            "description": "Reviews the mandatory frequency, size, and location rules for dining events.",
        },
        {
            "id": "q3",
            "question": "Under the CASHEW model, what are the six Active Ageing Program Pillars and their monthly frequency targets?",
            "category": "Operations Standard",
            "description": "Lists the six pillars (Connected, Active, Sharp, Happy, Enriched, Well) and their monthly counts.",
        },
    ]


def _uploaded_sample_questions(session_id: Optional[str]):
    session = _session_engine(session_id)
    if not session:
        return []

    questions = []
    for idx, filename in enumerate(session.metadata.keys(), start=1):
        questions.extend(
            [
                {
                    "id": f"upload-{idx}-summary",
                    "question": f"Summarize the main points in {filename}.",
                    "category": "Uploaded PDF",
                    "description": "Creates a concise overview from the newly indexed document.",
                },
                {
                    "id": f"upload-{idx}-requirements",
                    "question": f"What key requirements, obligations, or action items are stated in {filename}?",
                    "category": "Uploaded PDF",
                    "description": "Finds operational requirements and follow-up actions in the upload.",
                },
                {
                    "id": f"upload-{idx}-figures",
                    "question": f"What dates, figures, deadlines, or named entities appear in {filename}?",
                    "category": "Uploaded PDF",
                    "description": "Extracts concrete facts for quick inspection.",
                },
            ]
        )
    return questions


def _validate_upload(file: UploadFile):
    filename = os.path.basename(file.filename or "")
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files can be uploaded.")
    if file.content_type not in {"application/pdf", "application/octet-stream", ""}:
        raise HTTPException(status_code=400, detail="Only PDF files can be uploaded.")

    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size == 0:
        raise HTTPException(status_code=400, detail=f"{filename} is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail=f"{filename} exceeds the 10 MB upload limit.")
    return filename


@app.get("/api/index-status")
def get_index_status(session_id: Optional[str] = Query(default=None)):
    if not _ensure_base_index():
        # No live extraction possible (prod without index.json) -> honest error.
        return {
            "indexed": False,
            "error": "Base index unavailable. Deploy a prebuilt backend/index.json.",
            "files": [],
        }

    files_list = [_format_file_meta(filename, meta) for filename, meta in rag.metadata.items()]

    session = _session_engine(session_id)
    if session:
        files_list.extend(
            _format_file_meta(filename, meta, uploaded=True)
            for filename, meta in session.metadata.items()
        )

    return {
        "indexed": rag.indexed or bool(session and session.indexed),
        "total_chunks": len(rag.retriever.documents)
        + (len(session.retriever.documents) if session else 0),
        "files": files_list,
    }


@app.post("/api/upload-pdfs")
def upload_pdfs(session_id: str = Form(...), files: list[UploadFile] = File(...)):
    if not session_id.strip():
        raise HTTPException(status_code=400, detail="session_id is required.")
    if not files:
        raise HTTPException(status_code=400, detail="Select at least one PDF file to upload.")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=400, detail=f"Upload up to {MAX_UPLOAD_FILES} PDF files at a time.")

    # Start from any already-persisted session so repeated uploads accumulate.
    session = _session_engine(session_id) or uploaded_sessions.setdefault(session_id, RAGEngine(PDF_DIR))
    uploaded_sessions[session_id] = session
    uploaded_files = []

    for file in files:
        filename = _validate_upload(file)
        try:
            meta = session.index_pdf_stream(filename, file.file)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not index {filename}: {exc}") from exc
        uploaded_files.append(_format_file_meta(filename, meta, uploaded=True))

    # Durably persist the session index so a later /query on a cold instance
    # can rehydrate it (KV if configured, else in-memory fallback).
    try:
        session_store.save_session(session_id, session.serialize())
    except Exception as e:
        print(f"Session persist failed (continuing with in-memory): {e}")

    return {
        "indexed": session.indexed,
        "uploaded_files": uploaded_files,
        "total_uploaded_chunks": len(session.retriever.documents),
    }


@app.post("/api/query")
def run_query(request: QueryRequest):
    # Model B: the user's key arrives per-request. Env var is an optional
    # fallback for a single-tenant/self-hosted deployment. No disk reads.
    api_key = request.api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")

    if not _ensure_base_index():
        raise HTTPException(
            status_code=503,
            detail="Base index unavailable. Deploy a prebuilt backend/index.json.",
        )

    try:
        return rag.query(
            user_query=request.query,
            api_key=api_key,
            model=request.model,
            mode=request.mode,
            top_k=request.top_k,
            use_filter=request.use_filter,
            use_expansion=request.use_expansion,
            extra_retrievers=_session_retrievers(request.session_id),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/save-key")
def save_key(request: SaveKeyRequest):
    # Stateless on serverless: the deployment filesystem is read-only, and a
    # shared process env var would leak one user's key to another on a multi-
    # tenant instance. The key is held client-side and passed as `api_key` on
    # each /api/query. We only validate shape here so the UI's save flow works.
    key = (request.api_key or "").strip()
    if not key:
        raise HTTPException(status_code=400, detail="API key cannot be empty.")
    return {
        "status": "success",
        "message": "API key accepted. It is used per request and not stored on the server.",
    }


@app.get("/api/sample-questions")
def get_sample_questions(session_id: Optional[str] = Query(default=None)):
    return _uploaded_sample_questions(session_id) + _base_sample_questions()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=5000)
