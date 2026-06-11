# Contributing

## Conventions

- **Language:** Python 3.12, FastAPI, Pydantic v2.
- **Golden rule:** the LLM only handles conversation. All pricing comes from the
  deterministic engine in `app/quoting.py`. Never let a model produce or alter numbers.
- **Style:** enforced by `ruff` (`ruff.toml`). Run `ruff check .` before committing.
- **Tests:** add/maintain pytest coverage for any change to pricing or extraction logic.

## Local setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt   # includes ruff
ruff check .
pytest -q
uvicorn app.main:app --reload
```

## Adding a new pricing rule

1. Add the constant(s) to `PRICING` in `app/quoting.py`.
2. Apply it in `calculate_quote` as an explicit, named line item.
3. Add a test in `tests/test_quoting.py` asserting the exact expected figure.

## Adding a new LLM provider

1. Add a `_yourprovider_reply(...)` function in `app/chat.py` mirroring `_deepseek_reply`.
2. Wire it into `handle_chat` behind an `LLM_PROVIDER` value.
3. Keep the mock fallback so the demo always runs without credentials.

See [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md) for the prioritised upgrade backlog.
