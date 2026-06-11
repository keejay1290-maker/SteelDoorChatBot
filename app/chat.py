"""Full AI sales consultant for Steel Door Company.

Architecture:
- Every message extracts structured fields from NL text (regex + LLM)
- Fields are merged into a server-side ConversationSession
- Readiness score (0-100) drives the conversation stage
- LLM (or mock) generates the reply; ALL numbers come from the deterministic engine
- When score >= 70 + has email → generates internal brief + routes to correct team

LLM providers: mock (default) | groq | deepseek
"""
from __future__ import annotations

import logging
import os
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

from .catalogue import CATALOGUE
from .models import ChatRequest, ChatResponse, QuoteRequest, QuoteResponse, SessionState
from .store import save_llm_metric
from .quoting import PRICING, calculate_quote
from .rag import format_rag_context, retrieve as rag_retrieve
from .session import (
    ConversationSession,
    build_internal_brief,
    calculate_readiness,
    determine_routing,
    load_session,
    save_session,
)


# ---------------------------------------------------------------------------
# Field extraction helpers
# ---------------------------------------------------------------------------

def _extract_fields(text: str, s: ConversationSession) -> ConversationSession:
    """Parse NL text and update session fields in-place. Regex-first, non-destructive."""
    t = text.lower()

    # --- Contact info ---
    email_m = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    if email_m and not s.email:
        s.email = email_m.group(0).lower()

    # UK phone: 07xx xxxxxx / +44 / 01xxx
    phone_m = re.search(r"(\+44\s*\d[\d\s]{9,12}|0\d[\d\s]{9,11})", text)
    if phone_m and not s.phone:
        s.phone = re.sub(r"\s+", "", phone_m.group(1))

    # UK postcode
    pc_m = re.search(r"\b([A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2})\b", text.upper())
    if pc_m and not s.postcode:
        s.postcode = pc_m.group(1).upper()

    # Name — "I'm John Smith" / "my name is" / "it's for Jane" / "name: John"
    _NAME_STOPWORDS = {
        "you", "us", "me", "the", "a", "an", "it", "this", "that", "these", "those",
        "single", "double", "internal", "external", "hinged", "sliding", "concertina",
        "black", "white", "grey", "anthracite", "clear", "frosted", "reeded", "bespoke",
        "fire", "rated", "steel", "door", "doors", "yes", "no", "ok", "okay", "sure",
        "help", "quote", "price", "cost", "survey", "company", "looking", "interested",
        "getting", "having", "buying", "want", "need", "like", "please", "thanks",
        "installing", "installation", "fitted", "fitting", "supply", "deliver",
        "residential", "commercial", "property", "house", "flat", "office", "warehouse",
        "new", "build", "renovation", "replacement", "upgrade", "extension",
    }
    # \s+ added between prefix and capture — original patterns omitted space before name
    # No .isupper() check — _normalise_text lowercases text so names arrive lowercase
    name_patterns = [
        r"(?:my name is|i[' ]m|name[:\s]+|it[' ]?s for)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
        r"(?:called|contact)\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)",
    ]
    if not s.name:
        for pat in name_patterns:
            nm = re.search(pat, text, re.IGNORECASE)
            if nm:
                candidate = nm.group(1).strip()
                words = candidate.lower().split()
                if len(candidate) >= 2 and not any(w in _NAME_STOPWORDS for w in words):
                    s.name = candidate.title()
                    break

    # --- Project context ---
    if not s.project_context:
        if any(w in t for w in ("house", "home", "flat", "apartment", "residential", "domestic", "bungalow")):
            s.project_context = "residential"
        elif any(w in t for w in ("office", "commercial", "warehouse", "shop", "business", "factory", "unit")):
            s.project_context = "commercial"

    if not s.build_type:
        if any(w in t for w in ("new build", "new development", "newbuild", "extension")):
            s.build_type = "new_build"
        elif any(w in t for w in ("renovation", "refurb", "replace", "existing", "upgrade")):
            s.build_type = "renovation"

    if s.installation_required is None:
        if any(w in t for w in ("supply only", "supply and install", "fit only", "just the door", "no installation")):
            s.installation_required = False
        elif any(w in t for w in ("install", "fit", "fitting", "installation")):
            s.installation_required = True

    # Budget — "£4,000-£6,000" / "£8k" / "around 8k" / "8000 budget"
    def _parse_budget(v: str, k: str | None = None) -> float:
        amt = float(v.replace(",", ""))
        return amt * 1000 if (k or amt < 100) else amt

    budget_m = re.search(r"£([\d,]+)(k)?(?:\s*[-–to]+\s*£?([\d,]+)(k)?)?", text, re.IGNORECASE)
    if not budget_m:
        budget_m = re.search(r"(\d[\d,]*)(k)?\s*(?:[-–to]+\s*(\d[\d,]*)(k?)?)?\s*(?:budget|spend|£)", t)
    if budget_m and not s.budget_min:
        s.budget_min = _parse_budget(budget_m.group(1), budget_m.group(2))
        if budget_m.group(3):
            s.budget_max = _parse_budget(budget_m.group(3), budget_m.group(4))

    # Timeline
    if not s.timeline_weeks:
        tl_m = re.search(r"(\d+)\s*weeks?", t)
        if tl_m:
            s.timeline_weeks = int(tl_m.group(1))
        elif any(w in t for w in ("asap", "urgent", "soon", "immediately")):
            s.timeline_weeks = 2
        elif "month" in t:
            mo_m = re.search(r"(\d+)\s*months?", t)
            if mo_m:
                s.timeline_weeks = int(mo_m.group(1)) * 4
            else:
                s.timeline_weeks = 8
        elif "end of " in t or "by " in t:
            s.timeline_weeks = 12  # rough estimate

    # --- Door spec ---
    if not s.door_set:
        if "double" in t:
            s.door_set = "double"
        elif "single" in t:
            s.door_set = "single"

    if not s.door_type:
        if any(w in t for w in ("fire", "fd30", "fd60", "fire rated", "fire-rated")):
            s.door_type = "fire_rated"
        elif "wine" in t:
            s.door_type = "wine_room"
        elif any(w in t for w in ("external", "patio", "outside", "exterior")):
            s.door_type = "external"
        elif "internal" in t or "inside" in t:
            s.door_type = "internal"

    if not s.mechanism:
        if any(w in t for w in ("concertina", "folding", "bifold", "bi-fold")):
            s.mechanism = "concertina"
        elif any(w in t for w in ("sliding", "slide")):
            s.mechanism = "sliding"
        elif "hinged" in t or "hinge" in t:
            s.mechanism = "hinged"

    # Dimensions: "1900 x 2100" / "1900×2100" / "900mm wide 2100mm tall"
    if not s.width_mm:
        dims = re.findall(r"(\d{3,4})\s*(?:mm)?\s*(?:x|by|\*|×)\s*(\d{3,4})", t)
        if dims:
            a, b = int(dims[0][0]), int(dims[0][1])
            s.width_mm, s.height_mm = (min(a, b), max(a, b))
        else:
            # "900mm wide 2100 high"
            w_m = re.search(r"(\d{3,4})\s*mm\s*(?:wide|width|w\b)", t)
            h_m = re.search(r"(\d{3,4})\s*mm\s*(?:high|tall|height|h\b)", t)
            if w_m: s.width_mm = float(w_m.group(1))
            if h_m: s.height_mm = float(h_m.group(1))

    if not s.quantity:
        qty_m = re.search(
            r"(\d+)\s*(?:double\b|single\b|doors?|sets?|units?|off)|(?:for|need|want|quote for)\s+(\d+)\b",
            t
        )
        if qty_m:
            s.quantity = int(qty_m.group(1) or qty_m.group(2))
            if s.quantity > 100: s.quantity = 1  # sanity cap

    if not s.glass:
        if any(w in t for w in ("reeded", "fluted")):
            s.glass = "reeded"
        elif any(w in t for w in ("frosted", "opaque", "privacy")):
            s.glass = "frosted"
        elif any(w in t for w in ("bespoke glass", "custom glass")):
            s.glass = "bespoke"
        elif any(w in t for w in ("clear", "transparent", "glass")):
            s.glass = "clear"

    if not s.ral_colour:
        ral_m = re.search(r"ral\s*(\d{3,4})", t)
        if ral_m:
            s.ral_colour = f"RAL {ral_m.group(1)}"
        elif "black" in t:
            s.ral_colour = "RAL 9005"
        elif "white" in t:
            s.ral_colour = "RAL 9003"
        elif "anthracite" in t or "grey" in t:
            s.ral_colour = "RAL 7016"

    if not s.fire_rating or s.fire_rating == "none":
        if "fd60" in t:
            s.fire_rating = "FD60"
        elif "fd30" in t:
            s.fire_rating = "FD30"

    panels_m = re.search(r"(\d+)\s*(?:side\s*)?panel", t)
    if panels_m and s.side_panels is None:
        s.side_panels = min(int(panels_m.group(1)), 4)

    # Threshold — "weathered" adds £80 for external doors (flush is default)
    if s.threshold == "flush":
        if any(w in t for w in ("weathered threshold", "weather threshold", "weathered")):
            s.threshold = "weathered"
        elif any(w in t for w in ("step over", "step-over", "step_over")):
            s.threshold = "step_over"

    return s


