"""Image tool: fetch project photos when a Sale actually asks to see something.

The Agent calls this the way it calls the inventory API — only when the question calls
for it. A Sale asking "giá căn 2PN bao nhiêu" wants a number, not a photo gallery; a Sale
asking "cho xem mặt bằng The Palma" wants the floor plans and nothing else.

Two filters run in order, and both must pass before a photo is returned:

1. **Intent** — the question has to ask for something visual ("hình ảnh", "mặt bằng",
   "phối cảnh"). Without that the tool returns nothing at all.
2. **Subject** — the project has to be named in the question or the answer, and the
   photo's own filename has to match the topic asked about. Catalogue filenames carry
   that topic (`mat-bang-phan-khu-...`, `phoi-canh-sao-bien-...`, `vi-tri-...`), which is
   what makes per-image relevance possible rather than dumping the whole gallery.

There is deliberately no cap on how many images come back: once both filters have run,
every remaining photo is one the Sale asked to see.
"""

import logging
import re

from sqlalchemy.orm import Session

from backend.models.project import Project
from backend.utils.text import strip_diacritics

logger = logging.getLogger(__name__)

# Below this, a "match" on a project name is almost certainly a coincidence: two- or
# three-letter names would otherwise hit on ordinary words in the question.
_MIN_NAME_LENGTH = 4

# Asking for something visual. Two things are deliberately absent. "xem" on its own,
# because "xem giá căn 2PN" is a text question. And bare "ảnh", because de-accented it is
# "anh" — a word that also addresses a person ("anh ơi cho hỏi giá") and would fire on
# every such question; it is only accepted in phrases that can only mean a picture.
_IMAGE_INTENT_KEYWORDS = (
    "hinh anh",
    "hinh",
    "xem anh",
    "coi anh",
    "buc anh",
    "tam anh",
    "cac anh",
    "photo",
    "image",
    "mat bang",
    "phoi canh",
    "so do",
    "ban ve",
    "layout",
    "mat cat",
    "thiet ke",
    "gallery",
    "thu vien anh",
)

# Only ever meaningful next to a topic — see `wants_images`.
_LOOK_VERBS = ("xem", "coi", "show")

# Topic asked about -> tokens that appear in catalogue filenames. Matching is done on the
# de-accented filename, so the values here are already in slug form.
_TOPIC_TOKENS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("mat bang", "layout", "so do", "ban ve", "mat cat"), ("mat-bang", "matbang")),
    (("tien ich",), ("tien-ich", "tienich")),
    (("vi tri", "ket noi", "lien ket", "ban do"), ("vi-tri", "ket-noi", "lien-ket", "vitri")),
    (("phoi canh", "toan canh", "tong the"), ("phoi-canh", "tong-the", "toan-canh")),
    (("biet thu",), ("biet-thu", "bietthu")),
    (("shophouse", "shop", "thuong mai"), ("shop", "thuong-mai")),
    (("can ho", "chung cu"), ("can-ho", "chung-cu")),
    (("be boi", "ho boi", "ho", "bien"), ("be-boi", "ho-", "bien")),
    (("cong vien", "canh quan"), ("cong-vien", "canh-quan")),
    (("noi that",), ("noi-that", "noithat")),
    (("phan khu",), ("phan-khu", "phankhu")),
    (("toa", "tower"), ("toa-", "toa")),
)


def wants_images(query: str) -> bool:
    """True when the question asks to see something, not merely to know something.

    Diacritic-insensitive: a Sale typing fast on a phone writes "cho xem mat bang" as
    often as "cho xem mặt bằng".
    """
    normalized = _normalize(query)
    if _contains_phrase(normalized, _IMAGE_INTENT_KEYWORDS):
        return True

    # "xem"/"coi" cannot trigger on their own ("xem giá căn 2PN" wants a number), but
    # paired with a subject the catalogue has photographs of, it is a request to look:
    # "cho xem vị trí", "cho xem biệt thự".
    #
    # Only *subjects* count here, never the bedroom qualifier: "2PN" narrows which photo
    # is wanted once images are in play, but "xem giá căn 2PN" is still a price question.
    return _contains_phrase(normalized, _LOOK_VERBS) and bool(_subject_tokens(normalized))


