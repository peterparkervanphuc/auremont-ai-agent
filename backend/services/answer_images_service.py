"""Image tool: attach the project photos that illustrate an answer.

Photos arrive by two different routes, and the distinction runs through this whole module:

**Requested** — the question asks to see something ("cho xem mặt bằng The Palma").
`wants_images` is true, and the Sale gets every photo matching the topic they named, with
no cap: each one is a photo they asked for. When the topic matches no filename the whole
project gallery is returned rather than nothing, because refusing someone who explicitly
asked to see something is the worse failure.

**Automatic** — the question asks to *know* something, and photos ride along to illustrate
the answer ("tiện ích dự án có gì" gets the amenity photos alongside the text). Nobody
asked, so the bar is higher and the posture inverts: capped at
`_AUTO_ATTACH_MAX_IMAGES`, and when the topic matches no filename the answer goes out with
no photos at all. An unasked-for photo of the wrong thing is worse than no photo, whereas
an unasked-for photo of the right thing is the point of this route.

Both routes then share the same subject filter: the project has to be named in the
question or the answer, and each photo's filename has to match the topic. Catalogue
filenames carry that topic (`mat-bang-phan-khu-...`, `phoi-canh-sao-bien-...`,
`vi-tri-...`), which is what makes per-image relevance possible rather than dumping the
whole gallery.
"""

import logging
import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.models.project import Project
from backend.utils.text import strip_diacritics

logger = logging.getLogger(__name__)

# Below this, a "match" on a project name is almost certainly a coincidence: two- or
# three-letter names would otherwise hit on ordinary words in the question.
_MIN_NAME_LENGTH = 4

# Cap for the automatic route only (see module docstring). Photos nobody asked for are
# supporting material: a strip of three sits under an answer without displacing it, while
# a dozen turns a text answer into a gallery the reader has to scroll past.
_AUTO_ATTACH_MAX_IMAGES = 3


@dataclass(frozen=True)
class ProjectReferences:
    """Catalogue projects named positively and negatively in one utterance."""

    included_ids: tuple[str, ...] = ()
    excluded_ids: tuple[str, ...] = ()

# Filename tokens for "a photo of the project overall" — used on the automatic route when
# the question names no visual topic of its own ("dự án này thế nào?"). These are the
# establishing shots, the ones that illustrate any answer about the project without
# claiming to depict a specific thing the asker did not mention.
_OVERVIEW_TOKENS = ("phoi-canh", "tong-the", "toan-canh")

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
    # "phong-" covers catalogues that name amenity photos after the specific room
    # ("phong-tap-gym-...", "phong-karaoke-...") rather than with the generic word. It is a
    # FILENAME token only — deliberately not a question phrase, because "phòng" in a
    # question is far more often "căn 2 phòng ngủ", and matching that would attach gym and
    # pool photos to a price question.
    (("tien ich",), ("tien-ich", "tienich", "phong-")),
    (("vi tri", "ket noi", "lien ket", "ban do"), ("vi-tri", "ket-noi", "lien-ket", "vitri")),
    (("phoi canh", "toan canh", "tong the"), ("phoi-canh", "tong-the", "toan-canh")),
    (("biet thu",), ("biet-thu", "bietthu")),
    (("shophouse", "shop", "thuong mai"), ("shop", "thuong-mai")),
    (("can ho", "chung cu"), ("can-ho", "chung-cu")),
    # A bare de-accented `ho-` also occurs in every `can-ho-*` filename (ho with
    # different Vietnamese accents normalizes identically). Use compound water subjects
    # so a lake-view question cannot accidentally attach apartment layouts.
    (("be boi", "ho boi"), ("be-boi", "ho-boi")),
    (("ho",), ("ho-dieu-hoa", "ho-canh-quan", "ho-ngoc-trai", "bien-ho")),
    (("bien",), ("bien-ho", "bien-")),
    (("cong vien", "canh quan"), ("cong-vien", "canh-quan")),
    (("view", "tam nhin", "huong nhin", "huong can"), ("view-", "tam-nhin", "huong-nhin")),
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


