from datetime import datetime

from sqlalchemy.orm import Session

from backend.core.enums import LiveChatStatus
from backend.models.livechat_request import LiveChatRequest


def create_request(db: Session, customer_id: str) -> LiveChatRequest:
    request = LiveChatRequest(customer_id=customer_id, status=LiveChatStatus.WAITING)
    db.add(request)
    db.commit()
    db.refresh(request)
    return request


def list_waiting_requests(db: Session) -> list[LiveChatRequest]:
    return (
        db.query(LiveChatRequest)
        .filter(LiveChatRequest.status == LiveChatStatus.WAITING)
        .order_by(LiveChatRequest.created_at)
        .all()
    )


def accept_request(db: Session, request_id: int, sale_id: int, session_id: int) -> LiveChatRequest:
    request = db.query(LiveChatRequest).filter(LiveChatRequest.id == request_id).first()
    if request is None:
        raise ValueError(f"LiveChatRequest with id={request_id} not found.")
    request.sale_id = sale_id
    request.session_id = session_id
    request.status = LiveChatStatus.ACTIVE
    request.accepted_at = datetime.utcnow()
    db.commit()
    db.refresh(request)
    return request


def end_request(db: Session, request_id: int) -> LiveChatRequest:
    request = db.query(LiveChatRequest).filter(LiveChatRequest.id == request_id).first()
    if request is None:
        raise ValueError(f"LiveChatRequest with id={request_id} not found.")
    request.status = LiveChatStatus.ENDED
    request.ended_at = datetime.utcnow()
    db.commit()
    db.refresh(request)
    return request
