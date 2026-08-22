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

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.minio_client import public_object_url
from backend.models.project import Project
from backend.utils.text import strip_diacritics

logger = logging.getLogger(__name__)


def public_gallery_url(value: str) -> str:
    """Normalise one `project.details["images"]["gallery"]` entry into a URL a browser can
    actually load.

    Two shapes exist in the data today, both from the same `scripts/_gallery.py` loader:
    a full external URL when `PROJECT_IMAGES_BASE_URL` was set at load time, and a bare
    MinIO object key with a stray leading slash (`/the-sapphire/mat-bang-...jpg`) when it
    wasn't — the common case in this dev catalogue, since the env var was never set before
    `scripts/load_apartment_projects.py`/`load_villa_shop_projects.py` ran. The object
    itself still exists — `scripts/upload_project_images.py` populated the same bucket
    under the same key names — so the fix is building the URL, not re-uploading anything.
    """
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return public_object_url(settings.minio_bucket_project_images, value.lstrip("/"))


# A handful of photos are the exact same file reused across more than one project's
# gallery — a genuinely shared complex-wide amenity (the one "Santa Monica" pool The
# Beverly and The London both list), not something that distinguishes either project.
# Showing the identical photo as the lead image for two different projects reads as a bug
# ("these two look the same?"), not as "these two share an amenity" — excluded wherever a
# gallery is read, rather than just at one call site.
_SHARED_NONDISTINGUISHING_PHOTO_PATTERN = re.compile(r"santan?-monica")


def _drop_shared_nondistinguishing_photos(gallery: list[str]) -> list[str]:
    return [url for url in gallery if not _SHARED_NONDISTINGUISHING_PHOTO_PATTERN.search(url.lower())]


# Below this, a "match" on a project name is almost certainly a coincidence: two- or
# three-letter names would otherwise hit on ordinary words in the question.
_MIN_NAME_LENGTH = 4

# Cap for the automatic route only (see module docstring). Photos nobody asked for are
# supporting material: a strip of three sits under an answer without displacing it, while
# a dozen turns a text answer into a gallery the reader has to scroll past.
_AUTO_ATTACH_MAX_IMAGES = 3

# Filename tokens for "a photo of the project overall" — used on the automatic route when
# the question names no visual topic of its own ("dự án này thế nào?"). These are the
# establishing shots, the ones that illustrate any answer about the project without
# claiming to depict a specific thing the asker did not mention.
#
# "phoi-canh"/"tong-the"/"toan-canh" alone miss a real gap: several catalogues (The Zurich)
# tag their establishing CGI render "3d-{project}...jpg" or their exterior shot
# "mat-ngoai-{project}...jpg" instead — neither word appears anywhere in a floor plan or a
# per-unit render, so both are safe to add without risking a wrong-topic photo.
_OVERVIEW_TOKENS = ("phoi-canh", "tong-the", "toan-canh", "3d-", "mat-ngoai")

