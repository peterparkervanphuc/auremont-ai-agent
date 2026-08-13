"""Tests for the JSON/console formatters, the redaction filter and setup_logging."""

import json
import logging
from datetime import datetime
from uuid import uuid4

import pytest

from backend.core.context import request_id_var
from backend.core.logging_config import (
    ConsoleFormatter,
    JsonFormatter,
    RedactingFilter,
    build_config,
    setup_logging,
)


def make_record(**kwargs) -> logging.LogRecord:
    record = logging.LogRecord(
        name=kwargs.pop("name", "backend.services.demo"),
        level=kwargs.pop("level", logging.INFO),
        pathname="/app/backend/services/demo.py",
        lineno=kwargs.pop("lineno", 42),
        msg=kwargs.pop("msg", "hello"),
        args=kwargs.pop("args", ()),
        exc_info=kwargs.pop("exc_info", None),
    )
    for key, value in kwargs.items():
        setattr(record, key, value)
    return record


def format_json(**kwargs) -> dict:
    return json.loads(JsonFormatter().format(make_record(**kwargs)))


class TestJsonFormatter:
    def test_emits_valid_json_with_the_core_keys(self):
        payload = format_json()

        assert set(payload) >= {
            "timestamp",
            "level",
            "logger",
            "message",
            "module",
            "func",
            "line",
            "request_id",
        }
        assert payload["level"] == "INFO"
        assert payload["logger"] == "backend.services.demo"
        assert payload["message"] == "hello"
        assert payload["line"] == 42

    def test_interpolates_message_args(self):
        assert format_json(msg="took %s ms", args=(12,))["message"] == "took 12 ms"

    def test_includes_extra_fields_at_top_level(self):
        payload = format_json(event="demo.event", document_id=7)

        assert payload["event"] == "demo.event"
        assert payload["document_id"] == 7

    def test_omits_internal_logrecord_attributes(self):
        payload = format_json()

        for noise in ("args", "msecs", "relativeCreated", "pathname", "levelno", "exc_text"):
            assert noise not in payload

    def test_serialises_values_json_cannot_handle(self):
        payload = format_json(when=datetime(2026, 8, 13, 10, 30), uid=uuid4())

        assert payload["when"].startswith("2026-08-13")
        assert isinstance(payload["uid"], str)

    def test_survives_a_value_whose_repr_raises(self):
        """default=str still runs __repr__, which can itself throw."""

        class Hostile:
            def __repr__(self):
                raise RuntimeError("nope")

        payload = format_json(obj=Hostile())

        assert payload["log_format_error"]
        # The core fields survive so the line is still useful.
        assert payload["message"] == "hello"
        assert payload["level"] == "INFO"

    def test_includes_exception_type_and_traceback(self):
        try:
            raise ValueError("boom")
        except ValueError:
            payload = json.loads(JsonFormatter().format(make_record(exc_info=logging.sys.exc_info())))

        assert payload["exc_type"] == "ValueError"
        assert "Traceback" in payload["exception"]
        assert "boom" in payload["exception"]

    def test_reads_the_request_id_contextvar(self):
        token = request_id_var.set("trace-abc")
        try:
            assert format_json()["request_id"] == "trace-abc"
        finally:
            request_id_var.reset(token)

    def test_preserves_vietnamese_text(self):
        """ensure_ascii=False — \\u-escaping makes `docker compose logs` unreadable."""
        raw = JsonFormatter().format(make_record(msg="Chưa có dữ liệu dự án"))

        assert "Chưa có dữ liệu dự án" in raw
        assert json.loads(raw)["message"] == "Chưa có dữ liệu dự án"

    def test_output_is_exactly_one_line(self):
        try:
            raise ValueError("multi\nline")
        except ValueError:
            raw = JsonFormatter().format(make_record(exc_info=logging.sys.exc_info()))

        assert "\n" not in raw


class TestConsoleFormatter:
    def test_includes_request_id_and_extras(self):
        token = request_id_var.set("req-7")
        try:
            line = ConsoleFormatter(ConsoleFormatter.default_fmt).format(make_record(document_id=3))
        finally:
            request_id_var.reset(token)

        assert "[req=req-7]" in line
        assert "document_id" in line


class TestRedactingFilter:
    @pytest.mark.parametrize(
        "key",
        ["password", "gemini_api_key", "secret_key", "authorization", "refresh_token", "minio_access_key"],
    )
    def test_scrubs_sensitive_field_names(self, key):
        record = make_record(**{key: "the-real-value"})

        RedactingFilter().filter(record)

        assert getattr(record, key) == "***REDACTED***"

    def test_leaves_ordinary_fields_alone(self):
        record = make_record(document_id=3, project_id="ocean-park-3")

        RedactingFilter().filter(record)

        assert record.document_id == 3
        assert record.project_id == "ocean-park-3"


class TestSetupLogging:
    def test_does_not_disable_existing_loggers(self):
        """uvicorn configures its loggers before importing the app; they must survive."""
        existing = logging.getLogger("uvicorn.error")

        setup_logging()

        assert existing.disabled is False

    def test_uvicorn_access_is_silenced(self):
        """Our middleware emits a better access line; uvicorn's would duplicate it."""
        config = build_config("INFO", use_json=True)

        assert config["loggers"]["uvicorn.access"]["handlers"] == []

    def test_audit_logger_is_pinned_to_info(self):
        """LOG_LEVEL=WARNING in production must not switch off the audit trail."""
        config = build_config("WARNING", use_json=True)

        assert config["loggers"]["salesmate.audit"]["level"] == "INFO"

    @pytest.mark.parametrize("name", ["httpx", "qdrant_client", "sqlalchemy.engine", "urllib3"])
    def test_noisy_third_party_loggers_are_capped(self, name):
        assert build_config("DEBUG", use_json=True)["loggers"][name]["level"] == "WARNING"

    def test_logs_go_to_stdout(self):
        """Collectors treat stderr as errors regardless of the level field."""
        assert build_config("INFO", use_json=True)["handlers"]["default"]["stream"] == "ext://sys.stdout"

    @pytest.mark.parametrize(
        ("use_json", "expected"),
        [(True, "json"), (False, "console")],
    )
    def test_formatter_follows_the_json_flag(self, use_json, expected):
        assert build_config("INFO", use_json)["handlers"]["default"]["formatter"] == expected
