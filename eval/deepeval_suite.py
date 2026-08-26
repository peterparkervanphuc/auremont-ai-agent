"""Offline DeepEval batch over the golden questions, with the real model in the loop.

The third eval layer, filling the gap the other two leave:

- `tests/test_services/test_golden_regression.py` runs the same questions with the LLM
  stubbed, so it proves routing and assembly but says nothing about answer quality.
- `eval/graders.py` grades recorded traces, which are content-free by design
  (`backend/core/tracing.py` records `query_len`, not the question) — no judge can score
  an answer it cannot read.

This module runs each golden question through the real pipeline with retrieval, inventory
and the cache frozen to the case's fixed world, and lets Gemini actually draft the answer.
The world is deterministic and the model is not, so what varies between runs is exactly
what DeepEval is asked to measure.

"Who judges the judge" is answered here in two ways, because the first is not enough on
its own.

`--judge-model` left at `GEMINI_MODEL` has the model grading its own drafts, which measures
self-consistency more than quality — the first live run scored a flat 1.00 on every metric.
Pointing it at a different, stronger model buys a second opinion, a sharper grader, and a
*separate quota bucket* (Gemini counts its per-minute limit per model). That independence is
still partial: one vendor, one training lineage.

So the gate that decides a case is not a judgement at all. `GoldenCase.expected_output`
holds a hand-written reference answer, and `REQUIRED_FACTS_METRIC` checks by string match
that the facts the reference commits to — a price, a unit code, a discount — actually
appear in what the model wrote. No model votes on that, so no model can be generous about
it. The judged metrics stay for what strings cannot see (is a claim grounded, is the answer
on topic, was a figure invented), and the report marks which numbers are which.

Costs real API calls, so it is opt-in and deliberately not wired into CI — deepeval lives
in `requirements-eval.txt` rather than `requirements.txt` for the same reason:

    pip install -r requirements-eval.txt
    python -m eval.deepeval_suite
    python -m eval.deepeval_suite --judge-model gemini-3-pro --rpm 150
    python -m eval.deepeval_suite --fail-under 0.9

Each metric spends several judge calls per answer, so a run is dozens of requests. `--rpm`
paces them to stay under the key's per-minute allowance (default: the free tier's 15),
which is far cheaper than tripping a 429 and waiting out the window afterwards.
"""

import argparse
import json
import statistics
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric, GEval
from deepeval.models.base_model import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase, SingleTurnParams
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel

from backend.core import gemini_client
from backend.core.config import settings
from backend.services import agent_pipeline
from backend.services.inventory_service import InventoryApiError
from backend.utils.text import strip_diacritics
from eval.golden_dataset import GOLDEN_CASES, GoldenCase

DEFAULT_OUT = Path("eval/results")

# The one gate no model has a vote in — see `_missing_required_facts`.
REQUIRED_FACTS_METRIC = "Required Facts"

# The Gemini free tier allows 15 generate_content requests per minute per model.
DEFAULT_RPM = 15

# Pacing keeps a run under the limit; this catches the case where it still is not — a key
# shared with another process, or an `--rpm` set higher than the key actually allows.
# `gemini_client` retries such a 429 at most once with a sub-second backoff on purpose: it
# sits under the interactive path's 3-second budget, where waiting out a quota window is
# worse than failing. Nothing here is interactive, so this waits instead of giving up.
_QUOTA_RETRY_ATTEMPTS = 5
_FALLBACK_QUOTA_WAIT_SECONDS = 20.0
# Gemini has been seen answering a 429 with `retryDelay: "0s"`, which spends an attempt on
# a retry that cannot succeed. Wait at least long enough for the window to have moved.
_MIN_QUOTA_WAIT_SECONDS = 5.0


