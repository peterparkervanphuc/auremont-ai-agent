"""Verifier Agent: score a draft answer against its source documents.

This is the gate between "the LLM said something plausible" and "a Sale reads those
figures out to a customer". The Main Agent generates from context but can still invent
numbers or drift off-topic, so the Verifier independently scores two things:

* **faithfulness** — is the answer grounded in the context, or partly invented?
* **relevancy** — does the answer actually address the question?

The final score is the `min` of the two: an answer that is truthful but off-topic, or
on-topic but with invented numbers, must not pass either way.

Uses LLM-as-judge via Gemini rather than DeepEval inline: DeepEval defaults to calling
OpenAI (this project runs Gemini) and is noticeably slower, while the whole pipeline has
to stay under a 3-second field response budget. DeepEval remains a good fit for offline
batch evaluation under `eval/`.
"""

import json
import logging
import re

from backend.core.config import settings
from backend.core.gemini_client import generate_text

logger = logging.getLogger(__name__)

_JUDGE_SYSTEM_INSTRUCTION = (
    "Bạn là bộ chấm điểm độc lập cho hệ thống RAG tư vấn bất động sản. "
    "Bạn KHÔNG trả lời câu hỏi, chỉ chấm điểm câu trả lời của người khác. "
    "Luôn trả về đúng một object JSON, không kèm giải thích."
)

_JUDGE_PROMPT = """Chấm điểm CÂU TRẢ LỜI dựa trên NGỮ CẢNH được trích từ tài liệu gốc.

Hai tiêu chí, mỗi tiêu chí cho điểm từ 0.0 đến 1.0:
- "faithfulness": mọi thông tin trong câu trả lời có được NGỮ CẢNH chứng minh không?
  Bịa số liệu, thêm cam kết không có trong ngữ cảnh -> điểm thấp.
- "relevancy": câu trả lời có trực tiếp giải đáp CÂU HỎI không?
  Lan man, trả lời sang chuyện khác -> điểm thấp.

CÂU HỎI:
{query}

NGỮ CẢNH:
{context}

CÂU TRẢ LỜI:
{answer}

Chỉ trả về JSON đúng định dạng: {{"faithfulness": <số>, "relevancy": <số>}}"""

# Grab the first JSON object even when the model wraps it in ```json ... ``` or adds prose.
_JSON_PATTERN = re.compile(r"\{.*?\}", re.DOTALL)


class VerifierResult:
    def __init__(self, faithfulness: float, relevancy: float):
        self.faithfulness = faithfulness
        self.relevancy = relevancy

    @property
    def score(self) -> float:
        return min(self.faithfulness, self.relevancy)


def score_answer(query: str, draft_answer: str, retrieved_context: list[str]) -> VerifierResult:
    """Score a draft answer. Never raises — a scoring failure returns 0.0.

    Returning 0.0 on failure is deliberate: the pipeline then takes the
    "Không đủ thông tin, liên hệ Admin" branch instead of handing the Sale an unverified
    answer. Fail closed, because bad advice costs more than a refusal does.
    """
    if not draft_answer.strip() or not retrieved_context:
        # With no context there is nothing to check against -> cannot be called faithful.
        return VerifierResult(0.0, 0.0)

    prompt = _JUDGE_PROMPT.format(
        query=query,
        context="\n---\n".join(retrieved_context),
        answer=draft_answer,
    )

    try:
        raw = generate_text(prompt, system_instruction=_JUDGE_SYSTEM_INSTRUCTION)
    except Exception:
        # ERROR, not WARNING: without this line, a broken Verifier looks exactly like a
        # low-quality answer on the Admin dashboard — both show score 0.0. This is the
        # most dangerous misdiagnosis the system can make.
        logger.exception(
            "Judge LLM that bai — tra ve diem 0.0 (fail closed).",
            extra={"event": "verifier.judge.failed", "context_count": len(retrieved_context)},
        )
        return VerifierResult(0.0, 0.0)

    return _parse_scores(raw)


def _parse_scores(raw: str) -> VerifierResult:
    """Read the scores out of the model output, tolerating junk around the JSON."""
    match = _JSON_PATTERN.search(raw or "")
    if match is None:
        logger.warning(
            "Khong tim thay JSON trong output cua judge.",
            extra={"event": "verifier.parse.no_json", "raw_head": (raw or "")[:120]},
        )
        return VerifierResult(0.0, 0.0)

    try:
        data = json.loads(match.group(0))
    except ValueError:
        logger.warning(
            "JSON cua judge khong parse duoc.",
            extra={"event": "verifier.parse.bad_json", "raw_head": match.group(0)[:120]},
        )
        return VerifierResult(0.0, 0.0)

    if not isinstance(data, dict):
        logger.warning(
            "Judge tra ve JSON khong phai object.",
            extra={"event": "verifier.parse.not_dict", "parsed_type": type(data).__name__},
        )
        return VerifierResult(0.0, 0.0)

    return VerifierResult(
        faithfulness=_clamp(data.get("faithfulness")),
        relevancy=_clamp(data.get("relevancy")),
    )


def _clamp(value: object) -> float:
    """Coerce a score into [0, 1]. The model sometimes returns '0.85', 85 or null."""
    try:
        score = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        # DEBUG: the docstring above notes `null` is a common model output, so WARNING
        # here would become constant noise rather than a real signal.
        logger.debug(
            "Diem khong doc duoc, quy ve 0.0.",
            extra={"event": "verifier.clamp.bad_value", "value_type": type(value).__name__},
        )
        return 0.0

    # The model sometimes mistakes the scale and returns 85 instead of 0.85. Only convert
    # when the number is clearly on a 0-100 scale; a slight overshoot like 1.5 is the model
    # being a little off on the 0-1 scale, and turning that into 0.015 would distort the
    # score far more than clamping it to 1.0.
    if score > 10.0:
        score = score / 100.0

    return max(0.0, min(1.0, score))


def passes_threshold(result: VerifierResult) -> bool:
    """Below the threshold -> show the limitation warning instead of giving the Sale the answer."""
    return result.score >= settings.verifier_threshold_sale