def _what_is_missing(s: ConversationSession) -> list[str]:
    """Return a prioritised list of fields still needed, in conversational order."""
    missing = []
    # Tier 1: spec
    if not s.door_type:   missing.append("door type (internal, external, fire-rated, or wine room)")
    if not s.door_set:    missing.append("single or double leaf")
    if not s.mechanism:   missing.append("mechanism (hinged, sliding, or concertina)")
    if not s.width_mm or not s.height_mm:
        missing.append("opening size (width × height in mm)")
    if not s.quantity:    missing.append("quantity")
    if not s.glass:       missing.append("glazing preference (clear, reeded, frosted, or bespoke)")
    # Tier 2: contact
    if not s.name:        missing.append("your name")
    if not s.email:       missing.append("your email address")
    if not s.phone:       missing.append("your phone number")
    if not s.postcode:    missing.append("your postcode (for survey scheduling)")
    return missing


def _build_quote_request_from_session(s: ConversationSession) -> Optional[QuoteRequest]:
    if not s.door_type:
        return None
    return QuoteRequest(
        door_set=s.door_set or "single",
        door_type=s.door_type or "internal",
        mechanism=s.mechanism or "hinged",
        width_mm=s.width_mm or (1900 if s.door_set == "double" else 900),
        height_mm=s.height_mm or 2100,
        glass=s.glass or "clear",
        ral_colour=s.ral_colour,
        fire_rating=s.fire_rating or "none",
        side_panels=s.side_panels or 0,
        threshold=s.threshold,
        quantity=s.quantity or 1,
    )


