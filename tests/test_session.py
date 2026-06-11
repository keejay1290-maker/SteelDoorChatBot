"""Tests for ConversationSession routing logic (TASK 0.3)."""
from app.session import ConversationSession, determine_routing


def _base(**kwargs) -> ConversationSession:
    s = ConversationSession()
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


def test_routing_supply_only_to_sales():
    s = _base(installation_required=False, readiness_score=65)
    assert determine_routing(s) == "sales"


def test_routing_supply_only_below_threshold_falls_through():
    # Supply-only but score < 60 → not enough spec yet → falls to default sales
    s = _base(installation_required=False, readiness_score=40)
    assert determine_routing(s) == "sales"


def test_routing_full_spec_with_email_to_survey():
    s = _base(readiness_score=75, email="jane@example.com", installation_required=None)
    assert determine_routing(s) == "survey"


def test_routing_full_spec_install_wanted_to_survey():
    s = _base(readiness_score=80, email="bob@example.com", installation_required=True)
    assert determine_routing(s) == "survey"


def test_routing_post_quote_followup_to_customer_care():
    s = _base(quote_reference="SDA-ABCD1234", stage=4)
    assert determine_routing(s) == "customer_care"


def test_routing_commercial_project_to_installation():
    s = _base(project_context="commercial")
    assert determine_routing(s) == "installation"


def test_routing_large_quantity_to_installation():
    s = _base(quantity=5)
    assert determine_routing(s) == "installation"


def test_routing_default_to_sales():
    s = ConversationSession()
    assert determine_routing(s) == "sales"
