"""Deterministic post-processing of generated answers.

Everything here exists because prompting alone proved unreliable. Instructions the model
ignores intermittently are enforced in code instead, where the behaviour is testable.
"""

from backend.services import answer_images_service
from backend.utils.text import strip_diacritics


def wants_images_for_prompt(query: str) -> bool:
    """Re-exported so `prompts` does not import the image service directly."""
    return answer_images_service.wants_images(query)


_IMAGE_DENIAL_MARKERS = (
    "khong chua hinh anh",
    "khong co hinh anh",
    "khong co anh",
    "khong co tep anh",
    "khong co file anh",
    "chua co hinh anh",
    "chua co anh",
    "khong hien thi duoc anh",
    "khong co hinh anh truc quan",
    "hinh anh truc quan de hien thi",
    "xin anh",
)


def drop_image_denials(answer: str, images: list[dict]) -> str:
    """Strip lines claiming there are no images, when there demonstrably are.

    Only runs when photos are attached, so an honest "chưa có ảnh cho hạng mục này" on a
    question that found none is left untouched. If every line is a denial, a plain factual
    line replaces them rather than returning an empty bubble.
    """
    if not images:
        return answer

    kept = [
        line
        for line in answer.splitlines()
        if not any(marker in strip_diacritics(line).lower() for marker in _IMAGE_DENIAL_MARKERS)
    ]
    cleaned = "\n".join(kept).strip()
    if cleaned:
        return cleaned

    return f"- Đang hiển thị {len(images)} ảnh {images[0].get('project_name') or 'dự án'} bên dưới."
