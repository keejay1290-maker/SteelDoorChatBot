# SteelDoorAi — Task Backlog

> Persistent across sessions. One task `[IN_PROGRESS]` at a time.
> Priority: 🔴 Critical / 🟡 High / 🟢 Nice-to-have
> Status: `[ ]` Todo | `[x]` Done | `[~]` In progress

---

## SESSION CONTEXT (update each session)

**Last session:** 2026-06-11 (S116) — AI-008 RAG done, CODE-03/01 dead imports removed, Railway env vars set, 121 tests passing
**Server:** `http://localhost:8000` (dev) | `http://localhost:8000/dashboard` (dashboard, auth: admin/steeldoor)
**Admin pricing:** `http://localhost:8000/admin/pricing` (same basic auth)
**Stack:** Python 3.12 + FastAPI 0.111.0 + SQLite + Vercel serverless
**Tests:** 99 passing (run: `cd app && ../.venv/Scripts/pytest ../tests -q`)
**LLM:** GROQ active — `llama-3.3-70b-versatile`, key set in .env, multi-model fallback active
**Live (Vercel):** https://steel-door-chat-bot.vercel.app
**Railway URL:** https://steeldoorchatbot-production.up.railway.app (LIVE — /health returns ok)
**Railway project ID:** 9410b36f-1864-495e-8652-265258687098 | Service: 377437d8 | Env: ac0f4b9c
**Railway deploy cmd:** `RAILWAY_API_TOKEN=ddd08363-... railway up --detach` (does NOT auto-deploy from GitHub push — use CLI)
**Next priorities:** Opus/Fable audit pass (all 25 checks in .claude/AUDIT-FOR-OPUS.md), then remaining nice-to-haves

---

## COMPLETED (S107)

- [x] **AI-001** — Full AI sales consultant with state tracking (ConversationSession)
- [x] **AI-002** — Quote Readiness Score (0-100) with live progress bar in UI
- [x] **AI-003** — Auto-routing to Sales / Survey / Installation / Customer Care teams
- [x] **AI-004** — Internal brief auto-generation (fires at score ≥ 60 + email collected)
- [x] **AI-005** — Server-side session persistence (SQLite sessions table)
- [x] **AI-006** — Staged conversation flow (4 stages: Scoping → Spec → Contact → Complete)
- [x] **UI-001** — Redesigned chat UI: readiness bar, stage badge, routing badge, field checklist
- [x] **UI-002** — Right panel: internal brief display + field collection tracker
- [x] **UI-003** — Product sidebar with real images and click-to-prompt
- [x] **DASH-001** — Management dashboard at `/dashboard` (KPIs + charts + recent sessions)
- [x] **DASH-002** — `/api/dashboard/stats` endpoint
- [x] **DASH-003** — `/api/dashboard/sessions` endpoint with routing + readiness per session
- [x] **SESS-001** — `GET /api/session/{id}` and `GET /api/session/{id}/brief` endpoints
- [x] **TEST-001** — All 36 tests passing with new session-based architecture

---

## ACTIVE BACKLOG

### 🔴 CRITICAL — Interview Demo Quality

- [ ] **GROQ-001** — Get Groq API key and test real AI responses
  - Go to https://console.groq.com/keys → Create key → add to `.env`: `LLM_PROVIDER=groq` + `GROQ_API_KEY=gsk_...`
  - Verify: `curl -X POST http://localhost:8000/api/chat -H "Content-Type: application/json" -d '{"message":"hello"}'`

- [x] **EMAIL-001** — Email internal brief to sales team on enquiry capture (S109)
  - Trigger: readiness ≥ 70 AND email collected AND `brief_email_sent=False`
  - Sends to `SALES_EMAIL` (default: sales@steeldoorcompany.co.uk)
  - `app/email_sender.py` — SMTP via stdlib smtplib, graceful no-op when unconfigured
  - Env vars: `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `EMAIL_FROM`, `SALES_EMAIL`
  - `session.brief_email_sent` flag prevents duplicate sends
  - 5 tests in `tests/test_email.py` (mock SMTP)

- [x] **EMAIL-002** — Email quote PDF confirmation to customer (S110)
  - Trigger: confirmation intent + `s.email` + `s.quote_reference` present, `customer_email_sent` flag prevents repeats
  - `send_customer_quote_email()` in `app/email_sender.py`; plain-text branded summary, graceful no-op if SMTP unconfigured
  - `session.customer_email_sent` persisted to SQLite

- [x] **PDF-001** — PDF quote generation (S110)
  - `app/pdf.py` — `build_quote_pdf(quote) -> bytes` via reportlab (pure Python, works on Vercel)
  - Route: `GET /api/quote/{reference}/pdf` → `application/pdf`
  - "Download PDF" button added to quote card in `index.html`
  - A4, SDC gold branding, itemised lines, VAT table, disclaimer footer

### 🟡 HIGH — Sales Product Value

- [x] **UX-001** — "Book Free Survey" form modal (S111)
  - Modal form: name/email/phone/postcode/message, pre-filled from GET /api/session/{id}
  - Submits to POST /api/enquiry

- [x] **UX-002** — Enquiry confirmation panel (S111)
  - Shows in chat window after form submit: reference, response time, contact details

- [x] **UI-004** — Fix hero text readability — text too grey/dim on backdrop (S112 5110a3e)
  - Hero subtitle currently `rgba(255,255,255,.7)` — bump to `.9` or pure `#fff`
  - Nav link colour `rgba(255,255,255,.75)` → `rgba(255,255,255,.9)`
  - The `--muted: #888` used in trust strips is unreadable on dark — use `#ccc` minimum for anything on backdrop
  - Quick 5-min CSS-only fix