def _build_quote_request(s: ConversationSession) -> Optional[QuoteRequest]:
    """Build a QuoteRequest from session fields. Returns None if no door product intent detected."""
    if not s.door_set and not s.door_type and not s.mechanism:
        return None  # nothing at all was detected
    return QuoteRequest(
        door_set=s.door_set or "single",
        door_type=s.door_type or "internal",
        mechanism=s.mechanism or "hinged",
        width_mm=s.width_mm or (1900 if s.door_set == "double" else 900),
        height_mm=s.height_mm or 2100,
        glass=s.glass or "clear",
        ral_colour=s.ral_colour,
        fire_rating=s.fire_rating or "none",
        side_panels=s.side_panels or 0,
        threshold=s.threshold,
        quantity=s.quantity or 1,
    )


def _extract_quote_request(text: str) -> Optional[QuoteRequest]:
    """Compatibility shim: extract a QuoteRequest from a single-message string."""
    _QUOTE_KEYWORDS = (
        "door", "quote", "price", "cost", "how much", "fd30", "fd60",
        "single", "double", "sliding", "concertina", "glass", "steel", "fire", "wine",
    )
    if not any(k in text.lower() for k in _QUOTE_KEYWORDS):
        return None
    s = _extract_fields(text, ConversationSession())
    # Apply same defaults the original function used so existing tests pass
    if not s.door_set:    s.door_set = "single"
    if not s.door_type:   s.door_type = "internal"
    if not s.mechanism:   s.mechanism = "hinged"
    return _build_quote_request_from_session(s)


# ---------------------------------------------------------------------------
# Mock reply generator (no LLM key required)
# ---------------------------------------------------------------------------

_SDC_CONTACT = (
    "**Steel Door Company**\n"
    "Unit C, Scarlet Court, Stafford ST16 1YJ\n"
    "Phone: **01785 526016**\n"
    "Email: **sales@steeldoorcompany.co.uk**\n"
    "Web: steeldoorcompany.co.uk\n"
    "Mon–Fri 8 am–6 pm | Sat 9 am–2 pm"
)

_HELP_TEXT = (
    "Here's what I can do for you:\n\n"
    "• **Get an instant estimate** — tell me what door you need and I'll price it up\n"
    "• **Answer product questions** — fire ratings, glazing options, RAL colours, dimensions\n"
    "• **Book a free site survey** — once I have your details I'll pass them to the team\n"
    "• **Compare options** — e.g. 'what's the difference between FD30 and FD60?'\n\n"
    "Just describe your project in plain English — I'll figure out the rest."
)


def _classify_intent(t: str) -> str:
    """Return intent class for message. t must be lowercased."""
    # Contact / company info
    if any(w in t for w in ("contact", "phone", "number", "email", "address", "location", "where are you", "opening hours", "opening time", "business hours")):
        return "contact_info"
    # Help
    if any(w in t for w in ("help", "what can you do", "what do you do", "how does this work", "what are you")):
        return "help"
    # Product info / pricing curiosity
    if any(w in t for w in ("most expensive", "cheapest", "cheapest", "cheapest option", "most affordable",
                             "difference between", "what is fd30", "what is fd60", "what's fd", "what are",
                             "how does", "tell me about", "explain", "what types", "options available")):
        return "product_info"
    # Confirmation / booking
    if any(w in t for w in ("yes", "yeah", "yep", "ok", "okay", "sure", "book", "schedule", "proceed", "let's go", "go ahead", "sounds good")):
        return "confirmation"
    # Adjustment
    if any(w in t for w in ("change", "adjust", "update", "different", "instead", "actually", "correction")):
        return "adjustment"
    # Greeting only (no spec content)
    if any(w in t for w in ("hello", "hi ", "hey ", "good morning", "good afternoon", "howdy")) and len(t) < 30:
        return "greeting"
    # Thanks
    if any(w in t for w in ("thank", "thanks", "cheers", "appreciate", "perfect", "great")):
        return "thanks"
    return "spec"


