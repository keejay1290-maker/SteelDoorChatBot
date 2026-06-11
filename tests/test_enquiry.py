"""Tests for the enquiry (lead capture) endpoint and store."""
import os
import tempfile

# Use a throwaway DB file for tests before importing the app/store.
os.environ["ENQUIRY_DB"] = os.path.join(tempfile.gettempdir(), "sda_test_enquiries.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.store import count_enquiries, init_db  # noqa: E402

client = TestClient(app)


def test_enquiry_is_saved():
    init_db()
    before = count_enquiries()
    res = client.post(
        "/api/enquiry",
        json={
            "name": "Test Customer",
            "email": "test@example.com",
            "phone": "01785526016",
            "postcode": "ST16 1YJ",
            "message": "Double sliding doors please",
            "quote_reference": "SDA-ABCD1234",
            "quote_total": 3360.0,
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["reference"].startswith("ENQ-")
    assert body["status"] == "received"
    assert count_enquiries() == before + 1


def test_enquiry_requires_name_and_email():
    res = client.post("/api/enquiry", json={"phone": "123"})
    assert res.status_code == 422
