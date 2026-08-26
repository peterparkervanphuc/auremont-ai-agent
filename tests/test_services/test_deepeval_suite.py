"""Wiring tests for the offline DeepEval suite, with no model and no judge involved.

`eval/deepeval_suite.py` exists to spend real API calls, so the thing that rots silently is
everything around them: the world-freezing patches, the retrieval context handed to the
judge, the report the run is read from. Those are checked here deterministically. What is
deliberately *not* checked is whether Gemini writes a good answer — that is the suite's own
job, on a developer's machine, against a real key.

Skipped when deepeval is absent: it ships in `requirements-eval.txt`, not `requirements.txt`,
so CI installs neither it nor its dependencies.
"""

import pytest

pytest.importorskip("deepeval", reason="deepeval is in requirements-eval.txt, not requirements.txt")

from backend.services import agent_pipeline  # noqa: E402
from backend.services.verifier_service import FailureMode, NextAction, VerifierResult  # noqa: E402
from eval import deepeval_suite  # noqa: E402
from eval.golden_dataset import GOLDEN_CASES  # noqa: E402


class _StubMetric:
    """Stands in for a DeepEval metric: measured once per case, then read for its verdict."""

    def __init__(self, name: str, score: float, passed: bool):
        self.__name__ = name
        self.score = score
        self.reason = f"{name} said so."
        self._passed = passed
        self.measured: list = []

    def measure(self, test_case) -> float:
        self.measured.append(test_case)
        return self.score

    def is_successful(self) -> bool:
        return self._passed


def _case(case_id: str):
    return next(case for case in GOLDEN_CASES if case.case_id == case_id)


def _stub_model(monkeypatch, case) -> None:
    """Stub only what `_fixed_world` deliberately leaves live: the model and the Verifier."""

    def _generate_json(prompt, schema, **_kwargs):
        return schema(text=case.answer_text, quick_replies=[], suggested_questions=[])

    monkeypatch.setattr(agent_pipeline, "generate_json", _generate_json)
    monkeypatch.setattr(
        agent_pipeline.verifier_service,
        "score_answer",
        lambda *a, **k: VerifierResult(
            faithfulness=0.9,
            relevancy=0.9,
            completeness=0.9,
            failure_mode=FailureMode("none"),
            feedback="",
            next_action=NextAction("accept"),
        ),
    )


def test_gradeable_cases_skip_the_ones_that_never_reach_generate():
    """A notice case has no model-written answer, so paying a judge to score it is waste."""
    gradeable = deepeval_suite.gradeable_cases()

    assert gradeable, "every golden case was filtered out"
    assert all(not case.expect_notice for case in gradeable)


def test_fixed_world_restores_every_patch():
    """A leaked patch would silently disable retrieval for the rest of the process."""
    case = _case("policy-payment-schedule")
    before = (
        agent_pipeline.retrieve,
        agent_pipeline.lookup_inventory,
        agent_pipeline._store_cache,
        agent_pipeline.cache_service.lookup_cache,
    )

    with deepeval_suite._fixed_world(case):
        assert agent_pipeline.retrieve(case.query) == case.retrieved_docs

    assert (
        agent_pipeline.retrieve,
        agent_pipeline.lookup_inventory,
        agent_pipeline._store_cache,
        agent_pipeline.cache_service.lookup_cache,
    ) == before


def test_retrieval_context_carries_documents_and_inventory():
    """Both sources ground the answer, so both must reach the judge — a unit code judged
    against documents alone would read as invented."""
    case = _case("mixed-inventory-and-policy")

    context = deepeval_suite._retrieval_context(case)

    assert case.retrieved_docs[0]["content"] in context
    assert any(case.inventory_units[0].unit_code in entry for entry in context)


def test_run_case_scores_the_pipelines_own_answer(monkeypatch):
    case = _case("inventory-available-units")
    _stub_model(monkeypatch, case)
    metric = _StubMetric("Faithfulness", 0.82, True)

    result = deepeval_suite.run_case(case, [metric])

    assert result["case_id"] == case.case_id
    assert result["passed"] is True
    assert result["metrics"]["Faithfulness"]["score"] == 0.82
    # The judge must see what the pipeline actually produced, not the golden expectation.
    assert metric.measured[0].actual_output == result["answer"]
    assert case.answer_text in result["answer"]


def test_delivered_answer_includes_the_listing_cards():
    """A unit code belongs on a card, not in the prose. Grading the prose alone would fail
    a model for following the LISTINGS instruction."""

    class _Result:
        draft_answer = "Hiện có 1 căn 2PN còn trống."
        listings = [
            {
                "project_name": "The Beverly",
                "unit_type": "2PN",
                "area_range": "68,2 m²",
                "price_range": "3,6 tỷ",
                "unit_code": "OP3-BE1-1205",
                "status": "còn trống",
                # Resolved from the catalogue after the fact, so not part of the answer.
                "image_urls": ["https://cdn/photo.jpg"],
            }
        ]

    delivered = deepeval_suite._delivered_answer(_Result())

    assert "OP3-BE1-1205" in delivered
    assert _Result.draft_answer in delivered
    assert "cdn/photo.jpg" not in delivered


def test_delivered_answer_is_just_the_prose_when_there_are_no_cards():
    class _Result:
        draft_answer = "Chính sách thanh toán chia theo 8 đợt."
        listings: list = []

    assert deepeval_suite._delivered_answer(_Result()) == _Result.draft_answer


