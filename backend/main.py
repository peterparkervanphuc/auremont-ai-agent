import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.core.config import get_settings
from backend.core.logging_config import setup_logging
from backend.core.seed import seed_projects, seed_users
from backend.middleware.logging import REQUEST_ID_HEADER, RequestContextMiddleware

# Importing the models registers them on Base.metadata (ORM relationships +
# Alembic autogenerate).
from backend.models import (  # noqa: F401
    chat_session,
    conflict_flag,
    document,
    hitl_log,
    message,
    project,
    user,
)
from backend.models import feedback as feedback_model  # noqa: F401
from backend.routers import (
    admin_conflicts,
    admin_eval,
    admin_settings,
    auth,
    dev_seed,
    documents,
    feedback,
    hitl,
    projects,
    sale_chat,
    users,
)

# Configure logging at import time, before the app object exists. Uvicorn applies
# its own dictConfig *before* importing this module, so ours runs last and wins.
# Doing it in `lifespan` would be too late: tests import `backend.main.app`
# without ever entering lifespan, and import-time warnings would go unlogged.
setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "Starting %s in %s mode",
        settings.app_name,
        settings.app_env,
        extra={"event": "app.startup", "app_env": settings.app_env, "log_json": settings.log_json},
    )
    # The schema is owned by Alembic (`alembic upgrade head`), not create_all:
    # create_all only adds missing tables and never ALTERs existing ones, so a
    # column added later would silently be absent until a query blew up at runtime.
    seed_users()
    seed_projects()
    yield
    logger.info("Shutting down", extra={"event": "app.shutdown"})


app = FastAPI(
    title="SalesMate AI Agent",
    description="Trợ lý AI RAG cho đội Sale bất động sản — Ingestion, Retrieval, Verify, HITL.",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()

# Middleware order: Starlette builds the stack by wrapping in REVERSE order of
# registration, so whatever is added last ends up outermost. Registering the
# request-context middleware first therefore puts it *inside* CORS, which is
# what we want: the contextvar is set as close to the endpoint as possible, and
# CORS preflight OPTIONS requests are answered by CORSMiddleware before reaching
# us, keeping preflight noise out of the access log.
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Without this the browser cannot read the id to quote in a bug report,
    # which is half the point of echoing it back.
    expose_headers=[REQUEST_ID_HEADER],
)


def _request_id_of(request: Request) -> str:
    """Read the id from the ASGI state, not the contextvar.

    Exception handlers run inside Starlette's ServerErrorMiddleware, which sits
    *outside* RequestContextMiddleware — by the time we get here its `finally`
    has already reset the contextvar.
    """
    return getattr(request.state, "request_id", "-")


# Registered against the Starlette class, not fastapi.HTTPException. FastAPI's
# subclasses Starlette's, and 404s raised by the router are the Starlette kind;
# registering the subclass would leave those going to the default handler
# unlogged.
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Deliberate, expected failures (401/404/413...). A warning, never a traceback."""
    logger.warning(
        "HTTP %s on %s %s",
        exc.status_code,
        request.method,
        request.url.path,
        extra={
            "event": "http.error",
            "status_code": exc.status_code,
            "method": request.method,
            "path": request.url.path,
            "detail": str(exc.detail),
        },
    )
    # `headers` must be preserved: auth.py sets WWW-Authenticate on its 401 and
    # dropping it silently breaks the OAuth2 flow.
    return JSONResponse(
        {"detail": exc.detail},
        status_code=exc.status_code,
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning(
        "Validation failed on %s %s",
        request.method,
        request.url.path,
        extra={
            "event": "http.validation_error",
            "method": request.method,
            "path": request.url.path,
            # Deliberately drops pydantic's "input" key: it echoes the offending
            # value, which for RefreshRequest would put a refresh token in the log.
            "errors": [
                {"loc": error.get("loc"), "type": error.get("type"), "msg": error.get("msg")} for error in exc.errors()
            ],
        },
    )
    # The response keeps FastAPI's exact 422 shape — the frontend parses it.
    return JSONResponse(
        {"detail": jsonable_encoder(exc.errors())},
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort: log the full traceback, tell the client nothing beyond an id."""
    logger.exception(
        "Unhandled exception on %s %s",
        request.method,
        request.url.path,
        extra={"event": "http.unhandled", "method": request.method, "path": request.url.path},
    )
    # No exception text in the body — it can leak internals. The request_id is
    # what lets support find the traceback in the log.
    return JSONResponse(
        {"detail": "Internal server error", "request_id": _request_id_of(request)},
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


# Internal (Sale/Admin)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(sale_chat.router, prefix="/api/v1")
app.include_router(hitl.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(admin_eval.router, prefix="/api/v1")
app.include_router(admin_conflicts.router, prefix="/api/v1")
app.include_router(admin_settings.router, prefix="/api/v1")

# Seeding endpoint for E2E — registered ONLY in development. See backend/routers/dev_seed.py.
if settings.app_env == "development":
    app.include_router(dev_seed.router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}
