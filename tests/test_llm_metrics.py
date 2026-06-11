"""Tests for LLM metrics storage + dashboard endpoint (OBS-001) and JSON logging (OBS-002)."""
import logging

from fastapi.testclient import TestClient

from app.main import app, _JsonFormatter
from app.store import get_llm_metrics_summary, save_llm_metric

client = TestClient(app)


# ---------------------------------------------------------------------------
# save_llm_metric / get_llm_metrics_summary
# ---------------------------------------------------------------------------

def test_save_llm_metric_no_crash():
    """Table exists and a metric row can be written without error."""
    save_llm_metric(
        session_id="S-TESTMETRIC",
        provider="groq",
        model="llama-3.1-8b-instant",
        latency_ms=420,
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        success=True,
    )


def test_save_llm_metric_failure_path():
    """A failed (429) call records success=False without error."""
    save_llm_metric(
        session_id="S-TESTFAIL",
        provider="groq",
        model="llama-3.3-70b-versatile",
        latency_ms=900,
        success=False,
    )


def test_llm_metrics_summary_shape():
    save_llm_metric("S-SUMMARY", "groq", "llama-3.1-8b-instant", 300,
                    prompt_tokens=80, completion_tokens=40, total_tokens=120, success=True)
    summary = get_llm_metrics_summary()
    assert "total_calls" in summary
    assert "successes" in summary
    assert "avg_latency_ms" in summary
    assert "total_tokens_used" in summary
    assert "recent" in summary
    assert summary["total_calls"] >= 1
    assert isinstance(summary["recent"], list)


def test_llm_metrics_summary_counts_increase():
    before = get_llm_metrics_summary()["total_calls"]
    save_llm_metric("S-COUNT", "groq", "gemma2-9b-it", 250, success=True)
    after = get_llm_metrics_summary()["total_calls"]
    assert after == before + 1


# ---------------------------------------------------------------------------
# /api/dashboard/llm-metrics endpoint
# ---------------------------------------------------------------------------

def test_llm_metrics_endpoint_requires_auth():
    res = client.get("/api/dashboard/llm-metrics")
    assert res.status_code == 401


def test_llm_metrics_endpoint_with_auth():
    save_llm_metric("S-ENDPOINT", "groq", "llama-3.1-8b-instant", 333,
                    total_tokens=99, success=True)
    res = client.get("/api/dashboard/llm-metrics", auth=("admin", "steeldoor"))
    assert res.status_code == 200
    body = res.json()
    assert "total_calls" in body
    assert body["total_calls"] >= 1
    assert "recent" in body


# ---------------------------------------------------------------------------
# _JsonFormatter (OBS-002)
# ---------------------------------------------------------------------------

def test_json_formatter_emits_valid_json():
    import json
    fmt = _JsonFormatter()
    record = logging.LogRecord(
        name="test.logger", level=logging.INFO, pathname=__file__, lineno=1,
        msg="hello %s", args=("world",), exc_info=None,
    )
    out = fmt.format(record)
    parsed = json.loads(out)
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test.logger"
    assert parsed["msg"] == "hello world"
    assert "ts" in parsed


def test_json_formatter_includes_exception():
    import json
    fmt = _JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = logging.LogRecord(
            name="test.logger", level=logging.ERROR, pathname=__file__, lineno=1,
            msg="failed", args=(), exc_info=sys.exc_info(),
        )
    out = fmt.format(record)
    parsed = json.loads(out)
    assert parsed["level"] == "ERROR"
    assert "exc" in parsed
    assert "ValueError" in parsed["exc"]
