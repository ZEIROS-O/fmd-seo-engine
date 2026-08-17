"""Failure injections proving autonomous paths fail loudly."""

import urllib.error
from datetime import datetime, timezone
import shutil
from pathlib import Path

import pytest
import yaml

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


def test_engine_freshness_counts_stale_and_never_observed_scheduled_checks(tmp_path):
    from fmd_seo.brain import load_brain
    from fmd_seo.freshness import freshness_records, freshness_report
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
        {
            "checks_attempted": 1,
            "checks_succeeded": 1,
            "checks_failed": 0,
            "source_status": "semrush=ok;ga4=not_selected;gbp=not_selected;site=not_selected",
        },
        fulfillment="engine",
        source="recent",
        observed_at="2026-08-01T12:00:00+00:00",
        directory=observations,
    )

    now = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)
    records = freshness_records(brain, observations, now=now)
    report = freshness_report(brain, observations, now=now)

    # facts.freshness is daily and 3 days old — stale past the one-day grace.
    # Every other scheduled check in the live registry has produced nothing at
    # all here, and a never-observed check is overdue: the engine does not
    # assume an unmeasured check is passing. freshness_records used to skip
    # those entirely and report 1.
    observed = {"facts.freshness", "sync.health"}
    never_observed = sorted(
        check.id for check in brain.checks
        if check.execution_mode == "scheduled"
        and check.cadence_days is not None
        and check.id not in observed | {"engine.freshness"}
    )
    assert never_observed  # the registry must still contain some, or this proves nothing
    assert records["stalest_check_age_days"] == 3
    assert records["checks_overdue"] == 1 + len(never_observed)
    # The two surfaces are one selector now; they cannot drift apart again.
    assert report["checks_overdue"] == records["checks_overdue"]
    assert report["never_observed"] == never_observed


def test_tick_records_daily_engine_health_without_provider_key(tmp_path, facts_file):
    from fmd_seo.loop_cli import cmd_tick
    from fmd_seo.observations import latest_observation

    observations = tmp_path / "observations"
    config = {
        "creds_env": str(tmp_path / "missing.env"),
        "paths": {"facts_file": str(facts_file)},
    }

    payload, code = cmd_tick(config, observations_dir=observations)

    assert code == 0
    assert payload["engine_checks"] == ["facts.freshness", "engine.freshness"]
    assert latest_observation("facts.freshness", observations) is not None
    assert latest_observation("engine.freshness", observations) is not None


def test_sync_command_returns_partial_when_some_due_checks_fail(tmp_path, monkeypatch):
    from fmd_seo import sync
    from fmd_seo.loop_cli import cmd_sync
    from fmd_seo.sync import SyncResult

    monkeypatch.setattr(
        sync,
        "sync_due",
        lambda *_args, **_kwargs: SyncResult(
            fetched=["competitor.authority_gap"],
            skipped_no_key=[],
            errors={"competitor.authority_gap": "provider failed"},
        ),
    )

    payload, code = cmd_sync(
        {"creds_env": str(tmp_path / "unused")},
        observations_dir=tmp_path / "observations",
    )
    assert payload["fetched"] == ["competitor.authority_gap"]
    assert code == 3


def test_sync_command_includes_successful_ga4_fetch(tmp_path, monkeypatch):
    from fmd_seo import ga4, gbp, site_facts, sync
    from fmd_seo.loop_cli import cmd_sync
    from fmd_seo.sync import SyncResult

    monkeypatch.setattr(
        sync,
        "sync_due",
        lambda *_args, **_kwargs: SyncResult([], [], {}),
    )
    monkeypatch.setattr(
        gbp,
        "sync_if_due",
        lambda *_args, **_kwargs: {"status": "skipped_config"},
    )
    monkeypatch.setattr(
        site_facts,
        "sync_public_facts",
        lambda *_args, **_kwargs: {"status": "skipped_config"},
    )
    monkeypatch.setattr(
        ga4,
        "sync_if_due",
        lambda *_args, **_kwargs: {
            "status": "fetched",
            "records": {"sessions": 1},
        },
    )

    payload, code = cmd_sync({}, observations_dir=tmp_path / "observations")

    assert payload["ga4"]["status"] == "fetched"
    assert payload["fetched"] == ["analytics.traffic"]
    # A GA4 success does not launder the two unconfigured providers: an absent
    # credential is a recorded failure, so the run is partial, not healthy.
    assert set(payload["errors"]) == {"gbp.performance", "site.facts_drift"}
    assert code == 3