def collect_images(
    db: Session, query: str, answer: str, project_id: str | None = None
) -> list[dict]:
    """Photos to show under this answer — those asked for, or those that illustrate it.

    Takes whichever of the two routes in the module docstring applies. `wants_images`
    decides which: an explicit request gets everything matching, uncapped, falling back to
    the project gallery; anything else gets at most `_AUTO_ATTACH_MAX_IMAGES` and only when
    they genuinely match the topic.

    Reads the project name from question *and* answer: a Sale often asks "cho xem mặt
    bằng" without naming the project, and the name only appears in the answer that
    retrieval grounded on.

    Never raises — images are a nice-to-have, and a failure here must not cost the Sale
    their answer.
    """
    try:
        haystack = _normalize(f"{query}\n{answer}")
        if not haystack.strip():
            return []

        # A scoped chat session is authoritative. Project names nest ("The Pavilion -
        # Vinhomes Ocean Park"), so resolving from prose alone can otherwise select the
        # longer parent project and attach its maps instead of the named P4 plan.
        references = resolve_project_references(db, query)
        excluded_ids = set(references.excluded_ids)
        project = db.get(Project, project_id) if project_id else _best_match(db, haystack)
        # A negative mention is useful for search scope, never for choosing the image
        # gallery.  Without this guard, "ngoài Zenpark" attached Zenpark photos under a
        # response that was explicitly supposed to recommend other subdivisions.
        if project is not None and project.id in excluded_ids:
            return []
        if project is None:
            return []

        details: dict = project.details or {}
        overview_towers = ((details.get("project") or {}).get("overview") or {}).get("towers") or []
        known_towers = overview_towers if isinstance(overview_towers, list) else []
        images: dict = details.get("images") or {}
        gallery = [url for url in images.get("gallery") or [] if isinstance(url, str) and url]
        if not gallery:
            return []

        normalized_query = _normalize(query)
        if wants_images(query):
            selected = _filter_by_topic(gallery, normalized_query, known_towers)
        else:
            selected = _auto_attach_images(gallery, normalized_query, known_towers)

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
        references = resolve_project_references(db, text)
        return references.included_ids[0] if references.included_ids else None
    except Exception:
        logger.exception(
            "Could not resolve a project from text.",
            extra={"event": "answer_images.resolve_project.failed"},
        )
        return None


def resolve_project_ids(db: Session, text: str) -> list[str]:
    """Every catalogue project explicitly named in text, in mention order.

    Unlike `resolve_project_id`, this supports comparison questions that name two or more
    subdivisions. A parent project is suppressed when its only match is contained inside
    a longer matched catalogue name.
    """
    try:
        return list(resolve_project_references(db, text).included_ids)
    except Exception:
        logger.exception(
            "Could not resolve projects from text.",
            extra={"event": "answer_images.resolve_projects.failed"},
        )
        return []


def resolve_project_references(db: Session, text: str) -> ProjectReferences:
    """Split catalogue mentions into included and excluded projects.

    Name resolution alone cannot distinguish "Zenpark" from "ngoài Zenpark".  The
    latter must keep the surrounding search broad and remove Zenpark from it; treating
    every mention as positive hard-scoped RAG and catalogue lookup to the one project the
    customer had just rejected.
    """
    try:
        haystack = _normalize(text or "")
        if not haystack:
            return ProjectReferences()

        included: list[str] = []
        excluded: list[str] = []
        for position, _negative_length, project_id in _project_matches(db, haystack):
            target = excluded if _is_negative_reference(haystack, position) else included
            if project_id not in target:
                target.append(project_id)

        # A project cannot be both scopes in one turn.  The local negative phrase wins:
        # "Ocean Park, nhưng ngoài Zenpark" includes the parent and excludes the child.
        excluded_set = set(excluded)
        return ProjectReferences(
            included_ids=tuple(project_id for project_id in included if project_id not in excluded_set),
            excluded_ids=tuple(excluded),
        )
    except Exception:
        logger.exception(
            "Could not resolve positive/negative project references from text.",
            extra={"event": "answer_images.resolve_project_references.failed"},
        )
        return ProjectReferences()


