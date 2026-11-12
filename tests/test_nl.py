"""Tests for the natural-language layer (rules engine + validation).

The LLM path is exercised through `_validate`, which is what guards against a
model inventing fields or returning wrong types.
"""

from __future__ import annotations

import pytest

from gsa_wrap import nl


# --------------------------------------------------------------------------
# rules engine — the always-available fallback
# --------------------------------------------------------------------------
def test_negation_binds_per_clause_not_globally():
    """'disable autoscroll' must not turn off the other two settings."""
    p = nl.interpret("turn on blacklist and dupecheck, disable autoscroll", prefer="rules")
    assert p.updates["misc::blacklist on"] is True
    assert p.updates["misc::global send dupecheck"] is True
    assert p.updates["misc::autoscroll"] is False


def test_number_before_label():
    p = nl.interpret("10 threads, timeout 300", prefer="rules")
    assert p.updates["misc::max threads"] == 10
    assert p.updates["misc::timeout"] == 300


def test_number_after_label():
    p = nl.interpret("set threads to 25 and timeout 300", prefer="rules")
    assert p.updates["misc::max threads"] == 25
    assert p.updates["misc::timeout"] == 300


def test_scheduler_fields():
    p = nl.interpret("max projects 10, max runtime 60", prefer="rules")
    assert p.updates["scheduler::max projects"] == 10
    assert p.updates["scheduler::max runtime"] == 60


def test_skip_is_negation():
    p = nl.interpret("skip dupecheck", prefer="rules")
    assert p.updates["misc::global send dupecheck"] is False


def test_no_match_is_empty_not_wrong():
    p = nl.interpret("do something clever", prefer="rules")
    assert p.updates == {}


def test_rules_only_emit_real_refs():
    from gsa_wrap.schema import SCHEMA
    p = nl.interpret("threads 5 timeout 60 blacklist dupecheck autoscroll", prefer="rules")
    for ref in p.updates:
        assert ref in SCHEMA, f"rules produced non-schema ref {ref}"


# --------------------------------------------------------------------------
# validation of (simulated) LLM output
# --------------------------------------------------------------------------
def test_validate_drops_invented_refs():
    p = nl._validate({
        "updates": {"misc::max threads": 15, "misc::totally made up": 1},
        "explanation": "x",
    }, engine="llm")
    assert p.updates == {"misc::max threads": 15}
    assert any("made up" in u for u in p.unknown)


def test_validate_rejects_out_of_range():
    p = nl._validate({"updates": {"misc::max threads": 9999}}, engine="llm")
    assert p.updates == {}
    assert p.notes


def test_validate_rejects_bad_allowed_value():
    p = nl._validate({"updates": {"misc::scaling mode": 7}}, engine="llm")
    assert p.updates == {}


def test_validate_keeps_good_values():
    p = nl._validate({
        "updates": {"misc::timeout": 90, "scheduler::send sites": True},
        "explanation": "ok",
        "notes": ["n"], "unknown": ["u"],
    }, engine="llm")
    assert p.updates == {"misc::timeout": 90, "scheduler::send sites": True}
    assert p.engine == "llm"


# --------------------------------------------------------------------------
# explain
# --------------------------------------------------------------------------
def test_explain_returns_guidance():
    e = nl.explain("misc::max threads")
    assert e["help"] and e["guidance"]
    assert e["range"] == [1, 200]
    assert e["confidence"] == "proven"


def test_explain_unknown_ref():
    with pytest.raises(KeyError):
        nl.explain("misc::nope")


def test_llm_schema_is_serialisable_and_small():
    import json
    msgs = nl.build_messages("hi")
    assert msgs[0]["role"] == "system"
    payload = json.loads(msgs[1]["content"].split("\n\nREQUEST:")[0])
    assert len(payload["schema"]) > 50
    # every row must be self-describing for the model
    for row in payload["schema"]:
        assert row["ref"] and row["help"] and row["type"]