def _mock_reply(s: ConversationSession, quote: Optional[QuoteResponse], text: str, new_quote: bool = False) -> str:
    t = text.lower().strip()
    intent = _classify_intent(t)

    # --- Special intents handled immediately regardless of stage ---
    if intent == "contact_info":
        suffix = ""
        if s.door_type and not s.email:
            suffix = "\n\nWant me to email you the quote? Just drop your email address here."
        return _SDC_CONTACT + suffix

    if intent == "help":
        return _HELP_TEXT

    if intent == "product_info":
        if "most expensive" in t or "expensive" in t:
            return (
                "Our most premium option is the **Wine Room door** (from £2,300 base) followed by "
                "**fire-rated FD60** (from £3,400 inc. rated glass and specialist fitting). "
                "Fire-rated doors also carry the biggest uplift if you add sliding mechanism or bespoke glazing. "
                "Want a quote on one of those, or something more budget-friendly?"
            )
        if "cheapest" in t or "affordable" in t or "budget" in t:
            return (
                "Our most affordable entry point is a **standard single internal door** — from £1,700 + VAT, "
                "hinged, with clear glass and a standard RAL colour. "
                "Size, glazing, and finish all affect the final number — want me to price one up for you?"
            )
        if "difference" in t and ("fd30" in t or "fd60" in t or "fire" in t):
            return (
                "**FD30** gives 30 minutes of fire resistance — the minimum for most building regs. "
                "**FD60** gives 60 minutes and is required for commercial corridors, stairwells, and some insurance policies. "
                "FD60 adds around £250 more than FD30. Which are you looking at?"
            )
        return (
            "We make four types: **internal** (residential or commercial), **external** (weatherproofed, with threshold), "
            "**fire-rated** (FD30 or FD60, fully certified), and **wine room** (insulated, bespoke). "
            "All are made to measure in any RAL colour. Which sounds right for your project?"
        )

    if intent == "greeting":
        name_part = f", {s.name}" if s.name else ""
        if s.door_type:
            known_spec = s.door_type.replace("_", " ") + (" door" if "room" not in s.door_type else "")
            return (
                f"Hi{name_part}! Good to have you back. We were looking at a {known_spec} — "
                "shall we pick up where we left off, or start fresh?"
            )
        return (
            f"Hi{name_part}! Good to hear from you — what can I help you with today? "
            "I can get you a quick price, answer product questions, or book a free site survey."
        )

    if intent == "thanks":
        if s.email:
            return (
                "You're welcome! The team will be in touch shortly. "
                "If anything else comes up, call **01785 526016** anytime."
            )
        return "Happy to help! Is there anything else I can assist with?"

    # --- Quote display — only show when new quote was just generated ---
    if quote and new_quote:
        missing = _what_is_missing(s)
        contact_missing = [m for m in missing if any(w in m for w in ("name", "email", "phone", "postcode"))]
        lines_txt = "\n".join(f"  {ln.label}: £{ln.amount:,.2f}" for ln in quote.lines)
        if quote.sale_discount:
            lines_txt += f"\n  Summer Sale (10% off): -£{quote.sale_discount:,.2f}"
        summary = (
            f"  Subtotal: £{quote.subtotal:,.2f}\n"
            f"  VAT (20%): £{quote.vat:,.2f}\n"
            f"  **Total: £{quote.total:,.2f} inc. VAT**\n"
            f"  Lead time: {quote.lead_time}"
        )
        name_prefix = f"{s.name}, " if s.name else ""
        cta = (
            f"\n\n{name_prefix}to confirm this and book your free site survey, could you share "
            + f"**{contact_missing[0]}**?"
            if contact_missing else
            f"\n\nAll set{', ' + s.name if s.name else ''}! Readiness **{s.readiness_score}/100**. "
            "The team will be in touch. Call **01785 526016** for anything urgent."
        )
        return (
            f"Here's your indicative estimate (ref **{quote.reference}**):\n\n"
            + lines_txt + "\n" + summary
            + "\n\n_Every door is made to measure — confirmed after a free site survey._"
            + cta
        )

    # --- Adjustment intent — acknowledge and ask what to change ---
    if intent == "adjustment":
        spec_known = []
        if s.door_set: spec_known.append(s.door_set + " leaf")
        if s.door_type: spec_known.append(s.door_type.replace("_", " "))
        if s.mechanism: spec_known.append(s.mechanism)
        known_str = ", ".join(spec_known) if spec_known else "your door"
        return (
            f"Sure — I currently have: **{known_str}**. "
            "What would you like to change? For example: door type, size, glass, or RAL colour?"
        )

    # --- Confirmation intent ---
    if intent == "confirmation":
        missing = _what_is_missing(s)
        contact_missing = [m for m in missing if any(w in m for w in ("name", "email", "phone", "postcode"))]
        if contact_missing:
            next_contact = contact_missing[0]
            if "name" in next_contact:
                return "Great — what name should I put on the quote?"
            if "email" in next_contact:
                name_part = f"{s.name}, w" if s.name else "W"
                return f"{name_part}hat's the best email to send the quote to?"
            if "phone" in next_contact:
                return "What's the best number to reach you on?"
            return f"What's your postcode? It helps the team schedule your free site survey."
        if s.quote_reference:
            return (
                f"All noted{', ' + s.name if s.name else ''}. The team will be in touch within 1 business day "
                "to arrange your free site survey. Is there anything else you'd like to know?"
            )
        return "I'd love to get a quote together for you — what kind of door are you looking for?"

    # --- Proactive contact nudge ---
    if 40 <= s.readiness_score <= 65 and not s.email and s.door_type and not quote:
        name_part = f" {s.name}" if s.name else ""
        return (
            f"We're making good progress{name_part}. What's the best email to send the quote to? "
            "I'll have a copy ready for you as soon as we're done."
        )

    # --- Spec-related messages — ask for next missing field ---
    missing = _what_is_missing(s)
    if not missing:
        return (
            "I think I have everything I need. One moment while I put your quote together..."
        )

    next_field = missing[0]
    # Acknowledge what we already know, then ask the next question
    known = []
    if s.door_set:    known.append(s.door_set + " leaf")
    if s.door_type:   known.append(s.door_type.replace("_", " "))
    if s.mechanism:   known.append(s.mechanism)
    if s.width_mm:    known.append(f"{int(s.width_mm)}×{int(s.height_mm or 0)}mm")

    question_map = {
        "door type":        "What type of door are you after? We do **internal, external, fire-rated (FD30/FD60)**, or wine room doors.",
        "single or double": "Is that a **single** or **double** leaf door?",
        "mechanism":        "And how should it open — **hinged, sliding**, or **concertina** (bi-fold)?",
        "opening size":     "What size is the opening? Width × height in mm is ideal — a standard single is usually 900×2100.",
        "quantity":         "How many doors do you need?",
        "glazing":          "Any glass? We can do **clear, reeded, frosted**, or fully bespoke glazing — or none at all.",
        "your name":        "Just so I can personalise the quote — what's your name?",
        "your email":       "What's the best email to send the quote to?",
        "your phone":       "A contact number would help the survey team — what's best for you?",
        "your postcode":    "Almost there — what's your postcode? It helps us schedule the free site survey.",
    }

    question = next(
        (v for k, v in question_map.items() if k in next_field.lower()),
        f"Could you confirm {next_field}?"
    )

    if known:
        ack = "Got it — " + ", ".join(known) + ". "
        return ack + question
    return question


