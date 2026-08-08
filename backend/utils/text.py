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


# Ngôi sao/gạch dưới bao quanh một đoạn không chứa xuống dòng: **đậm**, *nghiêng*, __đậm__.
_MD_EMPHASIS = re.compile(r"(\*{1,3}|_{1,3})(?=\S)(.+?)(?<=\S)\1", re.DOTALL)
# Bullet đầu dòng ở mọi mức thụt lề: "  *   ", "- ", "+ " -> "- "
_MD_BULLET = re.compile(r"^[ \t]*[*+-][ \t]+", re.MULTILINE)
# Tiêu đề ATX: "### Tiện ích" -> "Tiện ích"
_MD_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]*", re.MULTILINE)
# Link/ảnh Markdown: [nhãn](url) -> nhãn
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_MD_CODE_FENCE = re.compile(r"^[ \t]*```.*$", re.MULTILINE)
_EXCESS_BLANK_LINES = re.compile(r"\n{3,}")


def strip_markdown(text: str) -> str:
    """Gỡ cú pháp Markdown khỏi câu trả lời của LLM, giữ nguyên nội dung chữ.

    Khung chat render câu trả lời bằng text thuần (`<p>{content}</p>` trong
    frontend/src/routes/sale/ChatWindow.tsx), nên mọi ký tự Markdown mà model trả về sẽ
    hiện nguyên dấu: "*   **Tiện ích:**" thay vì một gạch đầu dòng sạch sẽ.

    Prompt đã yêu cầu model viết text thuần; hàm này là lớp chặn cuối cho những lần model
    vẫn quen tay bỏ Markdown vào. Cố ý giữ lại "- " ở đầu dòng vì đó là gạch đầu dòng đọc
    được ở dạng text thuần, không phải cú pháp cần gỡ.
    """
    if not text:
        return text

    cleaned = _MD_CODE_FENCE.sub("", text)
    cleaned = _MD_LINK.sub(r"\1", cleaned)
    cleaned = _MD_HEADING.sub("", cleaned)
    # Lặp tới khi ổn định: "***text***" cần nhiều lượt mới bóc hết các lớp lồng nhau.
    for _ in range(3):
        stripped = _MD_EMPHASIS.sub(r"\2", cleaned)
        if stripped == cleaned:
            break
        cleaned = stripped
    # Chuẩn hoá bullet sau khi đã gỡ nhấn mạnh, nếu không "*   **A**" sẽ còn sót dấu sao.
    cleaned = _MD_BULLET.sub("- ", cleaned)
    cleaned = _EXCESS_BLANK_LINES.sub("\n\n", cleaned)

    return cleaned.strip()
