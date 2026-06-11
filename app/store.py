"""SQLite store for customer enquiries (leads) and persisted quotes."""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import EnquiryRequest, QuoteResponse

DB_PATH = Path(os.environ.get("ENQUIRY_DB", "enquiries.db"))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS enquiries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference TEXT NOT NULL,
                created_at TEXT NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT,
                postcode TEXT,
                message TEXT,
                quote_reference TEXT,
                quote_total REAL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quotes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reference TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                product_name TEXT NOT NULL,
                total REAL NOT NULL,
                subtotal REAL NOT NULL,
                vat REAL NOT NULL,
                sale_discount REAL NOT NULL,
                quantity INTEGER NOT NULL,
                lead_time TEXT,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pricing_settings (
                key TEXT PRIMARY KEY,
                value REAL NOT NULL,
                description TEXT,
                updated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pricing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT NOT NULL,
                old_value REAL,
                new_value REAL NOT NULL,
                changed_at TEXT DEFAULT (datetime('now'))
            )
            """
        )


def save_enquiry(enquiry: EnquiryRequest, reference: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO enquiries
                (reference, created_at, name, email, phone, postcode, message,
                 quote_reference, quote_total)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reference,
                datetime.now(timezone.utc).isoformat(),
                enquiry.name,
                enquiry.email,
                enquiry.phone,
                enquiry.postcode,
                enquiry.message,
                enquiry.quote_reference,
                enquiry.quote_total,
            ),
        )
        return int(cur.lastrowid)


def save_quote(quote: QuoteResponse) -> None:
    """Persist a quote for audit / follow-up. Silently skips duplicates."""
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO quotes
                    (reference, created_at, product_name, total, subtotal, vat,
                     sale_discount, quantity, lead_time, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    quote.reference,
                    datetime.now(timezone.utc).isoformat(),
                    quote.product_name,
                    quote.total,
                    quote.subtotal,
                    quote.vat,
                    quote.sale_discount,
                    quote.quantity,
                    quote.lead_time,
                    quote.model_dump_json(),
                ),
            )
    except Exception:
        pass  # never let persistence errors break the quote flow


def count_enquiries() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM enquiries").fetchone()
        return int(row["n"]) if row else 0


def count_quotes() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM quotes").fetchone()
        return int(row["n"]) if row else 0


def get_enquiry(enquiry_id: int) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM enquiries WHERE id = ?", (enquiry_id,)
        ).fetchone()
        return dict(row) if row else None


def get_dashboard_stats() -> dict:
    with _connect() as conn:
        n_enquiries = conn.execute("SELECT COUNT(*) AS n FROM enquiries").fetchone()["n"]
        n_quotes = conn.execute("SELECT COUNT(*) AS n FROM quotes").fetchone()["n"]
        n_sessions = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
        avg_total = conn.execute("SELECT AVG(total) AS v FROM quotes").fetchone()["v"]
        top_products = conn.execute(
            "SELECT product_name, COUNT(*) AS n FROM quotes GROUP BY product_name ORDER BY n DESC LIMIT 5"
        ).fetchall()
        recent_quotes = conn.execute(
            "SELECT reference, created_at, product_name, total, quantity FROM quotes ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        # Use json_extract for reliable email detection (replaces fragile LIKE match)
        sessions_with_email = conn.execute(
            "SELECT COUNT(*) AS n FROM sessions "
            "WHERE json_extract(data_json, '$.email') IS NOT NULL "
            "AND json_extract(data_json, '$.email') != ''"
        ).fetchone()["n"]
        # Pipeline value by routing team
        pipeline_by_routing = conn.execute(
            "SELECT json_extract(data_json, '$.routing') AS routing, COUNT(*) AS n "
            "FROM sessions "
            "WHERE json_extract(data_json, '$.routing') IS NOT NULL "
            "GROUP BY routing"
        ).fetchall()
        # Daily quote revenue — last 14 days
        daily_revenue = conn.execute(
            "SELECT date(created_at) AS day, SUM(total) AS revenue, COUNT(*) AS n "
            "FROM quotes WHERE date(created_at) >= date('now', '-13 days') "
            "GROUP BY date(created_at) ORDER BY day"
        ).fetchall()
    return {
        "enquiries": n_enquiries,
        "quotes": n_quotes,
        "sessions": n_sessions,
        "sessions_with_contact": sessions_with_email,
        "avg_quote_value": round(avg_total, 2) if avg_total else 0.0,
        "conversion_rate": round(sessions_with_email / n_sessions * 100, 1) if n_sessions else 0.0,
        "top_products": [{"name": r["product_name"], "count": r["n"]} for r in top_products],
        "recent_quotes": [dict(r) for r in recent_quotes],
        "pipeline_by_routing": [{"routing": r["routing"], "count": r["n"]} for r in pipeline_by_routing],
        "daily_revenue": [{"day": r["day"], "revenue": round(r["revenue"], 2), "count": r["n"]} for r in daily_revenue],
    }


def get_all_quotes(limit: int = 5000) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT reference, created_at, product_name, total, subtotal, vat, "
            "sale_discount, quantity, lead_time FROM quotes ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_quote(reference: str) -> Optional[dict]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM quotes WHERE reference = ?", (reference,)
        ).fetchone()
        return dict(row) if row else None


# ---------------------------------------------------------------------------
# Pricing CRUD
# ---------------------------------------------------------------------------

def get_pricing_overrides() -> dict[str, float]:
    """Return all rows from pricing_settings as {key: value}. Empty dict if none set."""
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM pricing_settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def set_pricing_field(key: str, value: float, description: str = "") -> None:
    """Upsert a single pricing key, recording history."""
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT value FROM pricing_settings WHERE key = ?", (key,)
        ).fetchone()
        old_value = existing["value"] if existing else None
        conn.execute(
            """
            INSERT INTO pricing_settings (key, value, description, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                description=excluded.description, updated_at=excluded.updated_at
            """,
            (key, value, description, now),
        )
        conn.execute(
            "INSERT INTO pricing_history (key, old_value, new_value, changed_at) VALUES (?, ?, ?, ?)",
            (key, old_value, value, now),
        )


def get_pricing_history(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT key, old_value, new_value, changed_at FROM pricing_history "
            "ORDER BY changed_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
