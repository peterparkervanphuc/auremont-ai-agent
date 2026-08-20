"""Turn retrieved chunks into the citation list shown under an answer."""


def build_citations(docs: list[dict]) -> list[dict]:
    """Normalise citations into the exact shape of the `Citation` schema.

    One chip per file, not per page: retrieval routinely returns several chunks of the
    same PDF, and listing "Bảng giá · tr.1, Bảng giá · tr.2, Bảng giá · tr.10" told the Sale
    nothing they could act on while crowding the answer. The file name is the useful part.

    Deduplication is by title rather than by `document_id` on purpose: the same file
    uploaded twice becomes two documents with two ids, and keying on the id would put the
    identical name on screen twice — exactly the clutter this is meant to remove.

    Filtering is mandatory: `document_id` from a Qdrant payload may be None, while
    `Citation` declares a non-nullable `document_id: int` — letting one through becomes a
    ValidationError 500 while serializing the response. `content`/`score` are dropped too,
    since the schema does not accept those fields.

    `page` (and `y_position`, same reasoning) is kept from the FIRST chunk seen for that
    title — `docs` arrives already ordered by `_rerank`, so that's the chunk the answer is
    most likely actually drawing from. It lets the citation chip open straight to that
    spot instead of just the top of the file; later chunks of the same file (different
    pages) are still collapsed away, same as the title-level dedup above.
    """
    citations: list[dict] = []
    seen: set[str] = set()

    for doc in docs:
        document_id = doc.get("document_id")
        if document_id is None:
            continue

        title = doc.get("title") or "Tài liệu"
        key = title.strip().casefold()
        if key in seen:
            continue
        seen.add(key)

        citations.append(
            {
                "document_id": document_id,
                "title": title,
                "page": doc.get("page"),
                "y_position": doc.get("y_position"),
            }
        )

    return citations