def test_sync_command_surfaces_ga4_failure_in_health(tmp_path, monkeypatch):
    from fmd_seo import ga4, gbp, site_facts, sync
    from fmd_seo.loop_cli import cmd_sync
    from fmd_seo.sync import SyncResult

    monkeypatch.setattr(
        sync,
        "sync_due",
        lambda *_args, **_kwargs: SyncResult([], [], {}),
    )
    monkeypatch.setattr(
        gbp,
        "sync_if_due",
        lambda *_args, **_kwargs: {"status": "skipped_config"},
    )
    monkeypatch.setattr(
        site_facts,
        "sync_public_facts",
        lambda *_args, **_kwargs: {"status": "skipped_config"},
    )
    monkeypatch.setattr(
        ga4,
        "sync_if_due",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("GA4 denied")),
    )

    payload, code = cmd_sync({}, observations_dir=tmp_path / "observations")

    assert payload["ga4"] == {"status": "failed", "error": "GA4 denied"}
    assert payload["errors"]["analytics.traffic"] == "GA4 denied"
    assert code == 4


def test_missing_credential_is_a_recorded_failure_not_a_silent_skip(tmp_path, monkeypatch):
    """Semrush has no key, GA4 and site succeed, GBP is not due.

    The old accounting counted only fetched + errors, so an absent credential
    landed in neither and a fully unconfigured run exited 0 with no sync.health
    observation written at all -- the exact "zero attempts reads as healthy"
    state this check exists to eliminate.
    """
    from fmd_seo import ga4, gbp, site_facts, sync
    from fmd_seo.assess import assess_check
    from fmd_seo.brain import load_brain
    from fmd_seo.loop_cli import cmd_sync
    from fmd_seo.observations import latest_observation, load_observations
    from fmd_seo.sync import SyncResult

    monkeypatch.setattr(sync, "sync_due", lambda *a, **k: SyncResult(
        fetched=[], skipped_no_key=["market.demand"], errors={},
    ))
    monkeypatch.setattr(gbp, "sync_if_due", lambda *a, **k: {
        "status": "not_due", "observed_at": "2026-08-15T00:00:00+00:00",
    })
    monkeypatch.setattr(site_facts, "sync_public_facts", lambda *a, **k: {
        "status": "fetched", "url": "https://example.test", "fact_mismatches": 0,
        "surfaces": [],
    })
    monkeypatch.setattr(ga4, "sync_if_due", lambda *a, **k: {
        "status": "fetched", "records": {"sessions": 1},
    })
    observations = tmp_path / "observations"

    payload, code = cmd_sync({}, observations_dir=observations)

    assert payload["errors"] == {"market.demand": "no SEMRUSH_API_KEY present"}
    assert code == 3

    assert len(load_observations("sync.health", observations)) == 1
    health = latest_observation("sync.health", observations)
    assert health.records == {
        "checks_attempted": 3,
        "checks_succeeded": 2,
        "checks_failed": 1,
        "source_status": "semrush=no_credential;ga4=ok;gbp=not_due;site=ok",
    }

    _, findings = assess_check(load_brain(), "sync.health", observations)
    assert any(f.severity == "critical" for f in findings)


def test_sync_health_is_written_even_when_every_source_is_not_due(tmp_path, monkeypatch):
    """An all-not_due day still has to satisfy sync.health's daily cadence."""
    from fmd_seo import ga4, gbp, site_facts, sync
    from fmd_seo.loop_cli import cmd_sync
    from fmd_seo.observations import latest_observation
    from fmd_seo.sync import SyncResult

    monkeypatch.setattr(sync, "sync_due", lambda *a, **k: SyncResult([], [], {}))
    for module in (gbp, ga4):
        monkeypatch.setattr(module, "sync_if_due", lambda *a, **k: {
            "status": "not_due", "observed_at": "2026-08-15T00:00:00+00:00",
        })
    monkeypatch.setattr(site_facts, "sync_public_facts", lambda *a, **k: {
        "status": "not_due", "observed_at": "2026-08-15T00:00:00+00:00",
    })
    observations = tmp_path / "observations"

    payload, code = cmd_sync({}, observations_dir=observations)

    assert code == 0
    assert payload["errors"] == {}
    health = latest_observation("sync.health", observations)
    assert health is not None
    assert health.records["checks_attempted"] == 0
    assert health.records["source_status"] == (
        "semrush=not_due;ga4=not_due;gbp=not_due;site=not_due"
    )


