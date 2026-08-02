from enum import StrEnum


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class DocumentVisibility(StrEnum):
    """RBAC tier: INTERNAL chỉ Sale/Admin xem; PUBLIC là tài liệu Sale được phép chia sẻ cho khách."""

    INTERNAL = "internal"
    PUBLIC = "public"


class UserRole(StrEnum):
    SALE = "sale"
    ADMIN = "admin"


class MessageSender(StrEnum):
    """Chỉ Sale và Agent trao đổi trong một phiên — khách hàng không truy cập hệ thống."""

    SALE = "sale"
    AGENT = "agent"


class HitlStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class ConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class FeedbackType(StrEnum):
    """Đánh giá của Sale cho một câu trả lời của Agent — cấp dữ liệu cho Admin Tab 2."""

    HELPFUL = "helpful"
    WRONG = "wrong"  # câu trả lời sai
    INCOMPLETE = "incomplete"  # câu trả lời thiếu
