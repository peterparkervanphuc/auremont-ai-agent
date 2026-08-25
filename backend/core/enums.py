from enum import StrEnum


class DocumentStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"


class DocumentBlockReason(StrEnum):
    PROMPT_INJECTION = "prompt_injection"
    DUPLICATE_CONTENT = "duplicate_content"
    LEGACY_UNKNOWN = "legacy_unknown"


class DocumentVisibility(StrEnum):
    """RBAC tier: INTERNAL is Sale/Admin only; PUBLIC is safe for Sale to share with customers."""

    INTERNAL = "internal"
    PUBLIC = "public"


class UserRole(StrEnum):
    SALE = "sale"
    ADMIN = "admin"
    # A public visitor who registered/logged in through the customer chat gate. Always
    # retrieves at DocumentVisibility.PUBLIC clearance — see agent_pipeline.run_pipeline.
    CUSTOMER = "customer"


class MessageSender(StrEnum):
    """Sale, Agent, or a Customer chatting directly through the public/customer flow."""

    SALE = "sale"
    AGENT = "agent"
    CUSTOMER = "customer"


class MessageEmotion(StrEnum):
    """Drives AuremontAvatar.tsx's animation for one AGENT-authored message — computed
    deterministically from the pipeline/gate outcome already available, never a separate
    LLM call (matches this codebase's classifier style — see backend/ai/intent.py). Unset
    on a message defaults to a neutral "idle" pose on the frontend.
    """

    HAPPY = "happy"
    REGRETFUL = "regretful"
    RESPECTFUL = "respectful"


class SessionStatus(StrEnum):
    """Who is currently answering a customer-chat session — see ChatSession's docstring
    for how this interacts with the sale_id/customer_id/visitor_token ownership columns.
    """

    BOT_HANDLING = "bot_handling"
    WAITING_SALE = "waiting_sale"
    SALE_HANDLING = "sale_handling"


class SessionChannel(StrEnum):
    """Which conversation a customer session holds. A customer has at most one of each, and
    they are deliberately separate rows rather than one thread split by a timestamp: a Sale
    is never shown the AI conversation (`GET /sale-live/{id}/messages` can only ever read the
    session it was handed), so the isolation survives any future endpoint that forgets to
    filter. See ChatSession's docstring.
    """

    AI = "ai"
    LIVE = "live"


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
    """Business grouping of a document in the knowledge base."""

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
    """Outcome of the Admin's review of a proposed classification."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class LegalStatus(StrEnum):
    """Only meaningful when the category is LEGAL_DOCUMENT."""

    UNKNOWN = "unknown"
    NOT_YET_EFFECTIVE = "not_yet_effective"
    EFFECTIVE = "effective"
    EXPIRED = "expired"
    REPEALED = "repealed"
    REPLACED = "replaced"


class DocumentRelationType(StrEnum):
    """How a new document relates to one already in the knowledge base."""

    REPLACES = "replaces"
    AMENDS = "amends"
    REPEALS = "repeals"
    UPDATES = "updates"
    SUPERSEDES = "supersedes"
    GUIDES = "guides"
    RELATED_TO = "related_to"
