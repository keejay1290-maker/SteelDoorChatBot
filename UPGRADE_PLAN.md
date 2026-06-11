# SteelDoorAi — Audit Findings & Implementation Plan (for Sonnet)

> **Author:** Opus audit, S109 (2026-06-11)
> **Executor:** Sonnet
> **Repo:** https://github.com/keejay1290-maker/SteelDoorChatBot
> **Live:** https://steel-door-chat-bot.vercel.app
> **Baseline:** 41 tests passing. FastAPI + Pydantic v2 + SQLite + Vercel.

This document is the single source of truth for the next work session. Each task has:
a **rationale**, exact **files**, a **code sketch** where useful, and **acceptance criteria**.
Work top-to-bottom — phases are ordered by (interview value × low risk). Run `pytest -q`
after every task; never push with a failing suite. Commit per-task with the task ID in the
message. `git remote -v` is fine here (origin = SteelDoorChatBot); push to `master`, Vercel
auto-deploys.

---

## AUDIT SUMMARY — what's wrong / weak today

### 🔴 Confirmed bugs (fix first)

| ID | Bug | Evidence | Impact |
|----|-----|----------|--------|
| BUG-A | **Quote reference regenerates every chat turn.** `_quote_reference()` returns a fresh `uuid4` on every `calculate_quote()` call, and `handle_chat` calls it on every turn a spec exists. | `quoting.py:102-103`, `chat.py:608-617` | `new_quote` detection (`prev_quote_ref != quote.reference`) is **always True** → the bot re-displays the full quote card on every subsequent message (the "stuck" bug the S108 handover claimed was fixed is NOT fixed). |
| BUG-B | **Dashboard quote count is inflated.** Because each turn yields a new unique reference, `save_quote` (called every chat turn in `main.py:59-61`) inserts a **new row every turn**. | `store.py:93-118`, `main.py:56-61` | `quotes` count = number of chat turns, not distinct quotes. `avg_quote_value` and `recent_quotes` are skewed. Dashboard looks wrong in a demo. |
| BUG-C | **`.env` is never loaded.** No `python-dotenv`, no `--env-file` anywhere. | `grep` for dotenv = empty; `Makefile` runs bare `uvicorn`. | Locally the app **silently falls back to mock** even when `.env` has `LLM_PROVIDER=groq`. Only works on Vercel because env comes from `vercel.json`. Misleads anyone running it locally (incl. the interview if run on a laptop). |
| BUG-D | **Routing logic is a no-op.** `determine_routing` returns `"sales"` from nearly every branch; `installation` and `customer_care` are never returned. | `session.py:105-113` | The UI advertises 4-team routing but only ever shows sales/survey. Weak in a demo that highlights "auto-routing". |

### 🟡 Gaps / hardening

| ID | Gap | Files |
|----|-----|-------|
| GAP-E | No `GET /api/quote/{reference}` — quotes are persisted but unretrievable. | `main.py`, `store.py` (has `get_quote`, unused). |
| GAP-F | `/dashboard` is fully public and exposes customer PII (names, emails). No auth. | `main.py:106-108` |
| GAP-G | No rate limiting on `/api/chat` — a bot can burn Groq credits. | `main.py` |
| GAP-H | No CORS middleware — fine while same-origin, but blocks the future "embed widget on their site" goal stated by the owner. | `main.py` |
| GAP-I | `@app.on_event("startup")` is deprecated (warnings in test output). | `main.py:31-33` |
| GAP-J | `threshold` is a `QuoteRequest` field but is never extracted from NL in `_extract_fields` — dead intake field, always `"flush"`. | `chat.py`, `models.py` |
| GAP-K | Vercel SQLite at `/tmp` resets on cold start → dashboard frequently empty in the demo. | `vercel.json`, `api/index.py` |
| GAP-L | `vercel.json` uses the legacy `builds`/`routes` + deprecated `maxLambdaSize`. | `vercel.json` |
| GAP-M | No `tests/conftest.py` calling `init_db()` (TASKS BUG-003). Tests rely on a save-time table auto-create fallback. | `tests/` |
| GAP-N | `get_dashboard_stats` detects "has email" via fragile `LIKE '%"email": "%'` JSON string match. | `store.py:154-156` |
| GAP-O | `EnquiryRequest.email` is a plain `str`, not validated as an email. | `models.py:97` |
| GAP-P | `/api/enquiry` does not email anyone (EMAIL-001 only fires from the chat brief path, not the enquiry form). | `main.py:64-75` |

