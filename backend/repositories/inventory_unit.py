from sqlalchemy.orm import Session, joinedload

from backend.models.inventory_unit import InventoryUnit, InventoryUnitImage
from backend.schemas.inventory_unit import InventoryUnitCreate, InventoryUnitFilter, InventoryUnitUpdate


def get_unit_by_code(db: Session, unit_code: str) -> InventoryUnit | None:
    return db.query(InventoryUnit).filter(InventoryUnit.unit_code == unit_code).first()


def get_unit(db: Session, unit_id: int) -> InventoryUnit | None:
    return db.query(InventoryUnit).options(joinedload(InventoryUnit.images)).filter(InventoryUnit.id == unit_id).first()


def list_units(db: Session) -> list[InventoryUnit]:
    """Admin — toàn bộ căn, không lọc is_public (CLAUDE.md §6.6)."""
    return db.query(InventoryUnit).order_by(InventoryUnit.updated_at.desc()).all()


def list_public_units(db: Session, filters: InventoryUnitFilter) -> list[InventoryUnit]:
    """Customer Portal — chỉ căn is_public=True (CLAUDE.md §6.3.a)."""
    query = db.query(InventoryUnit).filter(InventoryUnit.is_public.is_(True))

    if filters.project_id:
        query = query.filter(InventoryUnit.project_id == filters.project_id)
    if filters.unit_type:
        query = query.filter(InventoryUnit.unit_type == filters.unit_type)
    if filters.min_price is not None:
        query = query.filter(InventoryUnit.price >= filters.min_price)
    if filters.max_price is not None:
        query = query.filter(InventoryUnit.price <= filters.max_price)

    return query.order_by(InventoryUnit.updated_at.desc()).all()


def create_unit(db: Session, schema: InventoryUnitCreate) -> InventoryUnit:
    unit = InventoryUnit(**schema.model_dump())
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


def update_unit(db: Session, unit_id: int, schema: InventoryUnitUpdate) -> InventoryUnit:
    unit = db.query(InventoryUnit).filter(InventoryUnit.id == unit_id).first()
    if unit is None:
        raise ValueError(f"Inventory unit {unit_id} not found")

    for field, value in schema.model_dump(exclude_unset=True).items():
        setattr(unit, field, value)

    db.commit()
    db.refresh(unit)
    return unit


def delete_unit(db: Session, unit_id: int) -> None:
    unit = db.query(InventoryUnit).filter(InventoryUnit.id == unit_id).first()
    if unit is None:
        raise ValueError(f"Inventory unit {unit_id} not found")
    db.delete(unit)
    db.commit()


def add_unit_image(db: Session, unit_id: int, image_path: str) -> InventoryUnitImage:
    image = InventoryUnitImage(unit_id=unit_id, image_path=image_path)
    db.add(image)

    unit = db.query(InventoryUnit).filter(InventoryUnit.id == unit_id).first()
    if unit is not None:
        unit.has_images = True

    db.commit()
    db.refresh(image)
    return image


def upsert_unit_from_bulk_row(db: Session, schema: InventoryUnitCreate) -> InventoryUnit:
    """Ghi 1 dòng từ Excel hàng loạt — ghi đè nếu Mã căn đã tồn tại (CLAUDE.md §6.6.a)."""
    existing = get_unit_by_code(db, schema.unit_code)
    if existing is not None:
        for field, value in schema.model_dump().items():
            setattr(existing, field, value)
        db.commit()
        db.refresh(existing)
        return existing

    return create_unit(db, schema)
