"""Tests for the planner: due ordering, fulfillment labeling, gate-aware priority."""

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
    # none of which adds a URL. Entity decontamination leads (schema now largely done).
    assert plan.priority_order
    assert "Entity decontamination" in plan.priority_order[0]
    assert any("reassess GATE-1" in line for line in plan.priority_order)


def test_plan_human_checks_sort_first(empty_obs):
    brain = load_brain()
    plan = build_plan(brain, has_semrush_key=False, observations_dir=empty_obs)
    fulfillments = [pc.fulfillment for pc in plan.due]
    if "human" in fulfillments:
        assert fulfillments[0] == "human"
