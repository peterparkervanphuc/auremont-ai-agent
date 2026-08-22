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


# The opposite failure: the image tool (answer_images_service.collect_images, called from
# _image_tool in the pipeline) found nothing — resolving the right project from a vague
# follow-up ("cho tôi xem hình khu này") depends on retrieval/history folding correctly,
# which is itself probabilistic and sometimes comes up empty — yet the model still writes
# a confident "ảnh đang hiển thị ngay trên màn hình" line anyway. The customer sees an
# empty message bubble under a claim that photos are right there. The prompt's own "ẢNH:
# catalogue không có ảnh nào khớp yêu cầu này" instruction is supposed to prevent this but,
# same as every other prompt-only rule in this module, is not reliably followed.
_FALSE_IMAGE_CONFIRMATION_MARKERS = (
    "dang hien thi",
    "da hien thi",
    "hien thi ngay tren man hinh",
    "ngay tren man hinh",
    "duoi tin nhan nay",
    "da dinh kem",
    "da gui hinh anh",
    "da gui cac hinh anh",
    "gui hinh anh thuc te",
)


def drop_false_image_confirmations(answer: str, images: list[dict]) -> str:
    """Strip lines falsely claiming photos are on screen, when none were actually attached.

    Mirrors `drop_image_denials` in the opposite direction. Only runs when `images` is
    empty, so a normal answer that legitimately mentions a project's on-screen presence
    for some other reason is untouched whenever photos really are attached.
    """
    if images:
        return answer

    kept = [
        line
        for line in answer.splitlines()
        if not any(marker in strip_diacritics(line).lower() for marker in _FALSE_IMAGE_CONFIRMATION_MARKERS)
    ]
    cleaned = "\n".join(kept).strip()
    if cleaned:
        return cleaned

    return "Hiện tại chưa có ảnh phù hợp với yêu cầu này ạ."
