"""Tests for the observation store, assess/threshold evaluation, and gate drift."""

import pytest

from fmd_seo.assess import assess_all, assess_check, assess_gates
from fmd_seo.brain import load_brain
from fmd_seo.observations import (
    latest_observation, load_observations, record_observation,
)


@pytest.fixture
def brain():
    return load_brain()


@pytest.fixture
def obs_dir(tmp_path):
    return tmp_path / "observations"


def test_observe_validates_missing_field(brain, obs_dir):
    with pytest.raises(ValueError, match="missing recorded field"):
        record_observation(brain, "seo.indexation", {"indexed": 4},
                           fulfillment="console", source="test", directory=obs_dir)


def test_observe_validates_extra_field(brain, obs_dir):
    with pytest.raises(ValueError, match="undeclared field"):
        record_observation(brain, "seo.indexation",
                           {"indexed": 4, "not_indexed": 18, "discovered_not_indexed": 14,
                            "crawled_not_indexed": 2, "bogus": 1},
                           fulfillment="console", source="test", directory=obs_dir)


def test_observe_validates_type(brain, obs_dir):
    with pytest.raises(ValueError, match="must be int"):
        record_observation(brain, "seo.indexation",
                           {"indexed": "four", "not_indexed": 18,
                            "discovered_not_indexed": 14, "crawled_not_indexed": 2},
                           fulfillment="console", source="test", directory=obs_dir)


def test_observe_rejects_bool_for_int(brain, obs_dir):
    # True is an int in Python; the store must still reject it for an int field.
    with pytest.raises(ValueError, match="must be int"):
        record_observation(brain, "seo.indexation",
                           {"indexed": True, "not_indexed": 18,
                            "discovered_not_indexed": 14, "crawled_not_indexed": 2},
                           fulfillment="console", source="test", directory=obs_dir)


def test_observe_and_readback(brain, obs_dir):
    record_observation(brain, "seo.indexation",
                       {"indexed": 4, "not_indexed": 18, "discovered_not_indexed": 14,
                        "crawled_not_indexed": 2},
                       fulfillment="console", source="baseline", directory=obs_dir)
    obs = latest_observation("seo.indexation", obs_dir)
    assert obs.records["not_indexed"] == 18
    assert obs.fulfillment == "console"


def test_assess_fires_critical_on_failing_indexation(brain, obs_dir):
    record_observation(brain, "seo.indexation",
                       {"indexed": 4, "not_indexed": 18, "discovered_not_indexed": 14,
                        "crawled_not_indexed": 2},
                       fulfillment="console", source="baseline", directory=obs_dir)
    _, findings = assess_check(brain, "seo.indexation", obs_dir)
    sevs = {f.severity for f in findings}
    assert "critical" in sevs  # not_indexed >= 8


def test_assess_no_finding_when_healthy(brain, obs_dir):
    record_observation(brain, "seo.indexation",
                       {"indexed": 20, "not_indexed": 0, "discovered_not_indexed": 0,
                        "crawled_not_indexed": 0},
                       fulfillment="console", source="future", directory=obs_dir)
    _, findings = assess_check(brain, "seo.indexation", obs_dir)
    # indexed>=10 and not_indexed<8 -> the info "recovering" finding fires, but no critical
    assert all(f.severity != "critical" for f in findings)


def test_gate1_drift_detected_when_indexation_recovers(brain, obs_dir):
    # state.yaml still declares GATE-1 CLOSED; a recovered observation should
    # surface drift rather than silently disagreeing.
    record_observation(brain, "seo.indexation",
                       {"indexed": 20, "not_indexed": 2, "discovered_not_indexed": 0,
                        "crawled_not_indexed": 0},
                       fulfillment="console", source="future", directory=obs_dir)
    gates = assess_gates(brain, obs_dir)
    g1 = next(g for g in gates if g.gate_id == "GATE-1")
    assert g1.drift is not None
    assert "consecutive" in g1.drift or "open" in g1.drift.lower()


def test_assess_all_ranks_critical_first(brain, obs_dir):
    record_observation(brain, "seo.indexation",
                       {"indexed": 4, "not_indexed": 18, "discovered_not_indexed": 14,
                        "crawled_not_indexed": 2},
                       fulfillment="console", source="b", directory=obs_dir)
    record_observation(brain, "seo.organic_footprint",
                       {"total_keywords": 4, "nonbranded_keywords": 0, "page1_keywords": 0},
                       fulfillment="console", source="b", directory=obs_dir)
    findings = assess_all(brain, obs_dir)
    assert findings  # something fired
    # ranked most-severe first
    ranks = [f.rank for f in findings]
    assert ranks == sorted(ranks, reverse=True)
