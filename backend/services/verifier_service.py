"""Verifier Agent: chấm điểm câu trả lời nháp so với tài liệu nguồn.

TODO:
- Chạy DeepEval FaithfulnessMetric / AnswerRelevancyMetric trên (query, draft_answer, retrieved_context).
- Nếu điểm dưới ngưỡng, báo cho caller bắt Main Agent sinh lại; nếu vẫn thấp thì
  hiển thị "Không đủ thông tin, liên hệ Admin".
"""

from backend.core.config import settings


class VerifierResult:
    def __init__(self, faithfulness: float, relevancy: float):
        self.faithfulness = faithfulness
        self.relevancy = relevancy

    @property
    def score(self) -> float:
        return min(self.faithfulness, self.relevancy)


def score_answer(query: str, draft_answer: str, retrieved_context: list[str]) -> VerifierResult:
    raise NotImplementedError("TODO: implement DeepEval Faithfulness/AnswerRelevancy scoring")


def passes_threshold(result: VerifierResult) -> bool:
    """Dưới ngưỡng -> hiển thị cảnh báo giới hạn thay vì đưa câu trả lời cho Sale."""
    return result.score >= settings.verifier_threshold_sale
