"""Tests for the observation store, assess/threshold evaluation, and gate drift."""

import json

import pytest

from fmd_seo.assess import assess_all, assess_check, assess_gates
from fmd_seo.brain import Brain, Check, load_brain
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
                            "crawled_not_indexed": 2, "unknown_to_google": 0,
                            "inspected_ok": 22, "bogus": 1},
                           fulfillment="console", source="test", directory=obs_dir)


def test_observe_validates_type(brain, obs_dir):
    with pytest.raises(ValueError, match="must be int"):
        record_observation(brain, "seo.indexation",
                           {"indexed": "four", "not_indexed": 18,
                            "discovered_not_indexed": 14, "crawled_not_indexed": 2,
                            "unknown_to_google": 0,
                            "inspected_ok": 22},
                           fulfillment="console", source="test", directory=obs_dir)


def test_observe_rejects_bool_for_int(brain, obs_dir):
    # True is an int in Python; the store must still reject it for an int field.
    with pytest.raises(ValueError, match="must be int"):
        record_observation(brain, "seo.indexation",
                           {"indexed": True, "not_indexed": 18,
                            "discovered_not_indexed": 14, "crawled_not_indexed": 2,
                            "unknown_to_google": 0,
                            "inspected_ok": 22},
                           fulfillment="console", source="test", directory=obs_dir)


def test_observe_validates_float_fields(obs_dir):
    float_check = Check(
        id="aeo.share_of_voice",
        domain="aeo",
        title="AEO share of voice",
        cadence="monthly",
        cost="free",
        method_kind="agent",
        method_run="measure",
        records=[{"name": "ai_sov_percent", "type": "float"}],
        thresholds=[],
        why="test",
    )
    float_brain = Brain(checks=[float_check], state={})

    with pytest.raises(ValueError, match="must be float"):
        record_observation(
            float_brain,
            "aeo.share_of_voice",
            {"ai_sov_percent": "1.9"},
            fulfillment="agent",
            source="test",
            directory=obs_dir,
        )

    path = record_observation(
        float_brain,
        "aeo.share_of_voice",
        {"ai_sov_percent": 1.9},
        fulfillment="agent",
        source="test",
        directory=obs_dir,
    )
    assert path.exists()


def test_observe_and_readback(brain, obs_dir):
    record_observation(brain, "seo.indexation",
                       {"indexed": 4, "not_indexed": 18, "discovered_not_indexed": 14,
                        "crawled_not_indexed": 2, "unknown_to_google": 0,
                        "inspected_ok": 22},
                       fulfillment="console", source="baseline", directory=obs_dir)
    obs = latest_observation("seo.indexation", obs_dir)
    assert obs.records["not_indexed"] == 18
    assert obs.fulfillment == "console"


def test_observe_same_second_preserves_both_records(brain, obs_dir):
    stamp = "2026-08-01T12:00:00+00:00"
    first = record_observation(
        brain,
        "facts.freshness",
        {"days_until_stale": 10},
        fulfillment="engine",
        source="first",
        observed_at=stamp,
        directory=obs_dir,
    )
    second = record_observation(
        brain,
        "facts.freshness",
        {"days_until_stale": 9},
        fulfillment="engine",
        source="second",
        observed_at=stamp,
        directory=obs_dir,
    )

    assert first != second
    assert len(list((obs_dir / "facts.freshness").glob("*.json"))) == 2
    assert [obs.source for obs in load_observations("facts.freshness", obs_dir)] == [
        "first",
        "second",
    ]


def test_assess_fires_critical_on_failing_indexation(brain, obs_dir):
    record_observation(brain, "seo.indexation",
                       {"indexed": 4, "not_indexed": 18, "discovered_not_indexed": 14,
                        "crawled_not_indexed": 2, "unknown_to_google": 0,
                        "inspected_ok": 22},
                       fulfillment="console", source="baseline", directory=obs_dir)
    _, findings = assess_check(brain, "seo.indexation", obs_dir)
    sevs = {f.severity for f in findings}
    assert "critical" in sevs  # not_indexed >= 8


def test_assess_no_finding_when_healthy(brain, obs_dir):
    record_observation(brain, "seo.indexation",
                       {"indexed": 20, "not_indexed": 0, "discovered_not_indexed": 0,
                        "crawled_not_indexed": 0, "unknown_to_google": 0,
                        "inspected_ok": 20},
                       fulfillment="console", source="future", directory=obs_dir)
    _, findings = assess_check(brain, "seo.indexation", obs_dir)
    # indexed>=10 and not_indexed<8 -> the info "recovering" finding fires, but no critical
    assert all(f.severity != "critical" for f in findings)


