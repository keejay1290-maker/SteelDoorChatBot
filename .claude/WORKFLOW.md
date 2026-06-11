# SteelDoorAi — Workflow (how to build, test, deploy, in order)

> Two deploy targets: **Railway** (primary backend, manual deploy) and **Vercel**
> (git-linked, auto-builds on push). Always do them in the order below.

---

## 0. Before you touch anything
- Read `.claude/COMMON_MISTAKES.md`.
- `cd C:\Users\Shadow\Downloads\steeldoorai-demo\steeldoorai-demo-main`
- Local dev + tests use **SQLite** (no `DATABASE_URL`). Production uses **Supabase Postgres**.

## 1. Develop
- Python venv: `.\.venv\Scripts\python.exe`
- Run locally: `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`
- Backend code: `app/` (chat.py, quoting.py, store.py, session.py, db.py, rag.py, main.py)
- Frontend: `app/static/index.html` (+ dashboard.html, admin_pricing.html)

## 2. Test (MANDATORY before deploy)
```
.\.venv\Scripts\python.exe -m pytest tests/ -q
```
Expected: **131 passed, 2 skipped**. If you changed DB code, this only proves the
SQLite path — also smoke-test Postgres (step 5).

## 3. Commit (only after tests pass)
```
git add <files>
git commit -m "..."   # end body with: Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
```

## 4. Deploy to Railway (backend) — MANUAL, does NOT auto-deploy from git
```powershell
$env:RAILWAY_API_TOKEN = "<RAILWAY_API_TOKEN>"   # value in local .env / Desktop notes — never commit
railway up --detach            # from steeldoorai-demo-main/
```
Then POLL the deployment to a terminal status and verify health:
```powershell
# poll: GraphQL { deployment(id:"<id>") { status } } until SUCCESS/FAILED
Invoke-RestMethod "https://steeldoorchatbot-production.up.railway.app/health"
# expect {"status":"ok","version":"0.4.0"}
```

### Setting Railway env vars (use GraphQL, NOT `railway variables` CLI)
```powershell
$headers = @{ "Authorization" = "Bearer $env:RAILWAY_API_TOKEN"; "Content-Type" = "application/json" }
$projectId = "9410b36f-1864-495e-8652-265258687098"
$envId     = "ac0f4b9c-2dc5-4ed4-a936-3bd957b8c1ec"
$svcId     = "377437d8-c6c1-4f89-aa98-0b3e33225b31"
$m = @{ query = "mutation { variableUpsert(input: { projectId: `"$projectId`", environmentId: `"$envId`", serviceId: `"$svcId`", name: `"KEY`", value: `"VALUE`" }) }" } | ConvertTo-Json
Invoke-RestMethod -Uri "https://backboard.railway.app/graphql/v2" -Method POST -Headers $headers -Body $m
```
Required Railway env vars: `GROQ_API_KEY`, `HUBSPOT_ACCESS_TOKEN`, `LLM_PROVIDER=groq`,
`DATABASE_URL` (Supabase transaction pooler), `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`,
`ENQUIRY_DB=/tmp/enquiries.db` (only used if DATABASE_URL unset).

## 5. Verify Postgres (after DB-related changes)
```powershell
# Get the full DATABASE_URL from the local .env (commented line) or the Desktop keys doc — NEVER commit it.
$env:DATABASE_URL="postgresql://postgres.kzjtwdkvxhhhmlckgthf:<DB_PASSWORD>@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
# run app store/session funcs against live DB, then CLEAN UP test rows.
Remove-Item Env:\DATABASE_URL   # IMPORTANT: unset again so you don't keep hitting prod
```

## 6. Push to GitHub (triggers Vercel auto-build)
```
git push origin master
```
Vercel rebuilds `steel-door-chat-bot.vercel.app`. Vercel gets its Postgres
connection from `POSTGRES_URL` (auto-injected by the Supabase–Vercel integration);
`app/db.py` reads `DATABASE_URL` OR `POSTGRES_URL`.

## Order summary
**test → commit → `railway up` → poll status → curl /health → (verify Postgres) → `git push` (Vercel) → verify Vercel**

---

## Quick reference
| Thing | Value |
|---|---|
| Railway URL | https://steeldoorchatbot-production.up.railway.app |
| Vercel URL | https://steel-door-chat-bot.vercel.app |
| Dashboard | `/dashboard` (basic auth: admin / steeldoor) |
| Admin pricing | `/admin/pricing` (same auth) |
| GitHub | keejay1290-maker/SteelDoorChatBot |
| Supabase | kzjtwdkvxhhhmlckgthf (eu-west-1), keys on Desktop |
| Tests | 131 passed, 2 skipped |
| LLM | Groq `llama-3.1-8b-instant` default, multi-model fallback |
