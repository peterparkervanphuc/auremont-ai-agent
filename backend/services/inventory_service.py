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

import re
from dataclasses import dataclass, fields

import httpx

from backend.core.config import settings

INVENTORY_TIMEOUT_SECONDS = 5.0

# Unit types a Sale commonly mentions: "2PN", "3 pn", "Penthouse", "Studio", "Shophouse", "Duplex".
# \b at both ends so "21PN" is not mis-matched as "1PN".
_UNIT_TYPE_PATTERN = re.compile(r"\b(\d+\s*pn|penthouse|studio|shophouse|duplex)\b", re.IGNORECASE)


class InventoryApiError(Exception):
    """Lost connection to, or a bad response from, the internal inventory API."""


@dataclass
class InventoryUnit:
    unit_code: str
    project_id: str
    unit_type: str | None
    price: float | None
    status: str


def lookup_inventory(project_id: str, query: str) -> list[InventoryUnit]:
    """Look up a project's inventory, filtered by the unit type mentioned in the question.

    Returns an empty list when the project has no matching units left — that is a valid
    answer ("there are no 2PN units available"), entirely different from failing to reach
    the inventory. Conflating the two would show the Sale "Tạm thời không tra được tồn kho"
    while the API is perfectly healthy and the correct answer is simply "sold out".

    Raises `InventoryApiError` only when data genuinely cannot be fetched from the API.
    """
    payload = _fetch_units(project_id)

    units = [unit for unit in (_parse_unit(item) for item in payload) if unit is not None]

    wanted_type = _extract_unit_type(query)
    if wanted_type is not None:
        units = [unit for unit in units if _normalize_unit_type(unit.unit_type) == wanted_type]

    return units


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
        return None

    data = {key: value for key, value in item.items() if key in _FIELD_NAMES}
    if not {"unit_code", "project_id", "status"} <= data.keys():
        return None

    unit_type = data.get("unit_type")
    return InventoryUnit(
        unit_code=str(data["unit_code"]),
        project_id=str(data["project_id"]),
        unit_type=str(unit_type) if unit_type is not None else None,
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
        return None


def _extract_unit_type(query: str) -> str | None:
    """Extract the unit type from a Sale's natural question. None means ask broadly, no filter."""
    match = _UNIT_TYPE_PATTERN.search(query)
    return _normalize_unit_type(match.group(0)) if match else None


def _normalize_unit_type(unit_type: str | None) -> str | None:
    """Normalise '3 pn' and '3PN' to '3PN' so matching does not depend on how the Sale or
    the API happens to spell it."""
    if unit_type is None:
        return None
    return re.sub(r"\s+", "", unit_type).upper()
