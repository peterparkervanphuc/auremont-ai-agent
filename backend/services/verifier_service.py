"""Verifier contract for the agent pipeline.

This MVP provides deterministic source-presence scoring.  It deliberately keeps
the public interface stable so DeepEval can replace the heuristic later.
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
    """Score safely until DeepEval metrics are connected.

    A non-empty answer needs at least one non-empty source to pass. This avoids
    presenting unsourced LLM output as a trustworthy Sales response.
    """
    if not query.strip() or not draft_answer.strip():
        return VerifierResult(faithfulness=0.0, relevancy=0.0)

    if not any(context.strip() for context in retrieved_context):
        return VerifierResult(faithfulness=0.3, relevancy=0.4)

    return VerifierResult(faithfulness=0.85, relevancy=0.85)


def passes_threshold(result: VerifierResult) -> bool:
    return result.score >= settings.verifier_threshold_sale
