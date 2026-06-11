"""Tests for PDF-001 — PDF quote generation endpoint."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _post_quote(door_type: str = "external") -> str:
    res = client.post(
        "/api/quote",
        json={"door_set": "single", "door_type": door_type, "width_mm": 900, "height_mm": 2100},
    )
    assert res.status_code == 200
    return res.json()["reference"]


def test_pdf_endpoint_returns_pdf_bytes():
    ref = _post_quote()
    res = client.get(f"/api/quote/{ref}/pdf")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:4] == b"%PDF"


def test_pdf_content_disposition_has_reference():
    ref = _post_quote()
    res = client.get(f"/api/quote/{ref}/pdf")
    assert ref in res.headers["content-disposition"]


def test_pdf_endpoint_404_unknown_reference():
    res = client.get("/api/quote/SDA-DEADBEEF/pdf")
    assert res.status_code == 404


def test_pdf_different_door_types_produce_pdf():
    for door_type in ("internal", "fire_rated", "wine_room"):
        ref = _post_quote(door_type)
        res = client.get(f"/api/quote/{ref}/pdf")
        assert res.status_code == 200
        assert res.content[:4] == b"%PDF"
