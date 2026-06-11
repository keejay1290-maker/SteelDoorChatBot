"""Vercel serverless entrypoint — wraps the FastAPI app.

SQLite uses /tmp which persists within a warm lambda but resets on cold start.
This is acceptable for a demo — the chat still works end-to-end within a session.
"""
import os
import sys

# Ensure the project root is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Vercel sets ENQUIRY_DB=/tmp/enquiries.db via vercel.json env
from app.main import app  # noqa: F401  — Vercel imports `app` from this module
