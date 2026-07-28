"""session_store.py -- durable storage for per-session uploaded-PDF indexes.

Problem it solves
-----------------
On Vercel serverless, a module-level ``uploaded_sessions`` dict is NOT shared
across function instances. A user can upload a PDF (indexed on instance A),
then have their next /query land on a cold instance B whose dict is empty, so
the upload appears to "vanish". This module persists each session's serialized
TF-IDF index to a Redis-compatible KV store (Vercel KV / Upstash Redis) over
the REST API, keyed by session_id, with a TTL.

Graceful degradation
--------------------
If no KV credentials are configured (local dev, or KV not yet provisioned on
Vercel), it transparently falls back to a process-local in-memory dict --
i.e. exactly the previous behavior -- so the app never breaks pre-provisioning.
Flip on durability later by adding the env vars; no code change required.

Dependencies: only ``requests`` (already in requirements.txt).
"""

import json
import os
import time

import requests

# How long an uploaded-session index lives. Uploads are ephemeral working data.
SESSION_TTL_SECONDS = int(os.environ.get("RAG_SESSION_TTL", "86400"))  # 24h
KEY_PREFIX = "rag:session:"

# Per-instance fallback cache: {session_id: {"payload": dict, "expires": float}}
_local_cache: dict[str, dict] = {}


def _kv_config():
    """Return (base_url, token) from Vercel KV or native Upstash env vars, else (None, None)."""
    url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
    token = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if url and token:
        return url.rstrip("/"), token
    return None, None


def is_durable() -> bool:
    """True if a KV backend is configured (uploads survive across instances)."""
    base_url, _ = _kv_config()
    return base_url is not None


def _kv_command(command: list, timeout: float = 5.0):
    """Run one Redis command via the Upstash REST API.

    Uses the JSON-array command form (POST to the base URL) so large index
    payloads travel in the request body, avoiding URL-length limits that the
    path-style ``/set/<key>/<value>`` endpoint would hit.

    Returns (result, ok). ok=False means "KV unavailable/failed" -> caller
    should fall back to the in-memory cache.
    """
    base_url, token = _kv_config()
    if not base_url:
        return None, False
    try:
        resp = requests.post(
            base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=command,
            timeout=timeout,
        )
        if resp.status_code == 200:
            return resp.json().get("result"), True
        print(f"[session_store] KV command {command[0]} failed {resp.status_code}: {resp.text[:200]}")
        return None, False
    except Exception as e:  # network error, timeout, bad JSON
        print(f"[session_store] KV request error: {e}")
        return None, False


def save_session(session_id: str, payload: dict) -> None:
    """Persist a session's serialized index. Durable if KV configured, else in-memory."""
    if not session_id:
        return
    key = KEY_PREFIX + session_id
    value = json.dumps(payload)
    _, ok = _kv_command(["SETEX", key, SESSION_TTL_SECONDS, value])
    if not ok:
        _local_cache[session_id] = {
            "payload": payload,
            "expires": time.time() + SESSION_TTL_SECONDS,
        }


def load_session(session_id: str):
    """Load a session's serialized index, or None if absent/expired."""
    if not session_id:
        return None
    key = KEY_PREFIX + session_id
    result, ok = _kv_command(["GET", key])
    if ok:
        if result is None:
            return None
        try:
            return json.loads(result)
        except (TypeError, ValueError):
            return None
    # KV not configured or transiently failed -> in-memory fallback
    entry = _local_cache.get(session_id)
    if not entry:
        return None
    if entry["expires"] < time.time():
        _local_cache.pop(session_id, None)
        return None
    return entry["payload"]
