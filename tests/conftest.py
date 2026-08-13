import logging

import pytest
from fastapi.testclient import TestClient

from backend.core.context import request_id_var
from backend.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def raw_client():
    """Client that routes 500s to the exception handler instead of re-raising.

    TestClient defaults to raise_server_exceptions=True, which makes
    ServerErrorMiddleware re-raise rather than call our handler. Only tests that
    assert on the 500 *response* need this; the default stays as it is so an
    unexpected exception in any other test still surfaces as a loud traceback
    rather than a confusing `assert 200 == 500`.
    """
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _reset_request_id():
    """Stop a request id leaking from one test into the next."""
    token = request_id_var.set("-")
    yield
    request_id_var.reset(token)


class RecordingHandler(logging.Handler):
    """Collects LogRecords so tests can assert on their `extra` fields directly."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        # Force formatting now: it is what would run in production, so a
        # formatter that raises must fail the test rather than pass silently.
        record.getMessage()
        self.records.append(record)

    def events(self, name: str) -> list[logging.LogRecord]:
        return [r for r in self.records if getattr(r, "event", None) == name]

    def event(self, name: str) -> logging.LogRecord:
        found = self.events(name)
        assert found, f"no {name!r} record; got {[getattr(r, 'event', r.getMessage()) for r in self.records]}"
        return found[0]


@pytest.fixture
def capture_logs():
    """Capture records from any logger, including propagate=False ones.

    `caplog` attaches to the root logger and relies on propagation, so it cannot
    see `salesmate.audit` (propagate: False). This attaches to each logger
    directly instead, which is immune both to propagation settings and to
    anything that replaces the root handlers — notably Alembic's `fileConfig()`
    in migrations/env.py, which resets the whole logging tree and would
    otherwise silently detach this handler mid-session.

    Hands back real LogRecords, so tests can assert on `extra` fields directly.
    """
    handler = RecordingHandler()
    names = ("backend", "salesmate", "salesmate.audit", "salesmate.access")
    loggers = [logging.getLogger(name) for name in names]

    previous = [(lg, lg.level, lg.propagate) for lg in loggers]
    for lg in loggers:
        lg.addHandler(handler)
        lg.setLevel(logging.DEBUG)

    # Alembic's fileConfig() (migrations/env.py, exercised by test_migrations.py)
    # runs with disable_existing_loggers=True and switches every already-created
    # backend.* logger off for the rest of the session. Re-enable them, or every
    # test ordered after test_migrations.py sees an empty log.
    disabled = [
        lg
        for lg in logging.Logger.manager.loggerDict.values()
        if isinstance(lg, logging.Logger) and lg.disabled
    ]
    for lg in disabled:
        lg.disabled = False

    yield handler

    for lg, level, propagate in previous:
        lg.removeHandler(handler)
        lg.setLevel(level)
        lg.propagate = propagate
    for lg in disabled:
        lg.disabled = True
