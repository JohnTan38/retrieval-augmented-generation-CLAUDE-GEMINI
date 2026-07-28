"""Vercel Python Function entrypoint.

Vercel detects the `app` symbol (ASGI/WSGI) and serves it via Fluid Compute.
All /api/* routes are rewritten to this single function (see vercel.json).
"""
import os
import sys

# Make backend/ importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from main import app  # noqa: E402,F401