def test_gate1_drift_detected_when_indexation_recovers(brain, obs_dir):
    # state.yaml still declares GATE-1 CLOSED; a recovered observation should
    # surface drift rather than silently disagreeing.
    record_observation(brain, "seo.indexation",
                       {"indexed": 20, "not_indexed": 2, "discovered_not_indexed": 0,
                        "crawled_not_indexed": 0, "unknown_to_google": 0,
                        "inspected_ok": 22},
                       fulfillment="console", source="future", directory=obs_dir)
    gates = assess_gates(brain, obs_dir)
    g1 = next(g for g in gates if g.gate_id == "GATE-1")
    assert g1.drift is not None
    assert "consecutive" in g1.drift or "open" in g1.drift.lower()


def test_assess_all_ranks_critical_first(brain, obs_dir):
    record_observation(brain, "seo.indexation",
                       {"indexed": 4, "not_indexed": 18, "discovered_not_indexed": 14,
                        "crawled_not_indexed": 2, "unknown_to_google": 0,
                        "inspected_ok": 22},
                       fulfillment="console", source="b", directory=obs_dir)
    record_observation(brain, "seo.query_footprint",
                       {"total_queries": 4, "nonbranded_queries": 3,
                        "queries_pos_1_3": 0, "queries_pos_4_10": 1,
                        "queries_pos_11_20": 1, "impressions_pos_1_3": 0,
                        "impressions_pos_4_10": 12, "impressions_pos_11_20": 8,
                        "impressions_pos_4_20": 20,
                        "ctr_leak_queries": 1, "pages_with_impressions": 2,
                        "pages_in_sitemap": 24},
                       fulfillment="console", source="b", directory=obs_dir)
    findings = assess_all(brain, obs_dir)
    assert findings  # something fired
    # ranked most-severe first
    ranks = [f.rank for f in findings]
    assert ranks == sorted(ranks, reverse=True)


def test_assess_all_survives_one_malformed_observation(brain, obs_dir):
    record_observation(
        brain,
        "seo.indexation",
        {
            "indexed": 4,
            "not_indexed": 18,
            "discovered_not_indexed": 14,
            "crawled_not_indexed": 2,
            "unknown_to_google": 0,
            "inspected_ok": 22,
        },
        fulfillment="console",
        source="valid",
        directory=obs_dir,
    )
    broken_dir = obs_dir / "seo.query_footprint"
    broken_dir.mkdir(parents=True)
    (broken_dir / "20260801T120000+0000.json").write_text(
        json.dumps({
            "check_id": "seo.query_footprint",
            "observed_at": "2026-08-01T12:00:00+00:00",
            "fulfillment": "engine_api",
            "records": {"total_queries": 4, "nonbranded_queries": 3},
            "source": "broken fixture",
            "note": "",
        }),
        encoding="utf-8",
    )

    findings = assess_all(brain, obs_dir)
    critical_ids = [finding.check_id for finding in findings if finding.severity == "critical"]
    assert "seo.indexation" in critical_ids
    assert "seo.query_footprint" in critical_ids
    synthetic = next(f for f in findings if f.check_id == "seo.query_footprint")
    assert "evaluation failed" in synthetic.finding.lower()


def test_assess_all_survives_invalid_observation_json(brain, obs_dir):
    record_observation(
        brain,
        "seo.indexation",
        {
            "indexed": 4,
            "not_indexed": 18,
            "discovered_not_indexed": 14,
            "crawled_not_indexed": 2,
            "unknown_to_google": 0,
            "inspected_ok": 22,
        },
        fulfillment="console",
        source="valid",
        directory=obs_dir,
    )
    broken_dir = obs_dir / "seo.query_footprint"
    broken_dir.mkdir(parents=True)
    (broken_dir / "20260801T120000+0000.json").write_text(
        "{not-json\n",
        encoding="utf-8",
    )

    findings = assess_all(brain, obs_dir)

    critical_ids = [finding.check_id for finding in findings if finding.severity == "critical"]
    assert "seo.indexation" in critical_ids
    assert "seo.query_footprint" in critical_ids