class _Pacer:
    """Spaces calls out so the per-minute limit is approached but never crossed.

    Reacting to a 429 is far more expensive than avoiding one: the response asks for a wait
    measured in seconds, and every metric mid-flight pays it. Spending the same seconds up
    front, spread between calls, costs the same wall-clock time and never loses a request.
    """

    def __init__(self, rpm: int):
        self._min_interval = 60.0 / rpm if rpm > 0 else 0.0
        # None rather than 0.0: `monotonic()`'s origin is arbitrary, so a zero here would
        # make the very first call pause for a window that nothing has used yet on any
        # machine whose clock happens to start near zero.
        self._last_call: float | None = None

    def wait(self) -> None:
        if not self._min_interval:
            return

        if self._last_call is not None:
            elapsed = time.monotonic() - self._last_call
            if elapsed < self._min_interval:
                time.sleep(self._min_interval - elapsed)

        self._last_call = time.monotonic()


def _quota_wait_seconds(exc: BaseException) -> float:
    """How long the API itself asked us to wait, found on whichever error carries it.

    The pipeline wraps SDK exceptions before they cross a service boundary, so the
    `RetryInfo` is often on a cause rather than on `exc` — the same walk
    `is_gemini_quota_error` does to recognise the error in the first place.
    """
    current: BaseException | None = exc
    visited: set[int] = set()
    while current is not None and id(current) not in visited:
        visited.add(id(current))
        if isinstance(current, genai_errors.APIError):
            return max(gemini_client.retry_delay_seconds(current), _MIN_QUOTA_WAIT_SECONDS)
        current = current.__cause__ or current.__context__

    return _FALLBACK_QUOTA_WAIT_SECONDS


def _with_quota_retry(call):
    """Wait out a Gemini quota window rather than losing the run half-graded.

    Wraps both sides of a case — the pipeline drafting the answer and the judge scoring it
    — because either can be the call that crosses the per-minute limit, and a crash in the
    middle throws away every case already paid for.
    """
    for attempt in range(1, _QUOTA_RETRY_ATTEMPTS + 1):
        try:
            return call()
        except Exception as exc:
            if attempt == _QUOTA_RETRY_ATTEMPTS or not gemini_client.is_gemini_quota_error(exc):
                raise

            delay = _quota_wait_seconds(exc)
            print(
                f"Gemini quota reached; waiting {delay:.0f}s (attempt {attempt}/{_QUOTA_RETRY_ATTEMPTS}).",
                file=sys.stderr,
            )
            time.sleep(delay)

    # Unreachable: the loop either returns or raises on its final attempt.
    raise RuntimeError("The quota retry loop exited without a result.")


class GeminiJudge(DeepEvalBaseLLM):
    """DeepEval's judge, on Gemini and on its own model.

    DeepEval defaults to OpenAI; this project has no OpenAI key and no reason to acquire
    one. It calls the SDK directly rather than going through `gemini_client` for two
    reasons the eval path does not share with the request path: the judge must be free to
    run on a *different* model than `GEMINI_MODEL` (see the module docstring), and
    `client_models_generate` books every call into the pipeline's token accounting, where
    eval traffic would show up as production spend on the Admin dashboard.

    Schema-constrained decoding is kept, because DeepEval asks for structured verdicts and
    a judge returning prose with a brace in it fails in a way that reads as a bad score.
    """

    def __init__(self, model_name: str, rpm: int = DEFAULT_RPM):
        self._model_name = model_name
        self._pacer = _Pacer(rpm)
        super().__init__(model_name)

    def load_model(self):
        return gemini_client.get_gemini_client()

    def get_model_name(self) -> str:
        return f"Gemini ({self._model_name})"

    def generate(self, prompt: str, schema: type[BaseModel] | None = None) -> Any:
        return _with_quota_retry(lambda: self._generate_once(prompt, schema))

    def _generate_once(self, prompt: str, schema: type[BaseModel] | None) -> Any:
        self._pacer.wait()
        response = self.model.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json" if schema else None,
                response_schema=schema,
            ),
        )

        if schema is None:
            return response.text or ""

        parsed = getattr(response, "parsed", None)
        if isinstance(parsed, schema):
            return parsed

        # Older SDK builds populate `.text` but not `.parsed`.
        raw = (response.text or "").strip()
        if not raw:
            raise RuntimeError(f"The judge returned nothing parseable as {schema.__name__}.")
        return schema.model_validate_json(raw)

    async def a_generate(self, prompt: str, schema: type[BaseModel] | None = None) -> Any:
        # The client here is synchronous; every metric runs with `async_mode=False`, so
        # this exists only to satisfy the base class.
        return self.generate(prompt, schema)


