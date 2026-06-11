"""Demo-data seeder for Vercel cold-start dashboard.

Only runs when SEED_DEMO=1 AND the sessions table is empty (idempotent).
Never seeds when real customer data exists.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import QuoteRequest
from .quoting import calculate_quote
from .session import (
    ConversationSession,
    calculate_readiness,
    determine_routing,
    save_session,
)
from .store import _connect, init_db, save_quote

_DEMO_PROFILES: list[dict[str, Any]] = [
    dict(
        name="Emma Wilson", email="emma@example.com", phone="07700900001",
        postcode="B1 1AA", door_set="single", door_type="external",
        mechanism="hinged", width_mm=900, height_mm=2100,
        project_context="residential", installation_required=True,
        glass="clear", quantity=1, stage=4,
    ),
    dict(
        name="James Carter", email="james.carter@acmeltd.co.uk", phone="07700900002",
        postcode="M1 1AB", door_set="double", door_type="internal",
        mechanism="sliding", width_mm=1800, height_mm=2400,
        project_context="commercial", installation_required=True,
        glass="reeded", quantity=3, stage=3,
    ),
    dict(
        name="Sophie Turner", email="sophie@example.com",
        door_set="single", door_type="fire_rated",
        mechanism="hinged", width_mm=900, height_mm=2100,
        project_context="residential", installation_required=True,
        fire_rating="FD30", quantity=2, stage=4,
    ),
    dict(
        name="Liam O'Brien", email="liam@obrien.ie",
        door_set="double", door_type="external",
        mechanism="concertina", width_mm=3600, height_mm=2200,
        project_context="residential", installation_required=True,
        glass="frosted", ral_colour="RAL 9005", quantity=1, stage=4,
    ),
    dict(
        name=None, email=None,
        door_set="single", door_type="internal",
        mechanism="hinged", width_mm=800, height_mm=2000,
        quantity=1, stage=2,
    ),
    dict(
        name="Priya Sharma", email="priya@designco.com",
        postcode="EC1A 1BB", door_set="double", door_type="wine_room",
        mechanism="hinged", width_mm=1200, height_mm=2100,
        project_context="commercial", installation_required=False,
        glass="bespoke", ral_colour="RAL 7016", quantity=1, stage=4,
    ),
]


def seed_demo_data() -> int:
    """Insert demo sessions + quotes when SEED_DEMO=1 and DB is empty.

    Returns the number of sessions inserted (0 if skipped).
    """
    if os.environ.get("SEED_DEMO", "0") != "1":
        return 0

    init_db()

    with _connect() as conn:
        n = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
    if n > 0:
        return 0  # real data or already seeded — never overwrite

    inserted = 0
    total = len(_DEMO_PROFILES)
    for i, profile in enumerate(_DEMO_PROFILES):
        s = ConversationSession()
        # Spread created_at across the last 7 days for a realistic dashboard view
        days_ago = total - i
        fake_ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
        s.created_at = fake_ts

        for k, v in profile.items():
            if hasattr(s, k) and v is not None:
                setattr(s, k, v)

        s.readiness_score = calculate_readiness(s)

        # Generate quote when the spec is complete enough to price
        if s.door_set and s.door_type and s.mechanism and s.width_mm and s.height_mm:
            req = QuoteRequest(
                door_set=s.door_set,
                door_type=s.door_type,
                mechanism=s.mechanism,
                width_mm=s.width_mm,
                height_mm=s.height_mm,
                glass=s.glass or "clear",
                ral_colour=s.ral_colour,
                fire_rating=s.fire_rating or "none",
                side_panels=s.side_panels or 0,
                quantity=s.quantity or 1,
            )
            quote = calculate_quote(req)
            s.quote_reference = quote.reference
            save_quote(quote)

        s.routing = determine_routing(s)
        save_session(s)
        inserted += 1

    return inserted
