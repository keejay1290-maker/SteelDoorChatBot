# SteelDoorAi — AI Sales Consultant

> **Live demo:** https://steel-door-chat-bot.vercel.app
> **Dashboard:** https://steel-door-chat-bot.vercel.app/dashboard
> **Last updated:** 2026-06-11 (S108)

An AI-powered sales consultant and quoting assistant for **Steel Door Company** — the UK's leading installer of bespoke steel doors. Designed to replace phone enquiries, capture customer details, produce accurate estimates, and route leads to the correct team.

Built as an AI Software Developer portfolio piece for a Systems Integration interview.

---

## What it does

- **Natural-language quoting** — describe your project and get an instant price estimate
- **Full sales replacement** — multi-stage conversation collects all project details (contact info, spec, measurements, budget, timeline)
- **Quote Readiness Score (0-100)** — live progress bar showing how complete an enquiry is
- **Automated routing** — Sales / Survey / Installation / Customer Care based on enquiry stage
- **Internal Brief auto-generation** — structured summary for staff when score ≥ 60
- **Management dashboard** — KPIs, routing distribution, recent sessions (at `/dashboard`)
- **Session persistence** — conversations survive server restarts (SQLite)
- **Real prices** — scraped from steeldoorcompany.co.uk Shopify product feed
- **Real product images** — scraped via Playwright

## Architecture

```
Browser UI (index.html)
  ↓ POST /api/chat (session_id)
FastAPI (app/main.py)
  ↓
chat.py — NL extraction + intent detection + session state
  ↓
session.py — ConversationSession (SQLite)
  ↓
quoting.py — deterministic pricing engine (LLM never touches numbers)
  ↓
LLM reply (Groq llama-3.3-70b / DeepSeek / mock fallback)
```

**Key principle:** The LLM handles conversation only. Every number comes from the deterministic engine — no hallucinated prices.

## Tech stack

- Python 3.12 + FastAPI 0.111.0 + Pydantic v2
- SQLite (stdlib) — sessions, quotes, enquiries
- Playwright (Chromium) — product image scraper
- Groq (llama-3.3-70b-versatile) — default LLM, free tier
- DeepSeek — backup LLM
- Mock provider — zero-config fallback (no API key needed)

## Quickstart

```bash
git clone https://github.com/keejay1290-maker/SteelDoorChatBot.git
cd SteelDoorChatBot

# Create venv
python -m venv .venv
.venv\Scripts\activate     # Windows
# or: source .venv/bin/activate  (Linux/Mac)

pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy env template and add keys (optional — mock works without keys)
copy .env.example .env

# Run server
uvicorn app.main:app --reload
# open http://localhost:8000
# dashboard: http://localhost:8000/dashboard
```

## Configuration (.env)

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `mock` | `mock` \| `groq` \| `deepseek` |
| `GROQ_API_KEY` | — | Free at console.groq.com/keys |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Any Groq model |
| `DEEPSEEK_API_KEY` | — | Backup LLM |
| `ENQUIRY_DB` | `enquiries.db` | SQLite path |

## Tests

```bash
pytest         # 36 tests, all passing
```

## Deploy (Railway)

```bash
railway up
```

Set env vars in Railway dashboard: `LLM_PROVIDER`, `GROQ_API_KEY`.

## Product Screenshots

- Chat UI with readiness bar, stage badge, routing badge
- Right panel: internal brief + field collection tracker
- Management dashboard: KPIs, top products chart, routing doughnut
- Quote card with real product image and itemised pricing

## Pricing model

Real prices from steeldoorcompany.co.uk Shopify feed (2026):

| Product | Base price (exc. VAT) |
|---|---|
| Single steel door | £1,700 |
| Double steel doors | £3,000 |
| Fire rated (FD30/FD60) | £3,400 |
| Sliding door system | £4,750 |
| Concertina doors | £5,250 |
| External patio doors | £5,000 |
| Wine room door | £2,300 |

Uplifts: external +£800, RAL colour +£150, glazing options, side panels +£400 each.

## Roadmap

See [TASKS.md](TASKS.md) for the full backlog with priorities.

Key next steps:
- Email internal brief to `sales@steeldoorcompany.co.uk` on enquiry capture
- PDF quote generation (WeasyPrint)
- HubSpot CRM integration
- WhatsApp channel (Twilio)
- Architect PDF schedule extraction

---

*Built by Kieran — AI Software Developer portfolio project, 2026.*
