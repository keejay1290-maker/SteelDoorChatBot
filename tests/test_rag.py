"""Tests for RAG retrieval (app/rag.py)."""
import pytest

from app.rag import format_rag_context, is_compliance_query, retrieve


# ---------------------------------------------------------------------------
# is_compliance_query
# ---------------------------------------------------------------------------

def test_compliance_query_fire_rating():
    assert is_compliance_query("Does this meet fire rating requirements?")


def test_compliance_query_fd30():
    assert is_compliance_query("I need an FD30 door for my escape route")


def test_compliance_query_fd60():
    assert is_compliance_query("FD60 required for my commercial corridor")


def test_compliance_query_building_regs():
    assert is_compliance_query("Does this comply with building regs Part B?")


def test_compliance_query_bs476():
    assert is_compliance_query("Is it tested to BS476?")


def test_compliance_query_escape_route():
    assert is_compliance_query("I need a door for a means of escape")


def test_compliance_query_part_m():
    assert is_compliance_query("Needs to meet Part M accessibility requirements")


def test_not_compliance_query_generic():
    assert not is_compliance_query("how much is a single internal door?")


def test_not_compliance_query_greeting():
    assert not is_compliance_query("hello, I need a quote")


def test_not_compliance_query_colour():
    assert not is_compliance_query("I want it in RAL 9005 black")


# ---------------------------------------------------------------------------
# retrieve
# ---------------------------------------------------------------------------

def test_retrieve_returns_empty_for_non_compliance():
    results = retrieve("I want a single sliding door in black")
    assert results == []


def test_retrieve_fd30_returns_relevant_chunks():
    results = retrieve("Does this FD30 door meet building regulations?")
    assert len(results) >= 1
    titles = [c["title"] for c in results]
    assert any("FD30" in t or "Fire" in t for t in titles)


def test_retrieve_fd60_returns_relevant_chunks():
    results = retrieve("I need FD60 for my commercial corridor escape route")
    assert len(results) >= 1
    titles = [c["title"] for c in results]
    assert any("FD60" in t or "Corridor" in t or "Escape" in t for t in titles)


def test_retrieve_returns_at_most_top_k():
    results = retrieve("fire rating certification building regs BS476 FD30 FD60", top_k=3)
    assert len(results) <= 3


def test_retrieve_top_k_respected():
    results = retrieve("Does this door have fire certification and building regs compliance?", top_k=2)
    assert len(results) <= 2


def test_retrieve_part_b_returns_building_regs_chunk():
    results = retrieve("Does this comply with Approved Document Part B fire safety?")
    assert len(results) >= 1
    sources = [c["source"] for c in results]
    assert any("Part B" in s or "Approved Document" in s for s in sources)


def test_retrieve_acoustic_query():
    results = retrieve("What is the sound reduction Rw value of your doors?")
    assert len(results) >= 1
    titles = [c["title"] for c in results]
    assert any("Acoustic" in t for t in titles)


def test_retrieve_chunks_have_required_keys():
    results = retrieve("fire rated FD30 certification")
    for chunk in results:
        assert "title" in chunk
        assert "content" in chunk
        assert "source" in chunk


# ---------------------------------------------------------------------------
# format_rag_context
# ---------------------------------------------------------------------------

def test_format_rag_context_empty():
    assert format_rag_context([]) == ""


def test_format_rag_context_includes_source():
    chunks = [{"title": "FD30 Standard", "source": "BS 476-22", "content": "30 min fire resistance"}]
    ctx = format_rag_context(chunks)
    assert "BS 476-22" in ctx
    assert "FD30 Standard" in ctx
    assert "30 min fire resistance" in ctx


def test_format_rag_context_cite_instruction():
    chunks = [{"title": "Test", "source": "Src", "content": "Content"}]
    ctx = format_rag_context(chunks)
    assert "cite" in ctx.lower() or "According to" in ctx or "source" in ctx.lower()


def test_format_rag_context_multiple_chunks():
    chunks = [
        {"title": "A", "source": "Src-A", "content": "Content A"},
        {"title": "B", "source": "Src-B", "content": "Content B"},
    ]
    ctx = format_rag_context(chunks)
    assert "Src-A" in ctx
    assert "Src-B" in ctx
