"""FastAPI application: API routes + static web chat UI."""
from __future__ import annotations

import uuid
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .catalogue import CATALOGUE
from .chat import handle_chat
from .models import (
    ChatRequest,
    ChatResponse,
    EnquiryRequest,
    EnquiryResponse,
    QuoteRequest,
    QuoteResponse,
)
from .quoting import calculate_quote
from .session import build_internal_brief, get_recent_sessions, load_session
from .store import get_dashboard_stats, init_db, save_enquiry, save_quote

app = FastAPI(title="Steel Door Company — Quote Assistant", version="0.4.0")

STATIC_DIR = Path(__file__).parent / "static"
(STATIC_DIR / "images").mkdir(parents=True, exist_ok=True)


@app.on_event("startup")
def _startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.get("/api/catalogue")
def api_catalogue() -> dict:
    return CATALOGUE


@app.post("/api/quote", response_model=QuoteResponse)
def api_quote(req: QuoteRequest) -> QuoteResponse:
    try:
        quote = calculate_quote(req)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Unsupported option: {exc}") from exc
    save_quote(quote)
    return quote


@app.post("/api/chat", response_model=ChatResponse)
def api_chat(req: ChatRequest) -> ChatResponse:
    response = handle_chat(req)
    if response.quote:
        save_quote(response.quote)
    return response


@app.post("/api/enquiry", response_model=EnquiryResponse)
def api_enquiry(req: EnquiryRequest) -> EnquiryResponse:
    reference = "ENQ-" + uuid.uuid4().hex[:8].upper()
    enquiry_id = save_enquiry(req, reference)
    return EnquiryResponse(
        id=enquiry_id,
        reference=reference,
        message=(
            "Thanks — your enquiry has been received. A member of the Steel Door Company "
            "team will be in touch shortly. For anything urgent call 01785 526016."
        ),
    )


@app.get("/api/session/{session_id}")
def api_get_session(session_id: str) -> dict:
    s = load_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    from dataclasses import asdict
    return asdict(s)


@app.get("/api/session/{session_id}/brief")
def api_get_brief(session_id: str) -> dict:
    s = load_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    brief = s.internal_brief or build_internal_brief(s)
    return {"session_id": session_id, "brief": brief, "readiness_score": s.readiness_score}


@app.get("/api/dashboard/stats")
def api_dashboard_stats() -> dict:
    return get_dashboard_stats()


@app.get("/api/dashboard/sessions")
def api_dashboard_sessions() -> list:
    return get_recent_sessions(50)


@app.get("/dashboard")
def dashboard() -> FileResponse:
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