@contextmanager
def _fixed_world(case: GoldenCase):
    """Freeze everything except the model, at the boundary the golden test stubs at.

    The cache is stubbed in both directions on purpose: a warm entry would return a
    previous run's answer (nothing to judge), and writing through would seed production's
    semantic cache from an eval run.
    """

    def _lookup(project_id, query):
        if case.inventory_raises:
            raise InventoryApiError("down")
        return case.inventory_units

    patches = [
        (agent_pipeline, "retrieve", lambda *a, **k: case.retrieved_docs),
        (agent_pipeline, "lookup_inventory", _lookup),
        (agent_pipeline, "_store_cache", lambda *a, **k: None),
        (agent_pipeline.cache_service, "lookup_cache", lambda *a, **k: None),
    ]
    originals = [(obj, name, getattr(obj, name)) for obj, name, _ in patches]

    for obj, name, replacement in patches:
        setattr(obj, name, replacement)
    try:
        yield
    finally:
        for obj, name, original in originals:
            setattr(obj, name, original)


def _retrieval_context(case: GoldenCase) -> list[str]:
    """Everything the answer is allowed to be grounded in, as the judge will see it.

    Inventory units are flattened into text because they reach the model as context the
    same way a document passage does; a unit the model never saw must read as ungrounded
    to the judge too.
    """
    context = [doc["content"] for doc in case.retrieved_docs]
    context += [
        f"{unit.unit_code} | {unit.subdivision} | {unit.unit_type} | "
        f"{unit.area_m2} m2 | {unit.price} VND | {unit.status}"
        for unit in case.inventory_units
    ]
    return context


# The text fields of a listing card, in the order a reader meets them. `image_urls`,
# `amenities` and `project_id` are left out: they are resolved from the catalogue after the
# model has spoken (`_resolve_listing_images`), so they are not part of what it answered.
_LISTING_FIELDS = ("project_name", "unit_type", "area_range", "price_range", "unit_code", "status")


def _delivered_answer(result: Any) -> str:
    """Everything the Sale actually reads: the prose plus the unit cards beside it.

    A unit code belongs in `SaleAnswer.listings`, not in the prose — the LISTINGS block of
    the system instruction tells the model to put per-unit figures on a card that the
    frontend renders as a badge, rather than repeat them in `text`. Grading `draft_answer`
    alone therefore marks a model that followed its instructions as having dropped the
    fact, which is a defect in the eval and not in the answer.
    """
    parts = [result.draft_answer]
    for listing in result.listings:
        values = [str(listing.get(field) or "") for field in _LISTING_FIELDS]
        parts.append(" | ".join(value for value in values if value))
    return "\n".join(part for part in parts if part)


def _missing_required_facts(case: GoldenCase, answer: str) -> list[str]:
    """The facts the draft had to state and did not — decided by string matching, not by a
    model.

    This is the answer to a judge that scores its own vendor's output generously: whether
    "3,6 tỷ" or "OP3-BE1-1205" appears in a sentence is not a matter of opinion, so nothing
    here asks for one. `expect_answer_contains` already names those facts per case; the
    golden regression test checks them against a stubbed draft, and this checks the same
    ones against what the real model wrote.

    Both sides go through `strip_diacritics` because the golden cases are written
    unaccented, the way a Sale types on a phone, while the model answers in full
    Vietnamese — "8 dot" has to match "8 đợt".
    """
    normalised = strip_diacritics(answer)
    return [fact for fact in case.expect_answer_contains if strip_diacritics(fact) not in normalised]


