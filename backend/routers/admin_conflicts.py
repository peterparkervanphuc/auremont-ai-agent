from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.repositories.conflict_flag import list_open_conflicts, resolve_conflict
from backend.schemas.conflict_flag import ConflictFlagResponse, ConflictResolveRequest

router = APIRouter(
    prefix="/admin/conflicts", tags=["Admin Conflicts"], dependencies=[Depends(require_role(UserRole.ADMIN))]
)


@router.get("", response_model=list[ConflictFlagResponse])
async def get_conflicts(db: Session = Depends(get_db)) -> list[ConflictFlagResponse]:
    """CLAUDE.md §6.5 Tab 3 — conflicting documents (e.g. two price-list versions of the same project)."""
    return list_open_conflicts(db)


@router.post("/{conflict_id}/resolve", response_model=ConflictFlagResponse)
async def resolve_conflict_flag(
    conflict_id: int, payload: ConflictResolveRequest, db: Session = Depends(get_db)
) -> ConflictFlagResponse:
    """Xoá tài liệu cũ / Ưu tiên tài liệu mới. TODO: delete/deprioritize the non-kept document."""
    try:
        return resolve_conflict(db, conflict_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
