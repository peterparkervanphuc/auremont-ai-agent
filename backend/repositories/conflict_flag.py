from sqlalchemy.orm import Session

from backend.core.enums import ConflictStatus, DocumentStatus
from backend.models.conflict_flag import ConflictFlag
from backend.models.document import Document
from backend.utils.time import utcnow


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


def resolve_conflict(
    db: Session,
    conflict_id: int,
    keep_document_id: int,
    resolved_by: int | None = None,
) -> ConflictFlag:
    """Đóng flag mâu thuẫn: giữ 1 tài liệu, vô hiệu hoá tài liệu còn lại.

    `keep_document_id` phải là một trong hai tài liệu của flag — nếu không, quyết
    định của Admin sẽ áp lên nhầm tài liệu.
    """
    conflict = db.query(ConflictFlag).filter(ConflictFlag.id == conflict_id).first()
    if conflict is None:
        raise ValueError(f"ConflictFlag with id={conflict_id} not found.")

    pair = (conflict.document_id_a, conflict.document_id_b)
    if keep_document_id not in pair:
        raise ValueError(f"keep_document_id={keep_document_id} is not part of conflict {conflict_id} {pair}.")

    superseded_id = conflict.document_id_b if keep_document_id == conflict.document_id_a else conflict.document_id_a

    # "Xoá tài liệu cũ / Ưu tiên tài liệu mới": đánh dấu BLOCKED thay vì DELETE.
    # Bản ghi flag vẫn trỏ tới tài liệu này qua khoá ngoại nên xoá hẳn sẽ vi phạm
    # ràng buộc; BLOCKED vừa loại nó khỏi kho tri thức, vừa giữ lại vết đối chiếu.
    superseded = db.query(Document).filter(Document.id == superseded_id).first()
    if superseded is not None:
        superseded.status = DocumentStatus.BLOCKED

    conflict.status = ConflictStatus.RESOLVED
    conflict.resolved_at = utcnow()
    conflict.resolved_by = resolved_by

    db.commit()
    db.refresh(conflict)
    return conflict
