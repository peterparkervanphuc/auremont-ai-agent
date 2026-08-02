"""Multi-agent orchestration: Retrieval -> Generation -> Verify -> HITL.

TODO:
- Build as a LangGraph StateGraph with nodes: retrieve, generate, verify, and a conditional edge that
  flags `requires_hitl` when a price/commitment risk is detected.
- Wire in Semantic Caching in front of the retrieve node.
- Detect price/commitment risk in the generated answer to decide whether a HITL card is required.
"""

from dataclasses import dataclass


@dataclass
class PipelineResult:
    draft_answer: str
    citations: list[dict]
    verifier_score: float
    requires_hitl: bool


def run_pipeline(query: str, project_id: str | None = None) -> PipelineResult:
    """Entry point cho luồng chat của Sale."""
    raise NotImplementedError("TODO: implement LangGraph pipeline (retrieve -> generate -> verify -> route)")
