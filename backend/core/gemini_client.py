import logging
import time
from typing import Any, TypeVar, cast

import google.genai as genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from backend.core.config import settings

logger = logging.getLogger(__name__)

# Bulk document upload (Admin's multi-file queue) fires one embed_content call per
# document in quick succession, each covering many chunks — comfortably enough to blow
# through the Gemini free tier's ~100 requests/minute embedding quota partway through a
# batch. A 429 there is not a real failure (the document is fine, the model call would
# succeed if it weren't for the moment's rate limit) but every retry-less call above this
# treated it as one, silently leaving gaps in the knowledge base that later read as "the
# AI has no data" for whichever project's doc lost the race. See _embed's retry loop.
_EMBED_MAX_ATTEMPTS = 4
_EMBED_RETRY_STATUS_CODES = {429}

# Generation (every answer, and every Verifier judgement) sits on the interactive path with
# its sub-3-second field budget, so it gets a far tighter policy than the batch embedding
# loop above: one retry, transient faults only, and a hard cap on the backoff — a 429's
# suggested retryDelay can be tens of seconds, which is worse than failing fast here.
# Without any retry a single blip failed the whole turn and reached the Admin dashboard
# looking identical to an answer the Verifier genuinely rejected.
_GENERATE_MAX_ATTEMPTS = 2
_GENERATE_RETRY_STATUS_CODES = {429, 500, 502, 503, 504}
_GENERATE_MAX_RETRY_DELAY_SECONDS = 1.0

ModelT = TypeVar("ModelT", bound=BaseModel)

_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def generate_text(prompt: str, system_instruction: str | None = None) -> str:
    config = (
        types.GenerateContentConfig(
            system_instruction=system_instruction,
        )
        if system_instruction
        else None
    )

    return client_models_generate(prompt, config).text or ""


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
    """The single entry point for every generation call, so the retry policy above cannot
    drift between the plain-text and schema-constrained paths."""
    for attempt in range(1, _GENERATE_MAX_ATTEMPTS + 1):
        try:
            return get_gemini_client().models.generate_content(
                model=settings.GEMINI_MODEL,
                contents=prompt,
                config=config,
            )
        except genai_errors.APIError as exc:
            if exc.code not in _GENERATE_RETRY_STATUS_CODES or attempt == _GENERATE_MAX_ATTEMPTS:
                raise

            delay = min(_retry_delay_seconds(exc), _GENERATE_MAX_RETRY_DELAY_SECONDS)
            logger.warning(
                "Gemini generation hit a transient fault; retrying once.",
                extra={
                    "event": "gemini.generate.retry",
                    "model": settings.GEMINI_MODEL,
                    "status_code": exc.code,
                    "attempt": attempt,
                    "delay_seconds": delay,
                },
            )
            time.sleep(delay)

    # Unreachable: the loop either returns or raises on its final attempt.
    raise RuntimeError("Gemini generation retry loop exited without a result.")


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

    response = None
    for attempt in range(1, _EMBED_MAX_ATTEMPTS + 1):
        try:
            response = get_gemini_client().models.embed_content(
                model=settings.embedding_model,
                contents=cast(Any, texts),
                config=types.EmbedContentConfig(**config_kwargs),
            )
            break
        except genai_errors.APIError as exc:
            is_last_attempt = attempt == _EMBED_MAX_ATTEMPTS
            if exc.code not in _EMBED_RETRY_STATUS_CODES or is_last_attempt:
                logger.exception(
                    "Gemini embedding call failed.",
                    extra={
                        "event": "gemini.embed.failed",
                        "model": settings.embedding_model,
                        "input_count": len(texts),
                        "status_code": exc.code,
                        "attempt": attempt,
                    },
                )
                raise GeminiEmbeddingError("Gemini embedding request failed.") from exc

            delay = _retry_delay_seconds(exc)
            logger.warning(
                "Gemini embedding rate-limited; retrying.",
                extra={
                    "event": "gemini.embed.rate_limited",
                    "model": settings.embedding_model,
                    "input_count": len(texts),
                    "attempt": attempt,
                    "delay_seconds": delay,
                },
            )
            time.sleep(delay)
        except Exception as exc:
            logger.exception(
                "Gemini embedding call failed.",
                extra={"event": "gemini.embed.failed", "model": settings.embedding_model, "input_count": len(texts)},
            )
            raise GeminiEmbeddingError("Gemini embedding request failed.") from exc

    assert response is not None  # every loop exit either raises or breaks with a response

    if not response.embeddings:
        raise GeminiEmbeddingError("Gemini returned no embeddings.")

    # Built as a loop rather than a comprehension so the None check actually narrows the
    # element type: `embedding.values` is optional in the SDK's own typing, and a None
    # reaching Qdrant would fail far from here with nothing pointing back at this call.
    vectors: list[list[float]] = []
    for embedding in response.embeddings:
        if embedding.values is None:
            raise GeminiEmbeddingError("Gemini returned an empty embedding.")
        vectors.append(embedding.values)

    if len(vectors) != len(texts):
        raise GeminiEmbeddingError("Gemini returned a different number of embeddings than inputs.")

    if any(len(vector) != settings.embedding_dimensions for vector in vectors):
        raise GeminiEmbeddingError("Gemini returned an embedding with an unexpected dimension.")

    return vectors


_DEFAULT_RETRY_DELAY_SECONDS = 20.0


def _retry_delay_seconds(exc: genai_errors.APIError) -> float:
    """The 429 response itself names how long to back off (google.rpc.RetryInfo,
    e.g. "21s") — use it instead of guessing, falling back to a fixed default only if the
    response is ever shaped differently than the one this was built against.

    `exc.details` is the raw response body, `{"error": {..., "details": [...]}}` — note
    the outer "details" is the whole error object (APIError's own attribute name), the
    inner one is the list of google.rpc.* structs actually being searched here.
    """
    body = getattr(exc, "details", None)
    error = body.get("error") if isinstance(body, dict) else None
    entries = error.get("details") if isinstance(error, dict) else None
    if isinstance(entries, list):
        for entry in entries:
            retry_delay = isinstance(entry, dict) and entry.get("retryDelay")
            if isinstance(retry_delay, str) and retry_delay.endswith("s"):
                try:
                    return float(retry_delay[:-1])
                except ValueError:
                    pass
    return _DEFAULT_RETRY_DELAY_SECONDS
