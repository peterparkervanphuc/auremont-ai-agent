import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.models.project import Project
from backend.repositories.project import get_project, list_projects
from backend.schemas.project import (
    CategoryDetail,
    CategorySummary,
    CategoryTypeRow,
    ProjectDetail,
    ProjectSummary,
)

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
    dependencies=[Depends(require_role(UserRole.SALE, UserRole.ADMIN))],
)


def _primary_type(details: dict | None) -> str:
    if not details:
        return "Dự án"
    categories = {p["category"] for p in (details.get("pricing") or []) if p.get("category")}
    if len(categories) > 1:
        return "Khu đô thị"
    return next(iter(categories), "Dự án")


def _price_from(details: dict | None) -> str | None:
    mins = [p["price_min"] for p in (details or {}).get("pricing") or [] if p.get("price_min") is not None]
    if not mins:
        return None
    return f"{min(mins) / 1_000_000_000:.1f} tỷ"


def _cover_image(details: dict | None) -> str | None:
    gallery = (details or {}).get("images", {}).get("gallery") or []
    return gallery[0] if gallery else None


def _to_summary(row: Project) -> ProjectSummary:
    return ProjectSummary(
        id=row.id,
        name=row.name,
        location=row.location,
        description=row.description,
        type=_primary_type(row.details),
        price_from=_price_from(row.details),
        cover_image=_cover_image(row.details),
    )


@router.get("", response_model=list[ProjectSummary])
def get_projects(db: Session = Depends(get_db)) -> list[ProjectSummary]:
    # Bỏ qua các row chưa có `details` — project rỗng (chưa nạp catalog) không đáng hiển thị để duyệt.
    return [_to_summary(row) for row in list_projects(db) if row.details]


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project_detail(project_id: str, db: Session = Depends(get_db)) -> ProjectDetail:
    row = get_project(db, project_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    details = row.details or {}
    project_info = details.get("project", {})
    summary = _to_summary(row)
    return ProjectDetail(
        **summary.model_dump(),
        developer=project_info.get("developer"),
        highlights=project_info.get("highlights", []),
        pricing=details.get("pricing", []),
        amenities=details.get("amenities", []),
        gallery=details.get("images", {}).get("gallery", []),
        contact=details.get("contact"),
    )


def _slugify(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()


def _billions(value: float) -> str:
    return f"{value / 1_000_000_000:.1f} tỷ"


CATEGORY_DESCRIPTION_FIELD = {
    "Chung cư": "apartment_description",
    "Biệt thự": "villa_description",
}


def _category_description(category: str, project_info: dict) -> str:
    field = CATEGORY_DESCRIPTION_FIELD.get(category)
    if field and project_info.get(field):
        return project_info[field]
    return project_info.get("overview_description") or project_info.get("description", "")


def _get_project_or_404(db: Session, project_id: str) -> Project:
    row = get_project(db, project_id)
    if row is None or not row.details:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return row


def _group_pricing_by_category(details: dict) -> dict[str, list[dict]]:
    """Giữ nguyên thứ tự xuất hiện trong `pricing` — dùng chung để cả 2 endpoint
    (list + detail) suy ra CÙNG một index cho từng category, nhờ đó chọn đúng ảnh
    đại diện nhất quán giữa danh sách và trang chi tiết (không bị trùng ảnh)."""
    groups: dict[str, list[dict]] = {}
    for tier in details.get("pricing", []):
        groups.setdefault(tier["category"], []).append(tier)
    return groups


def _cover_image_for(category: str, groups: dict[str, list[dict]], gallery: list[str]) -> str | None:
    if not gallery:
        return None
    index = list(groups.keys()).index(category)
    return gallery[index % len(gallery)]


@router.get("/{project_id}/categories", response_model=list[CategorySummary])
def get_categories(project_id: str, db: Session = Depends(get_db)) -> list[CategorySummary]:
    row = _get_project_or_404(db, project_id)
    details = row.details
    gallery = details.get("images", {}).get("gallery", [])
    groups = _group_pricing_by_category(details)

    summaries = []
    for category, tiers in groups.items():
        mins = [t["price_min"] for t in tiers if t.get("price_min") is not None]
        maxs = [t["price_max"] for t in tiers if t.get("price_max") is not None]
        sizes_min = [t["size_min_sqm"] for t in tiers if t.get("size_min_sqm") is not None]
        sizes_max = [t["size_max_sqm"] for t in tiers if t.get("size_max_sqm") is not None]
        summaries.append(
            CategorySummary(
                slug=_slugify(category),
                name=category,
                price_from=_billions(min(mins)) if mins else "Liên hệ",
                price_to=_billions(max(maxs)) if maxs else "Liên hệ",
                size_from=min(sizes_min) if sizes_min else None,
                size_to=max(sizes_max) if sizes_max else None,
                types_count=len(tiers),
                cover_image=_cover_image_for(category, groups, gallery),
                type_names=[t["apartment_type"] for t in tiers],
            )
        )
    return summaries


@router.get("/{project_id}/categories/{category_slug}", response_model=CategoryDetail)
def get_category_detail(project_id: str, category_slug: str, db: Session = Depends(get_db)) -> CategoryDetail:
    row = _get_project_or_404(db, project_id)
    details = row.details
    project_info = details.get("project", {})
    gallery = details.get("images", {}).get("gallery", [])
    groups = _group_pricing_by_category(details)

    tiers = [t for t in details.get("pricing", []) if _slugify(t["category"]) == category_slug]
    if not tiers:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    category_name = tiers[0]["category"]
    types = [
        CategoryTypeRow(
            type=t["apartment_type"],
            size_range=(
                f"{t['size_min_sqm']} - {t['size_max_sqm']} m²"
                if t.get("size_min_sqm") is not None and t.get("size_max_sqm") is not None
                else "—"
            ),
            price_range=(
                f"{_billions(t['price_min'])} - {_billions(t['price_max'])}"
                if t.get("price_min") is not None and t.get("price_max") is not None
                else "Liên hệ"
            ),
            description=t.get("description"),
            storeys=t.get("storeys"),
        )
        for t in tiers
    ]

    return CategoryDetail(
        slug=category_slug,
        name=category_name,
        description=_category_description(category_name, project_info),
        cover_image=_cover_image_for(category_name, groups, gallery),
        types=types,
        amenities=details.get("amenities", []),
        highlights=project_info.get("highlights", []),
        gallery=gallery,
    )
