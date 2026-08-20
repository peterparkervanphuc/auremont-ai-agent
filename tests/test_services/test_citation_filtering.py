"""_citations_for: drop citations when retrieval span multiple unrelated projects.

An unscoped search that returns top hits from 2+ different projects is the same shape of
query that makes the model ask "which project do you mean?" instead of answering from any
of them — citing files from projects the reply never engaged with would be misleading.
"""

from backend.services.agent_pipeline import _citations_for


def _doc(document_id: int, title: str, project_id: str | None) -> dict:
    return {"document_id": document_id, "title": title, "content": "...", "page": 1, "project_id": project_id}


def test_single_project_keeps_citations():
    docs = [_doc(1, "bang-gia.pdf", "the-beverly"), _doc(2, "chinh-sach.docx", "the-beverly")]

    assert _citations_for(docs) == [
        {"document_id": 1, "title": "bang-gia.pdf", "page": 1, "y_position": None},
        {"document_id": 2, "title": "chinh-sach.docx", "page": 1, "y_position": None},
    ]


def test_multiple_projects_drops_citations():
    docs = [_doc(1, "beverly.pdf", "the-beverly"), _doc(2, "zurich.pdf", "the-zurich")]

    assert _citations_for(docs) == []


def test_missing_project_id_is_not_treated_as_ambiguous():
    """A doc with no project_id (company-wide policy, applies everywhere) shouldn't by
    itself count as a second "project" alongside a real one."""
    docs = [_doc(1, "bang-gia.pdf", "the-beverly"), _doc(2, "quy-dinh-chung.pdf", None)]

    assert _citations_for(docs) == [
        {"document_id": 1, "title": "bang-gia.pdf", "page": 1, "y_position": None},
        {"document_id": 2, "title": "quy-dinh-chung.pdf", "page": 1, "y_position": None},
    ]