### 🟢 Feature upgrades (high demo value)

- PDF quote generation + download link (PDF-001).
- Quote email to customer (EMAIL-002).
- LLM structured extraction with regex fallback (AI-007).
- Demo-data seeding so the dashboard is never empty on a cold Vercel lambda.

---

## PHASE 0 — Correctness (do first, ~1–2 hrs)

### TASK 0.1 — Stable quote reference (fixes BUG-A + BUG-B)
**Why:** A quote for an unchanged spec must keep the same reference so (a) `new_quote`
detection works and the bot stops re-spamming the card, and (b) `save_quote`'s
`INSERT OR IGNORE` actually dedupes.

**How:** Derive the reference deterministically from the priced spec, not random UUID.

`quoting.py` — replace `_quote_reference()`:
```python
import hashlib

def _quote_reference(req: "QuoteRequest") -> str:
    """Deterministic ref: same spec → same reference (enables dedupe + new_quote detection)."""
    key = "|".join(str(x) for x in (
        req.door_set, req.door_type, req.mechanism,
        int(req.width_mm), int(req.height_mm), req.glass,
        req.ral_colour or "", req.fire_rating, req.side_panels,
        req.threshold, req.quantity,
    ))
    digest = hashlib.sha1(key.encode()).hexdigest()[:8].upper()
    return f"SDA-{digest}"
```
Update the call site in `calculate_quote` to pass `req`. Existing tests assert
`reference.startswith("SDA-")` — still true. Add a new test asserting **same spec → same ref,
different spec → different ref**.

**Acceptance:**
- New test `test_quote_reference_is_deterministic` passes.
- Manual: send the same door spec twice in one chat session; the quote card appears **once**,
  not on every follow-up turn.
- All 41 existing tests still green.

### TASK 0.2 — Load `.env` locally (fixes BUG-C)
**Why:** Running locally with a Groq key in `.env` should actually use Groq.

