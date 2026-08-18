from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.core.config import get_settings
from backend.core.deps import require_role
from backend.core.enums import UserRole

router = APIRouter(
    prefix="/admin/settings", tags=["Admin Settings"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)


class SettingsResponse(BaseModel):
    verifier_threshold_sale: float


class SettingsUpdateRequest(BaseModel):
    verifier_threshold_sale: float | None = None


@router.get("", response_model=SettingsResponse)
async def get_settings_values() -> SettingsResponse:
    settings = get_settings()
    return SettingsResponse(verifier_threshold_sale=settings.verifier_threshold_sale)


@router.put("", response_model=SettingsResponse)
async def update_settings_values(payload: SettingsUpdateRequest) -> SettingsResponse:
    """Configure the Verifier Agent's minimum confidence threshold.

    TODO: persist to DB/config store instead of only reflecting env-based settings — the current
    `Settings` object is process-wide and env-driven, so this endpoint cannot durably mutate it yet.
    """
    settings = get_settings()
    return SettingsResponse(
        verifier_threshold_sale=payload.verifier_threshold_sale or settings.verifier_threshold_sale,
    )
