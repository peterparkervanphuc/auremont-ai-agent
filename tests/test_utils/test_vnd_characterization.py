"""Records what every VND price parser in the codebase does today, disagreements included.

Written before unifying them, so the unification has something to diff against. The table
below is not a specification — several rows document behaviour that is plainly wrong. They
are pinned here anyway, because a refactor that silently changes what "1.500 trieu" means is
exactly the failure this file exists to catch.

Five call sites parse Vietnamese money, and they do not agree:

  backend/services/inventory_service.py:_price_to_vnd   units: tỷ ty t triệu trieu tr
  backend/services/ingestion_service.py:_price_to_vnd   units: ty billion trieu tr million vnd dong d
  backend/services/search_criteria.py                   regex only; delegates to inventory's
  backend/services/memory_service.py                    regex only; no `tr`
  backend/routers/admin_observability.py                regex only; the only one with `tỉ`

The disagreements that matter are marked DIFF in the ids below.
"""

import pytest

from backend.services import ingestion_service, inventory_service

# (number, unit, inventory_result, ingestion_result, note)
# `None` for a result means the parser raises rather than returning a number.
CASES = [
    # --- the two agree here ---
    ("3", "tỷ", 3_000_000_000.0, 3_000_000_000, "agree"),
    ("3", "ty", 3_000_000_000.0, 3_000_000_000, "agree"),
    ("3", "triệu", 3_000_000.0, 3_000_000, "agree"),
    ("3", "trieu", 3_000_000.0, 3_000_000, "agree"),
    ("3", "tr", 3_000_000.0, 3_000_000, "agree"),
    ("2,5", "tỷ", 2_500_000_000.0, 2_500_000_000, "agree: comma is a decimal separator"),
    ("2.5", "tỷ", 2_500_000_000.0, 2_500_000_000, "agree: dot is a decimal separator"),
    ("1.500", "tỷ", 1_500_000_000.0, 1_500_000_000, "agree: 1.5 tỷ, dot read as decimal"),
    ("3", "vnd", 3.0, 3, "agree: plain đồng"),
    # --- DIFF: `tỉ` (northern spelling) is a unit to neither, so both read a bare number ---
    ("3", "tỉ", 3.0, 3, "DIFF vs admin_observability, whose regex is the only one matching tỉ"),
    # --- DIFF: bare `t` means tỷ to inventory and nothing to ingestion ---
    ("3", "t", 3_000_000_000.0, 3, "DIFF: 3 tỷ vs 3 đồng"),
    # --- DIFF: grouped thousands. ingestion is the only parser that handles them ---
    ("1.500.000", "VND", None, 1_500_000, "DIFF: inventory raises, ingestion reads 1.5 triệu"),
    ("1.500", "trieu", 1_500_000.0, 1_500_000_000, "DIFF 1000x: 1.5 triệu vs 1.5 tỷ"),
    # --- DIFF: English unit names are ingestion-only ---
    ("3", "million", 3.0, 3_000_000, "DIFF: unit ignored vs 3 triệu"),
    ("3", "billion", 3.0, 3_000_000_000, "DIFF: unit ignored vs 3 tỷ"),
]


def _ids() -> list[str]:
    return [f"{number}_{unit}_{note.split(':')[0]}" for number, unit, _, _, note in CASES]


@pytest.mark.parametrize(("number", "unit", "expected", "_ingestion", "_note"), CASES, ids=_ids())
def test_inventory_price_to_vnd(number, unit, expected, _ingestion, _note):
    if expected is None:
        with pytest.raises(ValueError):
            inventory_service._price_to_vnd(number, unit)
        return
    assert inventory_service._price_to_vnd(number, unit) == expected


@pytest.mark.parametrize(("number", "unit", "_inventory", "expected", "_note"), CASES, ids=_ids())
def test_ingestion_price_to_vnd(number, unit, _inventory, expected, _note):
    assert ingestion_service._price_to_vnd(number, unit or "") == expected


def test_the_two_arithmetic_parsers_disagree_on_five_inputs():
    """Pins the size of the problem, so unifying them has a number to drive to zero.

    Kept as one assertion rather than a per-case xfail: the point is the exact set, and a
    per-case marker would quietly pass if a sixth divergence appeared.

    `("3", "tỉ")` is absent because both parsers ignore that spelling identically (3.0 == 3);
    its divergence is against admin_observability's regex, covered separately below.
    """
    disagreements = []
    for number, unit, inventory_expected, ingestion_expected, _note in CASES:
        if inventory_expected is None or inventory_expected != ingestion_expected:
            disagreements.append((number, unit))

    assert disagreements == [
        ("3", "t"),
        ("1.500.000", "VND"),
        ("1.500", "trieu"),
        ("3", "million"),
        ("3", "billion"),
    ]


def test_only_admin_observability_recognises_the_ti_spelling():
    """`tỉ` and `tỷ` are the same word; four of the five sites see only one of them."""
    from backend.routers.admin_observability import _BUDGET_PATTERN
    from backend.services.memory_service import BUDGET_PATTERN
    from backend.services.search_criteria import _VAGUE_AROUND_PATTERN

    assert _BUDGET_PATTERN.search("tầm 3 tỉ") is not None
    assert BUDGET_PATTERN.search("tầm 3 tỉ") is None
    assert _VAGUE_AROUND_PATTERN.search("tầm 3 tỉ") is None


def test_only_memory_service_rejects_the_tr_abbreviation():
    """ "800tr" is ordinary Vietnamese for 800 triệu; long-term memory drops it."""
    from backend.routers.admin_observability import _BUDGET_PATTERN
    from backend.services.memory_service import BUDGET_PATTERN
    from backend.services.search_criteria import _VAGUE_AROUND_PATTERN

    assert BUDGET_PATTERN.search("ngân sách 800tr") is None
    assert _BUDGET_PATTERN.search("ngân sách 800tr") is not None
    assert _VAGUE_AROUND_PATTERN.search("tầm 800tr") is not None
