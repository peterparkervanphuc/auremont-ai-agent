"""Project catalogue — the list a Sale picks from when opening a consultation session.

`project_id` is the key that makes two features work: real-time inventory lookups
(`lookup_inventory` requires it) and filtering retrieval to one project's documents.
Without a way to read the catalogue the frontend has nothing to put in its dropdown,
so both features stay dead no matter how complete the pipeline is.

Reading is open to SALE as well as ADMIN — a Sale must see the list to choose a
project — while creating a project stays ADMIN-only.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.deps import require_role
from backend.core.enums import UserRole
from backend.core.mysql_client import get_db
from backend.repositories.project import create_project, get_project, list_projects
from backend.schemas.project import ProjectCreate, ProjectResponse

router = APIRouter(
    prefix="/projects",
    tags=["Projects"],
    dependencies=[Depends(require_role(UserRole.SALE, UserRole.ADMIN))],
)


@router.get("", response_model=list[ProjectResponse])
async def get_projects(db: Session = Depends(get_db)) -> list[ProjectResponse]:
    """List every project. An empty list drives the Sale-side empty state."""
    return list_projects(db)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project_by_id(project_id: str, db: Session = Depends(get_db)) -> ProjectResponse:
    project = get_project(db, project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role(UserRole.ADMIN))],
)
async def add_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> ProjectResponse:
    """Create a project. ADMIN only — this defines the catalogue Sales work against."""
    return create_project(db, payload)
