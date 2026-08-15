"""Tool for looking up unit inventory through the company's real-time internal API.

The Main Agent calls this (Function Calling) when a Sale's question needs live inventory
data — something deliberately kept out of the Vector DB, because stock changes constantly
and anything ingested into Qdrant would answer with stale numbers.

During the build phase `INVENTORY_API_URL` points at a mock API (mockapi.io) shaped
exactly like the internal production API, so switching to the real one is an environment
variable change rather than a code change.

Every API failure is wrapped in `InventoryApiError` so the router/pipeline can show the
proper "Tạm thời không tra được tồn kho" message instead of letting the error escape as a 500.
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, fields

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

INVENTORY_TIMEOUT_SECONDS = 5.0

# Unit types a Sale commonly mentions: "2PN", "3 pn", "2 phòng ngủ",
# "Penthouse", "Studio", "Shophouse", "Duplex".  The captured bedroom forms
# are normalised to the API convention (for example, "2 phòng ngủ" -> "2PN").
# \b at both ends so "21PN" is not mis-matched as "1PN".
_UNIT_TYPE_PATTERN = re.compile(
    r"\b(\d+\s*(?:pn|phòng\s*ngủ|phong\s*ngu)|penthouse|studio|shophouse|duplex)\b",
    re.IGNORECASE,
)
_AREA_RANGE_PATTERN = re.compile(r"\b(?:từ\s*)?(\d+(?:[.,]\d+)?)\s*(?:-|đến|tới)\s*(\d+(?:[.,]\d+)?)\s*m(?:2|²)\b", re.IGNORECASE)
_AREA_MAX_PATTERN = re.compile(r"\b(?:dưới|<=?|không quá|tối đa)\s*(\d+(?:[.,]\d+)?)\s*m(?:2|²)\b", re.IGNORECASE)
_AREA_MIN_PATTERN = re.compile(r"\b(?:trên|>=?|từ)\s*(\d+(?:[.,]\d+)?)\s*m(?:2|²)\b", re.IGNORECASE)
_PRICE_RANGE_PATTERN = re.compile(r"\b(?:từ\s*)?(\d+(?:[.,]\d+)?)\s*(tỷ|triệu|tr|t)?\s*(?:-|đến|tới)\s*(\d+(?:[.,]\d+)?)\s*(tỷ|triệu|tr|t)\b", re.IGNORECASE)
_PRICE_MAX_PATTERN = re.compile(r"\b(?:dưới|<=?|không quá|tối đa)\s*(\d+(?:[.,]\d+)?)\s*(tỷ|triệu|tr|t)\b", re.IGNORECASE)
_PRICE_MIN_PATTERN = re.compile(r"\b(?:trên|>=?|từ)\s*(\d+(?:[.,]\d+)?)\s*(tỷ|triệu|tr|t)\b", re.IGNORECASE)
_STATUS_PATTERN = re.compile(r"\b(còn căn|còn bán|còn hàng|còn trống|available|giữ chỗ|đặt chỗ|reserved|đã bán|sold)\b", re.IGNORECASE)
_STATUS_ALIASES = {"còn căn": "available", "còn bán": "available", "còn hàng": "available", "còn trống": "available", "available": "available", "giữ chỗ": "reserved", "đặt chỗ": "reserved", "reserved": "reserved", "đã bán": "sold", "sold": "sold"}


class InventoryApiError(Exception):
    """Lost connection to, or a bad response from, the internal inventory API."""


@dataclass
class InventoryUnit:
    unit_code: str
    project_id: str
    subdivision: str | None
    unit_type: str | None
    area_m2: float | None
    price: float | None
    status: str


def lookup_inventory(project_id: str | None, query: str) -> list[InventoryUnit]:
    """Look up a project's inventory, filtered by the unit type mentioned in the question.

    `project_id` is the catalogue slug held on the chat session, or None when the session
    carries no project — `resolve_api_project_id` translates it into the code the
    inventory API actually keys units by. None is a normal case, not an error: the session
    flow no longer asks the Sale to pick a project, so the configured catch-all decides
    which project's stock to read.

    Returns an empty list when the project has no matching units left — that is a valid
    answer ("there are no 2PN units available"), entirely different from failing to reach
    the inventory. Conflating the two would show the Sale "Tạm thời không tra được tồn kho"
    while the API is perfectly healthy and the correct answer is simply "sold out".

    Raises `InventoryApiError` only when data genuinely cannot be fetched from the API.
    """
    api_project_id = resolve_api_project_id(project_id)
    if api_project_id is None:
        raise InventoryApiError(
            "No inventory project id: the session carries no project and "
            "INVENTORY_PROJECT_MAP defines no '*' catch-all."
        )

    payload = _fetch_units(api_project_id)

    units = [unit for unit in (_parse_unit(item) for item in payload) if unit is not None]
    units = [unit for unit in units if unit.project_id == api_project_id]

    return _apply_query_filters(units, query)


def resolve_api_project_id(project_id: str | None) -> str | None:
    """Translate a catalogue slug into the inventory API's own project code.

    The two namespaces are genuinely different: `projects.id` is a catalogue slug per
    sub-zone (`the-palma`, `hai-au`), while the inventory API groups every one of those
    under a single project code (`ocean-park-3`) and exposes the sub-zone as
    `subdivision`. Sending the slug through unmapped is a guaranteed 404.

    Returns None only when nothing can be resolved — no project on the session and no
    catch-all configured — which the caller turns into `InventoryApiError`.
    """
    mapping = _project_map()

    if project_id:
        # An exact mapping wins; otherwise fall through to the catch-all, and finally to
        # the slug itself so an API keyed by the same slugs needs no configuration.
        return mapping.get(project_id) or mapping.get("*") or project_id

    return mapping.get("*")


def _project_map() -> dict[str, str]:
    """Parse INVENTORY_PROJECT_MAP ("slug=code, *=code") into a dict.

    Malformed entries are skipped with a warning rather than raising: a typo in one pair
    must not take down inventory lookups for every other project.
    """
    raw = settings.inventory_project_map
    if not raw:
        return {}

    mapping: dict[str, str] = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        key, separator, value = entry.partition("=")
        key, value = key.strip(), value.strip()
        if not separator or not key or not value:
            logger.warning(
                "Bo qua muc INVENTORY_PROJECT_MAP khong hop le.",
                extra={"event": "inventory.project_map.invalid_entry", "entry": entry},
            )
            continue
        mapping[key] = value

    return mapping


def _fetch_units(project_id: str) -> list:
    """Call the inventory API and return the raw payload, guaranteed to be a list."""
    if not settings.inventory_api_url:
        raise InventoryApiError("INVENTORY_API_URL is not configured.")

    headers = {}
    if settings.inventory_api_key:
        headers["Authorization"] = f"Bearer {settings.inventory_api_key}"

    try:
        response = httpx.get(
            settings.inventory_api_url,
            params={"project_id": project_id},
            headers=headers,
            timeout=INVENTORY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPError as exc:
        # Catch the whole HTTPError branch: ConnectError, TimeoutException and
        # HTTPStatusError (raised by raise_for_status) are all subclasses of it.
        raise InventoryApiError(f"Inventory API unreachable: {exc}") from exc
    except ValueError as exc:
        # json.JSONDecodeError subclasses ValueError — hit when the API returns an HTML
        # error page instead of JSON, usually because the URL points somewhere wrong.
        raise InventoryApiError("Inventory API returned a body that is not JSON.") from exc

    if not isinstance(payload, list):
        raise InventoryApiError(f"Inventory API returned {type(payload).__name__}, expected a list.")

    return payload


_FIELD_NAMES = {field.name for field in fields(InventoryUnit)}


def _parse_unit(item: object) -> InventoryUnit | None:
    """Turn a raw record into an `InventoryUnit`; return None if the record is unusable.

    Skips bad records rather than raising: both the mock and the internal API carry extra
    fields (`id`, `createdAt`) or occasionally omit one, and a single dirty row is not
    worth failing a Sale's entire lookup over.
    """
    if not isinstance(item, dict):
        logger.warning(
            "Bo qua ban ghi ton kho khong phai object.",
            extra={"event": "inventory.record.not_dict", "record_type": type(item).__name__},
        )
        return None

    data = {key: value for key, value in item.items() if key in _FIELD_NAMES}
    if not {"unit_code", "project_id", "status"} <= data.keys():
        # Log only the NAMES of missing fields, not the values: the record may contain
        # the unit code and price.
        logger.warning(
            "Bo qua ban ghi ton kho thieu truong bat buoc.",
            extra={
                "event": "inventory.record.incomplete",
                "missing_fields": sorted({"unit_code", "project_id", "status"} - data.keys()),
            },
        )
        return None

    unit_type = data.get("unit_type")
    return InventoryUnit(
        unit_code=str(data["unit_code"]),
        project_id=str(data["project_id"]),
        subdivision=str(data["subdivision"]) if data.get("subdivision") is not None else None,
        unit_type=str(unit_type) if unit_type is not None else None,
        area_m2=_to_float(data.get("area_m2")),
        price=_to_float(data.get("price")),
        status=str(data["status"]),
    )


def _to_float(value: object) -> float | None:
    """Price arrives as a number or a string depending on the API; a bad price is left
    blank rather than discarding the whole unit."""
    if value is None or value == "":
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        # DEBUG: an unparseable price only blanks the price field; the unit record is
        # still valid and kept.
        logger.debug(
            "Gia ton kho khong doc duoc, de trong.",
            extra={"event": "inventory.price.unparseable", "value_type": type(value).__name__},
        )
        return None


def _extract_unit_type(query: str) -> str | None:
    """Extract the unit type from a Sale's natural question. None means ask broadly, no filter."""
    match = _UNIT_TYPE_PATTERN.search(query)
    return _normalize_unit_type(match.group(0)) if match else None


