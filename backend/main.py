from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_settings
from backend.routers import auth, documents, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    yield
    print("Shutting down...")


app = FastAPI(
    title="AI20K Project",
    description="AI-powered application built with LangGraph and FastAPI",
    version="1.0.0",
    lifespan=lifespan,
)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(documents.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}

