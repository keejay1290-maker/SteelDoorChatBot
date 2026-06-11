"""COR-04 regression: HubSpot push + webhook must fire at most once per session,
even when SMTP is unconfigured (brief_email_sent never flips). Guarded by the
dedicated hubspot_pushed / webhook_fired persisted flags.
"""
from unittest.mock import patch

from app.chat import handle_chat
from app.models import ChatRequest

# A single message that reaches readiness >= 70 via regex extraction alone:
# door_set(10)+door_type(10)+mechanism(5)+dims(20)+name(10)+email(15) = 70
_QUALIFYING = (
    "I need a single external hinged door, 900 x 2100mm. "
    "I'm Jane Smith, email jane@example.com"
)


def test_hubspot_push_fires_once_across_messages(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "test-token")

    with patch("app.hubspot.push_to_hubspot", return_value=True) as mock_push, \
         patch("app.webhook.fire_webhook", return_value=True) as mock_webhook:
        first = handle_chat(ChatRequest(message=_QUALIFYING))
        sid = first.session.session_id
        assert first.session.readiness_score >= 70

        # Two more messages on the same session — must NOT re-push
        handle_chat(ChatRequest(message="any update?", session_id=sid))
        handle_chat(ChatRequest(message="still there?", session_id=sid))

    assert mock_push.call_count == 1
    assert mock_webhook.call_count == 1


def test_hubspot_retries_when_first_push_fails(monkeypatch):
    """If the first push fails (returns False), the flag stays False and a later
    message retries — no permanent loss of the lead."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "test-token")

    with patch("app.hubspot.push_to_hubspot", side_effect=[False, True]) as mock_push, \
         patch("app.webhook.fire_webhook", return_value=True):
        first = handle_chat(ChatRequest(message=_QUALIFYING))
        sid = first.session.session_id
        handle_chat(ChatRequest(message="any update?", session_id=sid))

    assert mock_push.call_count == 2  # retried after first failure
