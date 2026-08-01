from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_settings
from backend.routers import (
    admin_conflicts,
    admin_eval,
    admin_settings,
    auth,
    chatbot,
    customer_auth,
    documents,
    hitl,
    inventory,
    livechat,
    sale_chat,
    users,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    yield
    print("Shutting down...")


app = FastAPI(
    title="SalesMate AI Agent",
    description="Trợ lý AI RAG cho đội Sale bất động sản — Customer Portal, Chatbot, Live Chat, HITL.",
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

# Internal (Sale/Admin)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(documents.router, prefix="/api/v1")
app.include_router(sale_chat.router, prefix="/api/v1")
app.include_router(hitl.router, prefix="/api/v1")
app.include_router(admin_eval.router, prefix="/api/v1")
app.include_router(admin_conflicts.router, prefix="/api/v1")
app.include_router(admin_settings.router, prefix="/api/v1")
app.include_router(inventory.admin_router, prefix="/api/v1")

# Public (Customer Portal / Chatbot / Live Chat)
app.include_router(inventory.public_router, prefix="/api/v1")
app.include_router(customer_auth.router, prefix="/api/v1")
app.include_router(chatbot.router, prefix="/api/v1")
app.include_router(livechat.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}

