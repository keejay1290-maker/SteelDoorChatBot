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