# Asking for something visual. Two things are deliberately absent. "xem" on its own,
# because "xem giá căn 2PN" is a text question. And bare "ảnh", because de-accented it is
# "anh" — a word that also addresses a person ("anh ơi cho hỏi giá") and would fire on
# every such question; it is only accepted in phrases that can only mean a picture.
#
# "toi anh"/"em anh"/"minh anh" cover "cho tôi ảnh ...", "gửi em ảnh ..." — the object
# pronoun sits directly in front of "ảnh" only when it means "[give] me a picture"; nobody
# addresses a person as "anh" right after saying "tôi"/"em"/"mình", so this stays
# unambiguous the same way "xem anh"/"coi anh" already are.
_IMAGE_INTENT_KEYWORDS = (
    "hinh anh",
    "hinh",
    "xem anh",
    "coi anh",
    "buc anh",
    "tam anh",
    "cac anh",
    "toi anh",
    "em anh",
    "minh anh",
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

        # An answer naming several distinct real projects at once (e.g. "The Metropolitan
        # gồm The Zurich, The London, The Pavilion và The Beverly") is not "about" whichever
        # one `_best_match` happens to prefer (longest name, first match...) — attaching
        # that one project's photo under a multi-project answer misrepresents it as THE
        # answer. Only applies to the auto-illustrate route (nobody asked to see anything
        # specific) and only when no project was already pinned by the caller; an explicit
        # "cho xem ảnh X" naming one project by name still resolves to it even if the
        # surrounding context also happens to mention others.
        if project_id is None and not wants_images(query) and len(resolve_project_ids(db, haystack)) > 1:
            return []

        # A scoped chat session is authoritative. Project names nest ("The Pavilion -
        # Vinhomes Ocean Park"), so resolving from prose alone can otherwise select the
        # longer parent project and attach its maps instead of the named P4 plan.
        project = db.get(Project, project_id) if project_id else _best_match(db, haystack)
        if project is None:
            # No single project's own name/alias matched — but the question may still name
            # a product CATEGORY ("ảnh biệt thự") that several real projects share. A
            # category word is not part of any one project's alias set, so _best_match
            # above always misses it; without this, a perfectly answerable "ảnh biệt thự"
            # falls through to "no photos" even though three villa projects have real
            # galleries.
            return _images_from_category(db, _normalize(query))

        details: dict = project.details or {}
        overview_towers = ((details.get("project") or {}).get("overview") or {}).get("towers") or []
        known_towers = overview_towers if isinstance(overview_towers, list) else []
        images: dict = details.get("images") or {}
        gallery = _drop_shared_nondistinguishing_photos(
            [url for url in images.get("gallery") or [] if isinstance(url, str) and url]
        )
        if not gallery:
            return []

        normalized_query = _normalize(query)
        if wants_images(query):
            selected = _filter_by_topic(gallery, normalized_query, known_towers)
        else:
            selected = _auto_attach_images(gallery, normalized_query, known_towers)

        return [
            {"url": public_gallery_url(url), "project_id": project.id, "project_name": project.name}
            for url in selected
        ]
    except Exception:
        logger.exception(
            "Could not resolve answer images; answering without them.",
            extra={"event": "answer_images.failed"},
        )
        return []


# A tower-wide floor-plan sheet's own code, e.g. "toa-ld1" -> "LD1" — distinct from
# `_UNIT_TYPE_PHOTO_PATTERN`, which is about the unit type shown, not which tower a
# whole-tower sheet covers.
_FLOORPLAN_SHEET_TOWER_PATTERN = re.compile(r"toa-([a-z]{1,5}\d+)")


def floor_plan_only_towers(
    db: Session, query: str, answer: str, project_id: str | None = None
) -> list[str] | None:
    """None when the resolved project's gallery has real per-unit-type floor-plan photos —
    nothing extra to tell the model. Otherwise, the tower codes of whatever tower-wide
    floor-plan SHEETS exist in the gallery (e.g. ["LD1", "LD2", "LD3"]), possibly an empty
    list when the project has no floor-plan asset of either kind.

    Some catalogues (The London) were only ever digitised as one big architectural sheet
    per tower, showing every unit type on the floor at once (see PAVILION_GALLERY's sibling
    fixture in tests) — `select_listing_images` correctly excludes those from a "2PN" card
    (a tower-wide sheet is not a photo of one unit type), but that leaves the model with no
    way to know a bedroom-count follow-up ("xem thêm mặt bằng 2PN?") has no photo to answer
    it, while a tower-named one ("xem mặt bằng tòa LD1?") does. This is what lets
    `build_prompt` steer the suggestion toward the one that actually works.
    """
    try:
        haystack = _normalize(f"{query}\n{answer}")
        project = db.get(Project, project_id) if project_id else _best_match(db, haystack)
        if project is None:
            return None

        gallery = [
            url for url in ((project.details or {}).get("images") or {}).get("gallery") or [] if isinstance(url, str)
        ]
        if not gallery or any(_UNIT_TYPE_PHOTO_PATTERN.search(_normalize_filename(url)) for url in gallery):
            return None

        towers: list[str] = []
        for url in gallery:
            name = _normalize_filename(url)
            if "mat-bang" not in name and "matbang" not in name:
                continue
            match = _FLOORPLAN_SHEET_TOWER_PATTERN.search(name)
            if match:
                towers.append(match.group(1).upper())
        return list(dict.fromkeys(towers))
    except Exception:
        logger.exception(
            "Could not resolve floor-plan tower availability; answering without the note.",
            extra={"event": "answer_images.floor_plan_towers.failed"},
        )
        return None


# Product-category words -> the exact `category` string a project's own pricing tiers use
# (see catalog_offer_service.build_catalog_overview, which reads the same field). Kept
# separate from _TOPIC_TOKENS (filename tokens) since this maps to a *catalogue* field,
# not a *filename* pattern.
_CATEGORY_MATCH_TERMS: tuple[tuple[str, str], ...] = (
    ("biet thu", "Biệt thự"),
    ("chung cu", "Chung cư"),
    ("shophouse", "Shophouse"),
    ("shop tmdv", "Shophouse"),
    ("shop thuong mai", "Shophouse"),
)

# Per project, when pulling from several at once for a category-only request — enough to
# suggest the project's own gallery without one project's many photos crowding out another.
_IMAGES_PER_CATEGORY_PROJECT = 2


def named_category(text: str) -> str | None:
    """The product category (as `catalog_offer_service`/`Project.details["pricing"]` spell
    it) named in free text, or None. Used by `agent_pipeline._scope_resolve` to tell a real
    topic switch ("biệt thự" after discussing an apartment project) apart from a follow-up
    on the same project — see the module docstring on `_CATEGORY_MATCH_TERMS`.
    """
    normalized = _normalize(text)
    return next((label for phrase, label in _CATEGORY_MATCH_TERMS if phrase in normalized), None)


def project_categories(project: Project) -> set[str]:
    """Every product category this project's own catalogue pricing sells, e.g. {"Biệt thự"}
    for a single-category sub-zone or {"Chung cư", "Biệt thự", "Shophouse"} for the umbrella
    "Vinhomes Ocean Park" entry."""
    pricing = (project.details or {}).get("pricing") or []
    return {tier["category"] for tier in pricing if isinstance(tier, dict) and tier.get("category")}


def _images_from_category(db: Session, normalized_query: str) -> list[dict]:
    """A few real photos from every project of the product category named in the query
    ("ảnh biệt thự" -> Hải Âu, Ngọc Trai, Sao Biển each), for when no single project's own
    name matched anything (see the `project is None` branch in `collect_images`) because
    the question named a category, not a specific project — a category word is never part
    of any one project's own alias set, so it can never resolve to exactly one project the
    way "ảnh The Zurich" does. Excludes any project whose pricing spans MULTIPLE categories
    (the umbrella "Vinhomes Ocean Park" catalogue entry) — that one photo of everything
    would dominate every category's results with an unrelated overview shot.
    """
    category = next((label for phrase, label in _CATEGORY_MATCH_TERMS if phrase in normalized_query), None)
    if category is None:
        return []

    results: list[dict] = []
    for project in db.query(Project).all():
        pricing = (project.details or {}).get("pricing") or []
        categories = {tier["category"] for tier in pricing if tier.get("category")}
        if categories != {category}:
            continue

        gallery = _drop_shared_nondistinguishing_photos(
            [url for url in ((project.details or {}).get("images") or {}).get("gallery") or [] if isinstance(url, str) and url]
        )
        if not gallery:
            continue

        picked = _auto_attach_images(gallery, normalized_query, [])[:_IMAGES_PER_CATEGORY_PROJECT]
        results.extend(
            {"url": public_gallery_url(url), "project_id": project.id, "project_name": project.name} for url in picked
        )
    return results


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


def resolve_project_ids(db: Session, text: str) -> list[str]:
    """Every catalogue project explicitly named in text, in mention order.

    Unlike `resolve_project_id`, this supports comparison questions that name two or more
    subdivisions. A parent project is suppressed when its only match is contained inside
    a longer matched catalogue name.
    """
    try:
        haystack = _normalize(text or "")
        if not haystack:
            return []

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
            # threshold. Accept one only when it is explicitly a known tower of exactly
            # one catalogue project; ambiguous tower codes are discarded below.
            details = project.details or {}
            tower_names = _known_project_towers(details)
            for tower in tower_names:
                match = re.search(rf"(?<!\w){re.escape(tower)}(?!\w)", haystack)
                if match is not None:
                    occurrences.append((match.start(), len(tower)))
            if occurrences:
                position, length = min(occurrences, key=lambda item: (item[0], -item[1]))
                matches.append((position, -length, project.id))

        # A bare tower identifier is useful only when unique. Names/sub-zones with the
        # same start position remain multiple on purpose (e.g. The Ocean View scopes a
        # comparison/search across all of its child projects).
        grouped: dict[tuple[int, int], list[str]] = {}
        for position, negative_length, project_id in matches:
            grouped.setdefault((position, negative_length), []).append(project_id)
        matches = [
            item
            for item in matches
            if -item[1] >= _MIN_NAME_LENGTH or len(grouped[(item[0], item[1])]) == 1
        ]
        matches.sort()
        return list(dict.fromkeys(project_id for _, _, project_id in matches))
    except Exception:
        logger.exception(
            "Could not resolve projects from text.",
            extra={"event": "answer_images.resolve_projects.failed"},
        )
        return []


_SUB_ZONE_NAME_PATTERN = re.compile(r"([a-z]+)\s+(\d+)$")


def _sub_zone_tokens(project_name: str) -> list[str]:
    """Filename tokens for a numbered sub-zone name ("The Sapphire 2" -> "sapphire-2").

    The Sapphire is the one catalogue project where two distinct sub-zones (Sapphire 1,
    Sapphire 2) share a single Project row and gallery — every other tier/tower has its
    own row. Their only visually distinguishing photo is a single sub-zone-level master
    plan each ("mat-bang-khu-sapphire-1-...jpg"), which the generic "mat-bang" exclusion
    in `select_listing_images` would otherwise treat identically to a misleading
    tower/unit floor plan and drop — leaving both sub-zones' cards showing the exact same
    generic park photos, with nothing telling them apart.
    """
    match = _SUB_ZONE_NAME_PATTERN.search(_normalize(project_name))
    if not match:
        return []
    word, number = match.groups()
    return [f"{word}-{number}", f"khu-{word}-{number}"]


_ZONE_OVERVIEW_UNIT_TYPE = "nhieu loai can"

# A filename tagged for one specific unit type (bedroom count, studio, or villa build
# type) — see `_unit_type_tokens`, re-expressed as a pattern to test a FILENAME against
# rather than a query. Used only by the zone-overview branch below: a "Nhiều loại căn"
# summary card must show photos of the ZONE (exterior/landscape/amenities), not a 3D
# cutaway render of one particular unit type, even though those renders are not tagged
# "mat-bang" and would otherwise pass the normal floor-plan-only exclusion.
#
# The hyphen before "ngu"/"pn"/"phong-ngu" is optional: catalogues disagree on the
# convention exactly like `_unit_type_tokens` above does ("can-ho-2pn-..." vs
# "can-ho-1-ngu-zr1-..."), so both "2pn" and "2-ngu" have to match here too.
_UNIT_TYPE_PHOTO_PATTERN = re.compile(
    r"(?:^|-)\d-?(?:ngu|pn|phong-ngu)(?:-|$)|(?:^|-)studio(?:-|$)|(?:^|-)(?:don-lap|song-lap|lien-ke)(?:-|$)"
)


def select_listing_images(gallery: list[str], unit_type: str, project_name: str = "") -> list[str]:
    """Pick photos to illustrate one recommended listing (agent_pipeline.PropertyListing):
    photos of that exact unit type when the catalogue has any, otherwise every other real
    photo of the subdivision except floor plans — never a floor plan for the wrong unit
    type, and never padded out to some fixed count with photos that do not actually match.

    Matches on `_unit_type_tokens` only (bedroom count / "studio"), deliberately not the
    broader `_wanted_tokens`/`_subject_tokens` used elsewhere in this module — those also
    match the generic "mat-bang" topic token, which would let a whole-tower floor plan
    (any filename with "mat-bang" in it) count as a match for every unit type in that
    tower. A listing is about one specific unit type; a tower-wide floor plan is not a
    photo of it, it just happens to share a topic word.

    No cap on how many are returned: accuracy matters more than a fixed count, and a real
    unit type rarely has more than a handful of photos in the catalogue anyway. Also no
    floor — a listing that only has 1-2 real photos of its exact type shows exactly those,
    never padded with an unrelated exterior/skyline shot just to hit a round number.
    """
    if not gallery:
        return []

    normalized_unit_type = _normalize(unit_type)
    unit_tokens = _unit_type_tokens(normalized_unit_type)
    type_matches = list(dict.fromkeys(url for url in gallery if any(token in _normalize_filename(url) for token in unit_tokens)))
    if type_matches:
        return type_matches

    # No photo tagged for this specific unit type — fall back to every OTHER real photo of
    # the project (scenic/overview shots, lobby, architecture...), not just the narrowly
    # "phoi-canh"/"tong-the"-tagged ones. A project like The Palma has several genuine
    # scenic photos (kien-truc-the-palma.jpg, the-palma.jpg...) that don't happen to carry
    # those exact keywords; stopping at a narrow set once any match was found under-showed
    # real photos for no good reason. The one thing still excluded, deliberately, is
    # anything reading as a floor plan ("mat-bang") — the one photo category proven
    # misleading when shown for the wrong unit type.
    fallback = [url for url in gallery if "mat-bang" not in _normalize_filename(url) and "matbang" not in _normalize_filename(url)]

    # The zone-summary card (prompts.py's "Nhiều loại căn" listing, shown before the
    # customer has picked a unit type) additionally excludes every per-unit-type render —
    # those are correct for a specific-unit-type listing but read as "the floor plan" when
    # shown under a summary card that has not narrowed to one unit type yet.
    if normalized_unit_type == _ZONE_OVERVIEW_UNIT_TYPE:
        without_unit_photos = [url for url in fallback if not _UNIT_TYPE_PHOTO_PATTERN.search(_normalize_filename(url))]
        # Only apply the stricter filter if it leaves something — a gallery with nothing
        # but per-unit renders should still show something rather than an empty card.
        if without_unit_photos:
            fallback = without_unit_photos

    # Exception to that exclusion: a sub-zone's own master plan (see _sub_zone_tokens) is
    # not a misleading unit/tower floor plan, it is the one real photo that tells this
    # sub-zone apart from its siblings sharing the same gallery — put it first.
    sub_zone_tokens = _sub_zone_tokens(project_name)
    if sub_zone_tokens:
        sub_zone_matches = [url for url in gallery if any(token in _normalize_filename(url) for token in sub_zone_tokens)]
        if sub_zone_matches:
            return list(dict.fromkeys([*sub_zone_matches, *fallback]))

    return fallback


def select_listing_amenities(project: Project, max_amenities: int = 4) -> list[str]:
    """A few named amenities from the project's own catalogue record, for a listing card.

    Deterministic, read straight from `project.details["amenities"]` — never left for the
    model to invent, same reasoning as `select_listing_images` never letting it guess a URL.
    """
    amenities = (project.details or {}).get("amenities") or []
    names = [item["name"] for item in amenities if isinstance(item, dict) and isinstance(item.get("name"), str)]
    return names[:max_amenities]


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


def _subject_tokens(normalized_query: str) -> list[str]:
    """Filename tokens for the subjects named — the things the catalogue photographs."""
    tokens: list[str] = []
    for phrases, filename_tokens in _TOPIC_TOKENS:
        if _contains_phrase(normalized_query, phrases):
            tokens.extend(filename_tokens)
    return tokens


def _unit_type_tokens(normalized_query: str) -> list[str]:
    """Filename tokens for a bedroom count or "studio" named in the text — nothing else.

    Kept separate from `_subject_tokens` (which includes the generic "mat-bang"/"matbang"
    topic token) on purpose: `select_listing_images` needs ONLY the unit-type-specific
    tokens, precisely so a whole-tower floor plan (any filename with "mat-bang" in it,
    regardless of which unit type it shows) does not qualify as a match for "2PN" just
    because both happen to say "mat-bang" somewhere.
    """
    tokens: list[str] = []

    # Unit types are written straight into filenames, but different catalogues disagree on
    # the convention: some use "...-2pn-.../...-3-phong-ngu-...", others (The Zurich, The
    # Zenpark) instead use "...-1-ngu-..." (from listing.unit_type values like "1 ngủ").
    # Both are generated so either matches. The extraction regex accepts bare "ngu" too
    # (not just "phong ngu"), since that shorter form is exactly how those unit_type
    # values already read once diacritics are stripped ("1 ngủ" -> "1 ngu").
    for bedrooms in re.findall(r"\b(\d)\s*(?:pn|phong\s*ngu|ngu)\b", normalized_query):
        tokens.extend([f"{bedrooms}pn", f"{bedrooms}-phong-ngu", f"{bedrooms}-pn", f"{bedrooms}-ngu"])

    # "Studio" has no bedroom count to extract, so it needs its own check — the catalogue
    # tags studio floor plans/renders with the literal word ("can-ho-studio-zr1-...").
    if re.search(r"\bstudio\b", normalized_query):
        tokens.append("studio")

    # Villa unit types have no bedroom count at all — they're named by build type instead
    # ("Biệt thự đơn lập"/"song lập"/"liền kề"), and the catalogue tags villa photos the
    # same way ("don-lap-hai-au.jpg").
    for phrase, token in (("don lap", "don-lap"), ("song lap", "song-lap"), ("lien ke", "lien-ke")):
        if phrase in normalized_query:
            tokens.append(token)

    return tokens


def _wanted_tokens(normalized_query: str) -> list[str]:
    """Subjects plus qualifiers — everything usable to narrow the gallery."""
    tokens = _subject_tokens(normalized_query)
    tokens.extend(_unit_type_tokens(normalized_query))

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
    projects = db.query(Project).all()

    for project in projects:
        for normalized in _project_aliases(project):
            if len(normalized) < _MIN_NAME_LENGTH or normalized not in haystack:
                continue
            if len(normalized) > best_length:
                best, best_length = project, len(normalized)

    if best is not None:
        return best

    # Fallback for a multi-word project name written with no space between words (a model
    # occasionally writes "SaoBiển" instead of "Sao Biển" in a listing's project_name) —
    # only tried once the spaced match above found nothing, so a real spaced match always
    # wins and this never changes behaviour for the normal case.
    compact_haystack = haystack.replace(" ", "")
    for project in projects:
        for normalized in _project_aliases(project):
            compact_alias = normalized.replace(" ", "")
            if len(compact_alias) < _MIN_NAME_LENGTH or compact_alias not in compact_haystack:
                continue
            if len(compact_alias) > best_length:
                best, best_length = project, len(compact_alias)

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
    aliases.update(alias.removeprefix("the ") for alias in tuple(aliases))
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