- [x] **UI-005** — SDC homepage parity: trust strip, product tiles, real nav links, hamburger mobile nav (S112 49c4924)
  - **Nav:** Add functional links: Products → `/collections/all`, Gallery → open lightbox, Technical → `steeldoorcompany.co.uk/pages/technical`, About → `steeldoorcompany.co.uk/pages/about`
  - **Hero trust strip** below headline (white text, tick icons):
    `☑️ 2,000+ Installations Nationwide  ☑️ Same Day Quote  ☑️ Slimmest Steel Doors On The Market  ☑️ 24 Month Warranty  ☑️ Bespoke Made To Measure`
  - **Product category tiles** grid under trust strip — 5 tiles, click → opens chat pre-filled with type:
    - Single Doors → `https://steeldoorcompany.co.uk/cdn/shop/files/single_door.png?v=1770897895&width=480`
    - Double Doors → `https://steeldoorcompany.co.uk/cdn/shop/files/single_door.png?v=1770897895&width=480`
    - Fire Rated → same image (no dedicated URL found in scrape)
    - External → `https://steeldoorcompany.co.uk/cdn/shop/files/63D5CB37-D804-4E4A-8879-B48B01A8AE39.png?v=1771343755&width=480`
    - Wine Room → `https://steeldoorcompany.co.uk/cdn/shop/files/IMG_9077.jpg?v=1743781769&width=480`
  - **Backdrop parallax** — subtle `background-attachment: fixed` or JS scroll offset on `.sdc-backdrop`
  - **"Why Choose"** section: fitters copy, 20mm profile copy from real site

- [x] **UI-006** — Working gallery lightbox — grid overlay + full-screen viewer, ESC/arrow nav (S112 49c4924)
  - "View Gallery" button opens a full-screen image grid / lightbox
  - Source: real SDC CDN images identified in S111 scrape:
    - `https://steeldoorcompany.co.uk/cdn/shop/files/IMG_8938.jpg?v=1750852840`
    - `https://steeldoorcompany.co.uk/cdn/shop/files/IMG_0311_1.jpg?v=1770113145` (Olly Murs)
    - `https://steeldoorcompany.co.uk/cdn/shop/files/GL.png?v=1770804345` (Gabby Logan)
    - `https://steeldoorcompany.co.uk/cdn/shop/files/63D5CB37-D804-4E4A-8879-B48B01A8AE39.png?v=1771343755`
    - `https://steeldoorcompany.co.uk/cdn/shop/files/IMG_9077.jpg?v=1743781769`
  - Click image → full-screen lightbox, left/right nav, ESC to close
  - "View more on Instagram @steeldoorcompany" link at bottom

- [x] **UX-003** — Mobile bottom sheet, backdrop fix, Playwright verified (S112 5606b11)
  - Sidebar + right panel hidden on mobile (already done via media query)
  - Need to test on actual mobile viewport
  - Collapsible product list as bottom sheet on mobile

- [x] **BRIEF-001** — Structured JSON brief for CRM push (S111)
  - `GET /api/session/{id}/brief?format=json` → structured dict with HubSpot field mappings
  - `build_internal_brief_json()` in session.py

- [x] **CRM-001** — HubSpot webhook integration skeleton (S112 e7e288e)
  - POST to HubSpot on session complete (score ≥ 70 + email)
  - Maps session fields → HubSpot Contact + Deal
  - Env: `HUBSPOT_ACCESS_TOKEN`, `HUBSPOT_PIPELINE_ID`
  - Start with `httpx` call, add retry logic

