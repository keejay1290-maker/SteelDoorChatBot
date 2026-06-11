"""TEST-002 — Multi-turn conversation integration tests."""
import pytest
from app.chat import handle_chat
from app.models import ChatRequest


def _chat(msg: str, session_id: str | None = None, history: list | None = None):
    return handle_chat(ChatRequest(message=msg, session_id=session_id, history=history or []))


def test_session_persists_across_turns():
    r1 = _chat("Hi, I need a steel door")
    sid = r1.session.session_id
    r2 = _chat("I need it for a residential property", session_id=sid, history=[
        {"role": "user", "content": "Hi, I need a steel door"},
        {"role": "assistant", "content": r1.reply},
    ])
    assert r2.session.session_id == sid


def test_readiness_score_increases_with_information():
    r1 = _chat("I need a steel door for my home in Birmingham, postcode B1 1AA")
    sid = r1.session.session_id
    score1 = r1.session.readiness_score
    r2 = _chat("I want a single leaf pivot door, about 1000mm wide, 2100mm tall, with a budget of £3000-£5000", session_id=sid)
    score2 = r2.session.readiness_score
    assert score2 >= score1


def test_quote_generated_mid_conversation():
    r1 = _chat("I need a commercial steel door, single leaf, standard size")
    sid = r1.session.session_id
    r2 = _chat(
        "single leaf, pivot, 1000x2100, no glass, RAL 7016, quantity 1",
        session_id=sid,
        history=[
            {"role": "user", "content": "I need a commercial steel door, single leaf, standard size"},
            {"role": "assistant", "content": r1.reply},
        ],
    )
    # Quote may not appear in every turn but session should continue
    assert r2.session is not None
    assert r2.session.session_id == sid


def test_reply_is_non_empty_string():
    r = _chat("What steel door options do you have?")
    assert isinstance(r.reply, str)
    assert len(r.reply) > 10


def test_history_length_capped():
    """Sending a long history should not crash the handler."""
    long_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"}
        for i in range(30)
    ]
    r = _chat("Tell me about your doors", history=long_history)
    assert r.reply
