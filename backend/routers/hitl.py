from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.models.user import User
from backend.repositories.hitl_log import confirm_hitl_log, create_hitl_log
from backend.repositories.message import get_message
from backend.schemas.hitl_log import HitlConfirmRequest, HitlLogResponse

router = APIRouter(prefix="/hitl", tags=["HITL"], dependencies=[Depends(require_role(UserRole.SALE, UserRole.ADMIN))])


@router.post("/{message_id}/confirm", response_model=HitlLogResponse)
async def confirm_hitl(
    message_id: int,
    payload: HitlConfirmRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.SALE, UserRole.ADMIN)),
) -> HitlLogResponse:
    """Mandatory 'XÁC NHẬN & GỬI' action before a price/commitment answer can be sent or copied.

    Cả SALE và ADMIN đều chat được nên đều có thể xác nhận; hitl_log.sale_id ghi
    lại chính người bấm xác nhận, phục vụ truy vết sau này.
    """
    message = get_message(db, message_id)
    if message is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    if not message.requires_hitl:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message does not require HITL")

    log = create_hitl_log(db, message_id=message_id, sale_id=user.id)
    return confirm_hitl_log(db, log_id=log.id, confirmed_content=payload.confirmed_content)