# ---------------------------------------------------------------------------
# LLM system prompt
# ---------------------------------------------------------------------------

def _build_system_prompt(s: ConversationSession, missing: list[str], rag_context: str = "") -> str:
    products = []
    for key, p in CATALOGUE.items():
        products.append(
            f"  {p['name']}: from £{p['base_price']:,.0f} | "
            f"baseline {p['baseline_w_mm']}×{p['baseline_h_mm']}mm | "
            f"lead time: {p['lead_time']}"
        )

    session_summary = []
    if s.name: session_summary.append(f"Customer name: {s.name}")
    if s.email: session_summary.append(f"Email: {s.email}")
    if s.phone: session_summary.append(f"Phone: {s.phone}")
    if s.postcode: session_summary.append(f"Postcode: {s.postcode}")
    if s.project_context: session_summary.append(f"Project type: {s.project_context}")
    if s.door_type: session_summary.append(f"Door type: {s.door_type}")
    if s.door_set: session_summary.append(f"Door set: {s.door_set}")
    if s.mechanism: session_summary.append(f"Mechanism: {s.mechanism}")
    if s.width_mm: session_summary.append(f"Size: {int(s.width_mm)}×{int(s.height_mm or 0)}mm")
    if s.quantity: session_summary.append(f"Quantity: {s.quantity}")
    if s.glass: session_summary.append(f"Glass: {s.glass}")
    if s.ral_colour: session_summary.append(f"Colour: {s.ral_colour}")

    missing_str = ", ".join(missing[:3]) if missing else "nothing — ready to confirm"

    name_address = f" {s.name.split()[0]}," if s.name else ","

    return (
        "You are the virtual customer service advisor for Steel Door Company — "
        "the UK's leading installer of bespoke steel doors and windows. "
        "You represent the Steel Door Company brand with the highest possible standard of customer care. "
        "Think of yourself as a senior, trusted member of the team: warm, knowledgeable, unhurried, and genuinely helpful.\n\n"

        "COMPANY:\n"
        "  Steel Door Company — Unit C, Scarlet Court, Stafford ST16 1YJ\n"
        "  Phone: 01785 526016 | Email: sales@steeldoorcompany.co.uk\n"
        "  Founded by Sam Hackett (manufacturing family since 1985) and Josh (digital agency Grow.Online).\n"
        "  Mission: do things properly — transparent pricing, no pressure, fast clear communication.\n\n"

        "YOUR CHARACTER:\n"
        "  - Warm, calm, and polished. Never rushed, never curt.\n"
        "  - Speak like a trusted expert adviser, not a salesperson.\n"
        "  - Address the customer by their first name once you know it (e.g. 'Of course" + name_address + " ...').\n"
        "  - Celebrate their choices genuinely ('That's a beautiful option', 'Great choice — the sliding mechanism gives a really clean look').\n"
        "  - Show empathy for the project ('A project like this is a real investment — we'll make sure we get it exactly right for you.').\n\n"

        "CUSTOMER SERVICE STANDARDS (non-negotiable):\n"
        "  - NEVER correct a customer, argue, or make them feel foolish — ever.\n"
        "  - NEVER use negative phrases: 'I can't', 'That's wrong', 'You need to', 'I don't know'.\n"
        "  - NEVER swear, use slang, or write anything that could embarrass the Steel Door Company brand.\n"
        "  - NEVER rush the customer — if they go off-topic, follow their lead briefly, then gently return.\n"
        "  - If someone is frustrated or impatient, acknowledge their feeling first before anything else.\n"
        "  - If someone is uncertain, reassure them — 'There's no pressure at all, we can take this at whatever pace suits you.'\n"
        "  - If someone uses a typo or informal phrasing, silently understand and respond naturally — never point it out.\n"
        "  - Always end a reply by either asking a single gentle question OR offering the next helpful step.\n"
        "  - Prefer positive framing: instead of 'I need your postcode', say 'Could I take your postcode so we can confirm availability in your area?'\n\n"

        "LANGUAGE TO USE:\n"
        "  Absolutely | Of course | Certainly | That's a lovely choice | I'd be delighted to help\n"
        "  Leave it with me | We'll take care of that | Rest assured | My pleasure\n"
        "  'Let me find that out for you' (when uncertain) | 'Great news — ...'\n\n"

        "LANGUAGE TO AVOID:\n"
        "  No problem | Obviously | Actually | But | You should | You need to | Unfortunately\n"
        "  I can't | I don't know | That's incorrect | As I said | Just (as a minimiser)\n\n"

        "PRODUCT RANGE:\n" + "\n".join(products) + "\n\n"
        "PRICING UPLIFTS:\n"
        "  Glass: clear £0 | reeded +£120 | frosted +£100 | bespoke +£300\n"
        "  Fire rating: FD30 +£350 | FD60 +£600\n"
        "  RAL colour: +£150 | Side panels: +£400 each\n"
        "  Mechanism: sliding +£1,750 | concertina +£2,250\n"
        "  Door type: external +£800 | fire_rated +£1,700 | wine room +£600\n"
        "  VAT: 20% on all prices shown\n\n"

        "KNOWN CUSTOMER INFO:\n" +
        ("\n".join(f"  {l}" for l in session_summary) if session_summary else "  Nothing collected yet") +
        "\n\nSTILL NEEDED (collect gently, one at a time): " + missing_str + "\n\n"

        + (("\n\n" + rag_context) if rag_context else "")
        + "\n\nOPERATIONAL RULES:\n"
        "1. NEVER invent or estimate prices. Only relay a [QUOTE FROM DETERMINISTIC ENGINE] block verbatim when one appears — never before.\n"
        "2. Collect ONE missing detail per message — weave the question naturally into your reply, never list them.\n"
        "3. NEVER show a progress counter — it sounds robotic and impersonal.\n"
        "4. If the customer says 'help' — warmly explain what you can assist with, don't immediately ask about door type.\n"
        "5. If a [QUOTE] block appears, present it clearly and offer to book a free survey as the natural next step.\n"
        "6. Keep replies to 2–4 sentences. Concise but warm — never curt, never a wall of text.\n"
        "7. Readiness score (internal only, never mention): " + str(s.readiness_score) + "/100.\n"
        "8. If TECHNICAL SPECIFICATIONS appear above, cite the source in your answer: 'According to [source], ...'."
    )


