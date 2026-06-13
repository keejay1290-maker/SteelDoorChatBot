"""SQLite/Postgres store for customer enquiries (leads) and persisted quotes.

Backend is chosen by ``app.db`` — SQLite locally + in tests, Supabase Postgres
in production (when ``DATABASE_URL`` is set). All SQL here is written once with
``?`` placeholders and dialect-specific fragments from ``app.db``.
"""
from __future__ import annotations

from datetime import UTC, datetime

from . import db
from .db import AUTOINC_PK, NOW_DEFAULT, as_date, date_days_ago, json_field, q
from .models import EnquiryRequest, QuoteResponse

# Backwards-compatible alias: callers (incl. session.py) import _connect from here.
DB_PATH = db.DB_PATH


def _connect():
    return db.connect()


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
            f"""
            CREATE TABLE IF NOT EXISTS sai_enquiries (
                id {AUTOINC_PK},
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
            f"""
            CREATE TABLE IF NOT EXISTS sai_quotes (
                id {AUTOINC_PK},
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
            f"""
            CREATE TABLE IF NOT EXISTS pricing_settings (
                key TEXT PRIMARY KEY,
                value REAL NOT NULL,
                description TEXT,
                updated_at TEXT DEFAULT {NOW_DEFAULT}
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS pricing_history (
                id {AUTOINC_PK},
                key TEXT NOT NULL,
                old_value REAL,
                new_value REAL NOT NULL,
                changed_at TEXT DEFAULT {NOW_DEFAULT}
            )
            """
        )
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS llm_metrics (
                id {AUTOINC_PK},
                session_id TEXT,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                latency_ms INTEGER NOT NULL,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                total_tokens INTEGER,
                success INTEGER NOT NULL DEFAULT 1,
                created_at TEXT DEFAULT {NOW_DEFAULT}
            )
            """
        )


def save_enquiry(enquiry: EnquiryRequest, reference: str) -> int:
    params = (
        reference,
        datetime.now(UTC).isoformat(),
        enquiry.name,
        enquiry.email,
        enquiry.phone,
        enquiry.postcode,
        enquiry.message,
        enquiry.quote_reference,
        enquiry.quote_total,
    )
    cols = ("INSERT INTO sai_enquiries "
            "(reference, created_at, name, email, phone, postcode, message, "
            "quote_reference, quote_total) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
    with _connect() as conn:
        if db.IS_POSTGRES:
            row = conn.execute(q(cols + " RETURNING id"), params).fetchone()
            return int(row["id"])
        cur = conn.execute(cols, params)
        return int(cur.lastrowid)


def save_quote(quote: QuoteResponse) -> None:
    """Persist a quote for audit / follow-up. Silently skips duplicate references."""
    cols = ("sai_quotes (reference, created_at, product_name, total, subtotal, vat, "
            "sale_discount, quantity, lead_time, payload_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)")
    if db.IS_POSTGRES:
        sql = f"INSERT INTO {cols} ON CONFLICT (reference) DO NOTHING"
    else:
        sql = f"INSERT OR IGNORE INTO {cols}"
    params = (
        quote.reference,
        datetime.now(UTC).isoformat(),
        quote.product_name,
        quote.total,
        quote.subtotal,
        quote.vat,
        quote.sale_discount,
        quote.quantity,
        quote.lead_time,
        quote.model_dump_json(),
    )
    try:
        with _connect() as conn:
            conn.execute(q(sql), params)
    except Exception:
        pass  # never let persistence errors break the quote flow


def count_enquiries() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM sai_enquiries").fetchone()
        return int(row["n"]) if row else 0


def count_quotes() -> int:
    with _connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM sai_quotes").fetchone()
        return int(row["n"]) if row else 0


def get_enquiry(enquiry_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            q("SELECT * FROM sai_enquiries WHERE id = ?"), (enquiry_id,)
        ).fetchone()
        return dict(row) if row else None


def get_dashboard_stats() -> dict:
    with _connect() as conn:
        n_enquiries = conn.execute("SELECT COUNT(*) AS n FROM sai_enquiries").fetchone()["n"]
        n_quotes = conn.execute("SELECT COUNT(*) AS n FROM sai_quotes").fetchone()["n"]
        n_sessions = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]
        avg_total = conn.execute("SELECT AVG(total) AS v FROM sai_quotes").fetchone()["v"]
        top_products = conn.execute(
            "SELECT product_name, COUNT(*) AS n FROM sai_quotes GROUP BY product_name ORDER BY n DESC LIMIT 5"
        ).fetchall()
        recent_quotes = conn.execute(
            "SELECT reference, created_at, product_name, total, quantity FROM sai_quotes ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        email_expr = json_field("data_json", "email")
        sessions_with_email = conn.execute(
            f"SELECT COUNT(*) AS n FROM sessions "
            f"WHERE {email_expr} IS NOT NULL AND {email_expr} != ''"
        ).fetchone()["n"]
        routing_expr = json_field("data_json", "routing")
        pipeline_by_routing = conn.execute(
            f"SELECT {routing_expr} AS routing, COUNT(*) AS n "
            f"FROM sessions WHERE {routing_expr} IS NOT NULL GROUP BY {routing_expr}"
        ).fetchall()
        daily_revenue = conn.execute(
            f"SELECT {as_date('created_at')} AS day, SUM(total) AS revenue, COUNT(*) AS n "
            f"FROM sai_quotes WHERE {as_date('created_at')} >= {date_days_ago(13)} "
            f"GROUP BY {as_date('created_at')} ORDER BY day"
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
        "daily_revenue": [{"day": str(r["day"]), "revenue": round(r["revenue"], 2), "count": r["n"]} for r in daily_revenue],
    }


def get_all_quotes(limit: int = 5000) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            q("SELECT reference, created_at, product_name, total, subtotal, vat, "
              "sale_discount, quantity, lead_time FROM sai_quotes ORDER BY created_at DESC LIMIT ?"),
            (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_quote(reference: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute(
            q("SELECT * FROM sai_quotes WHERE reference = ?"), (reference,)
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
    now = datetime.now(UTC).isoformat()
    with _connect() as conn:
        existing = conn.execute(
            q("SELECT value FROM pricing_settings WHERE key = ?"), (key,)
        ).fetchone()
        old_value = existing["value"] if existing else None
        conn.execute(
            q("""
            INSERT INTO pricing_settings (key, value, description, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                description=excluded.description, updated_at=excluded.updated_at
            """),
            (key, value, description, now),
        )
        conn.execute(
            q("INSERT INTO pricing_history (key, old_value, new_value, changed_at) VALUES (?, ?, ?, ?)"),
            (key, old_value, value, now),
        )


def get_pricing_history(limit: int = 50) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            q("SELECT key, old_value, new_value, changed_at FROM pricing_history "
              "ORDER BY changed_at DESC LIMIT ?"),
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def save_llm_metric(
    session_id: str | None,
    provider: str,
    model: str,
    latency_ms: int,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    success: bool = True,
) -> None:
    with _connect() as conn:
        conn.execute(
            q("""
            INSERT INTO llm_metrics
                (session_id, provider, model, latency_ms, prompt_tokens,
                 completion_tokens, total_tokens, success)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """),
            (session_id, provider, model, latency_ms, prompt_tokens,
             completion_tokens, total_tokens, 1 if success else 0),
        )


def get_llm_metrics_summary() -> dict:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) as total_calls,
                SUM(CASE WHEN success=1 THEN 1 ELSE 0 END) as successes,
                ROUND(AVG(CASE WHEN success=1 THEN latency_ms END)) as avg_latency_ms,
                SUM(total_tokens) as total_tokens_used,
                MAX(created_at) as last_call
            FROM llm_metrics
            """
        ).fetchone()
        recent = conn.execute(
            """
            SELECT provider, model, latency_ms, total_tokens, success, created_at
            FROM llm_metrics ORDER BY created_at DESC LIMIT 20
            """,
        ).fetchall()
    return {
        "total_calls": row["total_calls"] or 0,
        "successes": row["successes"] or 0,
        "avg_latency_ms": row["avg_latency_ms"] or 0,
        "total_tokens_used": row["total_tokens_used"] or 0,
        "last_call": row["last_call"],
        "recent": [dict(r) for r in recent],
    }