def _project_matches(db: Session, haystack: str) -> list[tuple[int, int, str]]:
    matches: list[tuple[int, int, str]] = []
    for project in db.query(Project).all():
        candidates = _project_aliases(project)
        occurrences = [
            (match.start(), len(candidate))
            for candidate in candidates
            if len(candidate) >= _MIN_NAME_LENGTH
            for match in [re.search(rf"(?<!\w){re.escape(candidate)}(?!\w)", haystack)]
            if match is not None
        ]

        # Tower codes such as P4 are shorter than the normal project-name safety
        # threshold. Accept one only when it is explicitly a known tower of exactly one
        # catalogue project; ambiguous tower codes are discarded below.
        details = project.details or {}
        for tower in _known_project_towers(details):
            match = re.search(rf"(?<!\w){re.escape(tower)}(?!\w)", haystack)
            if match is not None:
                occurrences.append((match.start(), len(tower)))
        if occurrences:
            position, length = min(occurrences, key=lambda item: (item[0], -item[1]))
            matches.append((position, -length, project.id))

    # A bare tower identifier is useful only when unique. Names/sub-zones with the same
    # start position remain multiple on purpose (e.g. The Ocean View scopes a search
    # across all of its child projects).
    grouped: dict[tuple[int, int], list[str]] = {}
    for position, negative_length, project_id in matches:
        grouped.setdefault((position, negative_length), []).append(project_id)
    matches = [
        item
        for item in matches
        if -item[1] >= _MIN_NAME_LENGTH or len(grouped[(item[0], item[1])]) == 1
    ]
    matches.sort()
    return matches


_NEGATIVE_PROJECT_PREFIX = re.compile(
    r"(?:\bngoai\b(?!\s+ra\b)|\btru\b|\bkhong phai\b|\bkhong lay\b|\bkhong chon\b|"
    r"\bloai tru\b|\btranh\b|\bkhac voi\b)(?:\s+\w+){0,5}\s*$",
    re.IGNORECASE,
)


def _is_negative_reference(haystack: str, position: int) -> bool:
    # Sixty characters cover natural bridges such as "các phân khu khác ngoài" without
    # letting a negation from an unrelated clause flip a later positive project mention.
    prefix = haystack[max(0, position - 60) : position]
    return _NEGATIVE_PROJECT_PREFIX.search(prefix) is not None


def _filter_by_topic(
    gallery: list[str], normalized_query: str, known_towers: list[str] | None = None
) -> list[str]:
    """Narrow the gallery to the topic the question named.

    Falls back to the whole gallery in two cases, both deliberate: the question named no
    topic ("cho xem hình ảnh The Palma" — they want the project's photos), or it named one
    the catalogue has no picture of. Returning nothing to someone who explicitly asked to
    see something is worse than returning that project's photos.
    """
    exact_tower_tokens = _tower_tokens(normalized_query, known_towers)
    if exact_tower_tokens:
        exact = [url for url in gallery if any(token in _normalize_filename(url) for token in exact_tower_tokens)]
        # A named tower is an exact visual request. Showing another tower because this
        # one has no uploaded plan is materially misleading, so do not use the usual
        # requested-photo gallery fallback here.
        return exact

    view_match = _filter_view_images(gallery, normalized_query)
    if view_match is not None:
        # Like an exact tower plan, a requested view is a precise visual claim. Falling
        # back to layouts or amenity photos would imply they depict that view.
        return view_match

    tokens = _wanted_tokens(normalized_query)
    if not tokens:
        return gallery

    matched = [url for url in gallery if any(token in _normalize_filename(url) for token in tokens)]
    return matched or gallery


def _auto_attach_images(
    gallery: list[str], normalized_query: str, known_towers: list[str] | None = None
) -> list[str]:
    """The automatic route's selection: matching photos only, capped.

    Two deliberate differences from `_filter_by_topic`, both following from nobody having
    asked for these (see module docstring):

    * No fall back to the whole gallery. A topic the catalogue has no photo of yields no
      photo — attaching an unrelated one to an answer that never mentioned pictures reads
      as the system padding itself out.
    * A question naming no visual topic at all ("chính sách thanh toán thế nào?") is not
      treated as "anything goes" either. It gets the project's establishing shots, which
      illustrate the project without claiming to depict a specific thing, and nothing when
      the catalogue has none of those either.
    """
    # An exact tower code is a stronger qualifier than the generic subject "tòa". Without
    # this first pass, "tòa P4" matches every `mat-bang-toa-p*` filename and the cap keeps
    # P1-P3 while dropping the one image the asker actually named.
    exact_tower_tokens = _tower_tokens(normalized_query, known_towers)
    if exact_tower_tokens:
        exact = [url for url in gallery if any(token in _normalize_filename(url) for token in exact_tower_tokens)]
        return exact[:_AUTO_ATTACH_MAX_IMAGES]

    view_match = _filter_view_images(gallery, normalized_query)
    if view_match is not None:
        return view_match[:_AUTO_ATTACH_MAX_IMAGES]

    # Keyed off the SUBJECT, not `_wanted_tokens`: that also returns bedroom qualifiers
    # ("2pn"), and "giá căn 2 phòng ngủ" would then count as naming a visual topic it never
    # named — yielding no photo at all instead of the overview shots, since no filename
    # carries a bare bedroom count.
    if _subject_tokens(normalized_query):
        tokens = _wanted_tokens(normalized_query)
    else:
        tokens = list(_OVERVIEW_TOKENS)

    matched = [url for url in gallery if any(token in _normalize_filename(url) for token in tokens)]
    return matched[:_AUTO_ATTACH_MAX_IMAGES]


