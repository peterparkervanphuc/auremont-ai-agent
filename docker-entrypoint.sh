#!/bin/sh
# Đưa schema lên bản mới nhất trước khi app nhận request.
#
# Container chỉ khởi động sau khi MySQL báo healthy (depends_on trong
# docker-compose.yml), nên tới bước này DB đã sẵn sàng. Nếu migration lỗi thì
# dừng hẳn — chạy app trên schema cũ sẽ hỏng theo kiểu khó lần ra hơn nhiều.
set -e

echo "[entrypoint] Applying database migrations..."
alembic upgrade head

echo "[entrypoint] Starting application..."
exec "$@"
