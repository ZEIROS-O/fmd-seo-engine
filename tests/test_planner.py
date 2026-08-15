"""Tests for the planner: due ordering, fulfillment labeling, gate-aware priority."""

from pathlib import Path

from fmd_seo import planner
from fmd_seo.brain import load_brain
from fmd_seo.loop_cli import cmd_beat, cmd_brief
from fmd_seo.planner import build_plan
import pytest


@pytest.fixture
def empty_obs(tmp_path):
    return tmp_path / "obs"


def test_plan_labels_console_check_human(empty_obs):
    brain = load_brain()
    plan = build_plan(brain, has_semrush_key=False, observations_dir=empty_obs)
    idx = next(pc for pc in plan.due if pc.check_id == "seo.indexation")
    assert idx.fulfillment == "human"


def test_plan_mcp_check_is_session_without_key(empty_obs):
    brain = load_brain()
    plan = build_plan(brain, has_semrush_key=False, observations_dir=empty_obs)
    auth = next(pc for pc in plan.due if pc.check_id == "competitor.authority_gap")
    assert auth.fulfillment == "session"
    assert auth.api_reports == []


def test_plan_mcp_check_becomes_engine_api_with_key(empty_obs):
    brain = load_brain()
    plan = build_plan(brain, has_semrush_key=True, observations_dir=empty_obs)
    auth = next(pc for pc in plan.due if pc.check_id == "competitor.authority_gap")
    assert auth.fulfillment == "engine_api"
    assert "backlinks_overview" in auth.api_reports


def test_plan_ga4_check_becomes_engine_api_when_available(empty_obs):
    brain = load_brain()
    plan = build_plan(
        brain,
        has_semrush_key=False,
        has_ga4=True,
        observations_dir=empty_obs,
    )
    traffic = next(pc for pc in plan.due if pc.check_id == "analytics.traffic")
    assert traffic.fulfillment == "engine_api"
    assert traffic.api_reports == ["ga4:runReport"]


def test_plan_ga4_check_is_human_when_unavailable(empty_obs):
    brain = load_brain()
    plan = build_plan(
        brain,
        has_semrush_key=False,
        has_ga4=False,
        observations_dir=empty_obs,
    )
    traffic = next(pc for pc in plan.due if pc.check_id == "analytics.traffic")
    assert traffic.fulfillment == "human"


def test_plan_query_footprint_uses_gsc_search_analytics(empty_obs):
    brain = load_brain()
    plan = build_plan(
        brain,
        has_semrush_key=True,
        has_gsc=True,
        observations_dir=empty_obs,
    )
    footprint = next(pc for pc in plan.due if pc.check_id == "seo.query_footprint")
    assert footprint.fulfillment == "engine_api"
    assert footprint.api_reports == ["gsc:searchAnalytics.query"]


def test_beat_derives_ga4_availability_from_property_and_key(tmp_path):
    key_path = tmp_path / "google.json"
    key_path.write_text("{}", encoding="utf-8")
    configured, code = cmd_beat({
        "ga4": {
            "key_path": str(key_path),
            "property_id": "541970582",
        },
    })
    assert code == 0
    traffic = next(
        item for item in configured["due"]
        if item["check_id"] == "analytics.traffic"
    )
    assert traffic["fulfillment"] == "engine_api"

    briefing, code = cmd_brief({
        "ga4": {
            "key_path": str(key_path),
            "property_id": "541970582",
        },
    })
    assert code == 0
    traffic = next(
        item for item in briefing["due_now"]
        if item["check_id"] == "analytics.traffic"
    )
    assert traffic["fulfillment"] == "engine_api"

    incomplete, code = cmd_beat({
        "ga4": {"key_path": str(key_path)},
    })
    assert code == 0
    traffic = next(
        item for item in incomplete["due"]
        if item["check_id"] == "analytics.traffic"
    )
    assert traffic["fulfillment"] == "human"

    missing_key, code = cmd_beat({
        "ga4": {
            "key_path": str(tmp_path / "missing.json"),
            "property_id": "541970582",
        },
    })
    assert code == 0
    traffic = next(
        item for item in missing_key["due"]
        if item["check_id"] == "analytics.traffic"
    )
    assert traffic["fulfillment"] == "human"

    directory_key, code = cmd_beat({
        "ga4": {
            "key_path": str(tmp_path),
            "property_id": "541970582",
        },
    })
    assert code == 0
    traffic = next(
        item for item in directory_key["due"]
        if item["check_id"] == "analytics.traffic"
    )
    assert traffic["fulfillment"] == "human"


def test_plan_priority_reflects_closed_gate1(empty_obs):
    brain = load_brain()
    plan = build_plan(brain, has_semrush_key=False, observations_dir=empty_obs)
    # GATE-1 ships CLOSED -> the priority list is the gate-respecting work order,
    # none of which adds a URL. Reordered 2026-08-03: review velocity leads,
    # because the ring's radius is the binding constraint (T5).
    assert plan.priority_order
    assert "Review velocity" in plan.priority_order[0]
    assert "GBP configuration audit" in plan.priority_order[1]
    assert any("reassess GATE-1" in line for line in plan.priority_order)


def test_priority_order_is_exactly_the_brain_file_for_the_current_gate_state(empty_obs):
    """The planner must not hold a second copy of the order that can drift."""
    brain = load_brain()
    plan = build_plan(brain, has_semrush_key=False, observations_dir=empty_obs)
    state = brain.gate_state("GATE-1")

    expected = [entry["label"] for entry in brain.priorities
                if entry["gate"]["GATE-1"] == state]

    assert expected, f"brain/priorities.yaml has no entries for GATE-1 {state}"
    assert plan.priority_order == expected


def test_planner_module_holds_no_priority_literal():
    """S0.1: the ordering lives in brain/priorities.yaml, nowhere else."""
    source = Path(planner.__file__).read_text(encoding="utf-8")

    assert "GATE1_CLOSED_PRIORITY" not in source
    assert "GATE1_OPEN_PRIORITY" not in source
    assert "Entity decontamination" not in source
    assert "Review velocity" not in source


def test_open_gate1_priority_comes_from_the_same_file(empty_obs):
    brain = load_brain()
    brain.state["gates"]["GATE-1"] = dict(brain.gates["GATE-1"], state="OPEN")
    plan = build_plan(brain, has_semrush_key=False, observations_dir=empty_obs)

    expected = [entry["label"] for entry in brain.priorities
                if entry["gate"]["GATE-1"] == "OPEN"]

    assert expected
    assert plan.priority_order == expected
    assert plan.priority_order != [
        entry["label"] for entry in brain.priorities
        if entry["gate"]["GATE-1"] == "CLOSED"
    ]


def test_plan_human_checks_sort_first(empty_obs):
    brain = load_brain()
    plan = build_plan(brain, has_semrush_key=False, observations_dir=empty_obs)
    fulfillments = [pc.fulfillment for pc in plan.due]
    if "human" in fulfillments:
        assert fulfillments[0] == "human"
