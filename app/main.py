"""FastAPI application: API routes + static web chat UI."""
import os
import secrets
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address
    _limiter = Limiter(key_func=get_remote_address)
    _rate_limit_available = True
except ImportError:
    _limiter = None
    _rate_limit_available = False

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
from .session import build_internal_brief, build_internal_brief_json, get_recent_sessions, load_session
from .store import get_all_quotes, get_dashboard_stats, get_quote, init_db, save_enquiry, save_quote

# ---------------------------------------------------------------------------
# Dashboard auth
# ---------------------------------------------------------------------------

_basic = HTTPBasic()


def _require_dashboard(credentials: HTTPBasicCredentials = Depends(_basic)) -> str:
    expected_user = os.environ.get("DASHBOARD_USER", "admin").encode()
    expected_pass = os.environ.get("DASHBOARD_PASS", "steeldoor").encode()
    ok = (
        secrets.compare_digest(credentials.username.encode(), expected_user)
        and secrets.compare_digest(credentials.password.encode(), expected_pass)
    )
    if not ok:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    from .seed import seed_demo_data
    seed_demo_data()
    yield


app = FastAPI(title="Steel Door Company — Quote Assistant", version="0.4.0", lifespan=lifespan)

# CORS — allow the live Vercel URL + localhost by default; override via ALLOWED_ORIGINS
_allowed_origins = [
    o.strip()
    for o in os.environ.get(
        "ALLOWED_ORIGINS",
        "https://steel-door-chat-bot.vercel.app,http://localhost:8000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Rate limiting
if _rate_limit_available:
    app.state.limiter = _limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

STATIC_DIR = Path(__file__).parent / "static"
(STATIC_DIR / "images").mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": app.version}


@app.get("/api/catalogue")
def api_catalogue() -> dict:
    return CATALOGUE


@app.post("/api/quote", response_model=QuoteResponse)
@(_limiter.limit("30/minute") if _rate_limit_available else lambda f: f)
def api_quote(request: Request, req: QuoteRequest) -> QuoteResponse:
    try:
        quote = calculate_quote(req)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Unsupported option: {exc}") from exc
    save_quote(quote)
    return quote


@app.get("/api/quote/{reference}")
def api_get_quote(reference: str) -> dict:
    q = get_quote(reference)
    if not q:
        raise HTTPException(status_code=404, detail="Quote not found")
    return q


@app.get("/api/quote/{reference}/pdf")
def api_quote_pdf(reference: str) -> Response:
    row = get_quote(reference)
    if not row:
        raise HTTPException(status_code=404, detail="Quote not found")
    try:
        import json
        from .models import QuoteResponse
        from .pdf import build_quote_pdf
        quote = QuoteResponse.model_validate(json.loads(row["payload_json"]))
        pdf_bytes = build_quote_pdf(quote)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {exc}") from exc
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="quote-{reference}.pdf"'},
    )


@app.post("/api/chat", response_model=ChatResponse)
@(_limiter.limit("20/minute") if _rate_limit_available else lambda f: f)
def api_chat(request: Request, req: ChatRequest) -> ChatResponse:
    response = handle_chat(req)
    if response.quote:
        save_quote(response.quote)
    return response


@app.post("/api/enquiry", response_model=EnquiryResponse)
def api_enquiry(req: EnquiryRequest) -> EnquiryResponse:
    reference = "ENQ-" + uuid.uuid4().hex[:8].upper()
    enquiry_id = save_enquiry(req, reference)
    from .email_sender import send_enquiry_email
    send_enquiry_email(enquiry=req, reference=reference)
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
def api_get_brief(session_id: str, format: str = "text") -> dict:
    s = load_session(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    if format == "json":
        return build_internal_brief_json(s)
    brief = s.internal_brief or build_internal_brief(s)
    return {"session_id": session_id, "brief": brief, "readiness_score": s.readiness_score}


@app.get("/api/dashboard/stats")
def api_dashboard_stats(_: str = Depends(_require_dashboard)) -> dict:
    return get_dashboard_stats()


@app.get("/api/dashboard/sessions")
def api_dashboard_sessions(_: str = Depends(_require_dashboard)) -> list:
    return get_recent_sessions(50)


@app.get("/api/dashboard/sessions.csv")
def api_sessions_csv(_: str = Depends(_require_dashboard)) -> Response:
    import csv
    import io
    sessions = get_recent_sessions(5000)
    buf = io.StringIO()
    fields = ["session_id", "created_at", "updated_at", "name", "email",
              "readiness_score", "routing", "quote_reference", "door_type", "stage"]
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(sessions)
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=sessions.csv"},
    )


@app.get("/api/dashboard/quotes.csv")
def api_quotes_csv(_: str = Depends(_require_dashboard)) -> Response:
    import csv
    import io
    quotes = get_all_quotes()
    if not quotes:
        return Response(content="reference,created_at,product_name,total,subtotal,vat,sale_discount,quantity,lead_time\n",
                        media_type="text/csv")
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(quotes[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(quotes)
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=quotes.csv"},
    )


@app.post("/api/webhooks/test")
def api_webhook_test(payload: dict, _: str = Depends(_require_dashboard)) -> dict:
    """Manually fire the configured CRM webhook with a test payload."""
    from .webhook import fire_webhook
    test_payload = {"event": "test", "source": "steeldoorai", **payload}
    sent = fire_webhook(test_payload)
    return {"sent": sent, "webhook_configured": bool(__import__("os").environ.get("WEBHOOK_URL"))}


@app.get("/dashboard")
def dashboard(_: str = Depends(_require_dashboard)) -> FileResponse:
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
