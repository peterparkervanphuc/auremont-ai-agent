import logging

import pytest
from fastapi.testclient import TestClient

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
