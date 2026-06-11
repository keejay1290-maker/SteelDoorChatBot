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

import os
import re
from typing import Optional

from .catalogue import CATALOGUE
from .models import ChatRequest, ChatResponse, QuoteRequest, QuoteResponse, SessionState
from .quoting import PRICING, calculate_quote
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
    name_patterns = [
        r"(?:my name is|i[' ]m|name[:\s]+|it[' ]?s for\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"(?:called|contact)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
    ]
    if not s.name:
        for pat in name_patterns:
            nm = re.search(pat, text, re.IGNORECASE)
            if nm:
                candidate = nm.group(1).strip()
                # Reject single common words that aren't names
                if candidate.lower() not in {"you", "us", "me", "the", "a", "an"}:
                    s.name = candidate
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

    # Budget — "£4,000-£6,000" / "around 5k" / "budget is £8,000" / "8000 budget"
    budget_m = re.search(r"£([\d,]+)(?:\s*[-–to]+\s*£?([\d,]+))?", text)
    if not budget_m:
        budget_m = re.search(r"(\d[\d,]+)k?\s*(?:[-–to]+\s*(\d[\d,]+)k?)?\s*(?:budget|spend|£)", t)
    if budget_m and not s.budget_min:
        def parse_amount(v: str) -> float:
            v = v.replace(",", "")
            amt = float(v)
            return amt * 1000 if amt < 100 else amt
        s.budget_min = parse_amount(budget_m.group(1))
        if budget_m.lastindex >= 2 and budget_m.group(2):
            s.budget_max = parse_amount(budget_m.group(2))

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

    if intent == "greeting":
        return (
            "Hi! I'm the Steel Door Company AI consultant. I can get you an instant estimate or "
            "answer any questions about our range.\n\n"
            "What are you looking for today — a quote, product info, or to book a survey?"
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
        cta = (
            "\n\nTo confirm this and book your free site survey, could you share "
            + f"**{contact_missing[0]}**?"
            if contact_missing else
            f"\n\nAll set! Readiness **{s.readiness_score}/100**. The team will be in touch. "
            "Call **01785 526016** for anything urgent."
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
            return f"Glad to hear it! To get things moving, could I take **{contact_missing[0]}**?"
        if s.quote_reference:
            return (
                f"Your enquiry (ref **{s.quote_reference}**) has been noted. "
                "The team will be in touch within 1 business day to schedule your free site survey."
            )
        return "Could you give me a bit more detail about the door you need so I can get a quote together?"

    # --- Spec-related messages — ask for next missing field ---
    missing = _what_is_missing(s)
    if not missing:
        return (
            f"I think I have everything — readiness **{s.readiness_score}/100**. "
            "One moment while I prepare your quote and internal brief..."
        )

    next_field = missing[0]
    # Build known-so-far string for context
    known = []
    if s.door_set:    known.append(s.door_set + " leaf")
    if s.door_type:   known.append(s.door_type.replace("_", " "))
    if s.mechanism:   known.append(s.mechanism)
    if s.width_mm:    known.append(f"{int(s.width_mm)}×{int(s.height_mm or 0)}mm")
    if s.name:        known.append(f"for {s.name}")
    known_ctx = " (" + ", ".join(known) + ")" if known else ""

    question_map = {
        "door type":        "What type of door are you looking for? Options: **internal, external, fire-rated (FD30/FD60), or wine room**.",
        "single or double": "Would you prefer a **single** or **double** leaf door?",
        "mechanism":        "What's your preferred opening mechanism — **hinged, sliding**, or **concertina** (folding)?",
        "opening size":     "What's the opening size? Width × height in mm works best (e.g. 900×2100 for a standard single).",
        "quantity":         "How many doors do you need in total?",
        "glazing":          "Any glazing preference? We offer **clear, reeded, frosted**, or bespoke glass.",
        "your name":        "Could I take your name to put on the quote?",
        "your email":       "What email address should I send the quote to?",
        "your phone":       "A phone number would help our survey team reach you — optional though.",
        "your postcode":    "Last one — what's your postcode? Helps us schedule the free site survey.",
    }

    question = next(
        (v for k, v in question_map.items() if k in next_field.lower()),
        f"Could you confirm {next_field}?"
    )

    progress_n = 10 - len(missing)
    progress = f"({progress_n}/10 details collected{known_ctx})"

    return f"{question} {progress}"


# ---------------------------------------------------------------------------
# LLM system prompt
# ---------------------------------------------------------------------------

def _build_system_prompt(s: ConversationSession, missing: list[str]) -> str:
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

    return (
        "You are a friendly, professional AI sales consultant for Steel Door Company — "
        "the UK's leading installer of bespoke steel doors. Unit C, Scarlet Court, Stafford ST16 1YJ. "
        "Phone: 01785 526016. Email: sales@steeldoorcompany.co.uk.\n\n"
        "MISSION: Replace phone enquiries entirely. Guide customers through a natural "
        "conversation to collect all project details, produce an accurate estimate, and "
        "route the lead to the correct internal team.\n\n"
        "PRODUCT RANGE:\n" + "\n".join(products) + "\n\n"
        "PRICING UPLIFTS:\n"
        "  Glass: clear £0 | reeded +£120 | frosted +£100 | bespoke +£300\n"
        "  Fire rating: FD30 +£350 | FD60 +£600\n"
        "  RAL colour: +£150\n"
        "  Side panels: +£400 each\n"
        "  Mechanism: sliding +£1,750 | concertina +£2,250\n"
        "  Door type: external +£800 | fire_rated +£1,700 | wine room +£600\n"
        "  VAT: 20% on all prices\n\n"
        "KNOWN CUSTOMER INFO:\n" +
        ("\n".join(f"  {l}" for l in session_summary) if session_summary else "  Nothing collected yet") +
        "\n\nSTILL NEEDED (ask for these in order): " + missing_str + "\n\n"
        "RULES:\n"
        "1. NEVER invent prices. Only relay the [QUOTE FROM DETERMINISTIC ENGINE] block verbatim when it appears.\n"
        "2. Ask for ONE missing piece of info at a time — don't list all missing fields.\n"
        "3. If message is 'help', 'what can you do', or similar — describe capabilities, do NOT ask about door type.\n"
        "4. If message asks for contact details / phone / address — give: 01785 526016 | sales@steeldoorcompany.co.uk | Unit C Scarlet Court Stafford ST16 1YJ.\n"
        "5. Recognise spelling mistakes: qoute=quote, fd3=FD30, dbl=double, ext=external, int=internal.\n"
        "6. Keep responses to 2-4 sentences. Be warm, professional, knowledgeable.\n"
        "7. Readiness: " + str(s.readiness_score) + "/100. If no [QUOTE] block in the message, don't mention or repeat a quote."
    )


_PROVIDERS = {
    "groq": {
        "key_env": "GROQ_API_KEY",
        "base_url_env": "GROQ_BASE_URL",
        "default_base_url": "https://api.groq.com/openai/v1",
        "model_env": "GROQ_MODEL",
        "default_model": "llama-3.3-70b-versatile",
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

    resp = httpx.post(
        f"{base_url}/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": model, "messages": messages, "max_tokens": 400},
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


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

    # Extract fields from this message
    s = _extract_fields(normalised, s)

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

    missing = _what_is_missing(s)
    s.needs = missing[:5]

    # Generate reply
    provider = os.environ.get("LLM_PROVIDER", "mock").lower()
    cfg = _PROVIDERS.get(provider)

    user_content = normalised
    if quote and new_quote:
        user_content += (
            "\n\n[QUOTE FROM DETERMINISTIC ENGINE — relay verbatim]\n"
            + _format_quote(quote)
        )

    if cfg and os.environ.get(cfg["key_env"]):
        try:
            system_prompt = _build_system_prompt(s, missing)
            reply = _openai_compatible_reply(provider, system_prompt, req.history, user_content)
        except Exception:
            reply = _mock_reply(s, quote if new_quote else None, req.message, new_quote)
    else:
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

    return ChatResponse(reply=reply, quote=quote, session=session_state)
