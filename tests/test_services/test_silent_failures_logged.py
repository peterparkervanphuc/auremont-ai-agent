"""Regression suite for failure paths that used to be completely silent.

Every test here asserts **both** halves:

* the return value is unchanged — logging must not alter control flow;
* something was actually logged, with a traceback where one is warranted.

The first half matters as much as the second. These functions promise never to
raise, and the whole point of the logging change was that it added visibility
without touching behaviour.
"""

import logging

import pytest

from backend.core import security
from backend.services import agent_pipeline, cache_service, rag_service, verifier_service


def explode(*args, **kwargs):
    raise RuntimeError("dependency is down")


class TestAgentPipeline:
    def test_crash_returns_the_notice_and_logs_a_traceback(self, monkeypatch, capture_logs):
        monkeypatch.setattr(agent_pipeline, "_get_graph", explode)

        result = agent_pipeline.run_pipeline("giá căn 2PN?", project_id="ocean-park-3")

        assert result.draft_answer == agent_pipeline.GENERATION_ERROR_MESSAGE
        assert result.verifier_score == 0.0
        assert result.requires_hitl is False
        assert result.citations == []

        record = capture_logs.event("pipeline.crash")
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None
        assert record.project_id == "ocean-park-3"

    def test_crash_log_carries_query_length_not_the_query(self, monkeypatch, capture_logs):
        monkeypatch.setattr(agent_pipeline, "_get_graph", explode)

        agent_pipeline.run_pipeline("giá căn 2PN?")

        assert capture_logs.event("pipeline.crash").query_len == len("giá căn 2PN?")


class TestVerifier:
    def test_judge_failure_scores_zero_and_logs(self, monkeypatch, capture_logs):
        monkeypatch.setattr(verifier_service, "generate_text", explode)

        result = verifier_service.score_answer("q", "an answer", ["some context"])

        assert result.score == 0.0
        assert result.faithfulness == 0.0
        assert result.relevancy == 0.0

        record = capture_logs.event("verifier.judge.failed")
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None

    def test_missing_json_scores_zero_and_logs(self, capture_logs):
        result = verifier_service._parse_scores("the model rambled without JSON")

        assert result.score == 0.0
        assert capture_logs.event("verifier.parse.no_json").levelno == logging.WARNING

    def test_malformed_json_scores_zero_and_logs(self, capture_logs):
        result = verifier_service._parse_scores("{not: valid json,}")

        assert result.score == 0.0
        assert capture_logs.events("verifier.parse.bad_json")

    def test_array_without_an_object_scores_zero_and_logs(self, capture_logs):
        """_JSON_PATTERN looks for {...}, so a bare array is a no-JSON case."""
        result = verifier_service._parse_scores("[1, 2, 3]")

        assert result.score == 0.0
        assert capture_logs.events("verifier.parse.no_json")

    def test_valid_scores_are_not_logged_as_failures(self, capture_logs):
        result = verifier_service._parse_scores('{"faithfulness": 0.9, "relevancy": 0.8}')

        assert result.score == 0.8
        assert not [r for r in capture_logs.records if str(getattr(r, "event", "")).startswith("verifier.parse")]


class TestSemanticCache:
    def test_lookup_failure_is_a_miss_and_logs(self, monkeypatch, capture_logs):
        monkeypatch.setattr(cache_service, "get_qdrant_client", explode)

        assert cache_service.lookup_cache("giá căn 2PN?", "ocean-park-3") is None

        record = capture_logs.event("cache.lookup.failed")
        assert record.levelno == logging.WARNING
        assert record.exc_info is not None
        assert record.project_id == "ocean-park-3"

    def test_store_failure_is_swallowed_and_logs(self, monkeypatch, capture_logs):
        monkeypatch.setattr(cache_service, "get_qdrant_client", explode)

        assert cache_service.store_cache("q", "an answer", [], 0.9, "ocean-park-3") is None

        assert capture_logs.event("cache.store.failed").levelno == logging.WARNING


class TestRetrieval:
    def test_qdrant_failure_still_raises_and_logs_first(self, monkeypatch, capture_logs):
        """agent_pipeline discards RetrievalError, so this log is the only record."""
        class DeadClient:
            def collection_exists(self, name):
                raise RuntimeError("qdrant is down")

        monkeypatch.setattr(rag_service, "embed_query", lambda query: [0.0] * 768)
        monkeypatch.setattr(rag_service, "get_qdrant_client", lambda: DeadClient())

        with pytest.raises(rag_service.RetrievalError):
            rag_service.retrieve("giá căn 2PN?", "INTERNAL", "ocean-park-3", 5)

        record = capture_logs.event("retrieval.qdrant.failed")
        assert record.levelno == logging.ERROR
        assert record.exc_info is not None


class TestJwt:
    def test_rejected_token_returns_none_and_logs_the_reason(self, capture_logs):
        assert security.decode_token("not-a-real-jwt") is None

        record = capture_logs.event("auth.token.rejected")
        assert record.levelno == logging.WARNING
        assert record.reason  # the exception class name distinguishes expiry from tampering

    def test_the_token_itself_is_never_logged(self, capture_logs):
        token = "eyJhbGciOiJIUzI1NiJ9.TAMPERED_PAYLOAD_SECRET.sig"

        security.decode_token(token)

        for record in capture_logs.records:
            assert token not in str(record.__dict__)