_PROVIDERS = {
    "groq": {
        "key_env": "GROQ_API_KEY",
        "base_url_env": "GROQ_BASE_URL",
        "default_base_url": "https://api.groq.com/openai/v1",
        "model_env": "GROQ_MODEL",
        "default_model": "llama-3.1-8b-instant",
    },
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "default_base_url": "https://api.deepseek.com",
        "model_env": "DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
    },
    "anthropic": {
        "key_env": "ANTHROPIC_API_KEY",
        "base_url_env": "ANTHROPIC_BASE_URL",
        "default_base_url": "https://api.anthropic.com/v1",
        "model_env": "ANTHROPIC_MODEL",
        "default_model": "claude-haiku-4-5-20251001",
    },
}


def _openai_compatible_reply(
    provider: str,
    system_prompt: str,
    history: list,
    user_content: str,
    session_id: str | None = None,
) -> str:
    import httpx

    cfg = _PROVIDERS[provider]
    api_key = os.environ[cfg["key_env"]]
    base_url = os.environ.get(cfg["base_url_env"], cfg["default_base_url"])
    model = os.environ.get(cfg["model_env"], cfg["default_model"])

    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    for msg in history[-10:]:
        messages.append({"role": msg.role, "content": msg.content})
    messages.append({"role": "user", "content": user_content})

    # Fallback model list — all free on Groq, ordered fastest→largest
    _GROQ_FALLBACK_MODELS = [
        model,
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
        "llama3-8b-8192",
    ]
    seen = set()
    fallback_models = [m for m in _GROQ_FALLBACK_MODELS if not (m in seen or seen.add(m))]

    last_exc: Exception = RuntimeError("no models tried")
    for attempt_model in fallback_models:
        t0 = time.monotonic()
        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": attempt_model, "messages": messages, "max_tokens": 400},
            timeout=30.0,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        if resp.status_code == 429:
            logger.warning("Groq 429 on %s, trying next model", attempt_model)
            save_llm_metric(session_id, provider, attempt_model, latency_ms, success=False)
            last_exc = Exception(f"429 on {attempt_model}")
            continue
        resp.raise_for_status()
        data = resp.json()
        usage = data.get("usage", {})
        save_llm_metric(
            session_id, provider, attempt_model, latency_ms,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            success=True,
        )
        return data["choices"][0]["message"]["content"]
    raise last_exc


