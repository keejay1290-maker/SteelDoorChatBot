"""Keyword-based RAG retrieval for Steel Door Company technical specs.

No external dependencies — pure stdlib + math. Chunks live in
app/data/specs/steel_door_specs.json and are loaded once at first call.

Retrieval is triggered only when the customer message contains compliance
or specification keywords (fire rating, building regs, BS476, etc.).
Top-3 matching chunks are injected into the LLM system prompt with source
citations so the model can answer "According to [source]: ..." accurately.
"""
from __future__ import annotations

import json
import logging
import math
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_SPECS_PATH = Path(__file__).parent / "data" / "specs" / "steel_door_specs.json"

# Compliance/spec keywords that trigger retrieval
_RAG_TRIGGERS = {
    "fire rating", "fire rated", "fire door", "fire cert", "fire resist",
    "fire safe", "fire standard", "fire reg",
    "bs476", "bs 476", "bs en", "bsen",
    "building reg", "building regs", "building regulation",
    "part b", "part m", "approved doc",
    "fd30", "fd60", "fd 30", "fd 60",
    "escape route", "means of escape",
    "certified", "certificate", "certification", "certif",
    "complian", "regulation", "standard",
    "intumescent", "smoke seal", "self-closing", "self closing",
    "ce mark", "declaration of performance",
    "trada", "certifire", "bm trada",
    "insurance require", "insurer require",
    "acoustic", "sound reduct", "rw value", "db rating",
    "thermal", "u-value", "u value",
    "specification", "spec sheet", "technical spec",
    "bs en 1634", "bs en 14351", "bs 9999", "bs 9991",
    "rro", "fire safety order",
}


_chunks: list[dict] | None = None


def _load_chunks() -> list[dict]:
    global _chunks
    if _chunks is None:
        try:
            with _SPECS_PATH.open(encoding="utf-8") as f:
                _chunks = json.load(f)
            logger.info("RAG: loaded %d spec chunks from %s", len(_chunks), _SPECS_PATH)
        except Exception as exc:
            logger.warning("RAG: failed to load spec chunks: %s", exc)
            _chunks = []
    return _chunks


def _tokenise(text: str) -> set[str]:
    return set(re.findall(r"\b\w+\b", text.lower()))


def _score(query_tokens: set[str], chunk: dict) -> float:
    """TF overlap score with title boost and chunk weight. Pure stdlib."""
    title_tokens = _tokenise(chunk["title"])
    body_tokens = _tokenise(chunk["content"] + " " + chunk.get("source", ""))
    chunk_tokens = title_tokens | body_tokens

    overlap = len(query_tokens & chunk_tokens)
    if overlap == 0:
        return 0.0

    # Title matches count double
    title_overlap = len(query_tokens & title_tokens)
    total_overlap = overlap + title_overlap

    weight = chunk.get("weight", 1.0)
    return total_overlap * weight / math.sqrt(len(chunk_tokens) + 1)


def is_compliance_query(text: str) -> bool:
    """Return True if message likely asks about compliance, specs, or fire ratings."""
    t = text.lower()
    return any(kw in t for kw in _RAG_TRIGGERS)


def retrieve(query: str, top_k: int = 3) -> list[dict]:
    """Return top_k spec chunks most relevant to query. Returns [] if not a compliance query."""
    if not is_compliance_query(query):
        return []
    chunks = _load_chunks()
    if not chunks:
        return []
    query_tokens = _tokenise(query)
    scored = sorted(chunks, key=lambda c: _score(query_tokens, c), reverse=True)
    results = [c for c in scored[:top_k] if _score(query_tokens, c) > 0]
    logger.debug("RAG: retrieved %d chunks for query (truncated): %.60s", len(results), query)
    return results


def format_rag_context(chunks: list[dict]) -> str:
    """Format retrieved chunks for injection into the system prompt."""
    if not chunks:
        return ""
    lines = [
        "TECHNICAL SPECIFICATIONS — cite the source in your reply using 'According to [source]:':",
    ]
    for c in chunks:
        lines.append(f"[{c['source']}] {c['title']}: {c['content']}")
    return "\n".join(lines)
