"""Verifier Agent: scores a draft answer against its source documents (CLAUDE.md §6.1 step 4).

TODO:
- Run DeepEval's FaithfulnessMetric / AnswerRelevancyMetric against (query, draft_answer, retrieved_context).
- If score < threshold, signal the caller to ask Generation to retry (Sale channel) or to
  short-circuit to "Không đủ thông tin, liên hệ Admin" (public Chatbot has no fallback channel;
  see CLAUDE.md §5.4).
"""

from backend.core.config import settings
from backend.core.enums import UserRole


class VerifierResult:
    def __init__(self, faithfulness: float, relevancy: float):
        self.faithfulness = faithfulness
        self.relevancy = relevancy

    @property
    def score(self) -> float:
        return min(self.faithfulness, self.relevancy)


def score_answer(query: str, draft_answer: str, retrieved_context: list[str]) -> VerifierResult:
    raise NotImplementedError("TODO: implement DeepEval Faithfulness/AnswerRelevancy scoring")


def passes_threshold(result: VerifierResult, channel: UserRole | None) -> bool:
    """Public Chatbot has no HITL, so it is held to a higher bar than the Sale channel (CLAUDE.md §9)."""
    threshold = settings.verifier_threshold_sale if channel == UserRole.SALE else settings.verifier_threshold_public
    return result.score >= threshold
