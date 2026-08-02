"""Document ingest pipeline: sanitize -> chunk -> embed -> upsert to Qdrant.

TODO:
- Parse PDF/Excel/Word via LlamaIndex loaders.
- Scan for hidden prompt-injection payloads before chunking; on detection, mark the document
  status as BLOCKED and do not index it.
- Chunk + embed + upsert into Qdrant with payload {document_id, project_id, visibility}.
- After indexing, run a conflict-detection pass against existing documents in the same project
  (e.g. two price-list versions) and create a ConflictFlag when found.
"""


class PromptInjectionError(Exception):
    pass


def sanitize_and_scan(raw_text: str) -> str:
    """Strip/neutralize hidden prompt-injection payloads. Raises PromptInjectionError if unsafe."""
    raise NotImplementedError("TODO: implement prompt-injection scanning")


def ingest_document(document_id: int, raw_text: str, project_id: str | None, visibility: str) -> None:
    """Chunk, embed, and upsert the document into Qdrant; update Document.status when done."""
    raise NotImplementedError("TODO: implement chunk + embed + upsert pipeline")
