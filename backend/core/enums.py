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


class MessageSender(StrEnum):
    CUSTOMER = "customer"
    SALE = "sale"
    AGENT = "agent"


class HitlStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class ConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"
