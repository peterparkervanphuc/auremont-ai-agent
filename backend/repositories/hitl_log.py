from datetime import datetime

from sqlalchemy.orm import Session

from backend.core.enums import HitlStatus
from backend.models.hitl_log import HitlLog


def create_hitl_log(db: Session, message_id: int, sale_id: int) -> HitlLog:
    log = HitlLog(message_id=message_id, sale_id=sale_id, status=HitlStatus.PENDING)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def confirm_hitl_log(db: Session, log_id: int, confirmed_content: str) -> HitlLog:
    log = db.query(HitlLog).filter(HitlLog.id == log_id).first()
    if log is None:
        raise ValueError(f"HitlLog with id={log_id} not found.")
    log.status = HitlStatus.CONFIRMED
    log.confirmed_content = confirmed_content
    log.confirmed_at = datetime.utcnow()
    db.commit()
    db.refresh(log)
    return log
