from enum import StrEnum


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class DocumentVisibility(StrEnum):
    """RBAC tier: INTERNAL is Sale/Admin only; PUBLIC is safe for Sale to share with customers."""

    INTERNAL = "internal"
    PUBLIC = "public"


class UserRole(StrEnum):
    SALE = "sale"
    ADMIN = "admin"


class MessageSender(StrEnum):
    """Only Sale and Agent exchange messages in a session — customers never access the system."""

    SALE = "sale"
    AGENT = "agent"


class HitlStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"


class ConflictStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class FeedbackType(StrEnum):
    """A Sale's rating of an Agent answer — feeds the Admin Tab 2 dashboard."""

    HELPFUL = "helpful"
    WRONG = "wrong"  # the answer was incorrect
    INCOMPLETE = "incomplete"  # the answer was missing information
