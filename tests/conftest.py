import pytest
from app.store import init_db


@pytest.fixture(autouse=True, scope="session")
def _init_db():
    init_db()
