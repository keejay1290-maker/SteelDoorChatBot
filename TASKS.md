# SteelDoorAi — Task Backlog

> Persistent across sessions. One task `[IN_PROGRESS]` at a time.
> Priority: 🔴 Critical / 🟡 High / 🟢 Nice-to-have
> Status: `[ ]` Todo | `[x]` Done | `[~]` In progress

---

## SESSION CONTEXT (update each session)

**Last session:** S109 (2026-06-11)
**Server:** `http://localhost:8000` (dev) | `http://localhost:8000/dashboard` (dashboard)
**Stack:** Python 3.12 + FastAPI 0.4.0 + SQLite + Playwright
**Tests:** 36/36 passing
**LLM:** Set `LLM_PROVIDER=groq` + `GROQ_API_KEY=gsk_...` in `.env` for real AI

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

- [ ] **EMAIL-002** — Email quote PDF confirmation to customer
  - Trigger: when quote is generated AND customer email is collected
  - Content: branded HTML email with quote card + lead time + Steel Door Company contact
  - Priority: lower than EMAIL-001

- [ ] **PDF-001** — PDF quote generation
  - Library: `weasyprint` (HTML→PDF) or `reportlab`
  - Route: `GET /api/quote/{reference}/pdf`
  - Content: A4 branded quote with SDC logo, itemised lines, T&Cs, signature area
  - Download link shown in quote card UI

### 🟡 HIGH — Sales Product Value

- [ ] **UX-001** — "Book Free Survey" form modal
  - When customer clicks "Book Free Survey" in quote card
  - Form: name, email, phone, postcode, preferred date (date picker), notes
  - Submit → save as enquiry + send EMAIL-001
  - Currently just pre-fills the chat input — needs proper form

- [ ] **UX-002** — Enquiry confirmation page / modal
  - After enquiry captured: show reference number, expected response time, contact details
  - Currently just a chat message

- [ ] **UX-003** — Mobile-responsive layout
  - Sidebar + right panel hidden on mobile (already done via media query)
  - Need to test on actual mobile viewport
  - Collapsible product list as bottom sheet on mobile

- [ ] **BRIEF-001** — Structured JSON brief for CRM push
  - Route: `GET /api/session/{id}/brief?format=json`
  - Returns structured JSON matching HubSpot / Salesforce field names
  - Include: contact, deal stage, line items, custom fields

- [ ] **CRM-001** — HubSpot webhook integration skeleton
  - POST to HubSpot on session complete (score ≥ 70 + email)
  - Maps session fields → HubSpot Contact + Deal
  - Env: `HUBSPOT_ACCESS_TOKEN`, `HUBSPOT_PIPELINE_ID`
  - Start with `httpx` call, add retry logic

- [ ] **CRM-002** — Webhook endpoint for any CRM
  - `POST /api/webhooks/crm` — generic outbound push when session completes
  - Payload: JSON brief + quote ref + routing
  - Configurable `WEBHOOK_URL` in env

- [ ] **AI-007** — LLM-powered structured extraction (fallback to regex)
  - Use function calling / tool use to extract all session fields in one LLM call
  - Returns validated JSON, merged into session
  - Regex remains as fallback when LLM is mock or call fails
  - Provider: Groq function-calling, DeepSeek JSON mode, Claude tool-use

- [ ] **AI-008** — RAG on Steel Door Company product specs
  - Embed: fire rating certificates, building regs docs, technical spec PDFs
  - Store: ChromaDB or SQLite-vss
  - Use: answer compliance questions ("does this meet BS476 for escape routes?")
  - Cited sources in reply

- [ ] **PRICE-001** — Admin pricing table UI
  - Editable pricing at `/admin/pricing` (basic auth protected)
  - Updates PRICING dict in quoting.py OR stores in SQLite
  - Version history (who changed what, when)

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

- [ ] **DASH-004** — Revenue forecast chart
  - Dashboard: pipeline value (sum of quote totals by stage)
  - Historical trend: quotes per day, avg value per week

- [ ] **DASH-005** — Export to CSV
  - `GET /api/dashboard/sessions.csv` — all sessions as spreadsheet
  - `GET /api/dashboard/quotes.csv` — all quotes

- [ ] **OBS-001** — LLM cost + latency tracking
  - Track tokens used + latency per chat request
  - Store in SQLite `llm_metrics` table
  - Show on dashboard

- [ ] **OBS-002** — Structured JSON logging
  - Replace print() with structlog or Python logging JSON formatter
  - Include: session_id, readiness_score, routing, LLM provider, latency

- [ ] **AUTH-001** — Dashboard auth
  - Basic HTTP auth on `/dashboard` (configurable `DASHBOARD_USER` / `DASHBOARD_PASS`)
  - No customer-facing auth needed for demo

- [ ] **DEPLOY-001** — Railway / Fly.io deployment
  - Dockerfile already exists
  - Railway: `railway up` or Fly: `fly deploy`
  - Env vars: all from `.env` as Railway secrets
  - Custom domain: `demo.steeldoorcompany.co.uk` (needs their DNS)

- [ ] **DEPLOY-002** — Vercel edge for static UI
  - Separate static deploy of `index.html` + `dashboard.html` to Vercel
  - API backend stays on Railway
  - CORS: allow Vercel domain

- [ ] **TEST-002** — Session integration tests
  - Test full multi-turn conversation (3+ messages)
  - Assert session fields accumulate correctly
  - Assert readiness score increases with each message
  - Assert internal brief triggers at correct threshold

- [ ] **TEST-003** — Brief generation tests
  - Test `build_internal_brief()` with various partial sessions
  - Assert all known fields appear in output
  - Assert routing classification is correct

---

## KNOWN BUGS / TECH DEBT

- [ ] **BUG-001** — `_extract_fields` won't extract name from first-person intro mid-conversation
  - "It's for John Smith" → sometimes captures "John Smith" fails if surrounding context confuses regex
  - Fix: better name extraction patterns + dedupe against common words

- [ ] **BUG-002** — `_extract_fields` budget parser fails on "£8k" (lowercase k)
  - Fix: normalise lowercase k → multiply by 1000 before parse

- [ ] **BUG-003** — Sessions table not created in test context until first write
  - Workaround in place (init on first write) but init_db() should be called in test fixtures
  - Fix: add conftest.py with `@pytest.fixture(autouse=True)` calling `init_db()`

- [ ] **BUG-004** — `test_chat_endpoint_accepts_history` sends "how much for a double door?" with no
  door_type → defaults to internal. Consider: if only door_set detected, don't generate quote, ask type instead.

---

## INTERVIEW TALKING POINTS (summary)

See `INTERVIEW_NOTES.md` for full details. Key points:
- Price discrepancy: homepage £1,500 vs Shopify £1,700 (raise this)
- No HSTS / CSP on their site
- No rate limiting on API (must add before production)
- PII in SQLite — needs GDPR policy for production
- Architecture: deterministic pricing + LLM conversation (never hallucinate numbers)
- Pluggable LLM: Groq → DeepSeek → Claude (same interface, env var swap)
