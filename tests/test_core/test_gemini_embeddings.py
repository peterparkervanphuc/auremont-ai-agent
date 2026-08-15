from types import SimpleNamespace

import pytest

from backend.core import gemini_client


class FakeModels:
    def __init__(self, vectors: list[list[float]]):
        self.vectors = vectors
        self.calls = []

    def embed_content(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(embeddings=[SimpleNamespace(values=vector) for vector in self.vectors])


class FakeGeminiClient:
    def __init__(self, vectors: list[list[float]]):
        self.models = FakeModels(vectors)


def test_embed_documents_uses_document_task_type(monkeypatch):
    fake_client = FakeGeminiClient(
        vectors=[
            [0.1, 0.2, 0.3],
            [0.4, 0.5, 0.6],
        ]
    )

    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: fake_client)
    monkeypatch.setattr(gemini_client.settings, "embedding_model", "gemini-embedding-001")
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)

    vectors = gemini_client.embed_documents(
        ["chunk mot", "chunk hai"],
        title="bang-gia.pdf",
    )

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]

    call = fake_client.models.calls[0]
    assert call["model"] == "gemini-embedding-001"
    assert call["contents"] == ["chunk mot", "chunk hai"]
    assert call["config"].task_type == "RETRIEVAL_DOCUMENT"
    assert call["config"].title == "bang-gia.pdf"
    assert call["config"].output_dimensionality == 3


def test_embed_query_returns_one_vector(monkeypatch):
    fake_client = FakeGeminiClient(vectors=[[0.1, 0.2, 0.3]])

    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: fake_client)
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)

    vector = gemini_client.embed_query("Gia can 2PN bao nhieu?")

    assert vector == [0.1, 0.2, 0.3]
    assert fake_client.models.calls[0]["config"].task_type == "RETRIEVAL_QUERY"


def test_embed_documents_rejects_wrong_vector_dimension(monkeypatch):
    fake_client = FakeGeminiClient(vectors=[[0.1, 0.2]])

    monkeypatch.setattr(gemini_client, "get_gemini_client", lambda: fake_client)
    monkeypatch.setattr(gemini_client.settings, "embedding_dimensions", 3)

    with pytest.raises(gemini_client.GeminiEmbeddingError):
        gemini_client.embed_documents(["chunk"], title="bang-gia.pdf")
