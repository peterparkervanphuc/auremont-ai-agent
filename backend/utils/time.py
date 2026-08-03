from datetime import UTC, datetime


def utcnow() -> datetime:
    """Thời điểm hiện tại theo UTC, dạng naive — thay cho `datetime.utcnow()` đã deprecated.

    Các cột thời gian trong `backend/models/` đều khai `DateTime` không kèm timezone,
    nên phải trả về naive: gán một datetime aware vào cột naive khiến MySQL lặng lẽ
    cắt tzinfo, còn so sánh naive với aware trong Python thì nổ TypeError. Bỏ tzinfo
    ngay tại đây giữ cho toàn hệ thống chỉ có đúng một quy ước: naive = UTC.
    """
    return datetime.now(UTC).replace(tzinfo=None)
