"""Tests for the chatbot orchestration (mock LLM provider)."""
from app.chat import _extract_quote_request, handle_chat
from app.models import ChatRequest


def test_extract_double_sliding_spec():
    req = _extract_quote_request(
        "I'd like a double sliding fire-rated FD60 door 1900 x 2100 reeded glass RAL 9005 with 2 panels"
    )
    assert req is not None
    assert req.door_set == "double"
    assert req.mechanism == "sliding"
    assert req.door_type == "fire_rated"
    assert req.fire_rating == "FD60"
    assert req.glass == "reeded"
    assert req.ral_colour == "RAL 9005"
    assert req.side_panels == 2


def test_extract_defaults_single():
    req = _extract_quote_request("how much for a single internal steel door?")
    assert req is not None
    assert req.door_set == "single"
    assert req.width_mm == 900


def test_transparent_synonym_maps_to_clear():
    """'transparent' in user text should map to glass='clear'."""
    req = _extract_quote_request("I want a single door with transparent glass")
    assert req is not None
    assert req.glass == "clear"


def test_opaque_synonym_maps_to_frosted():
    """'opaque' in user text should map to glass='frosted'."""
    req = _extract_quote_request("double door with opaque glass please")
    assert req is not None
    assert req.glass == "frosted"


def test_privacy_glass_maps_to_frosted():
    req = _extract_quote_request("single door, privacy glass")
    assert req is not None
    assert req.glass == "frosted"


def test_concertina_extraction():
    req = _extract_quote_request("I want a double concertina door")
    assert req is not None
    assert req.mechanism == "concertina"


def test_wine_room_extraction():
    req = _extract_quote_request("door for my wine room please")
    assert req is not None
    assert req.door_type == "wine_room"


def test_non_quote_message_returns_none():
    assert _extract_quote_request("hello, who are you?") is None


def test_handle_chat_without_intent_has_no_quote():
    resp = handle_chat(ChatRequest(message="hi there"))
    assert resp.quote is None
    assert resp.reply


def test_handle_chat_with_spec_returns_quote():
    resp = handle_chat(ChatRequest(message="quote for 2 double internal doors 1900 x 2100"))
    assert resp.quote is not None
    assert resp.quote.quantity == 2
    assert resp.quote.total > 0
    assert "£" in resp.reply


def test_handle_chat_fire_rated():
    resp = handle_chat(ChatRequest(message="I need a fire rated FD30 single steel door"))
    assert resp.quote is not None
    assert resp.quote.product_name == "Fire Rated Steel Door (FD30/FD60)"


def test_handle_chat_with_history():
    """Conversation history is accepted without error."""
    from app.models import ChatMessage
    history = [
        ChatMessage(role="user", content="how much for a single door?"),
        ChatMessage(role="assistant", content="A single steel door starts from £1,700."),
    ]
    resp = handle_chat(ChatRequest(
        message="can I get that in RAL 9005?",
        history=history,
    ))
    assert resp.reply
