"""Long-term memory — what we remember about a person across sessions.

Short-term working memory (`prompts.ConversationTurn`) covers the current thread and
lives in MySQL. This module covers the layer above it: preferences that outlive any one
conversation, so a returning customer does not have to restate a budget they mentioned
last week, and a Sale gets their own recurring topics surfaced.

Two separate namespaces, never mixed:

- `memory:customer:{id}` — one person's own preferences (budget, unit types, projects
  they keep asking about). Personal to that customer.
- `memory:sale:{id}` — a Sale's *own* recurring topics, aggregated across the customers
  they consult for. Personal to that Sale: one Sale never sees another's.

Three rules hold this together, and each exists because breaking it causes a specific
kind of wrong answer:

1. **Fail open.** Every entry point swallows its exceptions and degrades to "no profile".
   Memory is a personalisation layer, not a source of truth — a Redis outage must cost
   some convenience, never the ability to answer.
2. **Remember questions, never answers.** Facts are extracted from what the *human*
   typed. Storing what the model said would let one hallucinated figure harden into a
   remembered "preference" and resurface in every later session.
3. **Preferences are hints about a person, not facts about a project.** Nothing in here
   is grounding, and the prompt says so explicitly — the model must still read every
   number out of retrieved documents.
"""

import json
import logging
import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Cap on remembered items per profile. A profile is a hint, and a long one stops being
# one: it crowds the prompt and buries the current question under old context.
MAX_ITEMS_PER_FIELD = 5

# Unit types worth remembering, matched as whole tokens ("2PN", "3 PN", "studio").
UNIT_TYPE_PATTERN = re.compile(r"\b(\d\s?PN|studio|shophouse|penthouse|duplex)\b", re.IGNORECASE)

# "3,6 ty", "3.6 tỷ", "5 ty dong", "800 trieu" — the number plus its unit.
BUDGET_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*(tỷ|ty|triệu|trieu)\b", re.IGNORECASE)

# A money figure only counts as *this person's budget* when the sentence says so. Without
# this gate every price the person merely asked about was stored as their budget: "căn 2PN
# giá 3.6 tỷ có đắt không?" recorded 3.6 tỷ as what they can afford, which is the opposite
# of what the question means. A missed budget costs a little personalisation; an invented
# one quietly reshapes how every later answer is framed.
BUDGET_CONTEXT_PATTERN = re.compile(
    r"(ngân\s*sách|ngan\s*sach|tài\s*chính|tai\s*chinh|budget"
    r"|tầm\s*giá|tam\s*gia|khoảng\s*giá|khoang\s*gia|trong\s*tầm|trong\s*tam"
    r"|có\s*sẵn|co\s*san|dư\s*(?:khoảng|chừng)?|du\s*(?:khoang|chung)?"
    r"|chỉ\s*có|chi\s*co|tối\s*đa|toi\s*da|dưới|duoi|trên\s*dưới|tren\s*duoi"
    r"|muốn\s*mua|muon\s*mua|định\s*mua|dinh\s*mua|tìm\s*căn|tim\s*can)",
    re.IGNORECASE,
)

# Words that mark a figure as belonging to a *unit* rather than to the person, even when a
# budget word appears elsewhere in the same sentence.
PRICE_QUESTION_PATTERN = re.compile(
    r"(giá\s*(?:căn|bán|gốc|niêm)|gia\s*(?:can|ban|goc|niem)"
    r"|bao\s*nhiêu|bao\s*nhieu|có\s*đắt|co\s*dat|đắt\s*hơn|dat\s*hon|rẻ\s*hơn|re\s*hon)",
    re.IGNORECASE,
)


@dataclass
class UserProfile:
    """What we remember about one person. Every field is optional and may be empty."""

    unit_types: list[str] = field(default_factory=list)
    budgets: list[str] = field(default_factory=list)
    projects: list[str] = field(default_factory=list)
    # Free-form topics the person keeps returning to (used for the Sale namespace).
    topics: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        return not (self.unit_types or self.budgets or self.projects or self.topics)


def customer_key(customer_id: int) -> str:
    return f"memory:customer:{customer_id}"


def sale_key(sale_id: int) -> str:
    return f"memory:sale:{sale_id}"


def load_profile(key: str) -> UserProfile:
    """Read a profile. Any failure — Redis down, corrupt JSON — yields an empty profile."""
    client = get_redis_client()
    if client is None:
        return UserProfile()

    try:
        raw = client.get(key)
    except Exception:
        # WARNING not ERROR: answers are still correct, only less personalised. Logged
        # because a permanently dead Redis has no other outward symptom.
        logger.warning(
            "Doc ho so ghi nho that bai; coi nhu chua co ho so.",
            exc_info=True,
            extra={"event": "memory.load.failed", "key": key},
        )
        return UserProfile()

    if not raw:
        return UserProfile()

    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        # A corrupt value must not be fatal, and must not be read again next turn.
        logger.warning("Ho so ghi nho hong; bo qua.", extra={"event": "memory.load.corrupt", "key": key})
        return UserProfile()

    if not isinstance(data, dict):
        return UserProfile()

    return UserProfile(
        unit_types=_clean_list(data.get("unit_types")),
        budgets=_clean_list(data.get("budgets")),
        projects=_clean_list(data.get("projects")),
        topics=_clean_list(data.get("topics")),
    )


