"""Business audit trail — who did what, distinct from diagnostic logging.

These events answer questions the Admin dashboard asks (README §5.3 Tab 2):
which answers scored badly, which documents were blocked, who confirmed a
price commitment. They go to a dedicated logger pinned at INFO so raising
`LOG_LEVEL` for noise control cannot switch the trail off.

`log_event` never raises. An audit record is valuable, but not so valuable that
failing to write one should break the Sale's request that triggered it.
"""

import logging
from typing import Any

from backend.core.logging_config import AUDIT_LOGGER_NAME

_audit_logger = logging.getLogger(AUDIT_LOGGER_NAME)

DEFAULT_TRUNCATE_LIMIT = 200


def truncate(text: str | None, limit: int = DEFAULT_TRUNCATE_LIMIT) -> str | None:
    """Shorten free text for logging, marking that it was cut."""
    if text is None:
        return None
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def log_event(event: str, **fields: Any) -> None:
    """Emit one audit event. Swallows its own errors by design."""
    try:
        _audit_logger.info(event, extra={"event": event, "audit": True, **fields})
    except Exception:  # pragma: no cover - audit must never break a request
        pass
