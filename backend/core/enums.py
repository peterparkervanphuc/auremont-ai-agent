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

class DocumentCategory(StrEnum):
    """Nhóm nghiệp vụ của tài liệu trong kho tri thức."""

    SALES_POLICY = "sales_policy"
    PRICE_LIST = "price_list"
    INVENTORY_SNAPSHOT = "inventory_snapshot"
    SUBDIVISION_INFO = "subdivision_info"
    BUILDING_INFO = "building_info"
    FLOOR_PLAN = "floor_plan"
    PAYMENT_SCHEDULE = "payment_schedule"
    PROMOTION = "promotion"
    LEGAL_DOCUMENT = "legal_document"
    CONTRACT_TEMPLATE = "contract_template"
    INTERNAL_GUIDE = "internal_guide"
    OTHER = "other"


class DocumentReviewStatus(StrEnum):
    """Kết quả duyệt phân loại của Admin."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class LegalStatus(StrEnum):
    """Chỉ áp dụng khi category là LEGAL_DOCUMENT."""

    UNKNOWN = "unknown"
    NOT_YET_EFFECTIVE = "not_yet_effective"
    EFFECTIVE = "effective"
    EXPIRED = "expired"
    REPEALED = "repealed"
    REPLACED = "replaced"


class DocumentRelationType(StrEnum):
    """Quan hệ giữa tài liệu mới và tài liệu đã tồn tại."""

    REPLACES = "replaces"
    AMENDS = "amends"
    REPEALS = "repeals"
    UPDATES = "updates"
    SUPERSEDES = "supersedes"
    GUIDES = "guides"
    RELATED_TO = "related_to"