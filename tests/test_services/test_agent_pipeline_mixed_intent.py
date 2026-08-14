from backend.services import agent_pipeline
from backend.services.inventory_service import InventoryApiError, InventoryUnit


def _policy_hit() -> dict:
    return {
        "document_id": 101,
        "title": "CSBH The Beverly V64.pdf",
        "page": 2,
        "content": "Can 2PN duoc chiet khau 5% khi thanh toan som.",
        "score": 0.9,
    }


def _available_2pn() -> InventoryUnit:
    return InventoryUnit(
        unit_code="OP3-BE1-1205",
        project_id="ocean-park-3",
        subdivision="The Beverly",
        unit_type="2PN",
        area_m2=68.2,
        price=3_600_000_000,
        status="available",
    )


def test_mixed_inventory_and_policy_question_uses_both_sources(monkeypatch):
    query = "Co can nao 2 phong ngu va chinh sach ban hang nhu nao?"
    calls: list[str] = []

    def fake_retrieve(*_args, **_kwargs):
        calls.append("qdrant")
        return [_policy_hit()]

    def fake_inventory(project_id: str, received_query: str):
        calls.append("inventory")
        assert project_id == "ocean-park-3"
        assert received_query == query
        return [_available_2pn()]

    monkeypatch.setattr(agent_pipeline, "retrieve", fake_retrieve)
    monkeypatch.setattr(agent_pipeline, "lookup_inventory", fake_inventory)

    retrieved = agent_pipeline._retrieve(
        {"query": query, "project_id": "ocean-park-3"}
    )
    inventory = agent_pipeline._tool_call(
        {"query": query, "project_id": "ocean-park-3", **retrieved}
    )
    prompt = agent_pipeline._build_prompt(
        query,
        retrieved["retrieved_docs"],
        inventory["inventory_units"],
        retrieved["needs_inventory"],
        inventory["inventory_failed"],
    )

    assert calls == ["qdrant", "inventory"]
    assert retrieved["needs_document_retrieval"] is True
    assert retrieved["needs_inventory"] is True
    assert "CSBH The Beverly V64.pdf" in prompt
    assert "OP3-BE1-1205" in prompt


def test_mixed_question_keeps_policy_context_when_inventory_fails(monkeypatch):
    state = {
        "query": "Co can 2PN va chinh sach ban hang the nao?",
        "project_id": "ocean-park-3",
        "retrieved_docs": [_policy_hit()],
    }

    monkeypatch.setattr(
        agent_pipeline,
        "lookup_inventory",
        lambda *_args: (_ for _ in ()).throw(InventoryApiError("offline")),
    )

    result = agent_pipeline._tool_call(state)

    assert result["inventory_failed"] is True
    assert result["inventory_units"] == []
    assert "notice" not in result
