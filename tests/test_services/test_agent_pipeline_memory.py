"""Short-term working memory: earlier turns of a session reaching the agent.

Covers the three places history changes behaviour — the prompt sent to the LLM, the
retrieval query, and the semantic cache being bypassed mid-conversation.
"""

from backend.ai import prompts
from backend.services import agent_pipeline

FOLLOW_UP = "Con 3PN thi sao?"
PREVIOUS_QUESTION = "Gia can 2PN The Palma bao nhieu?"


def _history() -> list[prompts.ConversationTurn]:
    return [
        prompts.ConversationTurn(is_sale=True, content=PREVIOUS_QUESTION),
        prompts.ConversationTurn(is_sale=False, content="- Can 2PN The Palma tu 3,6 ty dong."),
    ]


# --------------------------------------------------------------------------- prompt


def test_history_reaches_the_prompt_labelled_by_speaker():
    prompt = prompts.build_prompt(FOLLOW_UP, [], [], False, False, history=_history())

    assert "LỊCH SỬ HỘI THOẠI" in prompt
    assert PREVIOUS_QUESTION in prompt
    assert "Sale:" in prompt
    assert "Trợ lý:" in prompt


def test_history_section_precedes_the_current_question():
    """Model doc lich su truoc, roi moi den cau hoi dang can tra loi."""
    prompt = prompts.build_prompt(FOLLOW_UP, [], [], False, False, history=_history())

    assert prompt.index(PREVIOUS_QUESTION) < prompt.index("CÂU HỎI CỦA SALE")


def test_prompt_forbids_taking_figures_out_of_history():
    """Lich su chi de hieu ngu canh — con so phai lay tu NGU CANH, khong phai tu cau tra loi cu."""
    prompt = prompts.build_prompt(FOLLOW_UP, [], [], False, False, history=_history())

    assert "không lấy số liệu từ lịch sử" in prompt


def test_no_history_leaves_the_prompt_unchanged():
    """Cau hoi dau tien trong phien phai cho ra prompt y het truoc khi co memory."""
    without = prompts.build_prompt(FOLLOW_UP, [], [], False, False)
    with_empty = prompts.build_prompt(FOLLOW_UP, [], [], False, False, history=[])

    assert without == with_empty
    assert "LỊCH SỬ HỘI THOẠI" not in without


def test_long_agent_answer_is_truncated_but_sale_question_is_not():
    """Cau tra loi dai bi cat de khong lan at ngu canh; cau hoi cua Sale giu nguyen."""
    long_question = "A" * 400
    turns = [
        prompts.ConversationTurn(is_sale=True, content=long_question),
        prompts.ConversationTurn(is_sale=False, content="B" * 400),
    ]

    rendered = prompts.format_history(turns)

    assert long_question in rendered
    assert "B" * prompts.HISTORY_ANSWER_MAX_CHARS in rendered
    assert "B" * (prompts.HISTORY_ANSWER_MAX_CHARS + 1) not in rendered
    assert "..." in rendered


def test_blank_turns_are_dropped():
    turns = [
        prompts.ConversationTurn(is_sale=True, content="   "),
        prompts.ConversationTurn(is_sale=True, content="Gia bao nhieu?"),
    ]

    assert prompts.format_history(turns) == "Sale: Gia bao nhieu?"


# --------------------------------------------------------------------------- retrieval


def test_retrieval_query_carries_the_previous_question():
    """'Con 3PN thi sao?' khong co ten du an — phai lay tu cau hoi truoc de embed cho dung."""
    expanded = prompts.build_retrieval_query(FOLLOW_UP, _history())

    assert PREVIOUS_QUESTION in expanded
    assert FOLLOW_UP in expanded


def test_retrieval_query_ignores_agent_answers():
    """Cau tra loi dai se lan at vector — chi dung cau hoi cua Sale."""
    turns = [prompts.ConversationTurn(is_sale=False, content="- Can 2PN tu 3,6 ty dong.")]

    assert prompts.build_retrieval_query(FOLLOW_UP, turns) == FOLLOW_UP


def test_retrieval_query_without_history_is_the_bare_question():
    assert prompts.build_retrieval_query(FOLLOW_UP, []) == FOLLOW_UP


def test_retrieve_node_embeds_the_expanded_query(monkeypatch):
    seen: list[str] = []

    def fake_retrieve(query, *_args, **_kwargs):
        seen.append(query)
        return [{"document_id": 1, "title": "Bang gia", "page": 1, "content": "3PN tu 5 ty.", "score": 0.9}]

    monkeypatch.setattr(agent_pipeline, "retrieve", fake_retrieve)

    agent_pipeline._retrieve({"query": FOLLOW_UP, "project_id": "the-palma", "conversation_history": _history()})

    assert PREVIOUS_QUESTION in seen[0]


# --------------------------------------------------------------------------- cache


def test_cache_is_skipped_once_the_session_has_history(monkeypatch):
    """Cache khop theo cau chu — 'Con 3PN thi sao?' o phien khac la mot cau hoi hoan toan khac."""
    called = False

    def fake_lookup(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("cache must not be consulted mid-conversation")

    monkeypatch.setattr(agent_pipeline.cache_service, "lookup_cache", fake_lookup)

    result = agent_pipeline._cache_check({"query": FOLLOW_UP, "conversation_history": _history()})

    assert called is False
    assert result == {"used_cache": False}


def test_cache_still_serves_the_first_question_of_a_session(monkeypatch):
    """Bo cache khi co lich su, nhung cau hoi dau phien van phai duoc cache phuc vu."""
    monkeypatch.setattr(
        agent_pipeline.cache_service,
        "lookup_cache",
        lambda *_args, **_kwargs: agent_pipeline.cache_service.CachedAnswer(
            answer="Can 2PN tu 3,6 ty dong.", citations=[], verifier_score=0.92
        ),
    )

    result = agent_pipeline._cache_check({"query": PREVIOUS_QUESTION, "conversation_history": []})

    assert result["used_cache"] is True
    assert result["draft_answer"] == "Can 2PN tu 3,6 ty dong."


def test_mid_conversation_answers_are_never_written_to_the_cache(monkeypatch):
    """Ghi cache theo cau follow-up tran trui se dau doc cache cho moi phien sau."""
    stored: list[str] = []

    monkeypatch.setattr(agent_pipeline, "_store_cache", lambda query, *_a, **_k: stored.append(query))
    monkeypatch.setattr(
        agent_pipeline,
        "_get_graph",
        lambda: _FakeGraph({"draft_answer": "Can 3PN tu 5 ty dong.", "verifier_score": 0.95}),
    )

    agent_pipeline.run_pipeline(FOLLOW_UP, project_id="the-palma", conversation_history=_history())
    assert stored == []

    agent_pipeline.run_pipeline(PREVIOUS_QUESTION, project_id="the-palma")
    assert stored == [PREVIOUS_QUESTION]


class _FakeGraph:
    """Stands in for the compiled LangGraph so run_pipeline can be driven without LLM calls."""

    def __init__(self, state: dict):
        self._state = state

    def invoke(self, initial):
        return {**initial, **self._state}
