# S108 Handover — SteelDoorAi

**Date:** 2026-06-11
**Repo:** https://github.com/keejay1290-maker/SteelDoorChatBot
**Live URL:** https://steel-door-chat-bot.vercel.app
**Dashboard:** https://steel-door-chat-bot.vercel.app/dashboard

---

## What was built this session (S107 + S108)

### Core features completed

1. **Server-side session tracking** — `app/session.py` — `ConversationSession` dataclass persisted to SQLite; survives restarts
2. **Quote Readiness Score (0-100)** — live progress bar in UI; `calculate_readiness()` formula across 15 fields
3. **Automated team routing** — Sales / Survey / Installation / Customer Care based on session state
4. **Internal Brief auto-generation** — ASCII-bordered text brief shown in right panel when score ≥ 60
5. **Management dashboard** — `/dashboard` with 6 KPI tiles, Chart.js bar + doughnut, recent sessions table; 30s auto-refresh
6. **Intent classification** — `_classify_intent()` catches contact_info / help / greeting / thanks / confirmation / adjustment before spec logic
7. **Spell normalisation** — `_normalise_text()` handles typos (qoute→quote, fd3→fd30, dbl→double, etc.)
8. **Groq LLM integration** — `llama-3.3-70b-versatile`; DeepSeek backup; Anthropic claude-haiku-4-5 tertiary; mock zero-config fallback
9. **Bot-stuck fix** — `prev_quote_ref` tracking prevents quote re-display on every subsequent message
10. **Vercel deployment** — `api/index.py` entrypoint, `vercel.json` routing, `/tmp/enquiries.db` for demo persistence

### Files created / modified

| File | Change |
|---|---|
| `app/session.py` | NEW — ConversationSession, calculate_readiness, determine_routing, build_internal_brief, SQLite persistence |
| `app/chat.py` | MAJOR REWRITE — _extract_fields, _classify_intent, _normalise_text, _mock_reply intent-first, new_quote tracking |
| `app/models.py` | Added session_id to ChatRequest, SessionState model, session in ChatResponse |
| `app/main.py` | v0.4.0 — /api/session/:id, /api/dashboard/stats, /api/dashboard/sessions, /dashboard routes |
| `app/store.py` | Added get_dashboard_stats(), init_sessions_table() call |
| `app/static/index.html` | Full 3-panel UI rewrite — readiness bar, stage/routing badges, field checklist, brief panel |
| `app/static/dashboard.html` | NEW — KPI tiles, Chart.js charts, sessions table |
| `api/index.py` | NEW — Vercel serverless entrypoint |
| `vercel.json` | NEW — Vercel build + routing config |
| `TASKS.md` | NEW — 25-item cross-session backlog |
| `README.md` | Full rewrite + live URL added |

### Bugs fixed

- Bot stuck after quote (prev_quote_ref tracking)
- `help` / contact info messages ignored (intent classification added before spec logic)
- Name extraction missing capital letters (re.IGNORECASE added)
- `test_chat_endpoint_accepts_history` returning no quote (guard changed from `or` to `and`)
- pydantic None mechanism crash (defaults applied in _build_quote_request_from_session)
- SQLite sessions table missing in tests (save_session auto-creates table on failure)

---

## Active deployment

- **Platform:** Vercel (keejay1290-makers-projects/steel-door-chat-bot)
- **Env vars set:** GROQ_API_KEY, LLM_PROVIDER=groq, ENQUIRY_DB=/tmp/enquiries.db
- **Git:** master branch, commit 63f9cff pushed to GitHub
- **SQLite note:** Vercel uses /tmp — data persists within a warm lambda, resets on cold start. Acceptable for interview demo.

---

## Next priorities (from TASKS.md)

| ID | Task | Priority |
|---|---|---|
| GROQ-001 | Verify Groq key working in prod — test live chat | High |
| EMAIL-001 | Email internal brief to sales@steeldoorcompany.co.uk on score ≥ 60 | High |
| BUG-003 | Add tests/conftest.py calling init_db() so sessions table exists in all tests | Medium |
| PDF-001 | WeasyPrint quote PDF generation | Medium |
| UX-001 | Book Free Survey form modal | Medium |
| CRM-001 | HubSpot contact creation on enquiry capture | Low |
| MULTI-001 | WhatsApp channel via Twilio | Long-term |
| VISION-001 | Photo upload for site measurement | Long-term |
| PHONE-001 | Out-of-hours phone bot (Twilio Voice + STT) | Long-term |

---

## Architecture summary

```
Browser (index.html)
  POST /api/chat {session_id, message}
    ↓
FastAPI (app/main.py)
  ↓
chat.py
  _normalise_text()       ← spell correction
  _classify_intent()      ← contact/help/greeting first
  _extract_fields()       ← regex + session update
  calculate_readiness()   ← 0-100 score
  determine_routing()     ← sales/survey/install/care
  build_internal_brief()  ← staff summary
  LLM reply               ← Groq → DeepSeek → mock
    ↓
session.py (SQLite: /tmp/enquiries.db)
  ↓
ChatResponse {message, quote, session: {readiness_score, routing, ...}}
```

---

## Interview talking points

1. **Deterministic pricing** — LLM never touches numbers; all quotes from `quoting.py` price engine
2. **Multi-provider LLM failover** — Groq → DeepSeek → Anthropic → mock; zero config for local dev
3. **Session persistence** — SQLite ConversationSession survives restarts; stage machine (1-4)
4. **Quote Readiness Score** — 15-field formula gives business visibility into lead quality
5. **Internal brief auto-generation** — structured output for staff, ready for CRM/email integration
6. **Management dashboard** — real-time KPIs, routing distribution, recent sessions — built in vanilla HTML/Chart.js, no framework needed
7. **36 passing tests** — full coverage of pricing engine, extraction, intent classification
