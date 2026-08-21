"""Fixed golden questions: the regression gate the flywheel in `eval/graders.py` cannot be.

`eval/graders.py` grades whatever traffic happened to be recorded — it catches a regression
only after some run exhibited it. This module is the other half: a small, hand-picked set of
Sale questions with the *expected* routing and answer shape nailed down in advance, so a
change to intent.py, a prompt, or a routing edge can be judged against a known-good answer
on every PR, not just after it ships and gets traced.

Retrieval, inventory, and the LLM call are stubbed per case (same boundary
`tests/test_services/test_tracing.py` and `test_agent_pipeline_reflexion.py` stub at) so
these run deterministically in CI with no API key and no network call — what's under test is
the pipeline's own routing and assembly logic, not Gemini's output quality. A separate,
optional live-LLM batch eval (against `scripts/run_eval.py`'s recorded-run flywheel) is the
place for judging actual answer quality; this dataset exists to catch a wiring regression
before that traffic is ever recorded.

Each case is a realistic question a Sale actually asks in the field (see
`eval/results/report.md`'s manual test log, which this dataset formalises), covering the
branches ARCHITECTURE.md documents: plain document RAG, live inventory, mixed
inventory+policy, price/commitment risk (HITL), and the "not enough information" decline.
"""

from dataclasses import dataclass, field

from backend.services.inventory_service import InventoryUnit


@dataclass
class GoldenCase:
    """One fixed question and everything needed to run it deterministically."""

    case_id: str
    query: str
    project_id: str | None

    # What retrieval/inventory hand the pipeline — the world this question is asked in.
    retrieved_docs: list[dict] = field(default_factory=list)
    inventory_units: list[InventoryUnit] = field(default_factory=list)
    inventory_raises: bool = False

    # The answer `generate_json` returns, standing in for what Gemini would draft given the
    # context above. Fixed rather than templated so a case reads as a single realistic
    # transcript, the way `eval/results/report.md`'s manual log does.
    answer_text: str = "Khong co du lieu."
    quick_replies: list[str] = field(default_factory=list)
    suggested_questions: list[str] = field(default_factory=list)

    # The Verifier's verdict for this world — a golden case fixes what a *correctly working*
    # Verifier would say about this exact answer/context pair, so the test is about pipeline
    # wiring, not about re-deriving the verdict.
    verifier_score: float = 0.95
    verifier_next_action: str = "accept"
    verifier_failure_mode: str = "none"

    # --- expectations checked against the PipelineResult -------------------------------
    expect_notice: bool = False
    expect_cited_document_ids: set[int] = field(default_factory=set)
    expect_requires_hitl: bool = False
    expect_inventory_called: bool = False
    expect_answer_contains: tuple[str, ...] = ()


def _doc(document_id: int, title: str, content: str, *, project_id: str | None = None, page: int = 1) -> dict:
    return {
        "document_id": document_id,
        "title": title,
        "page": page,
        "content": content,
        "score": 0.9,
        "project_id": project_id,
    }


def _unit(unit_code: str, *, project_id: str, price: int, area_m2: float = 68.2) -> InventoryUnit:
    return InventoryUnit(
        unit_code=unit_code,
        project_id=project_id,
        subdivision="The Beverly",
        unit_type="2PN",
        area_m2=area_m2,
        price=price,
        status="available",
    )


GOLDEN_CASES: list[GoldenCase] = [
    # --- Plain document RAG: policy question, no price, no HITL ------------------------
    GoldenCase(
        case_id="policy-payment-schedule",
        query="Chinh sach thanh toan cua The Beverly nhu the nao?",
        project_id="ocean-park-3",
        retrieved_docs=[
            _doc(
                101,
                "CSBH The Beverly V64.pdf",
                "Thanh toan theo tien do 8 dot, dot 1 giu cho 50 trieu dong.",
                project_id="ocean-park-3",
            )
        ],
        answer_text="- Thanh toan theo tien do 8 dot.\n- Giu cho 50 trieu dong o dot 1.",
        expect_cited_document_ids={101},
        expect_requires_hitl=True,  # "50 trieu dong" is a money figure -> commitment risk
        expect_answer_contains=("8 dot",),
    ),
    # --- Live inventory: must call the tool, never answer stock from a document --------
    GoldenCase(
        case_id="inventory-available-units",
        query="Con can 2PN nao trong khong?",
        project_id="ocean-park-3",
        retrieved_docs=[],
        inventory_units=[_unit("OP3-BE1-1205", project_id="ocean-park-3", price=3_600_000_000)],
        answer_text="- Con can OP3-BE1-1205, gia 3,6 ty dong.",
        expect_requires_hitl=True,
        expect_inventory_called=True,
        expect_answer_contains=("OP3-BE1-1205",),
    ),
    # --- Inventory API down: must say so plainly, never fall back to stale document data.
    # `_tool_call` turns the failure straight into a fixed notice ("Tạm thời không tra được
    # tồn kho.") — the mocked `answer_text` never reaches Generate on this path, since the
    # notice short-circuits the graph the same way the empty-state case below does.
    GoldenCase(
        case_id="inventory-api-down",
        query="Con can 2PN nao trong khong?",
        project_id="ocean-park-3",
        retrieved_docs=[],
        inventory_raises=True,
        inventory_units=[],
        expect_notice=True,
        expect_inventory_called=True,
        expect_answer_contains=("Tạm thời không tra được tồn kho.",),
    ),
    # --- Mixed: one question, two sources, both must be used ---------------------------
    GoldenCase(
        case_id="mixed-inventory-and-policy",
        query="Co can nao 2 phong ngu va chinh sach ban hang nhu nao?",
        project_id="ocean-park-3",
        retrieved_docs=[
            _doc(
                101,
                "CSBH The Beverly V64.pdf",
                "Can 2PN duoc chiet khau 5% khi thanh toan som.",
                project_id="ocean-park-3",
            )
        ],
        inventory_units=[_unit("OP3-BE1-1205", project_id="ocean-park-3", price=3_600_000_000)],
        answer_text="- Con can OP3-BE1-1205 gia 3,6 ty dong.\n- Chiet khau 5% khi thanh toan som.",
        expect_cited_document_ids={101},
        expect_requires_hitl=True,
        expect_inventory_called=True,
        expect_answer_contains=("OP3-BE1-1205", "5%"),
    ),
    # --- Nothing retrieved for a question that names a real document topic -> empty state,
    # short-circuited inside `_retrieve` before Generate ever runs (see
    # `names_specific_document_topic` in intent.py). ------------------------------------
    GoldenCase(
        case_id="empty-state-no-evidence-at-all",
        query="Chinh sach ban hang cua du an X la gi?",
        project_id=None,
        retrieved_docs=[],
        expect_notice=True,
    ),
    # --- Documents retrieved but the Verifier judges them unable to support an answer ->
    # decline after Generate, not a retry (verifier_service.NextAction.DECLINE). ---------
    GoldenCase(
        case_id="verifier-declines-ungrounded-draft",
        query="Chinh sach ban hang cua The Beverly co gi dac biet?",
        project_id="ocean-park-3",
        retrieved_docs=[
            _doc(
                101,
                "CSBH The Beverly V64.pdf",
                "Tai lieu chi liet ke thong tin lien he, khong co chinh sach ban hang.",
                project_id="ocean-park-3",
            )
        ],
        answer_text="Xin loi, tai lieu khong de cap chinh sach ban hang dac biet.",
        verifier_score=0.0,
        verifier_next_action="decline",
        verifier_failure_mode="missing-evidence",
        expect_notice=True,
    ),
]
