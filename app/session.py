"""Server-side conversation session store.

Each chat session tracks a customer's accumulated spec, contact details, and
progression stage. Persisted to SQLite so sessions survive server restarts.

Readiness score: 0-100 based on completeness of spec + contact info.
Routing: sales / survey / installation / customer_care determined from session state.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .db import q
from .store import _connect


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def init_sessions_table() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                data_json TEXT NOT NULL
            )
            """
        )


@dataclass
class ConversationSession:
    session_id: str = field(default_factory=lambda: "S-" + uuid.uuid4().hex[:10].upper())
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    stage: int = 1  # 1=scoping 2=spec 3=contact 4=complete

    # Customer contact
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    postcode: Optional[str] = None

    # Project context
    project_context: Optional[str] = None   # "residential" | "commercial"
    build_type: Optional[str] = None         # "new_build" | "renovation"
    installation_required: Optional[bool] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    timeline_weeks: Optional[int] = None

    # Door spec
    door_set: Optional[str] = None          # "single" | "double"
    door_type: Optional[str] = None         # "internal" | "external" | "fire_rated" | "wine_room"
    mechanism: Optional[str] = None         # "hinged" | "sliding" | "concertina"
    width_mm: Optional[float] = None
    height_mm: Optional[float] = None
    quantity: Optional[int] = None
    glass: Optional[str] = None
    ral_colour: Optional[str] = None
    fire_rating: Optional[str] = None
    side_panels: Optional[int] = None
    threshold: str = "flush"                # "flush" | "weathered" | "step_over"

    # Output
    readiness_score: int = 0
    routing: Optional[str] = None            # "sales" | "survey" | "installation" | "customer_care"
    internal_brief: Optional[str] = None
    brief_email_sent: bool = False           # True after internal brief emailed to sales team
    customer_email_sent: bool = False        # True after quote confirmation email sent to customer
    hubspot_pushed: bool = False             # True after lead successfully pushed to HubSpot (prevents duplicate deals)
    webhook_fired: bool = False              # True after outbound CRM webhook successfully delivered
    quote_reference: Optional[str] = None
    needs: list = field(default_factory=list)  # fields still needed


# ---------------------------------------------------------------------------
# Readiness scoring
# ---------------------------------------------------------------------------

def calculate_readiness(s: ConversationSession) -> int:
    score = 0
    # Spec fields (60 pts total)
    if s.door_set:       score += 10
    if s.door_type:      score += 10
    if s.mechanism:      score += 5
    if s.width_mm and s.height_mm: score += 20
    if s.quantity:       score += 5
    if s.glass:          score += 5
    if s.ral_colour:     score += 3
    if s.fire_rating and s.fire_rating != "none": score += 2
    # Contact fields (35 pts total)
    if s.name:           score += 10
    if s.email:          score += 15
    if s.phone:          score += 5
    if s.postcode:       score += 5
    # Project context (5 pts total)
    if s.project_context: score += 3
    if s.installation_required is not None: score += 2
    return min(score, 100)


def determine_routing(s: ConversationSession) -> str:
    # Supply-only + fully specced → sales closes it (no site survey needed)
    if s.installation_required is False and s.readiness_score >= 60:
        return "sales"
    # Full spec + contact info + installation wanted → book a site survey
    if s.readiness_score >= 70 and s.email and s.installation_required is not False:
        return "survey"
    # Post-quote follow-up → customer care handles amendments/queries
    if s.quote_reference and s.stage >= 4:
        return "customer_care"
    # Commercial project or large quantity order → installation team scoping
    if s.project_context == "commercial" or (s.quantity or 0) >= 5:
        return "installation"
    return "sales"


def build_internal_brief(s: ConversationSession, quote_total: Optional[float] = None) -> str:
    def v(val, default="-"):
        return str(val) if val is not None else default

    spec_line = ""
    if s.width_mm and s.height_mm:
        spec_line = f"{int(s.width_mm)}×{int(s.height_mm)}mm"

    actions = []
    if not s.email:  actions.append("Collect email address")
    if not s.phone:  actions.append("Collect phone number")
    if not s.postcode: actions.append("Collect postcode for survey scheduling")
    if not s.width_mm: actions.append("Confirm opening dimensions")
    if s.installation_required is None: actions.append("Confirm supply only vs supply + install")
    if not s.timeline_weeks: actions.append("Ask about project timeline")
    if not actions:  actions.append("All information gathered — schedule free site survey")

    budget_str = "-"
    if s.budget_min and s.budget_max:
        budget_str = f"£{s.budget_min:,.0f} – £{s.budget_max:,.0f}"
    elif s.budget_min:
        budget_str = f"£{s.budget_min:,.0f}+"

    timeline_str = f"{s.timeline_weeks} weeks" if s.timeline_weeks else "Not specified"

    quote_line = ""
    if quote_total:
        quote_line = f"Estimate: £{quote_total:,.2f} inc. VAT"
    elif s.quote_reference:
        quote_line = f"Quote ref: {s.quote_reference}"

    now_str = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")

    lines = [
        f"╔══ INTERNAL BRIEF ══════════════════════════════════════",
        f"║  Generated: {now_str}",
        f"║  Session:   {s.session_id}",
        f"╟── CUSTOMER ──────────────────────────────────────────",
        f"║  Name:      {v(s.name)}",
        f"║  Email:     {v(s.email)}",
        f"║  Phone:     {v(s.phone)}",
        f"║  Postcode:  {v(s.postcode)}",
        f"╟── PROJECT CONTEXT ───────────────────────────────────",
        f"║  Type:      {v(s.project_context)} {v(s.build_type, '')}".rstrip(),
        f"║  Install:   {'Yes' if s.installation_required else 'Supply only' if s.installation_required is False else 'Not specified'}",
        f"║  Budget:    {budget_str}",
        f"║  Timeline:  {timeline_str}",
        f"╟── DOOR SPECIFICATION ────────────────────────────────",
        f"║  Door:      {v(s.door_set)} leaf, {v(s.door_type)}, {v(s.mechanism)}",
        f"║  Size:      {spec_line if spec_line else '-'}  ×  qty {v(s.quantity, '1')}",
        f"║  Glass:     {v(s.glass)}",
        f"║  Colour:    {v(s.ral_colour, 'Standard')}",
        f"║  Fire:      {v(s.fire_rating, 'none')}",
        f"║  Panels:    {v(s.side_panels, '0')} side panels",
    ]
    if quote_line:
        lines += [
            f"╟── ESTIMATE ──────────────────────────────────────────",
            f"║  {quote_line}",
        ]
    lines += [
        f"╟── READINESS: {s.readiness_score}/100 ── ROUTE TO: {(s.routing or 'sales').upper()} TEAM",
        f"╟── ACTIONS REQUIRED ──────────────────────────────────",
    ]
    for a in actions:
        lines.append(f"║  • {a}")
    lines.append("╚══════════════════════════════════════════════════════")
    return "\n".join(lines)


