import logging
import uuid

from qdrant_client import models

from backend.core.config import settings
from backend.core.qdrant_client import get_qdrant_client
from backend.services.chunking_service import DocumentChunk

logger = logging.getLogger(__name__)


class VectorStoreError(RuntimeError):
    """Failure while initialising the collection or writing vectors to Qdrant."""


def ensure_collection() -> None:
    """Create the collection if absent; reject a dimension mismatch if it already exists."""
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection

    if not client.collection_exists(collection_name):
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(
                size=settings.embedding_dimensions,
                distance=models.Distance.COSINE,
            ),
        )
        return

    collection = client.get_collection(collection_name)
    # Qdrant reports `vectors` as a single config, a mapping of named configs, or None.
    # This collection is created with one unnamed vector; the other two shapes have no
    # single size to compare and would otherwise fail with an AttributeError deep in the
    # ingestion path.
    vector_size = getattr(collection.config.params.vectors, "size", None)
    if vector_size is None:
        raise VectorStoreError(f"Collection '{collection_name}' does not use a single unnamed vector configuration.")

    if vector_size != settings.embedding_dimensions:
        raise VectorStoreError(
            f"Collection dimension is {vector_size}, but application expects {settings.embedding_dimensions}."
        )


def index_document_chunks(
    *,
    document_id: int,
    title: str,
    project_id: str | None,
    visibility: str,
    chunks: list[DocumentChunk],
    vectors: list[list[float]],
    review_status: str = "pending",
    legal_status: str = "unknown",
    category: str = "other",
    is_current: bool = True,
) -> int:
    """Write chunks and their corresponding vectors into Qdrant."""
    if len(chunks) != len(vectors):
        raise VectorStoreError("Number of chunks must match number of embeddings.")

    if not chunks:
        return 0

    if any(len(vector) != settings.embedding_dimensions for vector in vectors):
        raise VectorStoreError("An embedding has an unexpected dimension.")

    ensure_collection()

    points = [
        models.PointStruct(
            # Deterministic ID: the same document/chunk index never creates a duplicate.
            id=str(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    f"salesmate:document:{document_id}:chunk:{chunk.index}",
                )
            ),
            vector=vector,
            payload={
                "document_id": document_id,
                "project_id": project_id,
                "visibility": visibility,
                "title": title,
                "page": chunk.page,
                "chunk_index": chunk.index,
                "content": chunk.text,
                "category": category,
                "review_status": review_status,
                "legal_status": legal_status,
                "is_current": is_current,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]

    try:
        get_qdrant_client().upsert(
            collection_name=settings.qdrant_collection,
            points=points,
            wait=True,
        )
    except Exception as exc:
        logger.exception(
            "Writing vectors to Qdrant failed.",
            extra={"event": "vector_store.upsert.failed", "point_count": len(points)},
        )
        raise VectorStoreError("Could not upsert vectors into Qdrant.") from exc

    return len(points)


def delete_document_vectors(document_id: int) -> None:
    """Delete every vector belonging to a document; used when deleting or re-indexing it."""
    try:
        get_qdrant_client().delete(
            collection_name=settings.qdrant_collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
            wait=True,
        )
    except Exception as exc:
        logger.exception(
            "Deleting vectors for document %s failed.",
            document_id,
            extra={"event": "vector_store.delete.failed", "document_id": document_id},
        )
        raise VectorStoreError(f"Could not delete vectors for document {document_id}.") from exc


def update_document_vector_metadata(
    document_id: int,
    *,
    review_status: str,
    legal_status: str,
    category: str,
    visibility: str,
    is_current: bool,
) -> None:
    """Synchronise approval metadata for every existing chunk of one document.

    This does not re-embed content. It only changes Qdrant payload fields, which
    makes an Admin approval visible to retrieval immediately.
    """
    try:
        client = get_qdrant_client()
        if not client.collection_exists(settings.qdrant_collection):
            return

        client.set_payload(
            collection_name=settings.qdrant_collection,
            payload={
                "review_status": review_status,
                "legal_status": legal_status,
                "is_current": is_current,
                "category": category,
                "visibility": visibility,
            },
            points=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="document_id",
                            match=models.MatchValue(value=document_id),
                        )
                    ]
                )
            ),
            wait=True,
        )
    except Exception as exc:
        raise VectorStoreError(f"Could not update vector metadata for document {document_id}.") from exc
