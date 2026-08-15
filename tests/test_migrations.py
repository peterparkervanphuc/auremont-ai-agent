"""Migration phải luôn khớp với model.

Nếu ai đó sửa model mà quên tạo revision, `alembic upgrade head` trên môi trường
mới sẽ dựng ra schema thiếu cột — và lỗi chỉ nổ lúc chạy thật. Test này bắt
tình huống đó ngay từ CI.
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect

from backend.core.mysql_client import Base
from backend.models import (  # noqa: F401  (đăng ký bảng vào Base.metadata)
    audit_log,
    chat_session,
    conflict_flag,
    document,
    document_relation,
    feedback,
    hitl_log,
    message,
    project,
    user,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 8 bảng nghiệp vụ; hitl_logs là audit trail bắt buộc của luồng HITL.
EXPECTED_TABLES = {
    "users",
    "projects",
    "documents",
    "chat_sessions",
    "messages",
    "feedback",
    "hitl_logs",
    "conflict_flags",
    "document_relations",
}


@pytest.fixture
def migrated_db(tmp_path):
    """Chạy `alembic upgrade head` lên một SQLite trống."""
    db_path = tmp_path / "migrated.db"
    url = f"sqlite:///{db_path}"

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    # migrations/env.py gọi fileConfig(config.config_file_name), mà fileConfig mặc
    # định disable_existing_loggers=True — nó vô hiệu hóa MỌI logger đã tạo trước
    # đó, khiến các test chạy sau không bắt được log nào nữa. Bỏ trống tên file
    # cấu hình để env.py giữ nguyên logging của process (đây là cách dùng Alembic
    # theo kiểu programmatic; nội dung migration không bị ảnh hưởng).
    config.config_file_name = None
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    # env.py ưu tiên `sqlalchemy.url` từ Config, nên test không đụng tới .env thật.
    config.set_main_option("sqlalchemy.url", url)

    engine = create_engine(url)
    try:
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()


def test_migration_creates_every_business_table(migrated_db):
    tables = set(inspect(migrated_db).get_table_names())
    missing = EXPECTED_TABLES - tables
    assert not missing, f"Migration thiếu bảng: {sorted(missing)}"


def test_hitl_audit_trail_keeps_who_what_when(migrated_db):
    """HITL log là bằng chứng Sale đã đọc & xác nhận trước khi gửi khách."""
    columns = {c["name"] for c in inspect(migrated_db).get_columns("hitl_logs")}
    for column in ("message_id", "sale_id", "status", "confirmed_content", "confirmed_at", "created_at"):
        assert column in columns, f"hitl_logs thiếu cột audit: {column}"


def test_schema_matches_models(migrated_db):
    """Không được có drift giữa migration và model."""
    with migrated_db.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        diff = compare_metadata(context, Base.metadata)

    assert diff == [], (
        "Model đã đổi nhưng chưa có migration tương ứng. "
        "Chạy: alembic revision --autogenerate -m '<mô tả>'\n"
        f"Khác biệt: {diff}"
    )