**How:** Add `python-dotenv` to `requirements.txt`. In `app/main.py`, before reading any env,
load it (no-op if file absent, safe on Vercel):
```python
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
```
Place this at the **top** of `main.py` (and `api/index.py` imports `app.main`, so it's covered).
Keep mock as the zero-config default — only load, don't force a provider.

**Acceptance:** With `LLM_PROVIDER=groq` + key in `.env`, `uvicorn app.main:app` uses Groq
locally (verify: a reply that isn't the canned mock text). With no `.env`, still boots on mock.

### TASK 0.3 — Real routing logic (fixes BUG-D)
**Why:** The "auto-routing to 4 teams" is a headline demo feature; make it actually branch.

`session.py` — rewrite `determine_routing`:
```python
def determine_routing(s: ConversationSession) -> str:
    # Supply-only, fully specced → sales closes it
    if s.installation_required is False and s.readiness_score >= 60:
        return "sales"
    # Full spec + contact + install wanted → book a site survey
    if s.readiness_score >= 70 and s.email and s.installation_required is not False:
        return "survey"
    # Has an existing quote ref and is asking follow-ups → customer care
    if s.quote_reference and s.stage >= 4:
        return "customer_care"
    # Commercial / large jobs → installation team scoping
    if s.project_context == "commercial" or (s.quantity or 0) >= 5:
        return "installation"
    return "sales"
```
Add `routing-customer_care` CSS class + colour in `index.html` and `dashboard.html`
(reuse an existing palette var, e.g. a muted purple).

**Acceptance:** New tests in `tests/test_session.py` (create it) assert each branch:
supply-only→sales, full+email→survey, commercial→installation, post-quote follow-up→customer_care.

---

## PHASE 1 — Demo robustness (interview-critical, ~2 hrs)

### TASK 1.1 — Quote lookup endpoint (GAP-E)
`main.py`:
```python
from .store import get_quote

@app.get("/api/quote/{reference}")
def api_get_quote(reference: str) -> dict:
    q = get_quote(reference)
    if not q:
        raise HTTPException(status_code=404, detail="Quote not found")
    return q
```
**Acceptance:** `test_api.py::test_quote_lookup` — POST a quote, GET it back by reference, 200;
unknown ref → 404.

### TASK 1.2 — Dashboard basic auth (GAP-F)
**Why:** Don't expose customer PII publicly; shows security awareness in interview.

Use `fastapi.security.HTTPBasic`. Env `DASHBOARD_USER` / `DASHBOARD_PASS` (default
`admin`/`steeldoor` for demo — document in `.env.example`). Protect `/dashboard`,
`/api/dashboard/stats`, `/api/dashboard/sessions`, and the new quote lookup if it returns PII.
Use `secrets.compare_digest`. Keep the customer-facing `/`, `/api/chat`, `/api/quote`,
`/api/catalogue` open.

**Acceptance:** `/dashboard` returns 401 without creds, 200 with. Customer chat flow unaffected.
Tests use `client.get("/dashboard", auth=("admin","steeldoor"))`.

### TASK 1.3 — Demo-data seeding (GAP-K)
**Why:** On a cold Vercel lambda the dashboard is empty and looks broken mid-interview.

Add `app/seed.py` with `seed_demo_data()` that, **only if `sessions`/`quotes` are empty**,
inserts ~6 realistic sessions (varied routing, readiness 35–95) and ~5 quotes across products.
Call it from startup **only when** `SEED_DEMO=1` (set in `vercel.json` env). Never seed when real
data exists.

**Acceptance:** Fresh DB + `SEED_DEMO=1` → dashboard shows populated KPIs/charts. Existing data →
no duplication. A test asserts idempotency.

### TASK 1.4 — `conftest.py` (GAP-M / BUG-003)
`tests/conftest.py`:
```python
import pytest
from app.store import init_db

@pytest.fixture(autouse=True, scope="session")
def _init_db():
    init_db()
```
**Acceptance:** Remove the save-time auto-create fallback reliance is optional; tests pass with
the fixture present.

---

## PHASE 2 — Hardening (production-credibility, ~2–3 hrs)

### TASK 2.1 — Rate limiting (GAP-G)
Add `slowapi`. Limit `/api/chat` to e.g. `20/minute` per IP and `/api/quote` to `30/minute`.
Wire the limiter + exception handler in `main.py`. Document the limits in `INTERVIEW_NOTES.md`.
**Acceptance:** 21st chat call within a minute → 429. Test with a loop.

### TASK 2.2 — CORS allowlist (GAP-H)
Add `CORSMiddleware` with an env-driven allowlist (`ALLOWED_ORIGINS`, comma-separated; default
the Vercel URL + `http://localhost:8000`). Enables the owner's stated goal of embedding the
widget on steeldoorcompany.co.uk later.
**Acceptance:** Preflight `OPTIONS /api/chat` from an allowed origin returns the
`Access-Control-Allow-Origin` header.

### TASK 2.3 — FastAPI lifespan (GAP-I)
Replace `@app.on_event("startup")` with the `lifespan=` context-manager pattern. Removes the
deprecation warnings.
**Acceptance:** No `on_event` deprecation warnings in `pytest` output.

### TASK 2.4 — Modernise `vercel.json` (GAP-L)
Migrate from `version: 2` `builds`/`routes` to `functions` + `rewrites`. Drop `maxLambdaSize`
(or move to `functions.*.maxDuration`/size as supported). Verify the deploy still serves
`/static/*` and routes everything else to the function.
**Acceptance:** Vercel deploy succeeds; `/`, `/static/...`, `/dashboard`, `/api/*` all work in
prod. **Test the live URL after deploy.**

### TASK 2.5 — Email validation + enquiry email (GAP-O / GAP-P)
- Add `email-validator`; change `EnquiryRequest.email` to `pydantic.EmailStr`.
- In `api_enquiry`, after `save_enquiry`, call `send_brief_email`-style notification (reuse
  `email_sender.py`; add a `send_enquiry_email(enquiry, reference)` helper). No-op when SMTP
  unconfigured, exactly like EMAIL-001.
**Acceptance:** Invalid email → 422. Valid enquiry with SMTP env set → email attempted (mocked
in tests).

### TASK 2.6 — Drop or wire `threshold` (GAP-J)
Either (a) add threshold extraction to `_extract_fields` ("flush/weathered/step-over" keywords)
**or** (b) remove the field from `QuoteRequest`/`PRICING` if out of scope. Recommend (a) —
cheap, and external doors realistically need a weathered threshold (+£80).
**Acceptance:** "external door with a weathered threshold" → quote includes the threshold line.

---

## PHASE 3 — Feature upgrades (high demo value, pick by time available)

### TASK 3.1 — PDF quote generation (PDF-001) 🌟 best demo win
Use **`reportlab`** (pure-Python, no system libs — WeasyPrint needs native deps that fight
Vercel). New `app/pdf.py` → `build_quote_pdf(quote) -> bytes`. Route
`GET /api/quote/{reference}/pdf` returns `application/pdf`. Add a "Download PDF" button to the
quote card in `index.html`. A4, SDC gold/black branding, itemised lines, VAT, lead time,
"indicative estimate — confirmed after survey" disclaimer.
**Acceptance:** `test_pdf` asserts the endpoint returns PDF bytes (`%PDF` magic) for a known ref.

### TASK 3.2 — LLM structured extraction with regex fallback (AI-007)
When a real provider is active, send one function-call/JSON-mode request to extract all
`QuoteRequest`/contact fields, validate via Pydantic, merge into the session. Keep `_extract_fields`
(regex) as the fallback for mock/failure. Guard so mock path and all existing tests are unchanged.
**Acceptance:** New test mocks an LLM JSON response and asserts fields merge; mock-provider tests
unchanged.

### TASK 3.3 — Customer quote email (EMAIL-002)
On `confirmation` intent + email present, email the customer a branded summary (attach the 3.1
PDF if built). Reuse `email_sender.py`.
**Acceptance:** Mocked-SMTP test asserts a customer-addressed message is sent once.

---

## Cross-cutting requirements for Sonnet

1. **Tests:** every task ships with tests. Target: keep the suite green and growing (41 → ~60+).
   Create `tests/test_session.py`, `tests/test_pdf.py` as needed.
2. **Zero-config rule:** the mock provider must always work with no env vars; never make a real
   key mandatory. SMTP/Groq/PDF deps must degrade gracefully.
3. **Deterministic pricing rule (sacred):** the LLM must never produce a number. All pricing
   stays in `quoting.py`. TASK 3.2 extracts *spec*, not prices.
4. **Deps:** add to `requirements.txt` as introduced — `python-dotenv`, `slowapi`,
   `email-validator`, `reportlab`. Keep versions pinned.
5. **Docs:** update `TASKS.md` (tick items, add session note), `.env.example` (every new var),
   `INTERVIEW_NOTES.md` (rate limiting, auth, routing as talking points), and create a completion
   doc `.claude/completions/YYYY-MM-DD-sXXX-upgrade.md`.
6. **Deploy check:** after pushing, **load the live Vercel URL** and click through: open chat
   bubble → get a quote → verify it shows once → open Brief → open /dashboard (auth). Don't trust
   "build succeeded" alone.
7. **Commit cadence:** one commit per task, message `feat/fix: <TASK-ID> <summary>`. Co-author
   trailer: `Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>`.

## Suggested sequencing (if time-boxed)
- **Must (interview):** 0.1, 0.2, 0.3, 1.2, 1.3 — correctness + a dashboard that looks right + no PII leak.
- **Should:** 1.1, 1.4, 2.3, 2.4, 3.1 (PDF is the standout demo feature).
- **Nice:** 2.1, 2.2, 2.5, 2.6, 3.2, 3.3.
```