def remember(key: str, question: str, project_id: str | None = None, db: Session | None = None) -> None:
    """Fold one question into the stored profile. Never raises.

    Only the human's own words are read (see rule 2 in the module docstring). Writing is
    read-modify-write rather than atomic: two concurrent questions from the same person
    could drop one update, which costs a remembered preference and nothing more — not
    worth the complexity of a Lua script or a lock.

    `db` lets the project be recovered from the question itself when the session carries
    no `project_id`, which is now the normal case — see `_resolve_project`.
    """
    client = get_redis_client()
    if client is None or not question or not question.strip():
        return

    extracted = extract_facts(question, _resolve_project(question, project_id, db))
    if extracted.is_empty():
        return

    try:
        current = load_profile(key)
        merged = _merge(current, extracted)

        client.set(
            key,
            json.dumps(
                {
                    "unit_types": merged.unit_types,
                    "budgets": merged.budgets,
                    "projects": merged.projects,
                    "topics": merged.topics,
                },
                ensure_ascii=False,
            ),
            ex=get_settings().memory_ttl_seconds,
        )
    except Exception:
        # The answer being served is already complete; a failed write changes nothing
        # the user sees this turn.
        logger.warning(
            "Ghi ho so ghi nho that bai; cau tra loi khong bi anh huong.",
            exc_info=True,
            extra={"event": "memory.remember.failed", "key": key},
        )


def forget(key: str) -> None:
    """Delete a profile outright — the customer's "quen toi di" / privacy request."""
    client = get_redis_client()
    if client is None:
        return

    try:
        client.delete(key)
    except Exception:
        logger.warning(
            "Xoa ho so ghi nho that bai.",
            exc_info=True,
            extra={"event": "memory.forget.failed", "key": key},
        )


def _resolve_project(question: str, project_id: str | None, db: Session | None) -> str | None:
    """Which project this question is about: the session's, else the one it names.

    The session's own `project_id` wins when set, being an explicit choice. It is almost
    never set any more — the picker was dropped from session creation — so without the
    fallback below `projects` stayed permanently empty and a remembered profile could
    never say *which* project a Sale keeps asking about.

    Imported inside the function to keep the module importable without a database, which
    the pure-unit tests of `extract_facts` rely on.
    """
    if project_id:
        return project_id
    if db is None:
        return None

    from backend.services.answer_images_service import resolve_project_id

    return resolve_project_id(db, question)


def extract_facts(question: str, project_id: str | None = None) -> UserProfile:
    """Pull durable preferences out of one question.

    Deliberately conservative regex rather than an LLM call: this runs on every message,
    so an extra model round-trip here would spend tokens and latency on every single
    turn to learn something as small as "this person asks about 2PN". Missing a
    preference is cheap; inventing one is not — which is why `_extract_budgets` requires
    the sentence to actually be about affordability before recording a figure.
    """
    if not question or not question.strip():
        return UserProfile()

    unit_types: list[str] = []
    for match in UNIT_TYPE_PATTERN.finditer(question):
        # Normalise "3 PN" and "3pn" to one token so they don't accumulate as duplicates.
        token = re.sub(r"\s+", "", match.group(0)).upper()
        if token not in unit_types:
            unit_types.append(token)

    budgets = _extract_budgets(question)

    projects = [project_id] if project_id else []

    return UserProfile(unit_types=unit_types, budgets=budgets, projects=projects)


def _extract_budgets(question: str) -> list[str]:
    """Money figures that are this person's budget, not a price they asked about.

    Three gates, each earning its place:

    1. The sentence must actually talk about affordability ("ngân sách", "tầm giá",
       "muốn mua"). A bare figure is far more often a price being asked about.
    2. A price question wins outright. "Ngân sách 3 tỷ thì căn 5 tỷ có hợp không?" is
       about a 5 tỷ unit *and* a 3 tỷ budget, and picking the wrong one is worse than
       picking neither — so an explicit price question means nothing is stored.
    3. At most one figure. A sentence carrying several money figures is comparing units,
       not stating one budget.
    """
    if not BUDGET_CONTEXT_PATTERN.search(question) or PRICE_QUESTION_PATTERN.search(question):
        return []

    found: list[str] = []
    for number, unit in BUDGET_PATTERN.findall(question):
        token = f"{number} {unit.lower()}"
        if token not in found:
            found.append(token)

    return found if len(found) == 1 else []


def format_profile(profile: UserProfile) -> str:
    """Render a profile for the prompt. Empty profile renders as an empty string."""
    if profile.is_empty():
        return ""

    lines = []
    if profile.unit_types:
        lines.append(f"- Loại căn thường quan tâm: {', '.join(profile.unit_types)}")
    if profile.budgets:
        lines.append(f"- Mức giá từng nhắc tới: {', '.join(profile.budgets)}")
    if profile.projects:
        lines.append(f"- Dự án từng hỏi: {', '.join(profile.projects)}")
    if profile.topics:
        lines.append(f"- Chủ đề hay hỏi: {', '.join(profile.topics)}")
    return "\n".join(lines)


def _merge(current: UserProfile, extracted: UserProfile) -> UserProfile:
    """Newest first, de-duplicated, capped — so a profile tracks recent interest.

    Order matters: a customer who moved from 2PN to 3PN should have 3PN read first, and
    once the cap is reached the oldest interest is the one that falls off.
    """
    return UserProfile(
        unit_types=_bounded(extracted.unit_types, current.unit_types),
        budgets=_bounded(extracted.budgets, current.budgets),
        projects=_bounded(extracted.projects, current.projects),
        topics=_bounded(extracted.topics, current.topics),
    )


def _bounded(new_items: list[str], old_items: list[str]) -> list[str]:
    merged = list(new_items)
    for item in old_items:
        if item not in merged:
            merged.append(item)
    return merged[:MAX_ITEMS_PER_FIELD]


def _clean_list(value: object) -> list[str]:
    """Coerce whatever was stored into a list of non-empty strings.

    Defensive because the value may have been written by an older version of this code,
    or hand-edited in redis-cli during debugging.
    """
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()][:MAX_ITEMS_PER_FIELD]
