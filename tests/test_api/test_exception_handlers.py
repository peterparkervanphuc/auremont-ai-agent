"""Tests for the global exception handlers.

Three of these guard regressions that would be easy to introduce and painful to
diagnose: a 500 leaking internals, a 401 losing WWW-Authenticate (which breaks
the OAuth2 flow), and a 422 whose shape the frontend can no longer parse.
"""

import logging

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.main import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from backend.middleware.logging import REQUEST_ID_HEADER, RequestContextMiddleware

LEAKED_SECRET = "INTERNAL DETAIL THAT MUST NOT ESCAPE"


@pytest.fixture
def handler_client() -> TestClient:
    """A throwaway app wired with the same handlers as the real one."""
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    @app.get("/boom")
    def boom():
        raise RuntimeError(LEAKED_SECRET)

    @app.get("/unauthorized")
    def unauthorized():
        # Exactly what routers/auth.py raises on bad credentials.
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.get("/needs-param")
    def needs_param(count: int):
        return {"count": count}

    return TestClient(app, raise_server_exceptions=False)


class TestUnhandledException:
    def test_returns_a_generic_500(self, handler_client):
        response = handler_client.get("/boom")

        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error"

    def test_the_body_never_leaks_internals(self, handler_client):
        response = handler_client.get("/boom")

        assert LEAKED_SECRET not in response.text
        assert "Traceback" not in response.text

    def test_the_body_carries_the_request_id(self, handler_client):
        response = handler_client.get("/boom", headers={REQUEST_ID_HEADER: "corr-500"})

        assert response.json()["request_id"] == "corr-500"

    def test_the_traceback_goes_to_the_log(self, handler_client, capture_logs):
        handler_client.get("/boom")

        record = capture_logs.event("http.unhandled")
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None


class TestHttpException:
    def test_preserves_the_www_authenticate_header(self, handler_client):
        """Dropping this silently breaks the OAuth2 flow."""
        response = handler_client.get("/unauthorized")

        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"

    def test_preserves_the_detail_body(self, handler_client):
        response = handler_client.get("/unauthorized")

        assert response.json() == {"detail": "Incorrect username or password"}

    def test_is_logged_at_warning_without_a_traceback(self, handler_client, capture_logs):
        handler_client.get("/unauthorized")

        record = capture_logs.event("http.error")
        assert record.levelno == logging.WARNING
        assert record.status_code == 401
        assert record.exc_info is None

    def test_a_404_keeps_its_shape(self, client):
        response = client.get("/api/v1/no-such-route")

        assert response.status_code == 404
        assert response.json() == {"detail": "Not Found"}


class TestValidationError:
    def test_keeps_fastapis_422_shape(self, handler_client):
        """The frontend parses this; the list-of-errors shape must not change."""
        response = handler_client.get("/needs-param?count=not-a-number")

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert isinstance(detail, list)
        assert {"loc", "msg", "type"} <= set(detail[0])

    def test_is_logged_at_warning(self, handler_client, capture_logs):
        handler_client.get("/needs-param?count=not-a-number")

        assert capture_logs.event("http.validation_error").levelno == logging.WARNING

    def test_the_log_omits_the_offending_input_value(self, handler_client, capture_logs):
        """pydantic puts the input in errors(); for a token payload that would leak."""
        handler_client.get("/needs-param?count=SENSITIVE-VALUE")

        record = capture_logs.event("http.validation_error")
        assert "SENSITIVE-VALUE" not in str(record.errors)
        # ...while the response still shows it, exactly as FastAPI does by default.
        assert all({"loc", "msg", "type"} >= set(error) for error in record.errors)
