"""Tests for RequestContextMiddleware: request id in, access line out."""

import logging
import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.context import get_request_id
from backend.middleware.logging import REQUEST_ID_HEADER, RequestContextMiddleware


def build_app() -> FastAPI:
    """A throwaway app, so these tests never mutate the real router table."""
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/ping")
    def ping():
        # Proves the contextvar is visible inside a sync endpoint, which FastAPI
        # runs in a threadpool.
        return {"request_id": get_request_id()}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


class TestRequestId:
    def test_a_generated_id_is_echoed_back(self, client):
        response = client.get("/health")

        assert re.fullmatch(r"[0-9a-f]{32}", response.headers[REQUEST_ID_HEADER])

    def test_an_inbound_id_is_reused(self, client):
        """Lets a trace started at the frontend or a gateway survive the hop."""
        response = client.get("/health", headers={REQUEST_ID_HEADER: "corr-42"})

        assert response.headers[REQUEST_ID_HEADER] == "corr-42"

    def test_the_id_is_visible_inside_a_sync_endpoint(self):
        response = TestClient(build_app()).get("/ping", headers={REQUEST_ID_HEADER: "corr-7"})

        assert response.json()["request_id"] == "corr-7"

    def test_ids_do_not_leak_between_requests(self, client):
        first = client.get("/health").headers[REQUEST_ID_HEADER]
        second = client.get("/health").headers[REQUEST_ID_HEADER]

        assert first != second

    def test_the_contextvar_is_reset_after_the_request(self, client):
        client.get("/health", headers={REQUEST_ID_HEADER: "corr-1"})

        assert get_request_id() == "-"


class TestAccessLog:
    def test_one_line_per_request_with_a_duration(self, client, capture_logs):
        client.get("/health", headers={REQUEST_ID_HEADER: "corr-9"})

        record = capture_logs.event("http.access")
        assert record.method == "GET"
        assert record.path == "/health"
        assert record.status_code == 200
        assert isinstance(record.duration_ms, float)
        assert record.duration_ms >= 0

    def test_health_is_logged_at_debug(self, client, capture_logs):
        """The Docker healthcheck hits /health every 30s; at INFO it buries the log."""
        client.get("/health")

        assert capture_logs.event("http.access").levelno == logging.DEBUG

    def test_a_normal_request_is_logged_at_info(self, capture_logs):
        TestClient(build_app()).get("/ping")

        assert capture_logs.event("http.access").levelno == logging.INFO

    def test_a_client_error_is_logged_at_warning(self, client, capture_logs):
        client.get("/api/v1/no-such-route")

        assert capture_logs.event("http.access").levelno == logging.WARNING

    def test_authorization_header_never_reaches_the_log(self, client, capture_logs):
        client.get("/health", headers={"Authorization": "Bearer super-secret-token"})

        for record in capture_logs.records:
            assert "super-secret-token" not in str(record.__dict__)