def _normalize_unit_type(unit_type: str | None) -> str | None:
    """Normalise bedroom synonyms to the API form, e.g. '3 phòng ngủ' -> '3PN'."""
    if unit_type is None:
        return None

    normalized = _normalize_text(unit_type)
    bedroom_match = re.fullmatch(r"(\d+)\s*(?:pn|phong\s*ngu)", normalized)
    if bedroom_match:
        return f"{bedroom_match.group(1)}PN"
    return re.sub(r"\s+", "", unit_type).upper()


def _apply_query_filters(units: list[InventoryUnit], query: str) -> list[InventoryUnit]:
    """Apply all explicit natural-language filters with AND semantics."""
    wanted_type = _extract_unit_type(query)
    if wanted_type is not None:
        units = [unit for unit in units if _normalize_unit_type(unit.unit_type) == wanted_type]

    wanted_subdivision = _extract_subdivision(query, units)
    if wanted_subdivision is not None:
        units = [unit for unit in units if _normalize_text(unit.subdivision) == wanted_subdivision]

    area_range = _extract_area_range(query)
    if area_range is not None:
        minimum, maximum = area_range
        units = [unit for unit in units if unit.area_m2 is not None and minimum <= unit.area_m2 <= maximum]

    price_range = _extract_price_range(query)
    if price_range is not None:
        minimum, maximum = price_range
        units = [unit for unit in units if unit.price is not None and minimum <= unit.price <= maximum]

    wanted_status = _extract_status(query)
    if wanted_status is not None:
        units = [unit for unit in units if unit.status.strip().lower() == wanted_status]
    return units


