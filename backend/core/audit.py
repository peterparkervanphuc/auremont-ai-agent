"""Business-event audit trail on a dedicated logger.

Separate from diagnostic logging on purpose. These lines answer *who did what*,
are always INFO, and are pinned to INFO in `logging_config` so that running
production at `LOG_LEVEL=WARNING` cannot silently switch off the trail. Routing
them to their own sink later (a file, a SIEM) means editing one entry in the
dictConfig rather than touching any call site.

Every event carries the `request_id` through the formatter, so an audit line
joins to its access line and to any traceback from the same request.

**What must never appear here**: passwords or hashes, JWTs (not even a prefix),
the HITL confirmed content going to a customer, document file contents, or any
inventory field *value*. Truncate free text with `truncate()`.
"""

import logging

_audit = logging.getLogger("salesmate.audit")

_MAX_TEXT = 200

# `logging` raises KeyError if `extra` carries a name LogRecord already uses, and
# the whole event is then lost. `filename` is the one that bites in practice —
# it is a natural name for a document upload and also LogRecord's source file.
# Colliding names are prefixed rather than dropped, so no field is ever silently
# discarded.
_RESERVED_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",
}


def _safe_fields(fields: dict) -> dict:
    return {(f"field_{key}" if key in _RESERVED_RECORD_ATTRS else key): value for key, value in fields.items()}


def log_event(event: str, **fields: object) -> None:
    """Emit one audit record. Never raises — auditing must not break a request."""
    try:
        # The event name is both the message and a queryable field: the console
        # formatter then reads naturally, and the JSON has a stable `event` key.
        _audit.info(event, extra={"event": event, "audit": True, **_safe_fields(fields)})
    except Exception:  # pragma: no cover - defensive; logging must never propagate
        _audit.warning("Audit event failed to emit", extra={"event": "audit.failed", "failed_event": event})


def truncate(text: str | None, limit: int = _MAX_TEXT) -> str | None:
    """Cap free text so one long input cannot dominate the log."""
    if text is None:
        return None
    return text if len(text) <= limit else text[:limit] + "…"
