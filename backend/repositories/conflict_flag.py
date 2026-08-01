from datetime import datetime

from sqlalchemy.orm import Session

from backend.core.enums import ConflictStatus
from backend.models.conflict_flag import ConflictFlag


def create_conflict(db: Session, document_id_a: int, document_id_b: int, description: str | None) -> ConflictFlag:
    conflict = ConflictFlag(
        document_id_a=document_id_a,
        document_id_b=document_id_b,
        description=description,
        status=ConflictStatus.OPEN,
    )
    db.add(conflict)
    db.commit()
    db.refresh(conflict)
    return conflict


def list_open_conflicts(db: Session) -> list[ConflictFlag]:
    return db.query(ConflictFlag).filter(ConflictFlag.status == ConflictStatus.OPEN).all()


def resolve_conflict(db: Session, conflict_id: int) -> ConflictFlag:
    conflict = db.query(ConflictFlag).filter(ConflictFlag.id == conflict_id).first()
    if conflict is None:
        raise ValueError(f"ConflictFlag with id={conflict_id} not found.")
    conflict.status = ConflictStatus.RESOLVED
    conflict.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(conflict)
    return conflict
