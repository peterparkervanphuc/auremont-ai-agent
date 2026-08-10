from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.config import get_settings
from backend.core.enums import UserRole

# Import model để chúng được đăng ký vào Base.metadata (quan hệ ORM + Alembic autogenerate).
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
    admin_stats,
    auth,
    documents,
    feedback,
    hitl,
    projects,
    sale_chat,
    users,
)

# Tài khoản dùng chung cho cả team — khớp với gợi ý hiển thị ở màn hình đăng nhập
# (frontend/src/routes/sale/Login.tsx). Seed lại mỗi lần khởi động nên máy nào
# clone repo về rồi `docker compose up` cũng đăng nhập được ngay, không cần ai
# phải chia sẻ database hay chạy script tạo user thủ công.
#
# Email phải qua được EmailStr của UserResponse — tên miền .local/.test bị
# email-validator từ chối, seed vẫn tạo được user nhưng /auth/login sẽ nổ 500
# lúc serialize response.
SEED_USERS = [
    {
        "username": "sale_test",
        "email": "sale_test@salesmate.example.com",
        "password": "pass1234",
        "role": UserRole.SALE,
    },
    {
        "username": "admin_test",
        "email": "admin_test@salesmate.example.com",
        "password": "pass1234",
        "role": UserRole.ADMIN,
    },
]


def _seed_users() -> None:
    from backend.core.mysql_client import SessionLocal
    from backend.repositories.user import ensure_seed_user

    if SessionLocal is None:
        return

    db = SessionLocal()
    try:
        for seed in SEED_USERS:
            ensure_seed_user(db, **seed)
        print(f"Seeded {len(SEED_USERS)} test accounts: {', '.join(s['username'] for s in SEED_USERS)}")
    except Exception as exc:  # pragma: no cover - seed hỏng không được chặn app khởi động
        # Bảng `users` có thể chưa tồn tại nếu migration chưa chạy xong. Đây là
        # tiện ích cho dev, không phải điều kiện sống còn của service, nên chỉ log.
        db.rollback()
        print(f"Seeding test accounts failed, skipping: {exc}")
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    print(f"Starting {settings.app_name} in {settings.app_env} mode")
    # Schema do Alembic quản lý (`alembic upgrade head`), không dùng create_all:
    # create_all chỉ tạo bảng còn thiếu, không bao giờ ALTER bảng đã tồn tại, nên
    # cột thêm sau sẽ âm thầm vắng mặt cho tới khi có query nổ lỗi lúc chạy.
    _seed_users()
    yield
    print("Shutting down...")


app = FastAPI(
    title="SalesMate AI Agent",
    description="Trợ lý AI RAG cho đội Sale bất động sản — Ingestion, Retrieval, Verify, HITL.",
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
app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(sale_chat.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(hitl.router, prefix="/api/v1")
app.include_router(feedback.router, prefix="/api/v1")
app.include_router(admin_eval.router, prefix="/api/v1")
app.include_router(admin_conflicts.router, prefix="/api/v1")
app.include_router(admin_stats.router, prefix="/api/v1")
app.include_router(admin_settings.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok", "env": settings.app_env}


# Endpoint seed cho E2E — CHỈ đăng ký ở môi trường development.
# Nó tạo được tài khoản admin nên tuyệt đối không được tồn tại ở production;
# gắn vào app có điều kiện (thay vì kiểm tra bên trong hàm) để ở production route
# này không hề có mặt, kể cả khi ai đó dò đúng đường dẫn.
if settings.app_env == "development":
    from fastapi import Depends, HTTPException, status
    from pydantic import BaseModel, EmailStr
    from sqlalchemy.orm import Session

    from backend.core.mysql_client import get_db
    from backend.repositories.user import create_user, get_user_by_username

    class _SeedUserRequest(BaseModel):
        username: str
        # EmailStr để seed dùng đúng luật với UserResponse: nếu nhận email mà
        # response model từ chối (vd. tên miền .local), user tạo ra sẽ đăng nhập
        # được nhưng /auth/login nổ 500 lúc serialize.
        email: EmailStr
        password: str
        role: str = "sale"

    @app.post("/__test__/users", status_code=201, include_in_schema=False)
    async def seed_test_user(payload: _SeedUserRequest, db: Session = Depends(get_db)) -> dict:
        if payload.role not in ("sale", "admin"):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="role must be 'sale' or 'admin'")

        existing = get_user_by_username(db, payload.username)
        if existing is not None:
            return {"id": existing.id, "username": existing.username, "role": existing.role, "created": False}

        user = create_user(
            db,
            username=payload.username,
            email=payload.email,
            password=payload.password,
            role=payload.role,
        )
        return {"id": user.id, "username": user.username, "role": user.role, "created": True}

