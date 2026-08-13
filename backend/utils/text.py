"""Vietnamese text normalisation helpers for keyword matching."""

import re
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


# Asterisks/underscores wrapping a span with no line break: **bold**, *italic*, __bold__.
_MD_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3})(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
# Leading bullet at any indent level: "  *   ", "- ", "+ " -> "- "
_MD_BULLET = re.compile(r"^[ \t]*[*+-][ \t]+", re.MULTILINE)
# ATX heading: "### Tiện ích" -> "Tiện ích"
_MD_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]*", re.MULTILINE)
# Markdown link/image: [label](url) -> label
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MD_CODE_FENCE = re.compile(r"^[ \t]*```.*$", re.MULTILINE)
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def strip_markdown(text: str) -> str:
    """Strip Markdown syntax from an LLM answer while preserving the text content.

    The chat window renders answers as plain text (`<p>{content}</p>` in
    frontend/src/routes/sale/ChatWindow.tsx), so any Markdown character the model
    returns shows up literally: "*   **Tiện ích:**" instead of a clean bullet line.

    The prompt already instructs the model to write plain text; this function is the
    last line of defense for the times the model slips into Markdown out of habit.
    Leading "- " is deliberately kept, since that reads as a plain-text bullet rather
    than syntax that needs stripping.
    """
    if not text:
        return text

    cleaned = _MD_CODE_FENCE.sub("", text)
    cleaned = _MD_LINK.sub(r"\1", cleaned)
    cleaned = _MD_HEADING.sub("", cleaned)
    # Loop until stable: "***text***" needs several passes to peel off all nested layers.
    for _ in range(3):
        stripped = _MD_EMPHASIS.sub(r"\2", cleaned)
        if stripped == cleaned:
            break
        cleaned = stripped
    # Normalise bullets after emphasis has been stripped, otherwise "*   **A**" would
    # still leave a stray asterisk behind.
    cleaned = _MD_BULLET.sub("- ", cleaned)
    cleaned = _EXCESS_BLANK_LINES.sub("\n\n", cleaned)

    return cleaned.strip()
