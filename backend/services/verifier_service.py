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

import logging

from pydantic import BaseModel, Field, field_validator

from backend.core.config import settings
from backend.core.gemini_client import generate_json

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

NGOẠI LỆ QUAN TRỌNG: nếu CÂU TRẢ LỜI là một lời từ chối trung thực — thẳng thắn nói KHÔNG có
đủ dữ liệu để trả lời đúng điều được hỏi, không bịa số liệu thay thế — thì cho CẢ HAI tiêu chí
đều 1.0, bất kể câu đó có chứa số liệu hay không. Từ chối đúng lúc khi thiếu dữ liệu là hành vi
ĐÚNG của hệ thống, không phải câu trả lời kém chất lượng — không chấm thấp chỉ vì nó là câu giao
tiếp thay vì số liệu cụ thể.

CÂU HỎI:
{query}

NGỮ CẢNH:
{context}

CÂU TRẢ LỜI:
{answer}

Chỉ trả về JSON đúng định dạng: {{"faithfulness": <số>, "relevancy": <số>}}"""


class VerifierResult(BaseModel):
    """A judgement about one draft answer.

    Doubles as the response schema handed to Gemini, so the model is constrained to emit
    exactly these two fields in this range instead of prose that has to be scraped.
    """

    faithfulness: float = Field(ge=0.0, le=1.0, description="Is every claim supported by the context?")
    relevancy: float = Field(ge=0.0, le=1.0, description="Does the answer address the question asked?")

    @field_validator("faithfulness", "relevancy", mode="before")
    @classmethod
    def _coerce_score(cls, value: object) -> float:
        """Accept the shapes judges actually emit: "0.85", 85, None.

        A model that mistakes the scale and answers 85 means 0.85. Only values clearly on
        a 0-100 scale are converted; a slight overshoot like 1.5 is the judge being loose
        on the 0-1 scale, and dividing that would distort the score more than clamping.
        """
        try:
            score = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return 0.0

        if score > 10.0:
            score = score / 100.0
        return max(0.0, min(1.0, score))

    @property
    def score(self) -> float:
        """The weaker of the two. An answer that is truthful but off-topic, or on-topic
        with invented figures, must fail either way."""
        return min(self.faithfulness, self.relevancy)


_FAILED_VERIFICATION = VerifierResult(faithfulness=0.0, relevancy=0.0)


def score_answer(query: str, draft_answer: str, retrieved_context: list[str]) -> VerifierResult:
    """Score a draft answer. Never raises — a scoring failure scores 0.0.

    Failing closed is deliberate: the pipeline then takes the "not enough information"
    branch instead of handing the Sale an unverified answer. Bad advice costs more than a
    refusal does.
    """
    if not draft_answer.strip() or not retrieved_context:
        # With no context there is nothing to check against, so nothing can be called faithful.
        return _FAILED_VERIFICATION

    prompt = _JUDGE_PROMPT.format(
        query=query,
        context="\n---\n".join(retrieved_context),
        answer=draft_answer,
    )

    try:
        result = generate_json(prompt, VerifierResult, system_instruction=_JUDGE_SYSTEM_INSTRUCTION)
    except Exception:
        # ERROR, not WARNING: without this line a broken Verifier looks exactly like a
        # low-quality answer on the Admin dashboard — both show 0.0. That is the most
        # dangerous misdiagnosis this system can make.
        logger.exception(
            "Judge LLM call failed; scoring 0.0 (fail closed).",
            extra={"event": "verifier.judge.failed", "context_count": len(retrieved_context)},
        )
        return _FAILED_VERIFICATION

    if result is None:
        logger.warning(
            "Judge returned no parseable verdict; scoring 0.0 (fail closed).",
            extra={"event": "verifier.judge.empty"},
        )
        return _FAILED_VERIFICATION

    return result


def passes_threshold(result: VerifierResult) -> bool:
    """Below the threshold -> show the limitation warning instead of giving the Sale the answer."""
    return result.score >= settings.verifier_threshold_sale
