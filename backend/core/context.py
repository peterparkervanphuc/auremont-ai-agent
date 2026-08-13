"""Per-request context propagated to every log record.

Kept in its own module so `logging_config` (imported by everything) and the
middleware that sets the value never import each other.

**Threadpool note.** FastAPI runs non-async (`def`) endpoints via
`anyio.to_thread.run_sync`, which copies the current context into the worker
thread. `get_request_id()` therefore returns the right value inside sync
endpoints and inside everything they call synchronously — `run_pipeline` and all
of `backend/services/*` are sync, so the whole pipeline is covered. A value set
*inside* that thread would not propagate back out, but nothing does that.
"""

from contextvars import ContextVar, Token

# "-" rather than "" so a log line from outside any request (startup, seeding,
# a CLI script) is visibly unattributed instead of looking like a missing field.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(value: str) -> Token[str]:
    return request_id_var.set(value)


def reset_request_id(token: Token[str]) -> None:
    """Always call this in a `finally`.

    Uvicorn reuses the same task context tree across requests; without the reset a
    failed request leaves its id visible to whatever runs next.
    """
    request_id_var.reset(token)


def get_request_id() -> str:
    return request_id_var.get()
