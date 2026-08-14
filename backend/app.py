"""Same-origin FastAPI gateway for the immutable SWK501 corpus."""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from backend.config import ConfigurationUnavailable, get_settings, require_api_key
from backend.gemini_client import GeminiClient
from backend.index_store import IndexStore
from backend.retrieval import HybridRetriever
from backend.service import RagService, ServerSentEvent


LOGGER = logging.getLogger(__name__)
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
MAX_QUERY_LENGTH = 2_000
MAX_REQUEST_BYTES = 8_192
_CSP = "default-src 'self'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'; img-src 'self' data: blob:; font-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'"


class RequestBodyTooLarge(ValueError):
    pass


class QueryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    query: StrictStr = Field(min_length=1, max_length=MAX_QUERY_LENGTH)

    @field_validator("query")
    @classmethod
    def safe_query(cls, value: str) -> str:
        if not value.strip() or _CONTROL.search(value):
            raise ValueError("query contains invalid characters")
        return value.strip()


def create_app(*, store: object | None = None, retriever: object | None = None, gemini: object | None = None) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = _CSP
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), browsing-topics=()"
        if os.environ.get("VERCEL_ENV") == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        return response
    settings = get_settings()
    if store is None:
        try:
            store = IndexStore.load(settings.artifact_path)
        except ValueError:
            store = None
    if retriever is None and store is not None:
        retriever = HybridRetriever(store)
    if gemini is None and store is not None:
        try:
            gemini = GeminiClient(require_api_key(settings), store.artifact.embedding_model)
        except (ConfigurationUnavailable, ValueError):
            gemini = None
    app.state.gateway = RagService(retriever, gemini, settings.embedding_timeout_seconds, settings.generation_timeout_seconds, settings.total_timeout_seconds, store.embedding_dimensions) if retriever is not None and gemini is not None else None
    app.state.store = store

    @app.get("/api/health")
    async def health() -> JSONResponse:
        active = app.state.store
        if active is None:
            return JSONResponse({"ready": False, "status": "index_unavailable"})
        documents = active.artifact.documents
        return JSONResponse({"ready": True, "schema_version": active.artifact.schema_version, "corpus_version": active.artifact.corpus_version, "documents": len(documents), "pages": sum(document.pages for document in documents), "status": "ready"})

    @app.get("/api/corpus")
    async def corpus() -> JSONResponse:
        active = app.state.store
        if active is None:
            return _safe_error(503, "index_unavailable", "The study corpus is not ready.")
        return JSONResponse({"documents": [document.model_dump() if hasattr(document, "model_dump") else {name: getattr(document, name) for name in ("document_id", "filename", "title", "semester", "pages", "topics", "sha256", "download_url")} for document in active.artifact.documents]})

    @app.post("/api/query", response_model=None)
    async def query(request: Request):
        request_id = uuid.uuid4().hex
        content_type = request.headers.get("content-type", "")
        if content_type.split(";", 1)[0].strip().lower() != "application/json":
            return _safe_error(415, "invalid_request", "Content type must be application/json.", request_id)
        try:
            body = json.loads((await _read_limited_body(request)).decode("utf-8"))
        except RequestBodyTooLarge:
            return _safe_error(413, "invalid_request", "Request body is too large.", request_id)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return _safe_error(400, "invalid_request", "Request JSON is malformed.", request_id)
        try:
            payload = QueryRequest.model_validate(body)
        except Exception:
            return _safe_error(422, "invalid_request", "Query must be a single safe text field.", request_id)
        gateway = app.state.gateway
        if gateway is None:
            return _safe_error(503, "index_unavailable", "The study service is temporarily unavailable.", request_id)
        return StreamingResponse(_encode_events(gateway.stream_query(payload.query, request_id)), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Request-ID": request_id})

    return app


async def _encode_events(events: AsyncIterator[ServerSentEvent]) -> AsyncIterator[bytes]:
    async for event in events:
        yield f"event: {event.name}\ndata: {json.dumps(event.data, ensure_ascii=False, separators=(',', ':'))}\n\n".encode("utf-8")


def _safe_error(status: int, code: str, message: str, request_id: str | None = None) -> JSONResponse:
    payload: dict[str, object] = {"code": code, "message": message}
    if request_id:
        payload["request_id"] = request_id
    return JSONResponse(payload, status_code=status)


async def _read_limited_body(request: Request) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdecimal() and (len(declared) > len(str(MAX_REQUEST_BYTES)) or int(declared) > MAX_REQUEST_BYTES):
        raise RequestBodyTooLarge
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_REQUEST_BYTES:
            raise RequestBodyTooLarge
        chunks.append(chunk)
    return b"".join(chunks)


app = create_app()
