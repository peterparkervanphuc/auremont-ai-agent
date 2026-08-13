from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.models.conflict_flag import ConflictFlag
from backend.models.document import Document

router = APIRouter(prefix="/admin/stats", tags=["Admin Stats"], dependencies=[Depends(require_role(UserRole.ADMIN))])

TREND_DAYS = 14


def _cumulative_counts(created_dates: list[date], days: int) -> list[int]:
    """Tổng số dòng đã tồn tại tính đến hết mỗi ngày, dùng cho biểu đồ tăng trưởng."""
    start = date.today() - timedelta(days=days - 1)
    per_day: dict[date, int] = {}
    for d in created_dates:
        per_day[d] = per_day.get(d, 0) + 1

    running = sum(count for d, count in per_day.items() if d < start)
    result = []
    for i in range(days):
        day = start + timedelta(days=i)
        running += per_day.get(day, 0)
        result.append(running)
    return result


def _open_conflicts_trend(rows: list[tuple[date, date | None]], days: int) -> list[int]:
    """Số cảnh báo còn mở tính đến hết mỗi ngày (đã tạo, chưa được resolve tới thời điểm đó)."""
    start = date.today() - timedelta(days=days - 1)
    result = []
    for i in range(days):
        day = start + timedelta(days=i)
        open_count = sum(1 for created, resolved in rows if created <= day and (resolved is None or resolved > day))
        result.append(open_count)
    return result


@router.get("/trends")
async def get_admin_trends(db: Session = Depends(get_db)) -> dict:
    """Sparkline data cho AdminHome — chỉ tính trên field có sẵn (created_at/resolved_at),
    không suy diễn số liệu cho faithfulness/relevancy vì pipeline eval chưa được cài đặt thật."""
    doc_dates = [row[0].date() for row in db.query(Document.created_at).all()]
    conflict_rows = [
        (row[0].date(), row[1].date() if row[1] else None)
        for row in db.query(ConflictFlag.created_at, ConflictFlag.resolved_at).all()
    ]

    return {
        "documents": _cumulative_counts(doc_dates, TREND_DAYS),
        "open_conflicts": _open_conflicts_trend(conflict_rows, TREND_DAYS),
    }
