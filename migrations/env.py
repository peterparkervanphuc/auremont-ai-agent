"""Alembic environment.

Lấy connection string và metadata trực tiếp từ app, để migration không bao giờ
lệch với `backend/core/config.py` hay danh sách model đang dùng.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from backend.core.config import get_settings
from backend.core.mysql_client import Base

# Import để mọi bảng được đăng ký vào Base.metadata trước khi autogenerate chạy;
# thiếu một dòng ở đây thì Alembic sẽ tưởng bảng đó bị xoá.
from backend.models import (  # noqa: F401
    audit_log,
    chat_session,
    conflict_flag,
    customer_conversation_summary,
    document,
    document_relation,
    feedback,
    hitl_log,
    message,
    news_article,
    observability,
    project,
    user,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def get_url() -> str:
    # `sqlalchemy.url` đặt qua Config (test dùng SQLite tạm) được ưu tiên; ngoài
    # ra luôn lấy từ settings để migration và app dùng chung một nguồn cấu hình.
    override = config.get_main_option("sqlalchemy.url")
    if override:
        return override

    settings = get_settings()
    return settings.database_url or "sqlite:///./data/app.db"


def run_migrations_offline() -> None:
    """Sinh SQL ra stdout mà không cần kết nối DB (`alembic upgrade --sql`)."""
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Chạy migration trực tiếp trên DB."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = get_url()

    connectable = engine_from_config(configuration, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Bắt cả thay đổi kiểu cột, không chỉ thêm/xoá cột.
            compare_type=True,
            # SQLite không ALTER được cột — batch mode dựng bảng tạm rồi copy.
            render_as_batch=connection.dialect.name == "sqlite",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
