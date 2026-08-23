from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from backend.core.enums import (
    DocumentCategory,
    DocumentVisibility,
    LegalStatus,
)


class DocumentCreate(BaseModel):
    title: str
    file_path: str | None = None
    project_id: str | None = None
    visibility: DocumentVisibility = DocumentVisibility.INTERNAL

    category: DocumentCategory = DocumentCategory.OTHER
    subcategory: str | None = None
    subdivision_names: list[str] | None = None
    building_codes: list[str] | None = None
    unit_types: list[str] | None = None
    applicable_area: str | None = None

    version_label: str | None = None
    issued_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    applicable_period: str | None = None

    legal_document_type: str | None = None
    legal_document_number: str | None = None
    legal_issuer: str | None = None
    legal_domain: str | None = None
    legal_status: LegalStatus = LegalStatus.UNKNOWN


class DocumentSecurityFinding(BaseModel):
    rule_id: str
    severity: str
    description: str
    page: int | None = None
    excerpt: str


class DocumentResponse(BaseModel):
    id: int
    title: str
    file_path: str | None = None
    project_id: str | None = None
    status: str
    visibility: str

    category: str
    subcategory: str | None = None
    subdivision_names: list[str] | None = None
    building_codes: list[str] | None = None
    unit_types: list[str] | None = None
    applicable_area: str | None = None

    document_summary: str | None = None
    version_label: str | None = None
    issued_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    applicable_period: str | None = None

    legal_document_type: str | None = None
    legal_document_number: str | None = None
    legal_issuer: str | None = None
    legal_domain: str | None = None
    legal_status: str
    is_current: bool

    review_status: str
    classification_confidence: float | None = None
    classification_reason: str | None = None
    block_reason: str | None = None
    security_findings: list[DocumentSecurityFinding] = Field(default_factory=list)
    classification_requires_admin_review: bool | None = None
    classification_version: str | None = None
    classified_at: datetime | None = None
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None

    uploaded_by: int | None = None
    uploaded_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("security_findings", mode="before")
    @classmethod
    def _normalise_security_findings(cls, value):
        return value or []


class DocumentClassificationUpdate(BaseModel):
    category: DocumentCategory
    subcategory: str | None = None

    subdivision_names: list[str] | None = None
    building_codes: list[str] | None = None
    unit_types: list[str] | None = None
    applicable_area: str | None = None

    document_summary: str | None = None
    version_label: str | None = None
    issued_date: date | None = None
    effective_date: date | None = None
    expiry_date: date | None = None
    applicable_period: str | None = None

    legal_document_type: str | None = None
    legal_document_number: str | None = None
    legal_issuer: str | None = None
    legal_domain: str | None = None
    legal_status: LegalStatus = LegalStatus.UNKNOWN
