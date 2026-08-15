import logging
from typing import TypeVar

import google.genai as genai
from google.genai import types
from pydantic import BaseModel

from backend.core.config import settings

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def generate_text(prompt: str, system_instruction: str | None = None) -> str:
    client = get_gemini_client()
    config = (
        types.GenerateContentConfig(
            system_instruction=system_instruction,
        )
        if system_instruction
        else None
    )

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=config,
    )
    return response.text or ""


def generate_json(
    prompt: str,
    schema: type[ModelT],
    system_instruction: str | None = None,
) -> ModelT | None:
    """Generate a response constrained to `schema`, returning a parsed model instance.

    Uses Gemini's schema-constrained decoding rather than asking for JSON in the prompt
    and parsing whatever comes back. Critical AI decisions (verification scores, risk
    classification) must not depend on a regex finding a brace in prose.

    Returns None when the model returns nothing parseable; callers decide what a missing
    judgement means, and for verification it means fail closed.
    """
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        response_mime_type="application/json",
        response_schema=schema,
    )

    response = client_models_generate(prompt, config)
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, schema):
        return parsed

    # Older SDK builds populate `.text` but not `.parsed`.
    raw = (response.text or "").strip()
    if not raw:
        return None
    return schema.model_validate_json(raw)


def client_models_generate(prompt: str, config):
    return get_gemini_client().models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=config,
    )


class GeminiEmbeddingError(RuntimeError):
    """Gemini did not return a valid embedding."""


def embed_documents(texts: list[str], *, title: str) -> list[list[float]]:
    """Embed document chunks for storage in Qdrant.

    Uses RETRIEVAL_DOCUMENT because these are vectors of source data,
    not of a search query.
    """
    return _embed(
        texts,
        task_type="RETRIEVAL_DOCUMENT",
        title=title,
    )


def embed_query(query: str) -> list[float]:
    """Embed a query for retrieval against Qdrant."""
    vectors = _embed(
        [query],
        task_type="RETRIEVAL_QUERY",
        title=None,
    )
    return vectors[0]


def _embed(
    texts: list[str],
    *,
    task_type: str,
    title: str | None,
) -> list[list[float]]:
    if not texts:
        return []

    config_kwargs: dict = {
        "task_type": task_type,
        "output_dimensionality": settings.embedding_dimensions,
    }

    # A title improves retrieval quality for document embeddings.
    if title:
        config_kwargs["title"] = title

    try:
        response = get_gemini_client().models.embed_content(
            model=settings.embedding_model,
            contents=texts,
            config=types.EmbedContentConfig(**config_kwargs),
        )
    except Exception as exc:
        logger.exception(
            "Gemini embedding call failed.",
            extra={"event": "gemini.embed.failed", "model": settings.embedding_model, "input_count": len(texts)},
        )
        raise GeminiEmbeddingError("Gemini embedding request failed.") from exc

    if not response.embeddings:
        raise GeminiEmbeddingError("Gemini returned no embeddings.")

    vectors = [embedding.values for embedding in response.embeddings]

    if len(vectors) != len(texts):
        raise GeminiEmbeddingError("Gemini returned a different number of embeddings than inputs.")

    if any(len(vector) != settings.embedding_dimensions for vector in vectors):
        raise GeminiEmbeddingError("Gemini returned an embedding with an unexpected dimension.")

    return vectors
