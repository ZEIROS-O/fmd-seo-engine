"""Tests for the brain: loader, restricted evaluator, due-check scheduling."""

from datetime import datetime, timedelta, timezone

import pytest

from fmd_seo import brain as brain_mod
from fmd_seo.brain import (
    BrainError, ExpressionError, due_checks, evaluate, load_brain,
)


# ─────────────────────── restricted evaluator ───────────────────────

def test_evaluate_comparisons_and_bools():
    scope = {"a": 5, "b": 0, "flag": False}
    assert evaluate("a > 3", scope) is True
    assert evaluate("a > 3 and b == 0", scope) is True
    assert evaluate("a < 3 or b == 0", scope) is True
    assert evaluate("flag == false", scope) is True
    assert evaluate("a >= 8 and flag == false", scope) is False


def test_evaluate_literals_true_false_none():
    assert evaluate("x == true", {"x": True}) is True
    assert evaluate("x == none", {"x": None}) is True


def test_evaluate_rejects_calls_and_attributes():
    with pytest.raises(ExpressionError):
        evaluate("__import__('os')", {})
    with pytest.raises(ExpressionError):
        evaluate("a.foo", {"a": 1})
    with pytest.raises(ExpressionError):
        evaluate("a[0]", {"a": [1]})


def test_evaluate_unknown_field_raises_not_defaults():
    # A missing field must crash, never silently make the threshold False.
    with pytest.raises(ExpressionError):
        evaluate("missing > 0", {"present": 1})


# ─────────────────────────── loader ───────────────────────────

def _write_brain(tmp_path, checks_body, state_body=None):
    (tmp_path / "checks.yaml").write_text(checks_body, encoding="utf-8")
    (tmp_path / "state.yaml").write_text(
        state_body or "schema_version: 1\nsite: {domain: x.com}\ngates: {}\n",
        encoding="utf-8")
    (tmp_path / "thesis.md").write_text("# thesis\n", encoding="utf-8")
    (tmp_path / "gates.yaml").write_text(
        "schema_version: 1\ngates: {}\n",
        encoding="utf-8",
    )
    return load_brain(tmp_path)


def test_loader_rejects_threshold_referencing_unrecorded_field(tmp_path):
    body = """\
schema_version: 1
checks:
  - id: t.one
    domain: seo
    title: t
    cadence: weekly
    cost: free
    method: {kind: http, run: "do it"}
    records:
      - {name: a, type: int}
    thresholds:
      - {expr: "b > 0", severity: high, finding: f, action: act}
    why: because
"""
    with pytest.raises(BrainError, match="unrecorded field"):
        _write_brain(tmp_path, body)


def test_loader_rejects_duplicate_check_ids(tmp_path):
    body = """\
schema_version: 1
checks:
  - {id: dup, domain: seo, title: t, cadence: weekly, cost: free, method: {kind: http, run: r}, records: [{name: a, type: int}], thresholds: [], why: w}
  - {id: dup, domain: seo, title: t, cadence: weekly, cost: free, method: {kind: http, run: r}, records: [{name: a, type: int}], thresholds: [], why: w}
"""
    with pytest.raises(BrainError, match="duplicate"):
        _write_brain(tmp_path, body)


def test_real_brain_loads_clean():
    # The shipped brain must parse: every threshold field must be recorded.
    b = load_brain()
    assert b.check("seo.indexation")
    assert b.gate_state("GATE-1") in ("OPEN", "CLOSED")


def test_gate_rules_load_from_single_registry():
    b = load_brain()
    assert b.gate_rule("GATE-1") == {
        "indexed_min": 10,
        "not_indexed_max_exclusive": 8,
        "consecutive_clean_required": 2,
        "minimum_days_between_readings": 7,
    }


# ─────────────────────── due scheduling ───────────────────────

def test_never_observed_check_is_always_due():
    b = load_brain()
    due = due_checks(b, last_seen={})
    ids = {c.id for c, _ in due}
    assert "seo.indexation" in ids
    # per_draft checks are event-driven, never time-due
    assert "blog.cannibalization" not in ids


def test_recent_observation_not_due_until_cadence_elapses():
    b = load_brain()
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(days=1)).isoformat()
    due = due_checks(b, last_seen={"seo.indexation": fresh}, now=now)
    ids = {c.id for c, _ in due}
    assert "seo.indexation" not in ids  # weekly, observed 1d ago


def test_stale_observation_becomes_due():
    b = load_brain()
    now = datetime.now(timezone.utc)
    stale = (now - timedelta(days=10)).isoformat()
    due = due_checks(b, last_seen={"seo.indexation": stale}, now=now)
    ids = {c.id for c, _ in due}
    assert "seo.indexation" in ids  # weekly, observed 10d ago
