"""Failure injections proving autonomous paths fail loudly."""

import urllib.error
from datetime import datetime, timezone
import shutil
from pathlib import Path

import pytest

from fmd_seo import dataforseo, killswitch
from fmd_seo.dataforseo import ApiFailure, DataForSeoClient
from fmd_seo.spend import SpendLedger


def test_dataforseo_systemic_failure_counter_survives_client_rebuild(tmp_path, monkeypatch):
    creds = tmp_path / "dataforseo.env"
    creds.write_text(
        "DATAFORSEO_LOGIN=test-login\nDATAFORSEO_PASSWORD=test-password\n",
        encoding="utf-8",
    )
    health_file = tmp_path / "health.json"
    engaged_reasons: list[str] = []

    def fail_request(*_args, **_kwargs):
        raise urllib.error.HTTPError("https://api.test", 402, "balance", {}, None)

    monkeypatch.setattr(dataforseo.urllib.request, "urlopen", fail_request)
    monkeypatch.setattr(killswitch, "engage", lambda reason: engaged_reasons.append(reason))

    for _run in range(2):
        client = DataForSeoClient(
            creds,
            SpendLedger(tmp_path / "spend.json", 10.0, {}),
            systemic_failures_to_kill=2,
            health_file=health_file,
        )
        with pytest.raises(ApiFailure, match="HTTP 402"):
            client._request("/v3/test")

    assert len(engaged_reasons) == 1
    assert "x2" in engaged_reasons[0]


def test_engine_freshness_flags_observations_older_than_twice_cadence(tmp_path):
    from fmd_seo.brain import load_brain
    from fmd_seo.freshness import freshness_records
    from fmd_seo.observations import record_observation

    brain = load_brain()
    observations = tmp_path / "observations"
    record_observation(
        brain,
        "facts.freshness",
        {"days_until_stale": 10},
        fulfillment="engine",
        source="old",
        observed_at="2026-07-29T12:00:00+00:00",
        directory=observations,
    )
    record_observation(
        brain,
        "sync.health",
        {"checks_attempted": 1, "checks_succeeded": 1, "checks_failed": 0},
        fulfillment="engine",
        source="recent",
        observed_at="2026-08-01T12:00:00+00:00",
        directory=observations,
    )

    records = freshness_records(
        brain,
        observations,
        now=datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc),
    )
    assert records == {"stalest_check_age_days": 3, "checks_overdue": 1}


def test_sync_command_records_daily_engine_health_without_provider_key(tmp_path, facts_file):
    from fmd_seo.loop_cli import cmd_sync
    from fmd_seo.observations import latest_observation

    observations = tmp_path / "observations"
    config = {
        "creds_env": str(tmp_path / "missing.env"),
        "paths": {"facts_file": str(facts_file)},
    }

    payload, code = cmd_sync(config, observations_dir=observations)

    assert code == 0
    assert payload["engine_checks"] == ["facts.freshness", "engine.freshness"]
    assert latest_observation("facts.freshness", observations) is not None
    assert latest_observation("engine.freshness", observations) is not None


def test_sync_command_returns_partial_when_some_due_checks_fail(tmp_path, monkeypatch):
    from fmd_seo import freshness, sync
    from fmd_seo.loop_cli import cmd_sync
    from fmd_seo.sync import SyncResult

    monkeypatch.setattr(
        freshness,
        "record_daily_engine_checks",
        lambda *_args, **_kwargs: ["facts.freshness", "engine.freshness"],
    )
    monkeypatch.setattr(
        sync,
        "sync_due",
        lambda *_args, **_kwargs: SyncResult(
            fetched=["seo.organic_footprint"],
            skipped_no_key=[],
            errors={"competitor.authority_gap": "provider failed"},
        ),
    )

    payload, code = cmd_sync(
        {"creds_env": str(tmp_path / "unused")},
        observations_dir=tmp_path / "observations",
    )
    assert payload["fetched"] == ["seo.organic_footprint"]
    assert code == 3


def test_gate1_machine_counts_weekly_clean_readings_and_resets(tmp_path):
    from fmd_seo.gate_manager import update_gate1_state

    state_file = tmp_path / "state.yaml"
    shutil.copy2(
        Path(__file__).resolve().parents[1] / "brain" / "state.yaml",
        state_file,
    )
    rule = {
        "indexed_min": 10,
        "not_indexed_max_exclusive": 8,
        "consecutive_clean_required": 2,
        "minimum_days_between_readings": 7,
    }
    clean = {"indexed": 20, "not_indexed": 2}

    first = update_gate1_state(state_file, rule, clean, "2026-08-01T12:00:00+00:00")
    duplicate = update_gate1_state(state_file, rule, clean, "2026-08-01T13:00:00+00:00")
    second = update_gate1_state(state_file, rule, clean, "2026-08-08T12:00:00+00:00")
    dirty = update_gate1_state(
        state_file,
        rule,
        {"indexed": 4, "not_indexed": 18},
        "2026-08-15T12:00:00+00:00",
    )

    assert (first["state"], first["consecutive_clean_readings"]) == ("CLOSED", 1)
    assert duplicate["consecutive_clean_readings"] == 1
    assert (second["state"], second["consecutive_clean_readings"]) == ("OPEN", 2)
    assert (dirty["state"], dirty["consecutive_clean_readings"]) == ("CLOSED", 0)
