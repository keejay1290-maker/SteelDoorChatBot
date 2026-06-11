"""TEST-003 — Internal brief generation tests."""
import pytest
from app.session import ConversationSession, build_internal_brief, build_internal_brief_json


def _state(**kwargs) -> ConversationSession:
    s = ConversationSession()
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_brief_text_includes_name():
    s = _state(name="Alice", email="alice@example.com", postcode="SW1A 1AA", readiness_score=75)
    brief = build_internal_brief(s)
    assert "Alice" in brief


def test_brief_text_includes_email():
    s = _state(name="Bob", email="bob@test.com", readiness_score=60)
    brief = build_internal_brief(s)
    assert "bob@test.com" in brief


def test_brief_json_structure():
    s = _state(
        name="Charlie",
        email="charlie@example.com",
        phone="01234 567890",
        postcode="M1 1AE",
        door_type="single_leaf",
        build_type="commercial",
        budget_min=5000,
        budget_max=8000,
        readiness_score=80,
        routing="sales",
    )
    data = build_internal_brief_json(s, quote_total=6500.0)
    assert data["contact"]["name"] == "Charlie"
    assert data["contact"]["email"] == "charlie@example.com"
    assert data["project"]["build_type"] == "commercial"
    assert data["estimate"]["total_inc_vat"] == 6500.0
    assert data["hubspot"]["pipeline"] == "default"  # always "default" pipeline


def test_brief_json_missing_fields_dont_crash():
    s = _state(readiness_score=20)  # minimal state
    data = build_internal_brief_json(s)
    assert "session_id" in data
    assert data["contact"]["name"] is None
    assert data["contact"]["email"] is None


def test_brief_json_actions_required_non_empty_when_incomplete():
    s = _state(readiness_score=30)  # missing most fields
    data = build_internal_brief_json(s)
    assert isinstance(data["actions_required"], list)
    assert len(data["actions_required"]) > 0


def test_brief_json_no_actions_when_complete():
    s = _state(
        name="Dana",
        email="dana@example.com",
        phone="07700900000",
        postcode="EC1A 1BB",
        door_type="double_leaf",
        build_type="residential",
        budget_min=3000,
        budget_max=6000,
        width_mm=1000.0,
        height_mm=2100.0,
        installation_required=True,
        timeline_weeks=8,
        readiness_score=95,
        routing="survey",
    )
    data = build_internal_brief_json(s)
    # When all required fields are present, only the "schedule" action should remain
    assert len(data["actions_required"]) == 1
    assert "schedule" in data["actions_required"][0].lower()