def build_metrics(judge: DeepEvalBaseLLM, threshold: float) -> list[Any]:
    """Faithfulness and relevancy mirror the Verifier's own two axes, so their scores can
    be read against the `verifier_score` recorded per case; the other two are what generic
    grounding metrics miss — whether the answer says what a Sale needed it to say, and
    whether a figure in it was invented. A wrong price is not a style problem here."""
    return [
        FaithfulnessMetric(threshold=threshold, model=judge, async_mode=False, include_reason=True),
        AnswerRelevancyMetric(threshold=threshold, model=judge, async_mode=False, include_reason=True),
        GEval(
            name="Answer Correctness",
            criteria=(
                "Compare the answer against the reference answer, which is correct by "
                "definition. The answer scores well when it states the same facts as the "
                "reference — the same figures, units, unit codes and policy terms — and "
                "contradicts none of them. Extra detail is acceptable. Leaving out a fact "
                "the reference states is not. Ignore differences of wording, ordering, "
                "formatting, politeness and length."
            ),
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.EXPECTED_OUTPUT,
            ],
            threshold=threshold,
            model=judge,
            async_mode=False,
        ),
        GEval(
            name="No Invented Figures",
            criteria=(
                "Every concrete figure in the answer — prices, discounts and percentages, "
                "payment instalments, areas, dates, and unit codes — must be traceable to "
                "the retrieval context. Penalise any figure that is absent from the "
                "context, rounded differently, or attributed to the wrong unit or "
                "project. Do not penalise the answer for omitting figures, for wording, "
                "or for being written in Vietnamese."
            ),
            evaluation_params=[
                SingleTurnParams.INPUT,
                SingleTurnParams.ACTUAL_OUTPUT,
                SingleTurnParams.RETRIEVAL_CONTEXT,
            ],
            threshold=threshold,
            model=judge,
            async_mode=False,
        ),
    ]


def gradeable_cases() -> list[GoldenCase]:
    """Only the cases that actually reach Generate.

    A case expecting a notice short-circuits the graph before the model drafts anything
    (empty state, inventory down, Verifier decline), leaving a fixed string that no judge
    should be paid to score. Those stay the golden regression test's job.
    """
    return [case for case in GOLDEN_CASES if not case.expect_notice]


def run_case(case: GoldenCase, metrics: list[Any]) -> dict[str, Any]:
    with _fixed_world(case):
        result = _with_quota_retry(lambda: agent_pipeline.run_pipeline(case.query, project_id=case.project_id))

    delivered = _delivered_answer(result)
    test_case = LLMTestCase(
        input=case.query,
        actual_output=delivered,
        expected_output=case.expected_output,
        retrieval_context=_retrieval_context(case),
    )

    missing = _missing_required_facts(case, delivered)
    scores: dict[str, Any] = {
        REQUIRED_FACTS_METRIC: {
            "score": 0.0 if missing else 1.0,
            "passed": not missing,
            "reason": f"Missing from the answer: {', '.join(missing)}." if missing else "",
        }
    }

    for metric in metrics:
        metric.measure(test_case)
        # `__name__`, not `name`: only GEval carries a `name` attribute, and the built-in
        # metrics expose their display name here.
        scores[metric.__name__] = {
            "score": round(metric.score or 0.0, 4),
            "passed": bool(metric.is_successful()),
            "reason": metric.reason or "",
        }

    return {
        "case_id": case.case_id,
        "answer": result.draft_answer,
        # Recorded separately from `answer` so a reader can tell where a fact was
        # delivered: prose, card, or nowhere at all.
        "listings": result.listings,
        # The in-house Verifier's verdict on the same answer, for comparison: a case the
        # Verifier accepted and DeepEval failed is where `verifier_threshold_sale` or the
        # Verifier prompt needs attention.
        "verifier_score": result.verifier_score,
        "verifier_failure_mode": result.failure_mode,
        "requires_hitl": result.requires_hitl,
        "metrics": scores,
        "passed": all(entry["passed"] for entry in scores.values()),
    }


