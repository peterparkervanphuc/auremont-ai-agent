import re
import uuid
from io import BytesIO
from pathlib import PurePath

from sqlalchemy.orm import Session

from backend.core.config import settings
from backend.core.enums import DocumentStatus
from backend.core.gemini_client import embed_documents
from backend.core.minio_client import ensure_bucket, get_minio_client
from backend.models.document import Document
from backend.repositories.document import (
    update_document_status,
    update_document_storage_path,
)
from backend.services.chunking_service import chunk_sections
from backend.services.parser_service import parse_document
from backend.services.vector_store_service import index_document_chunks


class PromptInjectionError(ValueError):
    """Tài liệu có chỉ dẫn cố thao túng AI."""


class DocumentIngestionError(RuntimeError):
    """Lỗi parse, lưu object, embed hoặc index tài liệu."""


SUSPICIOUS_PATTERNS = [
    r"ignore\s+(all|any|previous|prior)\s+instructions",
    r"system\s+prompt",
    r"you\s+are\s+chatgpt",
    r"<\s*system\s*>",
    r"jailbreak",
    r"do\s+not\s+follow\s+(the\s+)?rules",
]


def sanitize_and_scan(raw_text: str) -> str:
    """Kiểm tra rule cơ bản trước khi tài liệu vào kho tri thức."""
    cleaned = raw_text.replace("\x00", "").strip()

    if not cleaned:
        raise DocumentIngestionError("Document contains no text.")

    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            raise PromptInjectionError(
                "Potential prompt-injection content detected."
            )

    return cleaned


def ingest_uploaded_document(
    db: Session,
    *,
    document: Document,
    filename: str,
    file_bytes: bytes,
    content_type: str | None,
) -> Document:
    """Luồng hoàn chỉnh cho một file PDF/DOCX đã được upload.

    Document phải được tạo trong DB trước, vì document.id được dùng để tạo
    MinIO object key và Qdrant point ID ổn định.
    """
    try:
        update_document_status(db, document.id, DocumentStatus.PROCESSING)

        sections = parse_document(filename, file_bytes)
        raw_text = "\n\n".join(section.text for section in sections)
        sanitize_and_scan(raw_text)

        object_key = _store_original_file(
            document_id=document.id,
            filename=filename,
            file_bytes=file_bytes,
            content_type=content_type,
        )
        update_document_storage_path(db, document.id, object_key)

        chunks = chunk_sections(sections)
        if not chunks:
            raise DocumentIngestionError("No chunks were produced.")

        # Chia batch để không gửi quá nhiều chunk trong một Gemini request.
        vectors: list[list[float]] = []
        batch_size = 32

        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors.extend(
                embed_documents(
                    [chunk.text for chunk in batch],
                    title=document.title,
                )
            )

        index_document_chunks(
            document_id=document.id,
            title=document.title,
            project_id=document.project_id,
            visibility=document.visibility,
            chunks=chunks,
            vectors=vectors,
        )

        return update_document_status(
            db,
            document.id,
            DocumentStatus.COMPLETED,
        )

    except PromptInjectionError:
        update_document_status(db, document.id, DocumentStatus.BLOCKED)
        raise

    except Exception as exc:
        update_document_status(db, document.id, DocumentStatus.FAILED)

        if isinstance(exc, DocumentIngestionError):
            raise

        raise DocumentIngestionError(
            f"Could not ingest document {document.id}."
        ) from exc


def _store_original_file(
    *,
    document_id: int,
    filename: str,
    file_bytes: bytes,
    content_type: str | None,
) -> str:
    """Lưu file gốc MinIO; DB chỉ lưu object key."""
    safe_filename = PurePath(filename).name
    object_key = (
        f"documents/{document_id}/"
        f"{uuid.uuid4().hex}-{safe_filename}"
    )

    try:
        ensure_bucket(settings.minio_bucket_documents)

        get_minio_client().put_object(
            bucket_name=settings.minio_bucket_documents,
            object_name=object_key,
            data=BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=content_type or "application/octet-stream",
        )
    except Exception as exc:
        raise DocumentIngestionError(
            "Could not store original file in MinIO."
        ) from exc

    return object_key
