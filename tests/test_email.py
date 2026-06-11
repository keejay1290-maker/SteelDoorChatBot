"""Tests for EMAIL-001 — internal brief email sending."""
import os
from unittest.mock import MagicMock, patch

import pytest

from app.email_sender import send_brief_email

DUMMY_BRIEF = "╔══ INTERNAL BRIEF ══\n║  Name: John Smith\n╚══════════════════"


def test_send_skipped_when_smtp_not_configured():
    """No SMTP env vars → returns False without raising."""
    env = {"SMTP_HOST": "", "SMTP_USER": "", "SMTP_PASS": ""}
    with patch.dict(os.environ, env, clear=False):
        result = send_brief_email(
            brief=DUMMY_BRIEF,
            session_id="S-TEST01",
            readiness_score=75,
        )
    assert result is False


def test_send_success_with_valid_smtp(monkeypatch):
    """Valid SMTP config → SMTP.sendmail is called, returns True."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "bot@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")
    monkeypatch.setenv("SALES_EMAIL", "sales@test.co.uk")

    mock_server = MagicMock()
    mock_smtp_cls = MagicMock(return_value=mock_server)
    mock_server.__enter__ = MagicMock(return_value=mock_server)
    mock_server.__exit__ = MagicMock(return_value=False)

    with patch("app.email_sender.smtplib.SMTP", mock_smtp_cls):
        result = send_brief_email(
            brief=DUMMY_BRIEF,
            session_id="S-TEST02",
            readiness_score=80,
            customer_name="John Smith",
            routing="survey",
        )

    assert result is True
    mock_server.sendmail.assert_called_once()
    call_args = mock_server.sendmail.call_args
    assert "sales@test.co.uk" in call_args[0][1]


def test_send_subject_contains_name_score_route(monkeypatch):
    """Subject line should include customer name, score, and routing team."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "bot@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")

    captured = {}
    mock_server = MagicMock()
    mock_server.__enter__ = MagicMock(return_value=mock_server)
    mock_server.__exit__ = MagicMock(return_value=False)

    def capture_sendmail(from_addr, to_addrs, message_str):
        captured["message"] = message_str

    mock_server.sendmail.side_effect = capture_sendmail

    with patch("app.email_sender.smtplib.SMTP", MagicMock(return_value=mock_server)):
        send_brief_email(
            brief=DUMMY_BRIEF,
            session_id="S-TEST03",
            readiness_score=85,
            customer_name="Jane Doe",
            routing="survey",
        )

    assert "Jane Doe" in captured["message"]
    assert "85" in captured["message"]
    assert "SURVEY" in captured["message"]


def test_send_returns_false_on_smtp_error(monkeypatch):
    """SMTP connection error → returns False, does not raise."""
    monkeypatch.setenv("SMTP_HOST", "smtp.broken.com")
    monkeypatch.setenv("SMTP_USER", "bot@example.com")
    monkeypatch.setenv("SMTP_PASS", "secret")

    with patch("app.email_sender.smtplib.SMTP", side_effect=ConnectionRefusedError("refused")):
        result = send_brief_email(
            brief=DUMMY_BRIEF,
            session_id="S-TEST04",
            readiness_score=75,
        )

    assert result is False


def test_brief_email_sent_flag_set_in_session():
    """brief_email_sent flag starts False and is set to True after successful send."""
    from app.session import ConversationSession

    s = ConversationSession()
    assert s.brief_email_sent is False
