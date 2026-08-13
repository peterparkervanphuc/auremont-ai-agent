"""Application logging: one JSON object per line in production, readable text in dev.

Everything is stdlib `logging` — no extra dependency. Three pieces:

* `JsonFormatter` / `ConsoleFormatter` — the two output shapes.
* `RedactingFilter` — a last-resort scrub for secrets that slip into `extra`.
* `setup_logging()` — the single `dictConfig` call that owns the whole tree.

Two rules that this file exists to enforce:

* **Logging must never break a request.** The formatter tolerates unserialisable
  values (`default=str`) rather than raising while formatting a record.
* **Everything goes to stdout**, never stderr. Log collectors treat any stderr
  line as an error regardless of the `level` field inside it, which would make
  every INFO line look like an incident.
"""

import json
import logging
import logging.config
from datetime import UTC, datetime

from backend.core.context import get_request_id

# Attributes every LogRecord carries. Anything outside this set arrived via
# `extra={...}` at the call site and is worth emitting as its own JSON field.
# Built by introspecting a throwaway record so it cannot drift from the stdlib.
_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "taskName",  # 3.12+; harmless to list on 3.11
}

# Third-party loggers that are chatty at INFO/DEBUG and drown out our own lines.
# httpx logs every outbound Gemini/inventory call; sqlalchemy.engine logs every
# statement; qdrant_client logs each request.
_NOISY_LOGGERS = (
    "httpx",
    "httpcore",
    "qdrant_client",
    "urllib3",
    "sqlalchemy.engine",
    "google_genai",
    "python_multipart",
    "minio",
)


class RedactingFilter(logging.Filter):
    """Scrub `extra` fields whose *name* suggests a secret.

    This is a safety net, not the primary defence — the real rule is that call
    sites never pass secrets to the logger at all. Two honest limits:

    * A handler-level filter only sees records that reach that handler.
    * It inspects field **names**, not the interpolated message body, so a secret
      f-stringed into the message text passes straight through.
    """

    SENSITIVE = (
        "password",
        "passwd",
        "token",
        "secret",
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "access_key",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(record.__dict__):
            if any(marker in key.lower() for marker in self.SENSITIVE):
                record.__dict__[key] = "***REDACTED***"
        return True


def _extra_fields(record: logging.LogRecord) -> dict:
    return {key: value for key, value in record.__dict__.items() if key not in _RESERVED and not key.startswith("_")}


class JsonFormatter(logging.Formatter):
    """One JSON object per line, for log collectors."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func": record.funcName,
            "line": record.lineno,
            "request_id": get_request_id(),
        }
        payload.update(_extra_fields(record))

        if record.exc_info:
            exc_type = record.exc_info[0]
            payload["exc_type"] = exc_type.__name__ if exc_type else None
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # ensure_ascii=False: messages in this codebase are Vietnamese, and
        # \u-escaping every one of them makes `docker compose logs` unreadable.
        # default=str: UUID/datetime/Decimal/ORM objects must not raise here.
        return json.dumps(payload, ensure_ascii=False, default=str)


class ConsoleFormatter(logging.Formatter):
    """Human-readable single line for local development."""

    default_fmt = "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d [req=%(request_id)s] %(message)s"

    def format(self, record: logging.LogRecord) -> str:
        # The format string references request_id, so it must exist on the record.
        record.request_id = get_request_id()
        base = super().format(record)

        extras = {key: value for key, value in _extra_fields(record).items() if key != "request_id"}
        if extras:
            base = f"{base} {extras}"
        if record.exc_info:
            base = f"{base}\n{self.formatException(record.exc_info)}"
        return base


def build_config(level: str, use_json: bool) -> dict:
    """The dictConfig payload. Split out so tests can inspect it without applying it."""
    level = level.upper()
    formatter = "json" if use_json else "console"

    return {
        "version": 1,
        # Critical: uvicorn configures its own loggers *before* importing this app.
        # Disabling existing loggers here would silence uvicorn entirely.
        "disable_existing_loggers": False,
        "filters": {
            "redact": {"()": "backend.core.logging_config.RedactingFilter"},
        },
        "formatters": {
            "json": {"()": "backend.core.logging_config.JsonFormatter"},
            "console": {
                "()": "backend.core.logging_config.ConsoleFormatter",
                "format": ConsoleFormatter.default_fmt,
                "datefmt": "%H:%M:%S",
            },
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": formatter,
                "filters": ["redact"],
                "stream": "ext://sys.stdout",
            },
        },
        "root": {"level": level, "handlers": ["default"]},
        "loggers": {
            # Application modules use getLogger(__name__) -> "backend.*", which
            # falls under root. These explicit entries exist so audit events can
            # later be routed to their own sink by editing one entry.
            "salesmate": {"level": level, "handlers": ["default"], "propagate": False},
            # Pinned at INFO on purpose: LOG_LEVEL=WARNING in production must not
            # silently switch off the compliance trail.
            "salesmate.audit": {"level": "INFO", "handlers": ["default"], "propagate": False},
            "uvicorn": {"level": level, "handlers": ["default"], "propagate": False},
            "uvicorn.error": {"level": level, "handlers": ["default"], "propagate": False},
            # Silenced: RequestContextMiddleware emits a strictly better access
            # line (request_id + duration_ms). Leaving this on would double every
            # request in the log.
            "uvicorn.access": {"level": "WARNING", "handlers": [], "propagate": False},
            **{name: {"level": "WARNING"} for name in _NOISY_LOGGERS},
        },
    }


def setup_logging(settings=None) -> None:
    """Configure the logging tree. Safe to call more than once."""
    # Local import: config.py must not import this module at load time.
    from backend.core.config import get_settings

    settings = settings or get_settings()
    logging.config.dictConfig(build_config(settings.log_level, bool(settings.log_json)))
