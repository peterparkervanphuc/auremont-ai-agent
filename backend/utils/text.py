"""Vietnamese text normalisation helpers for keyword matching."""

import unicodedata


def strip_diacritics(text: str) -> str:
    """Lowercase and strip Vietnamese diacritics: "Còn căn trống" -> "con can trong".

    Sales staff typing on a phone in front of a customer routinely drop every accent.
    Every keyword match in the AI flow (detecting inventory questions, screening for
    price/commitment risk) must go through this, otherwise an unaccented sentence
    silently slips past all the rules — most dangerously past RiskCheck, leaving a
    price answer without its mandatory HITL card.

    NFD does not decompose `đ` into a base letter plus a combining mark, so it has to
    be replaced by hand first.
    """
    lowered = text.lower().replace("đ", "d")
    decomposed = unicodedata.normalize("NFD", lowered)
    return "".join(char for char in decomposed if not unicodedata.combining(char))