def _format_quote(quote: QuoteResponse) -> str:
    lines = "\n".join(f"  - {ln.label}: £{ln.amount:,.2f}" for ln in quote.lines)
    sale = f"  Summer Sale discount: -£{quote.sale_discount:,.2f}\n" if quote.sale_discount else ""
    return (
        f"Quote ref {quote.reference}:\n{lines}\n"
        f"{sale}"
        f"  Unit price: £{quote.unit_price:,.2f} × {quote.quantity}\n"
        f"  Subtotal: £{quote.subtotal:,.2f}\n"
        f"  VAT (20%): £{quote.vat:,.2f}\n"
        f"  Total inc. VAT: £{quote.total:,.2f}\n"
        f"  Lead time: {quote.lead_time}"
    )


# ---------------------------------------------------------------------------
# Main handler
# ---------------------------------------------------------------------------

def _llm_extract_fields(provider: str, cfg: dict, text: str, s: ConversationSession) -> ConversationSession:
    """One JSON-mode LLM call to extract all spec + contact fields at once.

    Falls back silently on any error — the regex pass already ran, so this
    only fills in fields the regex missed. LLM never sets prices.
    """
    import httpx
    import json as _json

    api_key = os.environ.get(cfg["key_env"], "")
    if not api_key:
        return s

    schema_hint = (
        '{"door_set":"single|double|null","door_type":"internal|external|fire_rated|wine_room|null",'
        '"mechanism":"hinged|sliding|concertina|null","width_mm":"number|null","height_mm":"number|null",'
        '"glass":"clear|reeded|frosted|bespoke|null","ral_colour":"string|null",'
        '"fire_rating":"none|FD30|FD60","quantity":"number|null",'
        '"name":"string|null","email":"email string|null","phone":"string|null",'
        '"postcode":"UK postcode|null","project_context":"residential|commercial|null",'
        '"installation_required":"true|false|null","threshold":"flush|weathered|step_over"}'
    )
    system = (
        "Extract structured data from this customer message. "
        "Return ONLY valid JSON matching the schema below. "
        "Use null for any field not mentioned. Do NOT invent or guess values.\n"
        "Schema: " + schema_hint
    )

    base_url = os.environ.get(cfg["base_url_env"], cfg["default_base_url"])
    model = os.environ.get(cfg["model_env"], cfg["default_model"])

    try:
        resp = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": text},
                ],
                "max_tokens": 300,
                "response_format": {"type": "json_object"},
            },
            timeout=12.0,
        )
        resp.raise_for_status()
        extracted = _json.loads(resp.json()["choices"][0]["message"]["content"])
    except Exception:
        return s  # regex pass is sufficient; don't break the chat

    # Merge: only fill fields that regex left empty; never overwrite existing values
    _bool_map = {"true": True, "false": False, True: True, False: False}
    for field, raw in extracted.items():
        if raw is None or raw == "null":
            continue
        if not hasattr(s, field) or getattr(s, field) is not None:
            continue  # already set by regex or not a session field
        if field in ("width_mm", "height_mm", "quantity"):
            try:
                setattr(s, field, float(raw) if field != "quantity" else int(raw))
            except (TypeError, ValueError):
                pass
        elif field == "installation_required":
            val = _bool_map.get(raw)
            if val is not None:
                s.installation_required = val
        elif field == "threshold":
            if raw in ("flush", "weathered", "step_over"):
                s.threshold = raw
        else:
            setattr(s, field, str(raw).strip() or None)

    return s


def _normalise_text(text: str) -> str:
    """Light spell-normalisation: expand common abbreviations + fix obvious typos."""
    replacements = {
        r"\bfd\s*3\b": "fd30", r"\bfd\s*6\b": "fd60",
        r"\bdbl\b": "double", r"\bsgl\b": "single",
        r"\bsliding\s*door\b": "sliding door",
        r"\bconc\b": "concertina",
        r"\bext\b": "external", r"\bint\b": "internal",
        r"\bfr\b": "fire rated",
        r"\bhow\s+much\b": "how much",
        r"\bprice\s+for\b": "price for",
        r"\bqoute\b": "quote", r"\bquotr\b": "quote", r"\bquot\b": "quote",
        r"\bprcie\b": "price", r"\bpric\b": "price",
        r"\bcontact\s+info\b": "contact information",
        r"\bwhat'?s\s+the\s+number\b": "what is the phone number",
        r"\bdoors?\s+pls\b": "doors please",
        r"\bsingle\s+door\s+pls\b": "single door please",
        # internal/external typos
        r"\binteral\b": "internal", r"\bintrnal\b": "internal",
        r"\binternel\b": "internal",
        r"\bextenal\b": "external", r"\bexternl\b": "external",
        r"\bexterior\b": "external",
        # fire door typos — frie/feir/fery/firy/fry/fier/frie door
        r"\b(frie|feir|fery|firy|fier|fyre)\b": "fire",
        r"\bfr[iy]e?\s*door\b": "fire door",
        r"\bfier\s*rat": "fire rated", r"\bfireated\b": "fire rated",
        # double/single/hinge typos
        r"\bdoubl\b": "double", r"\bsingl\b": "single",
        r"\bhineg\b": "hinged", r"\bsldin\b": "sliding",
    }
    t = text.lower()
    for pat, rep in replacements.items():
        t = re.sub(pat, rep, t)
    return t


