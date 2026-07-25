import google.genai as genai
from google.genai import types

from backend.core.config import settings

_client: genai.Client | None = None


def get_gemini_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.GEMINI_API_KEY)
    return _client


def generate_text(prompt: str, system_instruction: str | None = None) -> str:
    client = get_gemini_client()
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
    ) if system_instruction else None

    response = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=config,
    )
    return response.text or ""

