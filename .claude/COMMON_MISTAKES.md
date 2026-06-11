# SteelDoorAi — Common Mistakes (READ FIRST each session)

> Hard-won gotchas. Each cost real time. Don't repeat them.
> Context: this is an interview showcase that is intended to **replace the
> client's entire website**. Treat it as production: deterministic pricing,
> durable data, no broken deploys.

---

## Deploy / Infra

1. **Railway does NOT auto-deploy from GitHub.** A `git push` does nothing on Railway.
   You MUST run `RAILWAY_API_TOKEN=<token> railway up --detach` from
   `steeldoorai-demo-main/`. (Vercel IS git-linked and auto-builds on push.)

2. **Railway env vars: set via GraphQL API, not the CLI.** `railway variables set`
   is interactive / errors in this non-TTY shell. Use the GraphQL `variableUpsert`
   mutation (see `.claude/WORKFLOW.md`). Project/env/service IDs are fixed (below).

3. **After deploy, ALWAYS poll status to terminal + curl /health.** "Online" status
   ≠ healthy build. Poll the deployment `status` until SUCCESS/FAILED, then hit
   `/health` → `{"status":"ok"}`. Old FAILED deployments that got superseded show
   as `REMOVED` — ignore those; only the latest matters.

## Supabase / Database

4. **The DIRECT Supabase connection (`db.<ref>.supabase.co:5432`) is IPv6-ONLY.**
   It times out from Railway, Vercel, and most local networks (IPv4). NEVER use it
   for the app. Use the **transaction pooler**:
   `postgresql://postgres.<ref>:<pwd>@aws-0-eu-west-1.pooler.supabase.com:6543/postgres`
   (region eu-west-1 for project kzjtwdkvxhhhmlckgthf).

5. **The new `sb_secret_`/`sb_publishable_` keys 401 on the REST API.** Don't waste
   time debugging this — the app talks to Postgres directly (psycopg), not REST.
   The REST 401 is irrelevant to the backend. (Frontend/Vercel use the publishable
   key only if it does client-side Supabase calls.)

6. **NEVER put `DATABASE_URL` uncommented in local `.env`.** `load_dotenv()` would
   make the **test suite + local dev hit the production Postgres** (slow, pollutes
   real data). Keep it commented in `.env`; set it ONLY in Railway/Vercel.
   `tests/conftest.py` defensively pops `DATABASE_URL`/`POSTGRES_URL` — keep that.

7. **psycopg + Supabase pooler needs `prepare_threshold=None` + `autocommit=True`.**
   The transaction pooler (pgBouncer) doesn't persist prepared statements across
   pooled transactions. `app/db.py` already sets this — don't remove it.

8. **Clean test rows out of the production DB after live testing.** Especially
   `pricing_settings` — a stray `base.single` override **corrupts real quote prices**
   (e.g. 1800 instead of the real 1700). Truncate or delete by id after smoke tests.

9. **SQLite on Railway/Vercel lives at `/tmp` and WIPES on every cold start.** This
   is *why* we added Postgres. Don't "fix" persistence by going back to SQLite in prod.

## App correctness

10. **The LLM never sets prices.** All numbers come from `quoting.py`
    (`calculate_quote`). The LLM only relays the `[QUOTE FROM DETERMINISTIC ENGINE]`
    block verbatim. If you change pricing, change it in `PRICING` / admin overrides.

11. **Fire-once flags must be gated on their OWN success flag, not a shared one.**
    (COR-04 bug: HubSpot/webhook were gated on `brief_email_sent`, which only flips
    on a successful SMTP send — so with SMTP off, every message re-pushed → duplicate
    HubSpot deals.) Each side-effect has its own persisted flag: `hubspot_pushed`,
    `webhook_fired`, `brief_email_sent`, `customer_email_sent`.

12. **slowapi `@limiter.limit()` requires `request: Request` in the function signature.**
    Forgetting it breaks the endpoint at runtime, not at import.

13. **Never log customer PII (name/email/phone) at INFO.** Log `session_id` /
    `reference` instead. (SEC-03.)

## Testing

14. **Run the full suite before every deploy:** `.\.venv\Scripts\python.exe -m pytest tests/ -q`.
    Target: **131 passed, 2 skipped**. The SQLite path must stay byte-identical when
    you touch `db.py`/`store.py`/`session.py`.

15. **Both DB backends share one SQL string + dialect fragments** (`app/db.py`:
    `q()`, `AUTOINC_PK`, `NOW_DEFAULT`, `json_field`, `as_date`, `date_days_ago`).
    When adding a query, use these helpers — don't hardcode SQLite-only syntax
    (`INSERT OR IGNORE`, `json_extract`, `datetime('now')`, `lastrowid`).

---

## Fixed IDs / endpoints (don't re-derive)
- Railway project `9410b36f-1864-495e-8652-265258687098` | env `ac0f4b9c-2dc5-4ed4-a936-3bd957b8c1ec` | service `377437d8-c6c1-4f89-aa98-0b3e33225b31`
- Railway URL: https://steeldoorchatbot-production.up.railway.app
- Vercel URL: https://steel-door-chat-bot.vercel.app (git-linked, auto-builds on push)
- Supabase project `kzjtwdkvxhhhmlckgthf` (eu-west-1) — keys on Desktop: `supabase-keys-kzjtwdkvxhhhmlckgthf.md`
- GitHub: keejay1290-maker/SteelDoorChatBot