def collect_images(db: Session, query: str, answer: str) -> list[dict]:
    """Photos the question asked to see, or [] when it did not ask for any.

    Reads the project name from question *and* answer: a Sale often asks "cho xem mặt
    bằng" without naming the project, and the name only appears in the answer that
    retrieval grounded on.

    Never raises — images are a nice-to-have, and a failure here must not cost the Sale
    their answer.
    """
    try:
        if not wants_images(query):
            return []

        haystack = _normalize(f"{query}\n{answer}")
        if not haystack.strip():
            return []

        project = _best_match(db, haystack)
        if project is None:
            return []

        details: dict = project.details or {}
        images: dict = details.get("images") or {}
        gallery = [url for url in images.get("gallery") or [] if isinstance(url, str) and url]
        if not gallery:
            return []

        selected = _filter_by_topic(gallery, _normalize(query))
        return [{"url": url, "project_id": project.id, "project_name": project.name} for url in selected]
    except Exception:
        logger.exception(
            "Could not resolve answer images; answering without them.",
            extra={"event": "answer_images.failed"},
        )
        return []


def resolve_project_id(db: Session, text: str) -> str | None:
    """The catalogue id of the project named in `text`, or None when none is.

    Exposed for long-term memory, which has to recognise "dự án The Palma" inside a
    question: sessions stopped carrying a `project_id` when the picker was dropped from
    session creation, so the question itself is the only place the project appears.

    Never raises — a caller that cannot identify the project simply remembers less.
    """
    try:
        normalized = _normalize(text or "")
        if not normalized.strip():
            return None

        project = _best_match(db, normalized)
        return project.id if project is not None else None
    except Exception:
        logger.exception(
            "Could not resolve a project from text.",
            extra={"event": "answer_images.resolve_project.failed"},
        )
        return None


def _filter_by_topic(gallery: list[str], normalized_query: str) -> list[str]:
    """Narrow the gallery to the topic the question named.

    Falls back to the whole gallery in two cases, both deliberate: the question named no
    topic ("cho xem hình ảnh The Palma" — they want the project's photos), or it named one
    the catalogue has no picture of. Returning nothing to someone who explicitly asked to
    see something is worse than returning that project's photos.
    """
    tokens = _wanted_tokens(normalized_query)
    if not tokens:
        return gallery

    matched = [url for url in gallery if any(token in _normalize_filename(url) for token in tokens)]
    return matched or gallery


def _subject_tokens(normalized_query: str) -> list[str]:
    """Filename tokens for the subjects named — the things the catalogue photographs."""
    tokens: list[str] = []
    for phrases, filename_tokens in _TOPIC_TOKENS:
        if _contains_phrase(normalized_query, phrases):
            tokens.extend(filename_tokens)
    return tokens


def _wanted_tokens(normalized_query: str) -> list[str]:
    """Subjects plus qualifiers — everything usable to narrow the gallery."""
    tokens = _subject_tokens(normalized_query)

    # Unit types are written straight into filenames ("...-2pn-...", "...-3-phong-ngu-...").
    for bedrooms in re.findall(r"\b(\d)\s*(?:pn|phong ngu)\b", normalized_query):
        tokens.extend([f"{bedrooms}pn", f"{bedrooms}-phong-ngu", f"{bedrooms}-pn"])

    return tokens


def _best_match(db: Session, haystack: str) -> Project | None:
    """The project whose name or slug appears in the text, longest match winning.

    Longest wins because catalogue names nest: "Vinhomes Ocean Park" is a substring of
    the text whenever "Vinhomes Ocean Park 3" is, and the more specific one is the one
    the Sale is asking about.
    """
    best: Project | None = None
    best_length = 0

    for project in db.query(Project).all():
        for candidate in (project.name, project.id):
            if not candidate:
                continue
            normalized = _normalize(candidate.replace("-", " "))
            if len(normalized) < _MIN_NAME_LENGTH or normalized not in haystack:
                continue
            if len(normalized) > best_length:
                best, best_length = project, len(normalized)

    return best


def _contains_phrase(haystack: str, phrases: tuple[str, ...]) -> bool:
    """Whole-word phrase match.

    Plain substring matching is wrong here and quietly so: "anh" is inside "thanh toán"
    and "ho" is inside "cho", so an unbounded search fires the image tool on questions
    about payment schedules.
    """
    return any(re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", haystack) for phrase in phrases)


def _normalize(text: str) -> str:
    """Lowercase, strip diacritics and collapse separators.

    A Sale typing quickly writes "hai au" for "Hải Âu", and slugs arrive as "hai-au",
    so all three forms have to reduce to the same string before comparison.
    """
    return " ".join(strip_diacritics(text).lower().replace("-", " ").split())


def _normalize_filename(url: str) -> str:
    """The filename in slug form, so topic tokens can be matched against it."""
    return strip_diacritics(url.rsplit("/", 1)[-1]).lower()
