"""Tests for HubSpot CRM integration (CRM-001)."""
import os
from unittest.mock import MagicMock, patch

from app.hubspot import push_to_hubspot
from app.session import ConversationSession


def _qualified_session() -> ConversationSession:
    s = ConversationSession()
    s.name = "Jane Smith"
    s.email = "jane@example.com"
    s.phone = "07700900000"
    s.postcode = "SW1A 1AA"
    s.door_type = "external"
    s.door_set = "single"
    s.mechanism = "hinged"
    s.readiness_score = 75
    s.routing = "survey"
    return s


def test_noop_without_token():
    """push_to_hubspot returns False (no-op) when HUBSPOT_ACCESS_TOKEN is absent."""
    env = {k: v for k, v in os.environ.items() if k != "HUBSPOT_ACCESS_TOKEN"}
    with patch.dict(os.environ, env, clear=True):
        result = push_to_hubspot(_qualified_session(), quote_total=3500.0)
    assert result is False


def test_push_creates_contact_and_deal():
    """Happy path — two POSTs (contact + deal) and one PUT (association)."""
    env_patch = {"HUBSPOT_ACCESS_TOKEN": "test-token"}

    contact_resp = MagicMock()
    contact_resp.status_code = 201
    contact_resp.json.return_value = {"id": "contact-123"}
    contact_resp.raise_for_status = MagicMock()

    deal_resp = MagicMock()
    deal_resp.status_code = 200
    deal_resp.json.return_value = {"id": "deal-456"}
    deal_resp.raise_for_status = MagicMock()

    assoc_resp = MagicMock()
    assoc_resp.status_code = 200

    with patch.dict(os.environ, env_patch):
        with patch("httpx.post") as mock_post, patch("httpx.put") as mock_put:
            mock_post.side_effect = [contact_resp, deal_resp]
            mock_put.return_value = assoc_resp

            result = push_to_hubspot(_qualified_session(), quote_total=3500.0)

    assert result is True
    assert mock_post.call_count == 2
    assert mock_put.call_count == 1

    # Verify deal amount was set
    deal_call_kwargs = mock_post.call_args_list[1].kwargs
    assert deal_call_kwargs["json"]["properties"]["amount"] == "3500.0"


def test_push_handles_409_conflict():
    """Contact already exists (409) — should search by email and continue."""
    env_patch = {"HUBSPOT_ACCESS_TOKEN": "test-token"}

    conflict_resp = MagicMock()
    conflict_resp.status_code = 409
    conflict_resp.json.return_value = {}

    search_resp = MagicMock()
    search_resp.status_code = 200
    search_resp.json.return_value = {"results": [{"id": "existing-contact-789"}]}
    search_resp.raise_for_status = MagicMock()

    patch_resp = MagicMock()
    patch_resp.status_code = 200

    deal_resp = MagicMock()
    deal_resp.status_code = 200
    deal_resp.json.return_value = {"id": "deal-456"}
    deal_resp.raise_for_status = MagicMock()

    assoc_resp = MagicMock()

    with patch.dict(os.environ, env_patch):
        with patch("httpx.post") as mock_post, patch("httpx.put") as mock_put, \
             patch("httpx.patch") as mock_patch:
            mock_post.side_effect = [conflict_resp, search_resp, deal_resp]
            mock_put.return_value = assoc_resp
            mock_patch.return_value = patch_resp

            result = push_to_hubspot(_qualified_session(), quote_total=None)

    assert result is True


def test_push_returns_false_on_error():
    """Any httpx error → returns False, does not raise."""
    import httpx as _httpx

    env_patch = {"HUBSPOT_ACCESS_TOKEN": "test-token"}
    with patch.dict(os.environ, env_patch):
        with patch("httpx.post", side_effect=_httpx.ConnectError("unreachable")):
            result = push_to_hubspot(_qualified_session(), quote_total=None)

    assert result is False
