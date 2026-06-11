# SteelDoorAi — AI Sales Consultant

> **Live demo:** https://steel-door-chat-bot.vercel.app
> **Dashboard:** https://steel-door-chat-bot.vercel.app/dashboard (admin / steeldoor)
> **Admin pricing:** https://steel-door-chat-bot.vercel.app/admin/pricing
> **Last updated:** 2026-06-11

An AI-powered sales consultant and quoting system built for **Steel Door Company** — the UK's leading installer of bespoke steel doors. Designed to replace phone enquiries end-to-end: capturing customer details, producing accurate estimates, routing leads to the right team, and pushing qualified leads into HubSpot CRM.

Built as a portfolio piece for an AI Software Developer interview at Steel Door Company.

**Built entirely in a single day.** Four phases shipped: core AI → sales features → production hardening → homepage + CRM. 82 tests. Live on Vercel.

---

## What it does

### AI Conversation
- **Natural-language quoting** — describe your project in plain English and get an instant itemised price estimate
- **Quote Readiness Score (0-100)** — live progress bar tracking how much information has been collected
- **4-stage conversation flow** — Scoping → Specification → Contact → Complete
- **Deterministic pricing engine** — LLM handles conversation only; every number comes from `quoting.py` (no hallucinated prices)
- **LLM field extraction** — regex-first extraction with LLM fallback for structured data (name, email, dimensions, budget, timeline)
- **Multi-model LLM chain** — Groq llama-3.3-70b → llama-3.1-8b-instant (429 fallback) → mock (zero-config)

### Sales Automation
- **Auto-routing** — Sales / Survey / Installation / Customer Care based on enquiry type and stage
- **Internal brief auto-generation** — structured summary fires at score ≥ 60 + email collected
- **PDF quote generation** — branded A4 quote with itemised lines, VAT table, disclaimer (reportlab, `GET /api/quote/{ref}/pdf`)
- **Sales team email** — brief fires to `SALES_EMAIL` on qualified lead (SMTP, configurable)
- **Customer confirmation email** — sends branded quote summary to customer on completion
- **Book Free Survey modal** — pre-filled form from session data, posts to `/api/enquiry`
- **HubSpot CRM push** — Contact + Deal created at readiness ≥ 70 + email; maps all session fields to HubSpot properties

### Homepage
- **SDC brand parity** — backdrop, trust strip, product tile grid, gallery lightbox, mobile hamburger nav
- **Shop overlay** — all 7 door types with price-from, specs, lead time, per-type quote CTA
- **Our Story section** — founder bios (Sam Hackett / Josh), 5 company values, contact address
- **Our Process timeline** — 6-step visual flow: Enquiry → Survey → Design → Manufacture → Installation → Aftercare
- **Sticky nav** — stays visible as users scroll through content sections
- **Mobile bottom sheet** — product browser as a slide-up panel on small screens

### Management Dashboard (`/dashboard`)
- KPIs: total sessions, avg readiness, conversion rate, pipeline value
- Routing distribution chart, top products chart
- Recent sessions table with readiness and routing per session
- Revenue trend (14-day Chart.js line chart)
- CSV exports for sessions and quotes
- Full internal brief viewer per session

### Admin (`/admin/pricing`)
- 25 editable pricing fields grouped by category
- SQLite-backed with full version history (last 20 changes per field)
- OVERRIDE badge, per-field reset, toast notifications
- Merges overrides into live pricing at quote time — no code deploys needed

### Production Features
- **Auth** — HTTPBasic on dashboard and admin (env-configurable credentials)
- **Rate limiting** — slowapi: 20 req/min on `/api/chat`, 30/min on `/api/quote`
- **CORS** — env-driven `ALLOWED_ORIGINS`
- **Session persistence** — SQLite survives serverless cold starts (Vercel)
- **Outbound webhook** — generic `WEBHOOK_URL` fires on qualified lead (with optional HMAC secret)
- **Structured logging** — HubSpot push logs `[HUBSPOT OK]` / `[HUBSPOT SKIPPED/FAILED]` with full traceback to stderr

---

## Architecture

```
Browser (index.html — single file, no framework)
  │
  └─ POST /api/chat  ──────────────────────────────────────────────┐
                                                                    │
FastAPI (app/main.py)                                              │
  │                                                                 │
  ├─ chat.py         NL extraction, intent detection, session state │
  │    ├─ regex extraction (name/email/phone/dimensions/budget)     │
  │    └─ LLM extraction fallback (JSON-mode, fills gaps only)      │
  │                                                                 │
  ├─ session.py      ConversationSession, readiness scoring, brief  │
  ├─ quoting.py      Deterministic pricing engine ← catalogue.py   │
  ├─ hubspot.py      Contact + Deal push at score ≥ 70             │
  ├─ email_sender.py SMTP brief + customer confirmation            │
  ├─ pdf.py          reportlab quote PDF generator                  │
  ├─ webhook.py      Generic outbound CRM webhook                   │
  └─ db.py           SQLite: sessions, quotes, enquiries,           │
                     pricing_settings, pricing_history              │
                                                                    │
LLM layer: Groq (llama-3.3-70b) → llama-3.1-8b (429) → mock ──────┘
```

