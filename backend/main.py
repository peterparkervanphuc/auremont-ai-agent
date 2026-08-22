import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.core.bootstrap_data import load_demo_data
from backend.core.config import get_settings
from backend.core.logging_config import setup_logging
from backend.core.seed import seed_projects, seed_users
from backend.middleware.logging import RequestContextMiddleware

# Importing the models registers them on Base.metadata (ORM relationships +
# Alembic autogenerate).
from backend.models import (  # noqa: F401
    chat_session,
    conflict_flag,
    document,
    document_relation,
    hitl_log,
    message,
    observability,
    project,
    user,
)
from backend.models import feedback as feedback_model  # noqa: F401
from backend.routers import (
    admin_conflicts,
    admin_eval,
    admin_observability,
    admin_sales,
    admin_settings,
    admin_stats,
    auth,
    customer_chat,
    dev_seed,
    document_relations,
    documents,
    feedback,
    hitl,
    projects,
    sale_chat,
    sale_live,
    users,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info(
        "Khoi dong %s (%s)",
        settings.app_name,
        settings.app_env,
        extra={"event": "app.startup", "app_name": settings.app_name, "app_env": settings.app_env},
    )
    # The schema is owned by Alembic (`alembic upgrade head`), not create_all:
    # create_all only adds missing tables and never ALTERs existing ones, so a
    # column added later would silently be absent until a query blew up at runtime.
    seed_users()
    seed_projects()
    # Project images + catalogue: runs after seeding because it upserts on top of
    # the seeded project. Never raises — see backend/core/bootstrap_data.py.
    load_demo_data()
    yield
    logger.info("Dang tat ung dung.", extra={"event": "app.shutdown"})


# Import time, not lifespan: uvicorn configures logging before importing this
# module, so ours has to run afterwards to win. The test suite also imports the
# app without entering lifespan.
setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(
    title="SalesMate AI Agent",
    description="Trợ lý AI RAG cho đội Sale bất động sản — Ingestion, Retrieval, Verify, HITL.",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
# Starlette wraps middleware in reverse order of registration, so whatever is
# added last ends up outermost. RequestContextMiddleware is registered first so
# it sits *inside* CORS: the contextvar is then set in the same task as the
# endpoint, and CORS preflight rejections do not generate access-log noise.
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Without this the browser cannot read the id back, so a frontend bug report
    # cannot quote the id needed to find the matching server logs.
    expose_headers=["X-Request-ID"],
)

# Internal (Sale/Admin)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(document_relations.router, prefix="/api/v1")
app.include_router(sale_chat.router, prefix="/api/v1")
app.include_router(sale_live.router, prefix="/api/v1")
app.include_router(hitl.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(admin_eval.router, prefix="/api/v1")
app.include_router(admin_conflicts.router, prefix="/api/v1")
app.include_router(admin_stats.router, prefix="/api/v1")
app.include_router(admin_sales.router, prefix="/api/v1")
app.include_router(admin_observability.router, prefix="/api/v1")
app.include_router(admin_settings.router, prefix="/api/v1")

# Public (anonymous visitors + logged-in CUSTOMER accounts) — see backend/routers/customer_chat.py
app.include_router(customer_chat.router, prefix="/api/v1")

# Seeding endpoint for E2E — registered ONLY in development. See backend/routers/dev_seed.py.
if settings.app_env == "development":
    app.include_router(dev_seed.router)


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


# --------------------------------------------------------------------------- error handling


def _request_id_of(request: Request) -> str:
    """Read the id from request state, not the contextvar.

    These handlers run inside `ServerErrorMiddleware`, which sits *outside*
    RequestContextMiddleware — by the time an unhandled exception reaches here
    the contextvar has already been reset in that middleware's `finally`.
    """
    return getattr(request.state, "request_id", "")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Log intentional HTTP errors, preserving FastAPI's response shape exactly.

    Registered against the Starlette class rather than `fastapi.HTTPException`:
    routing-level 404s are raised by Starlette itself, and registering the
    FastAPI subclass would leave those unlogged.
    """
    logger.warning(
        "%s %s -> %s",
        request.method,
        request.url.path,
        exc.status_code,
        extra={
            "event": "http.error",
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method,
            "detail": exc.detail,
            "request_id": _request_id_of(request),
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        # Dropping these would break OAuth2: auth.py sets WWW-Authenticate on 401.
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """422 handler that keeps FastAPI's body shape but never logs the input value.

    pydantic v2 puts the offending value in `errors()[*]["input"]`, so logging
    the errors verbatim would write a malformed password or refresh token
    straight into the log. Only the location, type and message are recorded.
    """
    safe_errors = [
        {"loc": error.get("loc"), "type": error.get("type"), "msg": error.get("msg")} for error in exc.errors()
    ]
    logger.warning(
        "Invalid request: %s %s",
        request.method,
        request.url.path,
        extra={
            "event": "http.validation_error",
            "status_code": 422,
            "path": request.url.path,
            "method": request.method,
            "errors": safe_errors,
            "request_id": _request_id_of(request),
        },
    )
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last resort: log the full traceback, return a generic body.

    The client gets the request id and nothing else — exception text can carry
    connection strings, file paths and query fragments. The id is what lets a
    user's bug report be matched to the traceback in the logs.
    """
    request_id = _request_id_of(request)
    logger.exception(
        "Unhandled error: %s %s",
        request.method,
        request.url.path,
        extra={
            "event": "http.unhandled_error",
            "status_code": 500,
            "path": request.url.path,
            "method": request.method,
            "request_id": request_id,
        },
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": request_id})
