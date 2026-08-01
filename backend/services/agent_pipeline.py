"""Multi-agent orchestration (CLAUDE.md §6.1): Retrieval -> Generation -> Verify -> HITL/Fallback.

TODO:
- Build as a LangGraph StateGraph with nodes: retrieve, generate, verify, and a conditional edge that
  routes to either `flag_hitl` (Sale channel, price/commitment risk) or `suggest_livechat`
  (public Chatbot channel, low verifier score).
- Wire in Semantic Caching in front of the retrieve node (CLAUDE.md §6.1 step 2).
- Detect price/commitment risk in the generated answer to decide whether a HITL card is required.
"""

from dataclasses import dataclass

from backend.core.enums import UserRole


@dataclass
class PipelineResult:
    draft_answer: str
    citations: list[dict]
    verifier_score: float
    requires_hitl: bool
    suggest_livechat: bool


def run_pipeline(query: str, channel: UserRole | None, project_id: str | None = None) -> PipelineResult:
    """Entry point used by both the Sale chat router and the public Chatbot router."""
    raise NotImplementedError("TODO: implement LangGraph pipeline (retrieve -> generate -> verify -> route)")
