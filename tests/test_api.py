"""End-to-end tests for the FastAPI endpoints."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_quote_endpoint_single():
    res = client.post(
        "/api/quote",
        json={"door_set": "single", "width_mm": 900, "height_mm": 2100},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["total"] > 0
    assert body["currency"] == "GBP"
    assert body["vat"] == round(body["subtotal"] * 0.20, 2)
    assert body["reference"].startswith("SDA-")
    assert body["lead_time"]


def test_quote_endpoint_double_fire_rated():
    res = client.post(
        "/api/quote",
        json={
            "door_set": "double",
            "door_type": "fire_rated",
            "glass": "reeded",
            "fire_rating": "FD30",
            "width_mm": 1200,
            "height_mm": 2100,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert "Fire Rated" in body["product_name"]
    assert body["total"] > 3000


def test_quote_endpoint_rejects_invalid_dimensions():
    res = client.post(
        "/api/quote",
        json={"door_set": "single", "width_mm": -5, "height_mm": 2100},
    )
    assert res.status_code == 422


def test_quote_endpoint_rejects_invalid_glass():
    res = client.post(
        "/api/quote",
        json={"door_set": "single", "glass": "transparent"},  # not a valid enum value
    )
    assert res.status_code == 422


def test_chat_endpoint_with_spec_returns_quote():
    res = client.post(
        "/api/chat",
        json={"message": "quote for 3 double internal doors 1900 x 2100"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["quote"] is not None
    assert body["quote"]["quantity"] == 3
    assert "£" in body["reply"]


def test_chat_endpoint_without_spec_has_no_quote():
    res = client.post("/api/chat", json={"message": "hello"})
    assert res.status_code == 200
    assert res.json()["quote"] is None


def test_chat_endpoint_accepts_history():
    from app.models import ChatMessage
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "Hello!"}]
    res = client.post(
        "/api/chat",
        json={"message": "how much for a double door?", "history": history},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["quote"] is not None


def test_catalogue_endpoint():
    res = client.get("/api/catalogue")
    assert res.status_code == 200
    data = res.json()
    assert "single" in data
    assert "double" in data
    assert data["single"]["base_price"] == 1700.0
    assert data["double"]["base_price"] == 3000.0


# ── TASK 1.1 — Quote lookup ──────────────────────────────────────────────────

def test_quote_lookup():
    # POST a quote first
    post = client.post(
        "/api/quote",
        json={"door_set": "single", "door_type": "external", "width_mm": 900, "height_mm": 2100},
    )
    assert post.status_code == 200
    ref = post.json()["reference"]

    # GET it back by reference
    get = client.get(f"/api/quote/{ref}")
    assert get.status_code == 200
    data = get.json()
    assert data["reference"] == ref
    assert data["total"] > 0


def test_quote_lookup_not_found():
    res = client.get("/api/quote/SDA-00000000")
    assert res.status_code == 404


# ── TASK 1.2 — Dashboard basic auth ─────────────────────────────────────────

def test_dashboard_requires_auth():
    assert client.get("/dashboard").status_code == 401
    assert client.get("/api/dashboard/stats").status_code == 401
    assert client.get("/api/dashboard/sessions").status_code == 401


def test_dashboard_accessible_with_auth():
    auth = ("admin", "steeldoor")
    assert client.get("/dashboard", auth=auth).status_code == 200
    assert client.get("/api/dashboard/stats", auth=auth).status_code == 200
    assert client.get("/api/dashboard/sessions", auth=auth).status_code == 200


def test_dashboard_rejects_wrong_password():
    assert client.get("/dashboard", auth=("admin", "wrong")).status_code == 401


# ── TASK 1.3 — Demo seeding idempotency ──────────────────────────────────────

def test_seed_idempotent(monkeypatch):
    """seed_demo_data() called twice with SEED_DEMO=1 must not double-insert."""
    import os
    from app.seed import seed_demo_data
    from app.store import _connect, init_db

    monkeypatch.setenv("SEED_DEMO", "1")
    init_db()

    # First call — may or may not insert (DB might already have rows from other tests)
    seed_demo_data()
    with _connect() as conn:
        n1 = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]

    # Second call — must be a no-op
    seed_demo_data()
    with _connect() as conn:
        n2 = conn.execute("SELECT COUNT(*) AS n FROM sessions").fetchone()["n"]

    assert n1 == n2


def test_seed_skipped_without_flag(monkeypatch):
    """seed_demo_data() returns 0 when SEED_DEMO is not set."""
    from app.seed import seed_demo_data
    monkeypatch.delenv("SEED_DEMO", raising=False)
    assert seed_demo_data() == 0