def build_report(results: list[dict[str, Any]], *, judge_model: str, answer_model: str) -> dict[str, Any]:
    """Aggregate to the same shape `eval/graders.py` reports in, so both live under
    `eval/results/` and can be read the same way.

    Both model names are recorded because a score only means something next to them: a
    pass rate that moved between runs is a different finding depending on whether the
    answer model changed, the judge did, or neither.
    """
    per_metric: dict[str, dict[str, Any]] = {}
    for name in dict.fromkeys(name for result in results for name in result["metrics"]):
        entries = [result["metrics"][name] for result in results if name in result["metrics"]]
        failed = [entry for entry in entries if not entry["passed"]]
        per_metric[name] = {
            "total": len(entries),
            "passed": len(entries) - len(failed),
            "failed": len(failed),
            "mean_score": round(statistics.fmean(entry["score"] for entry in entries), 4) if entries else 0.0,
            "examples": [entry["reason"] for entry in failed[:3]],
        }

    passed = sum(1 for result in results if result["passed"])
    return {
        "cases": len(results),
        "passed": passed,
        "failed": len(results) - passed,
        "pass_rate": round(passed / len(results), 4) if results else 0.0,
        "answer_model": answer_model,
        "judge_model": judge_model,
        "independent_judge": judge_model != answer_model,
        # Which numbers below survive a sceptical reading of the judge: these were decided
        # by rules over a hand-written reference, with no model in the loop.
        "deterministic_metrics": [REQUIRED_FACTS_METRIC],
        "metrics": per_metric,
        "cases_detail": results,
    }


def _summarise(report: dict[str, Any]) -> str:
    independence = "" if report["independent_judge"] else "  (grading its own answers)"
    lines = [
        f"Answer model: {report['answer_model']}",
        f"Judge model:  {report['judge_model']}{independence}",
        f"Cases:       {report['cases']}",
        f"Pass rate:   {report['pass_rate']:.1%} ({report['passed']} passed, {report['failed']} failed)",
        "",
        "Metrics:",
    ]
    for name, stats in report["metrics"].items():
        judged = "" if name in report["deterministic_metrics"] else "  (judged)"
        lines.append(f"  {stats['passed']:2}/{stats['total']}  mean {stats['mean_score']:.2f}  {name}{judged}")
        for example in stats["examples"]:
            lines.append(f"          {example}")

    failing = [case for case in report["cases_detail"] if not case["passed"]]
    if failing:
        lines.append("\nFailing cases:")
        for case in failing:
            lines.append(f"  {case['case_id']}  (verifier scored it {case['verifier_score']})")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="directory for deepeval_report.json")
    parser.add_argument(
        "--threshold",
        type=float,
        default=settings.verifier_threshold_sale,
        help="per-metric pass threshold (defaults to the Verifier's own)",
    )
    parser.add_argument(
        "--judge-model",
        default=settings.GEMINI_MODEL,
        metavar="MODEL",
        help="model that grades the answers; a different one to GEMINI_MODEL buys independence and its own quota",
    )
    parser.add_argument(
        "--rpm",
        type=int,
        default=DEFAULT_RPM,
        help=f"judge requests per minute the key allows (default {DEFAULT_RPM}, the free tier's)",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        metavar="RATE",
        help="exit non-zero when the case pass rate falls below RATE (0-1)",
    )
    args = parser.parse_args()

    if not settings.GEMINI_API_KEY:
        print("GEMINI_API_KEY is not set; this suite calls the real model.", file=sys.stderr)
        return 1

    metrics = build_metrics(GeminiJudge(args.judge_model, args.rpm), args.threshold)
    results = [run_case(case, metrics) for case in gradeable_cases()]

    report = build_report(results, judge_model=args.judge_model, answer_model=settings.GEMINI_MODEL)
    args.out.mkdir(parents=True, exist_ok=True)
    report_path = args.out / "deepeval_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print(_summarise(report))
    print(f"\nWrote {report_path}")

    if args.fail_under is not None and report["pass_rate"] < args.fail_under:
        print(
            f"\nFAIL: pass rate {report['pass_rate']:.1%} is below the required {args.fail_under:.1%}.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
