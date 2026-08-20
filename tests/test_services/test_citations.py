"""build_citations: file-level dedup that keeps the first chunk's page/Y position."""

from backend.ai.citations import build_citations


def test_dedupes_by_title_and_keeps_first_page():
    docs = [
        {"document_id": 1, "title": "bang-gia.pdf", "content": "...", "page": 3, "y_position": 120.5},
        {"document_id": 1, "title": "bang-gia.pdf", "content": "...", "page": 7, "y_position": 400.0},
    ]

    result = build_citations(docs)

    assert result == [{"document_id": 1, "title": "bang-gia.pdf", "page": 3, "y_position": 120.5}]


def test_drops_hits_with_no_document_id():
    docs = [{"document_id": None, "title": "no-id.pdf", "content": "...", "page": 1}]

    assert build_citations(docs) == []


def test_missing_page_and_y_position_stay_none():
    docs = [{"document_id": 2, "title": "policy.docx", "content": "..."}]

    result = build_citations(docs)

    assert result == [{"document_id": 2, "title": "policy.docx", "page": None, "y_position": None}]
