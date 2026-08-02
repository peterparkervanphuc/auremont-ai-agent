import uuid

from sqlalchemy.orm import Session

from backend.models.project import Project
from backend.schemas.project import ProjectCreate


def create_project(db: Session, schema: ProjectCreate) -> Project:
    project = Project(
        id=str(uuid.uuid4()),
        name=schema.name,
        location=schema.location,
        description=schema.description,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def list_projects(db: Session) -> list[Project]:
    return db.query(Project).order_by(Project.name).all()


def get_project(db: Session, project_id: str) -> Project | None:
    return db.query(Project).filter(Project.id == project_id).first()
