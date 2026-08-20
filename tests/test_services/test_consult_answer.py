"""_generate: PUBLIC clearance gets structured output (text + quick_replies) via
generate_json/ConsultAnswer; INTERNAL/Sale stays on plain generate_text with no quick
replies — see agent_pipeline._generate and prompts.ConsultAnswer.
"""

from backend.ai.prompts import ConsultAnswer
from backend.core.enums import DocumentVisibility
from backend.services import agent_pipeline


def test_public_clearance_uses_structured_output_and_keeps_quick_replies(monkeypatch):
    monkeypatch.setattr(
        agent_pipeline,
        "generate_json",
        lambda *_a, **_kw: ConsultAnswer(text="Anh chị mua để ở hay đầu tư ạ?", quick_replies=["Để ở", "Đầu tư"]),
    )

    result = agent_pipeline._generate({"query": "tư vấn giúp em", "clearance": DocumentVisibility.PUBLIC})

    assert result["draft_answer"] == "Anh chị mua để ở hay đầu tư ạ?"
    assert result["quick_replies"] == ["Để ở", "Đầu tư"]


def test_public_clearance_fails_closed_when_unparseable(monkeypatch):
    monkeypatch.setattr(agent_pipeline, "generate_json", lambda *_a, **_kw: None)

    result = agent_pipeline._generate({"query": "tư vấn giúp em", "clearance": DocumentVisibility.PUBLIC})

    assert result == {"notice": agent_pipeline.GENERATION_ERROR_MESSAGE}


def test_internal_clearance_uses_plain_text_and_no_quick_replies(monkeypatch):
    monkeypatch.setattr(agent_pipeline, "generate_text", lambda *_a, **_kw: "Giá căn 2PN là 3.6 tỷ.")

    result = agent_pipeline._generate({"query": "giá căn 2PN?", "clearance": DocumentVisibility.INTERNAL})

    assert result["draft_answer"] == "Giá căn 2PN là 3.6 tỷ."
    assert result["quick_replies"] == []
