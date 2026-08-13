"""Tests for the business-event audit trail."""

import logging

from backend.core.audit import log_event, truncate


def test_event_lands_on_the_audit_logger(capture_logs):
    log_event("sale.query", session_id=7, verifier_score=0.91)

    record = capture_logs.event("sale.query")
    assert record.name == "salesmate.audit"
    assert record.levelno == logging.INFO
    assert record.audit is True
    assert record.session_id == 7
    assert record.verifier_score == 0.91


def test_event_name_is_both_message_and_field(capture_logs):
    log_event("auth.logout", user_id=1)

    record = capture_logs.event("auth.logout")
    assert record.getMessage() == "auth.logout"


def test_survives_a_field_name_that_collides_with_logrecord(capture_logs):
    """`filename` is a LogRecord attribute; passing it raw drops the whole event."""
    log_event("document.upload", filename="bang-gia.pdf", document_id=3)

    record = capture_logs.event("document.upload")
    assert record.field_filename == "bang-gia.pdf"
    assert record.document_id == 3
    # The real source filename is untouched.
    assert record.filename.endswith(".py")


def test_never_raises_on_an_unserialisable_field():
    class Hostile:
        def __repr__(self):
            raise RuntimeError("nope")

    log_event("weird.event", obj=Hostile())  # must not raise


def test_audit_survives_a_raised_root_level(capture_logs):
    """Production at LOG_LEVEL=WARNING must not switch off the compliance trail."""
    root = logging.getLogger()
    previous = root.level
    root.setLevel(logging.ERROR)
    try:
        log_event("hitl.confirm", message_id=5)
    finally:
        root.setLevel(previous)

    assert capture_logs.events("hitl.confirm")


class TestTruncate:
    def test_returns_none_unchanged(self):
        assert truncate(None) is None

    def test_leaves_short_text_alone(self):
        assert truncate("giá căn 2PN?") == "giá căn 2PN?"

    def test_caps_long_text(self):
        result = truncate("x" * 500)

        assert len(result) == 201
        assert result.endswith("…")
