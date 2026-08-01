from enum import StrEnum


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class DocumentVisibility(StrEnum):
    """RBAC tier: INTERNAL is visible to Sale/Admin only, PUBLIC is visible to the customer Chatbot."""

    INTERNAL = "internal"
    PUBLIC = "public"


class UserRole(StrEnum):
    SALE = "sale"
    ADMIN = "admin"


class SessionSource(StrEnum):
    """Where a Sale consultation Session originated from."""

    SALE_INITIATED = "sale_initiated"
    LIVE_CHAT = "live_chat"


class MessageSender(StrEnum):
    CUSTOMER = "customer"
    SALE = "sale"
    AGENT = "agent"


class HitlStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class LiveChatStatus(StrEnum):
    WAITING = "waiting"
    ACTIVE = "active"
    ENDED = "ended"


class ConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class UnitStatus(StrEnum):
    """Trạng thái căn trong bảng inventory_units (CLAUDE.md §6.6)."""

    AVAILABLE = "available"
    RESERVED = "reserved"
    SOLD = "sold"
    LOCKED = "locked"
