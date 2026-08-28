import logging

import pytest
from fastapi.testclient import TestClient

from backend.core.config import settings
from backend.core.context import request_id_var
from backend.core.logging_config import AUDIT_LOGGER_NAME
from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def raw_client():
    """Client that lets the app's own 500 handler run.

    TestClient defaults to `raise_server_exceptions=True`, where
    ServerErrorMiddleware re-raises instead of calling our handler — so the
    response body can never be asserted. Kept separate from `client` on purpose:
    flipping the default globally would turn every unexpected error in the
    existing tests from a clear traceback into a puzzling `assert 200 == 500`.
    """
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_request_id():
    """Stop a request id set by one test from leaking into the next."""
    token = request_id_var.set("")
    yield
    request_id_var.reset(token)


@pytest.fixture(autouse=True)
def _stub_dependency_readiness(monkeypatch):
    """Unit/API tests do not require live MySQL, Qdrant, and Redis processes."""

    async def healthy_readiness():
        return {
            "status": "ok",
            "checks": {name: {"status": "ok", "latency_ms": 0.0} for name in ("mysql", "qdrant", "redis")},
        }

    monkeypatch.setattr("backend.main.check_readiness", healthy_readiness)


@pytest.fixture(autouse=True)
def _disable_live_semantic_conflict_calls(monkeypatch):
    """Unit tests opt in explicitly; no test may accidentally spend an LLM request."""

    monkeypatch.setattr(settings, "semantic_conflict_detection_enabled", False)


@pytest.fixture(autouse=True)
def _disable_live_observability_writes(monkeypatch):
    """Tests opt in explicitly; never write test metrics to a developer's MySQL."""

    monkeypatch.setattr(settings, "observability_metrics_enabled", False)


@pytest.fixture(autouse=True)
def _disable_live_lead_enrichment(monkeypatch):
    """Same rule as the semantic-conflict guard: no test spends an LLM request by accident.

    Lead scoring runs on every customer turn, so without this any test that posts a customer
    message and happens to land inside the enrichment decision band reaches for Gemini and
    hangs on the network. Rule scoring — the part these tests care about — is unaffected.
    """

    monkeypatch.setattr(settings, "lead_scoring_llm_enabled", False)


@pytest.fixture
def capture_audit():
    """Collect records from the audit logger.

    `caplog` cannot see these: it attaches to the root logger and relies on
    propagation, while the audit logger sets `propagate = False` by design.
    Attaching a handler directly is immune to that and yields the real
    LogRecords, so tests can assert on `record.__dict__` fields.
    """
    records: list[logging.LogRecord] = []

    class _Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Collector()
    logger = logging.getLogger(AUDIT_LOGGER_NAME)
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
