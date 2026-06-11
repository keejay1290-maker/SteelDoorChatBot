"""Database backend abstraction — SQLite (local/tests) or Postgres (production).

When ``DATABASE_URL`` is set (Supabase Postgres via the IPv4 transaction pooler),
the app uses Postgres for durable storage. Otherwise it falls back to a local
SQLite file — keeping local dev and the test suite fast, offline, and unchanged.

Only the dialect differences that this app actually uses are abstracted here:
placeholder style, auto-increment PK, "now" default, JSON field access, and
date casting. Everything else is standard SQL shared by both backends.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# DATABASE_URL is the primary switch. Also accept POSTGRES_URL, which the
# Supabase–Vercel integration injects automatically (pooled connection). Never
# use POSTGRES_URL_NON_POOLING — that is the IPv6 direct connection.
DATABASE_URL = (os.environ.get("DATABASE_URL") or os.environ.get("POSTGRES_URL") or "").strip()
IS_POSTGRES = DATABASE_URL.startswith("postgres")

DB_PATH = Path(os.environ.get("ENQUIRY_DB", "enquiries.db"))

if IS_POSTGRES:
    import psycopg
    from psycopg.rows import dict_row


def connect():
    """Return a connection with a dict-style row factory and per-statement commit.

    Postgres uses autocommit + ``prepare_threshold=None`` so it is safe behind
    the Supabase transaction pooler (pgBouncer), which does not persist prepared
    statements across pooled transactions.
    """
    if IS_POSTGRES:
        return psycopg.connect(
            DATABASE_URL,
            row_factory=dict_row,
            autocommit=True,
            prepare_threshold=None,
            connect_timeout=15,
        )
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def q(sql: str) -> str:
    """Translate ``?`` placeholders to ``%s`` for Postgres; no-op for SQLite."""
    return sql.replace("?", "%s") if IS_POSTGRES else sql


# --- Dialect fragments -----------------------------------------------------

#: Auto-increment integer primary key column definition.
AUTOINC_PK = (
    "BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY"
    if IS_POSTGRES else
    "INTEGER PRIMARY KEY AUTOINCREMENT"
)

#: DEFAULT expression giving the current timestamp as text.
NOW_DEFAULT = "(now()::text)" if IS_POSTGRES else "(datetime('now'))"


def json_field(col: str, key: str) -> str:
    """SQL expression extracting a top-level string field from a JSON text column."""
    if IS_POSTGRES:
        return f"({col}::jsonb ->> '{key}')"
    return f"json_extract({col}, '$.{key}')"


def as_date(col: str) -> str:
    """Cast an ISO-timestamp text column to a DATE for grouping/filtering."""
    if IS_POSTGRES:
        return f"({col}::timestamptz)::date"
    return f"date({col})"


def date_days_ago(n: int) -> str:
    """SQL expression for the date ``n`` days before today."""
    if IS_POSTGRES:
        return f"(CURRENT_DATE - INTERVAL '{n} days')"
    return f"date('now', '-{n} days')"
