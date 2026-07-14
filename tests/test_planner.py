"""Tests for the planner: due ordering, fulfillment labeling, gate-aware priority."""

from fmd_seo.brain import load_brain
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


def test_plan_priority_reflects_closed_gate1(empty_obs):
    brain = load_brain()
    plan = build_plan(brain, has_semrush_key=False, observations_dir=empty_obs)
    # GATE-1 ships CLOSED -> schema must be the first priority line
    assert "Schema" in plan.priority_order[0]


def test_plan_human_checks_sort_first(empty_obs):
    brain = load_brain()
    plan = build_plan(brain, has_semrush_key=False, observations_dir=empty_obs)
    fulfillments = [pc.fulfillment for pc in plan.due]
    if "human" in fulfillments:
        assert fulfillments[0] == "human"
