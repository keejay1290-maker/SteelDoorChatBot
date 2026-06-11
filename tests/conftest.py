import os

# Safety: tests ALWAYS run against local SQLite, never the production Postgres.
# Pop both vars before any app module imports app.db (which reads them at import).
os.environ.pop("DATABASE_URL", None)
os.environ.pop("POSTGRES_URL", None)

import pytest
from app.store import init_db


@pytest.fixture(autouse=True, scope="session")
def _init_db():
    init_db()
