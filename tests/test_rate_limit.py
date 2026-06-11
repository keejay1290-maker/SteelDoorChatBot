"""Rate-limit exhaustion test — isolated file to avoid poisoning shared client."""
import pytest
from fastapi.testclient import TestClient

try:
    from slowapi import Limiter  # noqa: F401
except ImportError:
    pytest.skip("slowapi not installed", allow_module_level=True)


def test_chat_rate_limit_returns_429():
    """21st POST to /api/chat within a minute must return 429."""
    # Build a fresh in-memory limiter so this test never affects others
    from limits.storage import MemoryStorage
    from slowapi import Limiter
    from slowapi.util import get_remote_address

    fresh_limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")

    from app.main import app
    original = getattr(app.state, "limiter", None)
    app.state.limiter = fresh_limiter

    try:
        c = TestClient(app, raise_server_exceptions=False)
        for _ in range(20):
            c.post("/api/chat", json={"message": "hello"})
        res = c.post("/api/chat", json={"message": "hello"})
        assert res.status_code == 429
    finally:
        if original is not None:
            app.state.limiter = original