def _extract_subdivision(query: str, units: list[InventoryUnit]) -> str | None:
    normalized_query = _normalize_text(query)
    candidates = {_normalize_text(unit.subdivision) for unit in units if unit.subdivision}
    matches = [candidate for candidate in candidates if candidate and candidate in normalized_query]
    return max(matches, key=len) if matches else None


def _extract_area_range(query: str) -> tuple[float, float] | None:
    match = _AREA_RANGE_PATTERN.search(query)
    if match:
        return _ordered_range(_to_number(match.group(1)), _to_number(match.group(2)))
    match = _AREA_MAX_PATTERN.search(query)
    if match:
        return 0.0, _to_number(match.group(1))
    match = _AREA_MIN_PATTERN.search(query)
    if match:
        return _to_number(match.group(1)), float("inf")
    return None


def _extract_price_range(query: str) -> tuple[float, float] | None:
    match = _PRICE_RANGE_PATTERN.search(query)
    if match:
        return _ordered_range(_price_to_vnd(match.group(1), match.group(2)), _price_to_vnd(match.group(3), match.group(4)))
    match = _PRICE_MAX_PATTERN.search(query)
    if match:
        return 0.0, _price_to_vnd(match.group(1), match.group(2))
    match = _PRICE_MIN_PATTERN.search(query)
    if match:
        return _price_to_vnd(match.group(1), match.group(2)), float("inf")
    return None


def _extract_status(query: str) -> str | None:
    match = _STATUS_PATTERN.search(query)
    return _STATUS_ALIASES[match.group(1).lower()] if match else None


def _normalize_text(text: str | None) -> str:
    lowered = (text or "").casefold().replace("đ", "d")
    unaccented = "".join(char for char in unicodedata.normalize("NFD", lowered) if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", unaccented).strip()


def _to_number(value: str) -> float:
    return float(value.replace(",", "."))


def _price_to_vnd(value: str, unit: str | None) -> float:
    multiplier = {"tỷ": 1_000_000_000, "t": 1_000_000_000, "triệu": 1_000_000, "tr": 1_000_000}.get((unit or "").lower(), 1.0)
    return _to_number(value) * multiplier


def _ordered_range(first: float, second: float) -> tuple[float, float]:
    return min(first, second), max(first, second)