def build_internal_brief_json(s: ConversationSession, quote_total: Optional[float] = None) -> dict:
    """Machine-readable brief suitable for CRM / HubSpot push."""
    actions = []
    if not s.email:       actions.append("Collect email address")
    if not s.phone:       actions.append("Collect phone number")
    if not s.postcode:    actions.append("Collect postcode for survey scheduling")
    if not s.width_mm:    actions.append("Confirm opening dimensions")
    if s.installation_required is None: actions.append("Confirm supply only vs supply + install")
    if not s.timeline_weeks: actions.append("Ask about project timeline")
    if not actions:       actions.append("All information gathered — schedule free site survey")

    deal_stage_map = {
        "survey": "appointmentscheduled",
        "sales": "qualifiedtobuy",
        "installation": "presentationscheduled",
        "customer_care": "closedwon",
    }
    return {
        "session_id": s.session_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "readiness_score": s.readiness_score,
        "routing": s.routing or "sales",
        "contact": {
            "name": s.name,
            "email": s.email,
            "phone": s.phone,
            "postcode": s.postcode,
        },
        "project": {
            "type": s.project_context,
            "build_type": s.build_type,
            "installation_required": s.installation_required,
            "budget_min": s.budget_min,
            "budget_max": s.budget_max,
            "timeline_weeks": s.timeline_weeks,
        },
        "door_spec": {
            "door_set": s.door_set,
            "door_type": s.door_type,
            "mechanism": s.mechanism,
            "width_mm": s.width_mm,
            "height_mm": s.height_mm,
            "quantity": s.quantity,
            "glass": s.glass,
            "ral_colour": s.ral_colour,
            "fire_rating": s.fire_rating,
            "side_panels": s.side_panels,
            "threshold": s.threshold,
        },
        "estimate": {
            "quote_reference": s.quote_reference,
            "total_inc_vat": quote_total,
        },
        "actions_required": actions,
        "hubspot": {
            "dealname": f"Steel Door — {s.name or 'Unknown'} — {s.quote_reference or 'No Quote'}",
            "deal_stage": deal_stage_map.get(s.routing or "sales", "qualifiedtobuy"),
            "amount": quote_total,
            "pipeline": "default",
        },
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

def load_session(session_id: str) -> Optional[ConversationSession]:
    with _connect() as conn:
        row = conn.execute(
            q("SELECT data_json FROM sessions WHERE session_id = ?"), (session_id,)
        ).fetchone()
    if not row:
        return None
    data = json.loads(row["data_json"])
    s = ConversationSession(**{k: v for k, v in data.items() if k in ConversationSession.__dataclass_fields__})
    return s


def save_session(s: ConversationSession) -> None:
    s.updated_at = datetime.now(timezone.utc).isoformat()
    data_json = json.dumps(asdict(s))
    upsert = q(
        """
        INSERT INTO sessions (session_id, created_at, updated_at, data_json)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            updated_at=excluded.updated_at,
            data_json=excluded.data_json
        """
    )
    params = (s.session_id, s.created_at, s.updated_at, data_json)
    try:
        with _connect() as conn:
            conn.execute(upsert, params)
    except Exception:
        # Table may not exist in test context (no FastAPI startup). Create it and retry once.
        try:
            init_sessions_table()
            with _connect() as conn:
                conn.execute(upsert, params)
        except Exception:
            pass  # never let session persistence break a chat response


def get_recent_sessions(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            q("SELECT session_id, created_at, updated_at, data_json FROM sessions ORDER BY updated_at DESC LIMIT ?"),
            (limit,)
        ).fetchall()
    result = []
    for row in rows:
        d = json.loads(row["data_json"])
        result.append({
            "session_id": row["session_id"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "name": d.get("name"),
            "email": d.get("email"),
            "readiness_score": d.get("readiness_score", 0),
            "routing": d.get("routing"),
            "quote_reference": d.get("quote_reference"),
            "door_type": d.get("door_type"),
            "stage": d.get("stage", 1),
        })
    return result
