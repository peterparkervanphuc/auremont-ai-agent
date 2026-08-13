"""Request-scoped logging: a request id in, one access line out.

Written as a **pure ASGI middleware** rather than a `BaseHTTPMiddleware`
subclass. `BaseHTTPMiddleware` runs the downstream app in a separate anyio task
connected by a memory stream, which breaks `contextvar` propagation to the
endpoint and interferes with how `ServerErrorMiddleware` sees exceptions. A pure
ASGI middleware sets the contextvar in the *same* task that runs the endpoint,
so `request_id` is reliably visible everywhere downstream — including inside the
sync services that make up the agent pipeline.
"""

import logging
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.core.context import request_id_var

logger = logging.getLogger("salesmate.access")

REQUEST_ID_HEADER = "x-request-id"

# The Dockerfile HEALTHCHECK hits /health every 30s. At INFO those lines would be
# the overwhelming majority of the log and would bury everything that matters,
# so they drop to DEBUG.
QUIET_PATHS = frozenset({"/health", "/favicon.ico"})


def _client_ip(scope: Scope, headers: Headers) -> str | None:
    """Caller IP, preferring the proxy header since deployments sit behind one."""
    forwarded = headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()

    client = scope.get("client")
    return client[0] if client else None


def _access_level(status_code: int, path: str) -> int:
    if status_code >= 500:
        return logging.ERROR
    if path in QUIET_PATHS:
        return logging.DEBUG
    if status_code >= 400:
        return logging.WARNING
    return logging.INFO


class RequestContextMiddleware:
    """Assign a request id, expose it to logs and the client, and log the request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        # Honour an inbound id so a trace started at the frontend or a gateway
        # survives across service boundaries.
        request_id = headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        token = request_id_var.set(request_id)

        # Also park it on the ASGI state: the unhandled-exception handler runs in
        # ServerErrorMiddleware, *outside* this middleware, by which point the
        # contextvar below has already been reset.
        scope.setdefault("state", {})["request_id"] = request_id

        start = time.perf_counter()
        # If the app raises before sending anything, ServerErrorMiddleware will
        # return a 500 — so 500 is the correct assumption, not a placeholder.
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            path = scope.get("path", "")
            method = scope.get("method", "-")
            logger.log(
                _access_level(status_code, path),
                "%s %s %s %sms",
                method,
                path,
                status_code,
                duration_ms,
                extra={
                    "event": "http.access",
                    "method": method,
                    "path": path,
                    # Only the query string; never headers — Authorization and
                    # Cookie must not reach the log.
                    "query": scope.get("query_string", b"").decode("latin-1")[:200] or None,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": _client_ip(scope, headers),
                    "user_agent": headers.get("user-agent"),
                },
            )
            request_id_var.reset(token)