def test_required_facts_match_across_vietnamese_diacritics():
    """The golden cases are written unaccented; the model answers in full Vietnamese. A
    literal match would report every correct answer as missing its facts."""
    case = _case("policy-payment-schedule")

    assert case.expect_answer_contains == ("8 dot",)
    assert deepeval_suite._missing_required_facts(case, "Thanh toán theo tiến độ 8 đợt.") == []


def test_required_facts_reports_what_the_answer_left_out():
    case = _case("mixed-inventory-and-policy")

    missing = deepeval_suite._missing_required_facts(case, "Còn căn OP3-BE1-1205, giá 3,6 tỷ.")

    assert missing == ["5%"]


def test_required_facts_gate_fails_a_case_no_judge_would(monkeypatch):
    """The whole point of the deterministic gate: every judged metric can pass an answer
    that dropped a fact the reference commits to, and the case must still fail."""
    case = _case("inventory-available-units")
    monkeypatch.setattr(deepeval_suite, "_missing_required_facts", lambda *a: ["OP3-BE1-1205"])
    _stub_model(monkeypatch, case)

    result = deepeval_suite.run_case(case, [_StubMetric("Faithfulness", 1.0, True)])

    assert result["passed"] is False
    assert result["metrics"][deepeval_suite.REQUIRED_FACTS_METRIC]["passed"] is False
    assert "OP3-BE1-1205" in result["metrics"][deepeval_suite.REQUIRED_FACTS_METRIC]["reason"]


def test_run_case_hands_the_reference_answer_to_the_judge(monkeypatch):
    """`Answer Correctness` grades against the reference, so it has to reach the test case."""
    case = _case("inventory-available-units")
    _stub_model(monkeypatch, case)
    metric = _StubMetric("Answer Correctness [GEval]", 0.9, True)

    deepeval_suite.run_case(case, [metric])

    assert metric.measured[0].expected_output == case.expected_output
    assert case.expected_output, "the case lost its reference answer"


def test_run_case_fails_when_any_metric_fails(monkeypatch):
    """One failed metric fails the case: an answer with an invented price is not two-thirds
    acceptable."""
    case = _case("inventory-available-units")
    _stub_model(monkeypatch, case)

    result = deepeval_suite.run_case(
        case,
        [_StubMetric("Faithfulness", 0.9, True), _StubMetric("No Invented Figures [GEval]", 0.2, False)],
    )

    assert result["passed"] is False


def test_build_report_aggregates_per_metric():
    results = [
        {"case_id": "a", "passed": True, "metrics": {"Faithfulness": {"score": 1.0, "passed": True, "reason": ""}}},
        {
            "case_id": "b",
            "passed": False,
            "metrics": {"Faithfulness": {"score": 0.0, "passed": False, "reason": "unsupported claim"}},
        },
    ]

    report = deepeval_suite.build_report(results, judge_model="judge", answer_model="answerer")

    assert report["cases"] == 2
    assert report["pass_rate"] == 0.5
    assert report["metrics"]["Faithfulness"] == {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "mean_score": 0.5,
        "examples": ["unsupported claim"],
    }


def test_build_report_handles_an_empty_run():
    """`--fail-under` reads `pass_rate`; a ZeroDivisionError here would look like a failing
    eval rather than an empty one."""
    report = deepeval_suite.build_report([], judge_model="judge", answer_model="answerer")

    assert report["cases"] == 0
    assert report["pass_rate"] == 0.0


def test_build_report_flags_a_judge_grading_its_own_answers():
    """The scores are worth less when both models are the same one, so the run says so
    rather than leaving a reader to compare two strings."""
    same = deepeval_suite.build_report([], judge_model="gemini-x", answer_model="gemini-x")
    different = deepeval_suite.build_report([], judge_model="gemini-pro", answer_model="gemini-x")

    assert same["independent_judge"] is False
    assert different["independent_judge"] is True


def test_pacer_spaces_calls_out_to_the_allowed_rate(monkeypatch):
    """Waiting before a call is the whole point: a 429 costs more than the pause avoiding
    it, and the first call must not pay for a window nothing has used yet."""
    slept: list[float] = []
    # Read once to stamp the first call, then twice more on the second: elapsed, then the
    # new stamp. The 0.1s gap leaves 0.9s of the one-second window still to wait out.
    clock = iter([0.0, 0.1, 0.1])
    monkeypatch.setattr(deepeval_suite.time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(deepeval_suite.time, "sleep", slept.append)

    pacer = deepeval_suite._Pacer(rpm=60)  # one call per second
    pacer.wait()
    pacer.wait()

    assert slept == [pytest.approx(0.9)]


def test_pacer_does_nothing_when_pacing_is_switched_off(monkeypatch):
    monkeypatch.setattr(deepeval_suite.time, "sleep", lambda _seconds: pytest.fail("should not sleep"))

    deepeval_suite._Pacer(rpm=0).wait()


def test_quota_wait_uses_the_delay_the_api_asked_for():
    """The 429 names its own retry delay; guessing a fixed 20s either wastes time or wakes
    up into the same closed window."""
    from google.genai import errors as genai_errors

    error = genai_errors.APIError(
        429,
        {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "details": [{"retryDelay": "9s"}]}},
    )

    assert deepeval_suite._quota_wait_seconds(error) == 9.0
    # Found through a wrapping exception too, the way service layers re-raise.
    assert deepeval_suite._quota_wait_seconds(RuntimeError("wrapped")) == deepeval_suite._FALLBACK_QUOTA_WAIT_SECONDS
