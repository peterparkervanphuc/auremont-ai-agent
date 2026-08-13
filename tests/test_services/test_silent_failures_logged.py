"""Regression guard for failures that used to be completely invisible.

Every test asserts **two** things: the return value is unchanged (the recovery
behaviour these call sites deliberately implement) *and* a record was emitted.
The first half is what stops a future "improvement" from turning a graceful
degradation into a 500 in front of a customer.
"""

import logging

import pytest

from backend.services import cache_service, verifier_service
from backend.services.agent_pipeline import GENERATION_ERROR_MESSAGE, run_pipeline
from backend.services.inventory_service import _parse_unit, _to_float


class _SimulatedError(Exception):
    pass


def _raise(*args, **kwargs):
    raise _SimulatedError("simulated infrastructure failure")


# --------------------------------------------------------------------------- cache


def test_cache_lookup_failure_is_logged_and_returns_a_miss(monkeypatch, caplog):
    monkeypatch.setattr(cache_service, "get_qdrant_client", _raise)

    with caplog.at_level(logging.WARNING, logger="backend.services.cache_service"):
        result = cache_service.lookup_cache("gia can 2PN?", "ocean-park-3")

    assert result is None
    record = next(r for r in caplog.records if getattr(r, "event", None) == "cache.lookup.failed")
    assert record.project_id == "ocean-park-3"
    assert record.exc_info is not None


def test_cache_store_failure_is_logged_and_swallowed(monkeypatch, caplog):
    monkeypatch.setattr(cache_service, "_ensure_cache_collection", _raise)

    with caplog.at_level(logging.WARNING, logger="backend.services.cache_service"):
        assert cache_service.store_cache("q", "a", [], 0.9, "ocean-park-3") is None

    assert any(getattr(r, "event", None) == "cache.store.failed" for r in caplog.records)


# --------------------------------------------------------------------------- verifier


def test_judge_failure_is_logged_at_error_and_still_fails_closed(monkeypatch, caplog):
    """A broken Verifier and a bad answer both score 0.0 - only the log separates them."""
    monkeypatch.setattr(verifier_service, "generate_text", _raise)

    with caplog.at_level(logging.ERROR, logger="backend.services.verifier_service"):
        result = verifier_service.score_answer("gia?", "3.6 ty", ["context"])

    assert result.score == 0.0
    record = next(r for r in caplog.records if getattr(r, "event", None) == "verifier.judge.failed")
    assert record.levelno == logging.ERROR
    assert record.exc_info is not None


@pytest.mark.parametrize(
    ("raw", "event"),
    [
        ("no json at all here", "verifier.parse.no_json"),
        ("{not valid json,}", "verifier.parse.bad_json"),
    ],
)
def test_unparseable_judge_output_is_logged(monkeypatch, caplog, raw, event):
    monkeypatch.setattr(verifier_service, "generate_text", lambda *a, **k: raw)

    with caplog.at_level(logging.WARNING, logger="backend.services.verifier_service"):
        result = verifier_service.score_answer("gia?", "3.6 ty", ["context"])

    assert result.score == 0.0
    assert any(getattr(r, "event", None) == event for r in caplog.records)


def test_null_score_is_only_debug_noise(monkeypatch, caplog):
    """The model returning null is common; WARNING here would be constant noise."""
    monkeypatch.setattr(
        verifier_service,
        "generate_text",
        lambda *a, **k: '{"faithfulness": null, "relevancy": 0.9}',
    )

    with caplog.at_level(logging.DEBUG, logger="backend.services.verifier_service"):
        result = verifier_service.score_answer("gia?", "3.6 ty", ["context"])

    assert result.score == 0.0
    record = next(r for r in caplog.records if getattr(r, "event", None) == "verifier.clamp.bad_value")
    assert record.levelno == logging.DEBUG


# --------------------------------------------------------------------------- pipeline


def test_pipeline_crash_is_logged_and_still_returns_the_standard_message(monkeypatch, caplog):
    """The single most valuable log line: without it a crash is entirely invisible."""
    import backend.services.agent_pipeline as pipeline

    class _ExplodingGraph:
        def invoke(self, _state):
            raise _SimulatedError("graph exploded")

    monkeypatch.setattr(pipeline, "_get_graph", lambda: _ExplodingGraph())

    with caplog.at_level(logging.ERROR, logger="backend.services.agent_pipeline"):
        result = run_pipeline("gia can 2PN?", project_id="ocean-park-3")

    # Compare against the constant, not a hardcoded string, so rewording the
    # user-facing message cannot silently break this guard.
    assert result.draft_answer == GENERATION_ERROR_MESSAGE
    assert result.verifier_score == 0.0
    assert result.requires_hitl is False

    record = next(r for r in caplog.records if getattr(r, "event", None) == "pipeline.crash")
    assert record.project_id == "ocean-park-3"
    assert record.exc_info is not None


# --------------------------------------------------------------------------- auth


def test_rejected_token_is_logged_without_ever_including_the_token(caplog):
    """A JWT prefix is header+payload and decodes to real data - never log any of it."""
    from backend.core.security import decode_token

    token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJzYWxlX3Rlc3QifQ.invalid-signature-part"

    with caplog.at_level(logging.WARNING, logger="backend.core.security"):
        assert decode_token(token) is None

    record = next(r for r in caplog.records if getattr(r, "event", None) == "auth.token.rejected")
    assert record.reason
    assert token not in caplog.text
    assert "eyJhbGciOiJIUzI1NiJ9" not in caplog.text


# --------------------------------------------------------------------------- inventory


def test_unparseable_price_is_logged_at_debug_and_left_blank(caplog):
    with caplog.at_level(logging.DEBUG, logger="backend.services.inventory_service"):
        assert _to_float("not-a-number") is None

    assert any(getattr(r, "event", None) == "inventory.price.unparseable" for r in caplog.records)


def test_incomplete_inventory_record_logs_field_names_only(caplog):
    """Unit codes and prices are business data; only the missing field names are safe."""
    with caplog.at_level(logging.WARNING, logger="backend.services.inventory_service"):
        assert _parse_unit({"unit_code": "OP3-A-0203", "price": 3600000000}) is None

    record = next(r for r in caplog.records if getattr(r, "event", None) == "inventory.record.incomplete")
    assert set(record.missing_fields) == {"project_id", "status"}
    assert "OP3-A-0203" not in caplog.text
    assert "3600000000" not in caplog.text


def test_non_dict_inventory_record_is_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="backend.services.inventory_service"):
        assert _parse_unit("just a string") is None

    assert any(getattr(r, "event", None) == "inventory.record.not_dict" for r in caplog.records)