**Key principle:** LLM = conversation only. Pricing = `quoting.py` always. The LLM cannot change a number.

---

## Tech stack

| Layer | Technology |
|---|---|
| Runtime | Python 3.12 |
| API | FastAPI 0.111.0 + Pydantic v2 |
| Database | SQLite (stdlib) |
| LLM | Groq llama-3.3-70b-versatile (free tier) |
| PDF | reportlab (pure Python, Vercel-compatible) |
| CRM | HubSpot Private App API v3 |
| Email | SMTP via stdlib smtplib |
| Frontend | Vanilla JS + CSS (no framework, single file) |
| Deploy | Vercel serverless (Python runtime) |
| Tests | pytest — 82 passing |

---

## Quickstart

```bash
git clone https://github.com/keejay1290-maker/SteelDoorChatBot.git
cd SteelDoorChatBot

python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -r requirements.txt
pip install -r requirements-dev.txt

copy .env.example .env        # add keys (all optional — mock works without any)

uvicorn app.main:app --reload
# http://localhost:8000
# http://localhost:8000/dashboard  (admin / steeldoor)
# http://localhost:8000/admin/pricing
```

---

## Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` \| `groq` \| `deepseek` |
| `GROQ_API_KEY` | — | Free at console.groq.com/keys |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Any Groq model |
| `DEEPSEEK_API_KEY` | — | Backup LLM |
| `HUBSPOT_ACCESS_TOKEN` | — | Private App token (`pat-eu1-...`) |
| `HUBSPOT_PIPELINE_ID` | `default` | HubSpot deal pipeline ID |
| `HUBSPOT_PIPELINE_STAGE` | `appointmentscheduled` | Initial deal stage |
| `WEBHOOK_URL` | — | Generic CRM/Zapier webhook on qualified lead |
| `WEBHOOK_SECRET` | — | Optional HMAC header for webhook auth |
| `SMTP_HOST` | — | Email server host |
| `SMTP_PORT` | `587` | Email server port |
| `SMTP_USER` | — | SMTP username |
| `SMTP_PASS` | — | SMTP password |
| `SALES_EMAIL` | `sales@steeldoorcompany.co.uk` | Brief recipient |
| `DASHBOARD_USER` | `admin` | Dashboard basic auth username |
| `DASHBOARD_PASS` | `steeldoor` | Dashboard basic auth password |
| `ENQUIRY_DB` | `enquiries.db` | SQLite path |

---

## Tests

```bash
cd app && ../.venv/Scripts/pytest ../tests -q
# 82 tests passing
```

Coverage: chat endpoint, session state, quoting engine, field extraction, email (mocked SMTP), PDF generation, brief generation, multi-turn integration, dashboard endpoints, enquiry submission.

---

## Pricing model

Real prices from steeldoorcompany.co.uk Shopify product feed (verified 2026-06-11):

| Product | Base price (exc. VAT) |
|---|---|
| Single steel door | £1,700 |
| Double steel doors | £3,000 |
| Fire rated (FD30/FD60) | £3,400 |
| Wine room door | £2,300 |
| Sliding door system | £4,750 |
| External patio doors | £5,000 |
| Concertina doors | £5,250 |

Uplifts applied at quote time: external installation +£800, RAL colour +£150, glazing options +£200–400, side panels +£400 each. All overridable via `/admin/pricing` without a code deploy.

---

## Build timeline

This project was built in a single day (2026-06-11):

| Phase | What shipped |
|---|---|
| **Phase 1 — Core** | AI sales consultant, readiness score, 4-stage flow, deterministic quoting, session persistence, routing, internal brief, dashboard, 36 tests |
| **Phase 2 — Sales** | PDF quotes, customer email, sales brief email, survey booking modal, CRM webhook, enquiry confirmation, revenue chart, CSV exports, 82 tests |
| **Phase 3 — Production** | HTTPBasic auth, rate limiting, CORS, deterministic quote refs, LLM field extraction fallback, GROQ 429 multi-model fallback, admin pricing table (25 fields, version history) |
| **Phase 4 — Homepage + CRM** | SDC brand homepage, trust strip, product tiles, gallery lightbox, mobile bottom sheet, shop overlay (7 products), Our Story, Our Process, HubSpot CRM push (Contact + Deal), sticky nav |

---

*Built by Kieran — AI Software Developer portfolio project, 2026.*