def _filter_view_images(gallery: list[str], normalized_query: str) -> list[str] | None:
    """Require filename evidence before claiming that a photo depicts a unit's view.

    ``None`` means this is not a view question. A generic view question accepts a file
    explicitly labelled as a view. If the asker qualifies it (lake, sea, landscape...),
    the filename must carry both the view label and a requested subject. Image order and
    project identity alone cannot prove which direction a photograph faces.
    """
    view_filename_tokens = ("view-", "tam-nhin", "huong-nhin")
    if not _contains_phrase(normalized_query, ("view", "tam nhin", "huong nhin", "huong can")):
        return None

    explicit_view_images = [
        url
        for url in gallery
        if any(token in _normalize_filename(url) for token in view_filename_tokens)
    ]
    subject_tokens = [
        token for token in _subject_tokens(normalized_query) if token not in view_filename_tokens
    ]
    if not subject_tokens:
        return explicit_view_images
    return [
        url
        for url in explicit_view_images
        if any(token in _normalize_filename(url) for token in subject_tokens)
    ]


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


def _tower_tokens(normalized_query: str, known_towers: list[str] | None = None) -> list[str]:
    """Exact named tower qualifiers in both dot and hyphen filename conventions."""
    matched_names = [
        tower
        for tower in known_towers or []
        if isinstance(tower, str)
        and re.search(rf"(?<!\w){re.escape(_normalize(tower))}(?!\w)", normalized_query)
    ]
    if not matched_names:
        matched_names = re.findall(r"\b(?:toa|tower)\s*([a-z]{1,5}\d+(?:\.\d+)?)\b", normalized_query)

    tokens: list[str] = []
    for name in matched_names:
        slug = _normalize(name).replace(" ", "-")
        tokens.extend((f"toa-{slug}", f"toa-{slug.replace('.', '-')}"))
    return list(dict.fromkeys(tokens))


def _best_match(db: Session, haystack: str) -> Project | None:
    """The project whose name or slug appears in the text, longest match winning.

    Longest wins because catalogue names nest: "Vinhomes Ocean Park" is a substring of
    the text whenever "Vinhomes Ocean Park 3" is, and the more specific one is the one
    the Sale is asking about.
    """
    best: Project | None = None
    best_length = 0

    for project in db.query(Project).all():
        for normalized in _project_aliases(project):
            if len(normalized) < _MIN_NAME_LENGTH or normalized not in haystack:
                continue
            if len(normalized) > best_length:
                best, best_length = project, len(normalized)

    return best


def _project_aliases(project: Project) -> set[str]:
    """All catalogue labels a customer can reasonably use for one project/sub-zone."""
    details = project.details or {}
    info = details.get("project") or {}
    raw = {
        project.id.replace("-", " "),
        project.name,
        project.name.split(" - ", 1)[0] if project.name else None,
        info.get("name"),
        info.get("full_name"),
        info.get("alternate_name"),
        info.get("sub_zone"),
    }
    aliases = {_normalize(str(value)) for value in raw if value}
    configured_aliases = info.get("aliases") or []
    if isinstance(configured_aliases, list):
        aliases.update(_normalize(str(value)) for value in configured_aliases if value)
    aliases.update(alias.removeprefix("the ") for alias in tuple(aliases))
    aliases.update(alias.removeprefix("vinhomes ") for alias in tuple(aliases))
    return {alias for alias in aliases if alias}


def _known_project_towers(details: dict) -> set[str]:
    overview = ((details.get("project") or {}).get("overview") or {}).get("towers") or []
    tower_details = details.get("tower_details") or {}
    raw = [*(overview if isinstance(overview, list) else []), *tower_details.keys()]
    return {_normalize(str(value)) for value in raw if value}


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