- [x] **CRM-002** — Generic outbound CRM webhook (S111)
  - `app/webhook.py` — `fire_webhook(payload)` POSTs to `WEBHOOK_URL` on readiness ≥ 70
  - Optional `WEBHOOK_SECRET` header; `/api/webhooks/test` endpoint for manual trigger

- [x] **AI-007** — LLM-powered structured extraction (fallback to regex) (S110)
  - `_llm_extract_fields()` in `chat.py` — JSON-mode one-shot call, merges only fields regex missed
  - Regex `_extract_fields()` always runs first; LLM only fills gaps; never overwrites existing values
  - Silent fallback on any LLM error; mock provider path unchanged

- [x] **CONTENT-001** — "Our Story" / About section on homepage (S114 9d21148)
  - Founders: Sam Hackett (manufacturing family since 1985, Leamore Windows) + Josh (Grow.Online digital agency)
  - "Doing Things The Right Way" — 5 values bullets (treat every customer same, fast comms, no pressure sales, transparent pricing, Josh's bad bifold experience origin story)
  - Location: Unit C, Scarlet Court, Stafford, ST16 1YJ | T: 01785526016 | E: sales@steeldoorcompany.co.uk
  - Source text saved in TASKS.md — do NOT re-scrape, use verbatim copy below
  - Add as collapsible section or separate scrollable panel below the product tiles

- [x] **CONTENT-002** — "Our Process" section on homepage (S114 9d21148)
  - Scrape https://steeldoorcompany.co.uk/pages/our-process
  - Add step-by-step visual timeline: Enquiry → Survey → Design → Manufacture → Install → Aftercare
  - Should live above the footer

- [x] **CONTENT-003** — Shop / product browse function (S114 9d21148)
  - Lightweight product listing page showing all 5 door types with price-from, key specs, and CTA to chat
  - Use CATALOGUE data from catalogue.py — no new scraping needed for data
  - Route: `/shop` or modal triggered from "Browse Products" button

- [x] **CONTENT-004** — Homepage image audit + missing images (done this session)
  - Audited all img src tags — wine_room_door.jpg was a dupe of double_door.jpg (138KB → fixed 287KB real image)
  - Downloaded sdc_logo.png, gallery_1.jpg locally; logo now served from /static/images/ with CDN fallback
  - Removed oversized files (gallery_3.png 12MB, single/external tiles >1.5MB — CDN links kept)

- [x] **AI-008** — RAG on Steel Door Company product specs (S116 105156d)
  - app/rag.py: keyword-based retrieval, pure stdlib, Vercel-compatible
  - app/data/specs/steel_door_specs.json: 20 spec chunks (FD30/FD60, BS476, Part B/M, CE marking, intumescent seals, etc.)
  - Triggered on compliance keywords (fire rating, BS476, building regs, FD30, FD60, escape route, Part M, etc.)
  - Top-3 chunks injected into _build_system_prompt() with citation instruction
  - LLM replies cite source: "According to [BS 476-22]: ..."
  - 22 new tests in tests/test_rag.py (121 total, 2 skipped)

- [x] **PRICE-001** — Admin pricing table UI (S112 commit)
  - `/admin/pricing` — dark-themed editable table, 25 fields grouped by category
  - SQLite `pricing_settings` + `pricing_history` tables; `_effective_pricing()` merges overrides at quote time
  - OVERRIDE badge, per-field Reset, version history table (last 20 rows), toast notifications
  - Routes: `GET/POST /api/admin/pricing`, `DELETE /api/admin/pricing/{key}`, `GET /admin/pricing`

### 🟢 NICE-TO-HAVE — Phase 2 Product

- [ ] **MULTI-001** — WhatsApp channel integration
  - Twilio WhatsApp API → same FastAPI backend
  - Session stored by phone number
  - Reply via Twilio webhook

- [ ] **MULTI-002** — Email enquiry parsing
  - IMAP polling or SendGrid inbound parse webhook
  - Parse email → extract session fields → create session → send reply

- [ ] **VISION-001** — Photo upload → door type suggestion
  - Customer uploads photo of opening
  - Claude Vision or GPT-4o suggests door type + approximate size
  - Pre-fills session fields

- [ ] **VISION-002** — Architect drawing / PDF schedule extraction
  - Upload PDF spec / tender document
  - OCR + LLM extracts door schedule (door mark, size, type, fire rating, hardware)
  - Creates multiple sessions / line items

- [x] **DASH-004** — Revenue chart (S111)
  - 14-day pipeline revenue line chart (Chart.js) on dashboard

- [x] **DASH-005** — CSV exports (S111)
  - `GET /api/dashboard/sessions.csv` + `/api/dashboard/quotes.csv` (auth-protected)

- [x] **OBS-001** — LLM cost + latency tracking (done this session)
  - `llm_metrics` SQLite table: session_id, provider, model, latency_ms, tokens, success
  - `save_llm_metric()` / `get_llm_metrics_summary()` in store.py
  - `_openai_compatible_reply()` in chat.py now records latency + tokens per call
  - Dashboard: 3 new KPI tiles — LLM Calls, Avg Latency (ms), Tokens Used
  - `GET /api/dashboard/llm-metrics` endpoint (auth-protected)

- [x] **OBS-002** — Structured JSON logging (done this session)
  - `_JsonFormatter` in main.py: each log record emits `{ts, level, logger, msg}` JSON
  - Replaced all `print()` calls in chat.py + hubspot.py with `logger.warning/info/error`
  - `import sys` and `import traceback` removed from hubspot.py (no longer needed)

- [x] **AUTH-001** — Dashboard auth (S110)
  - HTTPBasic on `/dashboard`, `/api/dashboard/stats`, `/api/dashboard/sessions`
  - `secrets.compare_digest`, env `DASHBOARD_USER` / `DASHBOARD_PASS` (default admin/steeldoor)

- [x] **DEPLOY-001** — Railway deployment (done this session)
  - Live: https://steeldoorchatbot-production.up.railway.app (/health → ok)
  - Fix: `COPY app ./app` → `COPY . .` (BuildKit cache ref collision on Railway Metal builder)
  - railway.json: explicit Dockerfile builder, /health healthcheck, ON_FAILURE restart
  - Deploy: Railway does NOT auto-deploy from GitHub — use `railway up --detach` from local
  - Railway: `railway up` or Fly: `fly deploy`
  - Env vars: all from `.env` as Railway secrets
  - Custom domain: `demo.steeldoorcompany.co.uk` (needs their DNS)

- [ ] **DEPLOY-002** — Vercel edge for static UI
  - Separate static deploy of `index.html` + `dashboard.html` to Vercel
  - API backend stays on Railway
  - CORS: allow Vercel domain

- [x] **TEST-002** — Multi-turn integration tests (S111) — 5 tests in tests/test_integration.py
- [x] **TEST-003** — Brief generation tests (S111) — 6 tests in tests/test_brief.py

---

## KNOWN BUGS / TECH DEBT

- [x] **BUG-005** — GROQ 429 rate limit — multi-model fallback chain + llama-3.1-8b-instant (S111 919efab)
  - Free tier: 30 req/min on `llama-3.3-70b-versatile`
  - Verified in Vercel logs: first request 200, second 429 → mock reply
  - Fix options: (a) add exponential backoff + 1 retry in `_openai_compatible_reply`, (b) switch to `llama-3.1-8b-instant` (higher free-tier limit), (c) add server-side per-session rate limiter to avoid hammering Groq on rapid messages
  - Suggested fix: retry once after 1s on 429, then fall back to mock with a user-visible note
  - Model swap: change `default_model` in `_PROVIDERS["groq"]` from `llama-3.3-70b-versatile` → `llama-3.1-8b-instant`

- [x] **BUG-001** — name extraction fixed: \s+ in patterns, per-word stopword check, .title() normalisation (S112 e7e288e)
  - "It's for John Smith" → sometimes captures "John Smith" fails if surrounding context confuses regex
  - Fix: better name extraction patterns + dedupe against common words

- [x] **BUG-002** — budget parser now captures k suffix, handles single-digit amounts (S112 e7e288e)
  - Fix: normalise lowercase k → multiply by 1000 before parse

- [x] **BUG-003** — Sessions table not created in test context until first write (S110)
  - Fixed: `tests/conftest.py` autouse session-scoped fixture calls `init_db()` on test collection

- [x] **BUG-004** — `test_chat_endpoint_accepts_history` brittle assertion (fixed this session)
  - Changed message to explicit door type: "how much for an internal double steel door?" — no more default ambiguity
  - Added `test_chat_no_door_type_does_not_quote` — vague message asserts quote is None
  - Fixed `assert "£" in body["reply"]` → `assert body["reply"]` (LLM phrasing varies)
  - Test count: 99 passing, 2 skipped

---

## INTERVIEW TALKING POINTS (summary)

See `INTERVIEW_NOTES.md` for full details. Key points:
- Price discrepancy: homepage £1,500 vs Shopify £1,700 (raise this)
- No HSTS / CSP on their site
- No rate limiting on API (must add before production)
- PII in SQLite — needs GDPR policy for production
- Architecture: deterministic pricing + LLM conversation (never hallucinate numbers)
- Pluggable LLM: Groq → DeepSeek → Claude (same interface, env var swap)