def handle_chat(req: ChatRequest) -> ChatResponse:
    # Load or create session
    s = None
    if req.session_id:
        s = load_session(req.session_id)
    if s is None:
        s = ConversationSession()

    # Normalise text (typos, abbreviations)
    normalised = _normalise_text(req.message)
    prev_quote_ref = s.quote_reference

    # Extract fields from this message — regex first, then LLM enrichment
    s = _extract_fields(normalised, s)
    provider = os.environ.get("LLM_PROVIDER", "mock").lower()
    cfg = _PROVIDERS.get(provider)
    if cfg and os.environ.get(cfg["key_env"]):
        s = _llm_extract_fields(provider, cfg, normalised, s)

    # Try to build a quote if enough spec is present
    quote: Optional[QuoteResponse] = None
    qr = _build_quote_request(s)
    if qr:
        try:
            quote = calculate_quote(qr)
            s.quote_reference = quote.reference
        except Exception:
            quote = None

    # Only flag as "new quote" if this is the first time we have one, or the spec changed
    new_quote = quote is not None and (prev_quote_ref is None or prev_quote_ref != quote.reference)

    # Update readiness + routing
    s.readiness_score = calculate_readiness(s)
    s.routing = determine_routing(s)

    # Advance stage based on completeness
    if s.readiness_score >= 30 and s.stage < 2:
        s.stage = 2
    if s.readiness_score >= 55 and s.stage < 3:
        s.stage = 3
    if s.readiness_score >= 75 and s.email and s.stage < 4:
        s.stage = 4

    # Generate internal brief when ready
    if s.readiness_score >= 60 and s.email and not s.internal_brief:
        s.internal_brief = build_internal_brief(
            s, quote_total=quote.total if quote else None
        )

    # Outbound CRM webhook + HubSpot push on first qualification (score 70 + email)
    if s.readiness_score >= 70 and s.email and not s.brief_email_sent:
        from .webhook import fire_webhook
        from .session import build_internal_brief_json
        from .hubspot import push_to_hubspot
        _qt = quote.total if quote else None
        fire_webhook(build_internal_brief_json(s, quote_total=_qt))
        hs_ok = push_to_hubspot(s, quote_total=_qt)
        if not hs_ok:
            token_set = bool(os.environ.get("HUBSPOT_ACCESS_TOKEN"))
            logger.warning(
                "[HUBSPOT SKIPPED/FAILED] session=%s score=%s token_set=%s",
                s.session_id, s.readiness_score, token_set,
            )

    # Email brief to sales team once score hits 70
    if s.readiness_score >= 70 and s.email and s.internal_brief and not s.brief_email_sent:
        from .email_sender import send_brief_email
        sent = send_brief_email(
            brief=s.internal_brief,
            session_id=s.session_id,
            readiness_score=s.readiness_score,
            customer_name=s.name,
            routing=s.routing,
        )
        if sent:
            s.brief_email_sent = True

    # EMAIL-002: send quote copy to customer on confirmation intent
    intent = _classify_intent(normalised.lower().strip())
    if (
        intent == "confirmation"
        and s.email
        and s.quote_reference
        and quote
        and not s.customer_email_sent
    ):
        from .email_sender import send_customer_quote_email
        sent = send_customer_quote_email(
            customer_email=s.email,
            customer_name=s.name,
            quote=quote,
        )
        if sent:
            s.customer_email_sent = True

    missing = _what_is_missing(s)
    s.needs = missing[:5]

    # Generate reply
    user_content = normalised
    if quote and new_quote:
        user_content += (
            "\n\n[QUOTE FROM DETERMINISTIC ENGINE — relay verbatim]\n"
            + _format_quote(quote)
        )

    if cfg and os.environ.get(cfg["key_env"]):
        try:
            rag_chunks = rag_retrieve(normalised)
            rag_ctx = format_rag_context(rag_chunks)
            system_prompt = _build_system_prompt(s, missing, rag_context=rag_ctx)
            reply = _openai_compatible_reply(provider, system_prompt, req.history, user_content, session_id=s.session_id)
        except Exception as exc:
            logger.warning("LLM call failed (%s), falling back to mock: %s", provider, exc)
            reply = _mock_reply(s, quote if new_quote else None, req.message, new_quote)
    else:
        logger.debug("No LLM key for provider=%s, using mock", provider)
        reply = _mock_reply(s, quote if new_quote else None, req.message, new_quote)

    # Persist session
    save_session(s)

    # Build session state for response
    session_state = SessionState(
        session_id=s.session_id,
        stage=s.stage,
        readiness_score=s.readiness_score,
        routing=s.routing,
        internal_brief=s.internal_brief if s.readiness_score >= 60 else None,
        has_name=bool(s.name),
        has_email=bool(s.email),
        has_phone=bool(s.phone),
        has_postcode=bool(s.postcode),
        has_door_spec=bool(s.door_set and s.door_type and s.mechanism),
        has_dimensions=bool(s.width_mm and s.height_mm),
        has_quantity=bool(s.quantity),
        has_glass=bool(s.glass),
        missing_fields=missing[:5],
    )

    return ChatResponse(reply=reply, quote=quote if new_quote else None, session=session_state)