def test_sync_note_never_records_a_credential(tmp_path, monkeypatch):
    """bin/fmd-seo-cron commits the observation, so an echoed key is permanent."""
    from fmd_seo import ga4, gbp, site_facts, sync
    from fmd_seo.loop_cli import cmd_sync, redact_secrets
    from fmd_seo.observations import latest_observation
    from fmd_seo.sync import SyncResult

    leak = (
        "HTTP 403 for https://api.test/v3?key=sk-live-abcdef123456&type=phrase_this "
        "(Authorization: Bearer ya29.a0AfB_secretvalue) for svc@fmd-seo.iam.test"
    )
    monkeypatch.setattr(sync, "sync_due", lambda *a, **k: SyncResult(
        fetched=[], skipped_no_key=[], errors={"market.demand": leak},
    ))
    for module in (gbp, ga4):
        monkeypatch.setattr(module, "sync_if_due", lambda *a, **k: {"status": "not_due"})
    monkeypatch.setattr(site_facts, "sync_public_facts", lambda *a, **k: {"status": "not_due"})
    observations = tmp_path / "observations"

    cmd_sync({}, observations_dir=observations)

    note = latest_observation("sync.health", observations).note
    for secret in ("sk-live-abcdef123456", "ya29.a0AfB_secretvalue", "svc@fmd-seo.iam.test"):
        assert secret not in note
    # Redaction must not eat the diagnosis along with the credential.
    assert "HTTP 403" in note and "phrase_this" in note

    assert redact_secrets("no secrets here") == "no secrets here"
    assert redact_secrets('{"api_key": "abc123"}') == '{"api_key": "[REDACTED]"}'


def test_semrush_blowup_does_not_abort_the_other_three_sources(tmp_path, monkeypatch):
    """sync_due raises outside its own per-check guard, so cmd_sync must guard it.

    The SemrushClient constructor and the brain.state["site"]["domain"] lookup
    both sit above sync_due's per-check try/except. An unguarded call let a
    Semrush-side error abort cmd_sync before gbp/site/ga4 ran and suppressed
    the sync.health observation entirely -- the loop's only failure signal.
    """
    from fmd_seo import ga4, gbp, site_facts, sync
    from fmd_seo.loop_cli import cmd_sync
    from fmd_seo.observations import latest_observation

    ran: list[str] = []

    def _boom(*_args, **_kwargs):
        raise KeyError("site")

    monkeypatch.setattr(sync, "sync_due", _boom)
    monkeypatch.setattr(gbp, "sync_if_due", lambda *a, **k: ran.append("gbp") or {
        "status": "not_due", "observed_at": "2026-08-15T00:00:00+00:00",
    })
    monkeypatch.setattr(site_facts, "sync_public_facts", lambda *a, **k: ran.append("site") or {
        "status": "fetched", "url": "https://example.test", "fact_mismatches": 0,
        "surfaces": [],
    })
    monkeypatch.setattr(ga4, "sync_if_due", lambda *a, **k: ran.append("ga4") or {
        "status": "fetched", "records": {"sessions": 1},
    })
    observations = tmp_path / "observations"

    payload, code = cmd_sync({}, observations_dir=observations)

    assert ran == ["gbp", "site", "ga4"]
    assert set(payload["errors"]) == {
        "competitor.authority_gap", "market.demand", "topics.related_clusters",
    }
    assert payload["fetched"] == ["site.facts_drift", "analytics.traffic"]
    health = latest_observation("sync.health", observations)
    assert health is not None
    assert health.records["checks_failed"] == 3
    assert code == 3


def test_gate1_machine_counts_weekly_clean_readings_and_resets(tmp_path):
    from fmd_seo.gate_manager import update_gate1_state

    state_file = tmp_path / "state.yaml"
    shutil.copy2(
        Path(__file__).resolve().parents[1] / "brain" / "state.yaml",
        state_file,
    )
    # Copying the real file exercises the true state.yaml shape, but its live
    # `last_counted_at` would make these fixed 2026-08-01 readings fail the
    # minimum_days_between_readings gap check. Drop it; the test supplies its own
    # timeline. See _clear_live_gate_timestamps in test_preflight_and_cli.py.
    state_file.write_text("".join(
        ln for ln in state_file.read_text(encoding="utf-8").splitlines(keepends=True)
        if "last_counted_at:" not in ln
    ), encoding="utf-8")
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


def test_gate1_update_does_not_depend_on_gate2_order(tmp_path):
    from fmd_seo.gate_manager import update_gate1_state

    state_file = tmp_path / "state.yaml"
    state_file.write_text("""\
schema_version: 1
gates:
  GATE-2:
    state: CLOSED
  GATE-1:
    state: CLOSED
    reason: "old"
    consecutive_clean_readings: 0
    last_counted_at: null
""", encoding="utf-8")
    result = update_gate1_state(
        state_file,
        {
            "indexed_min": 10,
            "not_indexed_max_exclusive": 8,
            "consecutive_clean_required": 2,
            "minimum_days_between_readings": 7,
        },
        {"indexed": 20, "not_indexed": 2},
        "2026-08-02T12:00:00+00:00",
    )

    assert result["consecutive_clean_readings"] == 1
    assert yaml.safe_load(state_file.read_text())["gates"]["GATE-2"]["state"] == "CLOSED"
