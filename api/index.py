"""Vercel serverless entry point.

Vercel's Python runtime serves the ASGI `app` exported here. All /api/* routes
are rewritten to this function (see vercel.json); FastAPI handles the routing.
"""
from app.main import app  # noqa: F401
