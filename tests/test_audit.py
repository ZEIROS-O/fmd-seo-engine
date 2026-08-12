"""Read-only integrity audit tests.

Every fixture below creates its own engine root.  These tests intentionally
never invoke the audit against the checkout's live evidence or receipts.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fmd_seo.contracts import sha256_text


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _engine_root(tmp_path: Path) -> Path:
    root = tmp_path / "engine"
    (root / "brain" / "observations").mkdir(parents=True)
    (root / "evals" / "invariants").mkdir(parents=True)
    (root / "receipts").mkdir()
    (root / "state").mkdir()
    (root / "evidence").mkdir()
    (root / "CONTRACT.md").write_text(
        "## Failure controls\n\n- Limits: $10 DataForSEO ceiling.\n",
        encoding="utf-8",
    )
    (root / "config").mkdir()
    (root / "config" / "engine.yaml").write_text(
        "schema_version: 1\nbudget:\n  total_usd: 50.0\n  endpoint_caps_usd:\n    serp: 5.0\n",
        encoding="utf-8",
    )
    (root / "brain" / "checks.yaml").write_text(
        """schema_version: 1
checks:
  - id: seo.local_visibility
    domain: seo
    title: Local visibility
    cadence: weekly
    cost: paid
    method: {kind: engine, run: test}
    records:
      - {name: pairs_tested, type: int}
      - {name: pairs_ranked, type: int}
      - {name: pairs_in_pack, type: int}
    thresholds: []
    why: test
  - id: gbp.performance
    domain: seo
    title: GBP performance
    cadence: weekly
    cost: free
    method: {kind: engine, run: test}
    records: [{name: calls, type: int}]
    thresholds: []
    why: test
  - id: engine.freshness
    domain: engine
    title: Freshness
    cadence: daily
    cost: free
    method: {kind: engine, run: test}
    records: [{name: age, type: int}]
    thresholds: []
    why: test
""",
        encoding="utf-8",
    )
    (root / "evals" / "invariants" / "records.yaml").write_text(
        """seo.local_visibility:
  - expr: pairs_in_pack <= pairs_ranked
    severity: critical
  - expr: pairs_ranked <= pairs_tested
    severity: critical
""",
        encoding="utf-8",
    )
    _write_json(root / "evals" / "grandfathered.json", {"observations": []})
    _write_json(root / "state" / "spend.json", [])
    return root


def _observation(root: Path, check_id: str, *, source: str, records: dict,
                 observed_at: str = "2026-08-03T12:00:00+00:00", **extra: str) -> Path:
    path = root / "brain" / "observations" / check_id / "observation.json"
    _write_json(path, {
        "check_id": check_id,
        "observed_at": observed_at,
        "fulfillment": "engine",
        "records": records,
        "source": source,
        "note": "",
        **extra,
    })
    return path


def test_audit_finds_grounding_failures_in_an_isolated_root(tmp_path: Path):
    from fmd_seo.audit import audit_repository

    root = _engine_root(tmp_path)
    source = root / "evidence" / "local.json"
    source.write_text('{"measured": true}\n', encoding="utf-8")
    # The source was changed after this observation was recorded.
    _observation(
        root,
        "seo.local_visibility",
        source="evidence/local.json",
        records={"pairs_tested": 4, "pairs_ranked": 2, "pairs_in_pack": 4},
        source_sha256=sha256_text("original evidence\n"),
        source_kind="file",
    )
    _observation(
        root,
        "gbp.performance",
        source="unstructured source description",
        records={"calls": 1},
        observed_at="2026-08-03T08:00:00-04:00",
    )
    _write_json(root / "state" / "spend.json", [{
        "id": "orphan", "ts": "2026-08-03T10:00:00+00:00", "endpoint": "serp",
        "reserved_usd": 1.0, "actual_usd": 1.0, "note": "test",
    }])
    _write_json(root / "receipts" / "run.json", {
        "run_id": "run", "status": "DONE", "command": "test",
        "started_at": "2026-08-03T11:00:00+00:00",
        "ended_at": "2026-08-03T11:01:00+00:00", "spend_usd": 0.0,
    })

    findings = audit_repository(root, now=datetime(2026, 8, 3, 13, tzinfo=timezone.utc))
    codes = {finding.code for finding in findings}
    assert {"contract_config_budget_drift", "record_invariant", "source_hash_mismatch",
            "non_utc_timestamp", "unwired_check", "missing_engine_freshness",
            "receipt_spend_mismatch", "orphan_spend"} <= codes
    assert any(f.severity == "critical" for f in findings)
    assert any(f.severity == "high" for f in findings)


def test_audit_rejects_missing_and_unhashed_file_provenance(tmp_path: Path):
    from fmd_seo.audit import audit_repository

    root = _engine_root(tmp_path)
    _observation(root, "seo.local_visibility", source="evidence/missing.json",
                 records={"pairs_tested": 1, "pairs_ranked": 1, "pairs_in_pack": 1})

    findings = audit_repository(root)
    codes = {finding.code for finding in findings}
    assert "source_missing" in codes
    assert "missing_source_hash" in codes


def test_audit_flags_observation_backdated_before_evidence(tmp_path: Path):
    from fmd_seo.audit import audit_repository

    root = _engine_root(tmp_path)
    source = root / "evidence" / "later.json"
    source.write_text('{"measured": true}\n', encoding="utf-8")
    later = datetime(2026, 8, 3, 12, tzinfo=timezone.utc).timestamp()
    os.utime(source, (later, later))
    _observation(root, "seo.local_visibility", source="evidence/later.json",
                 records={"pairs_tested": 1, "pairs_ranked": 1, "pairs_in_pack": 1},
                 observed_at="2026-08-03T11:00:00+00:00",
                 source_sha256=sha256_text('{"measured": true}\n'), source_kind="file")

    findings = audit_repository(root)
    assert any(f.code == "source_newer_than_observation" and f.severity == "critical"
               for f in findings)


def test_observation_source_fields_remain_backward_compatible():
    from fmd_seo.observations import Observation

    observation = Observation(
        check_id="test", observed_at="2026-08-03T00:00:00+00:00",
        fulfillment="engine", records={}, source="console",
    )
    assert observation.source_sha256 == ""
    assert observation.source_kind == ""


def test_audit_cli_writes_receipt_and_returns_critical_exit(tmp_path: Path, monkeypatch):
    from fmd_seo import cli, paths

    root = _engine_root(tmp_path)
    monkeypatch.setattr(paths, "ENGINE_ROOT", root)
    monkeypatch.setattr(paths, "RECEIPTS_DIR", root / "receipts")
    monkeypatch.setattr(paths, "CONFIG_FILE", root / "config" / "engine.yaml")

    assert cli.main(["audit"]) == 4
    receipt = next((root / "receipts").glob("*-audit-*.json"))
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["command"] == "audit"
    assert payload["status"] == "BLOCK"


def test_audit_recomputes_local_visibility_instead_of_trusting_records(tmp_path: Path):
    from fmd_seo.audit import audit_repository

    root = _engine_root(tmp_path)
    source = root / "evidence" / "local-results.jsonl"
    rows = [
        {"fmd_rank": 2, "fmd_in_pack": True, "fmd_reviews": 16},
        {"fmd_rank": 8, "fmd_in_pack": False, "fmd_reviews": 16},
        {"fmd_rank": None, "fmd_in_pack": False, "fmd_reviews": None},
        {"fmd_rank": None, "fmd_in_pack": False, "fmd_reviews": None},
    ]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    _observation(
        root,
        "seo.local_visibility",
        source="evidence/local-results.jsonl",
        records={"pairs_tested": 4, "pairs_ranked": 2, "pairs_in_pack": 4},
        source_sha256=sha256_text(source.read_text(encoding="utf-8")),
        source_kind="file",
    )

    findings = audit_repository(root)

    assert any(f.code == "recompute_mismatch" and f.severity == "critical"
               for f in findings)


def test_audit_uses_manifest_denominator_and_rejects_partial_measurement(tmp_path: Path):
    from fmd_seo.audit import audit_repository

    root = _engine_root(tmp_path)
    source = root / "evidence" / "grid-results.jsonl"
    rows = [
        {"query": "q", "fmd_local_pack_position": 2, "local_pack_businesses": []},
        {"query": "q", "fmd_local_pack_position": None, "local_pack_businesses": []},
    ]
    source.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    _write_json(root / "state" / "geogrid-task-manifest.json", {
        "completed_at": None,
        "tasks": [{"task_id": "1"}, {"task_id": "2"}, {"task_id": "3"}],
    })
    _observation(
        root,
        "seo.map_pack",
        source="evidence/grid-results.jsonl",
        records={"queries": 1, "points_sampled": 2, "points_missing": 0,
                 "points_present": 1, "median_rank": 2.0, "competitors_above": 0},
        source_sha256=sha256_text(source.read_text(encoding="utf-8")),
        source_kind="file",
    )

    findings = audit_repository(root)
    codes = {finding.code for finding in findings}

    assert "manifest_denominator_mismatch" in codes
    assert "partial_observation" in codes


def test_audit_flags_quality_improvement_when_denominator_shrinks(tmp_path: Path):
    from fmd_seo.audit import audit_repository

    root = _engine_root(tmp_path)
    obs_dir = root / "brain" / "observations" / "seo.local_visibility"
    obs_dir.mkdir(parents=True, exist_ok=True)
    for name, stamp, records in (
        ("one.json", "2026-08-01T12:00:00+00:00",
         {"pairs_tested": 100, "pairs_ranked": 10, "pairs_in_pack": 2}),
        ("two.json", "2026-08-02T12:00:00+00:00",
         {"pairs_tested": 80, "pairs_ranked": 12, "pairs_in_pack": 3}),
    ):
        _write_json(obs_dir / name, {
            "check_id": "seo.local_visibility", "observed_at": stamp,
            "fulfillment": "console", "records": records,
            "source": "console:local-visibility", "source_kind": "console",
            "source_sha256": "", "note": "",
        })

    findings = audit_repository(root)

    assert any(f.code == "shrinking_denominator" and f.severity == "high"
               for f in findings)


def test_audit_detects_hardcoded_committed_write_destination(tmp_path: Path):
    from fmd_seo.audit import audit_repository

    root = _engine_root(tmp_path)
    module = root / "src" / "fmd_seo" / "bad_writer.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "from fmd_seo import paths\n"
        "def write_result():\n"
        "    (paths.EVIDENCE_DIR / 'result.json').write_text('{}')\n",
        encoding="utf-8",
    )

    findings = audit_repository(root)

    assert any(f.code == "uninjectable_write" and f.severity == "critical"
               for f in findings)


def test_record_observation_quarantines_impossible_records_without_mutating_store(
    tmp_path: Path,
):
    from fmd_seo.brain import Brain, Check
    from fmd_seo.observations import record_observation

    root = _engine_root(tmp_path)
    brain = Brain(checks=[Check(
        id="seo.local_visibility", domain="seo", title="Local visibility",
        cadence="weekly", cost="paid", method_kind="engine", method_run="test",
        records=[
            {"name": "pairs_tested", "type": "int"},
            {"name": "pairs_ranked", "type": "int"},
            {"name": "pairs_in_pack", "type": "int"},
        ], thresholds=[], why="test",
    )], state={})
    observations = root / "brain" / "observations"
    before = list(observations.rglob("*"))

    with pytest.raises(ValueError, match="pairs_in_pack <= pairs_ranked"):
        record_observation(
            brain,
            "seo.local_visibility",
            {"pairs_tested": 4, "pairs_ranked": 2, "pairs_in_pack": 4},
            fulfillment="console",
            source="console:fixture",
            directory=observations,
            invariants_dir=root / "evals" / "invariants",
            quarantine_dir=root / "brain" / "quarantine",
        )

    assert list(observations.rglob("*")) == before
    rejection = next((root / "brain" / "quarantine" / "seo.local_visibility").glob("*.json"))
    payload = json.loads(rejection.read_text(encoding="utf-8"))
    assert payload["records"]["pairs_in_pack"] == 4
    assert "pairs_in_pack <= pairs_ranked" in payload["reason"]


def test_audit_enforces_frozen_geogrid_geometry(tmp_path: Path):
    from fmd_seo.audit import audit_repository

    root = _engine_root(tmp_path)
    (root / "config" / "engine.yaml").write_text(
        "schema_version: 1\n"
        "budget: {total_usd: 10, endpoint_caps_usd: {}}\n"
        "geogrid:\n"
        "  center: [41.4645, -81.5087]\n"
        "  radius_miles: 30\n"
        "  size: 5\n"
        "  strongholds:\n"
        "    - {name: Mayfield Heights, latitude: 41.5192, longitude: -81.4390}\n",
        encoding="utf-8",
    )
    (root / "evals" / "invariants" / "geometry.yaml").write_text(
        "geogrid:\n"
        "  sampling_radius_miles: 6\n"
        "  strongholds:\n"
        "    - {name: Mayfield Heights, latitude: 41.5192, longitude: -81.4390}\n",
        encoding="utf-8",
    )

    findings = audit_repository(root)

    assert any(f.code == "geometry_invariant" and f.severity == "critical"
               for f in findings)


def test_audit_proves_grid_points_fit_inside_service_ring(tmp_path: Path):
    from fmd_seo.audit import audit_repository

    root = _engine_root(tmp_path)
    facts = root / "facts.yaml"
    facts.write_text(
        "schema_version: 1\nservice_area: {base: Beachwood, radius_miles: 5}\n",
        encoding="utf-8",
    )
    (root / "config" / "engine.yaml").write_text(
        "schema_version: 1\n"
        "budget: {total_usd: 10, endpoint_caps_usd: {}}\n"
        f"paths: {{facts_file: {facts}}}\n"
        "geogrid:\n"
        "  center: [41.4645, -81.5087]\n"
        "  radius_miles: 6\n"
        "  size: 5\n"
        "  strongholds: []\n",
        encoding="utf-8",
    )
    (root / "evals" / "invariants" / "geometry.yaml").write_text(
        "geogrid:\n"
        "  sampling_radius_miles: 6\n"
        "  service_radius_source: business-facts.yaml#service_area.radius_miles\n"
        "  strongholds: []\n",
        encoding="utf-8",
    )

    findings = audit_repository(root)

    assert any(f.code == "geometry_invariant" and "service ring" in f.detail
               for f in findings)


def test_new_observation_must_match_declared_record_schema(tmp_path: Path):
    from fmd_seo.audit import audit_repository

    root = _engine_root(tmp_path)
    _observation(
        root,
        "seo.local_visibility",
        source="console:fixture",
        records={"pairs_tested": 4, "pairs_ranked": 2},
        source_kind="console",
    )

    findings = audit_repository(root)

    assert any(f.code == "record_schema_mismatch" and f.severity == "critical"
               for f in findings)


def test_spend_baseline_boundary_cannot_hide_later_ledger_entries(tmp_path: Path):
    from fmd_seo.audit import audit_repository

    root = _engine_root(tmp_path)
    _write_json(root / "state" / "spend.json", [
        {"id": "old", "ts": "2026-08-03T10:00:00+00:00", "endpoint": "serp",
         "reserved_usd": 1.0, "actual_usd": 1.0, "note": "historical"},
        # Timestamp is backdated, but position after the frozen id keeps it auditable.
        {"id": "hidden", "ts": "2026-08-03T09:00:00+00:00", "endpoint": "serp",
         "reserved_usd": 1.0, "actual_usd": 1.0, "note": "must not hide"},
    ])
    _write_json(root / "state" / "spend-reconciliation-baseline.json", {
        "captured_at": "2026-08-03T11:00:00+00:00",
        "ledger_total_usd": 1.0,
        "receipt_total_usd": 0.0,
        "last_reservation_id": "old",
        "endpoint_totals_usd": {"serp": 1.0},
        "endpoint_cap_exceptions_usd": {},
    })

    findings = audit_repository(root, now=datetime(2026, 8, 3, 12, tzinfo=timezone.utc))
    codes = {finding.code for finding in findings}

    assert "orphan_spend" in codes
    assert "receipt_spend_mismatch" in codes


def test_default_timestamp_is_not_earlier_than_just_written_source(tmp_path: Path):
    from fmd_seo.brain import Brain, Check
    from fmd_seo.observations import record_observation

    root = _engine_root(tmp_path)
    source = root / "evidence" / "fresh.json"
    source.write_text('{"measured": true}\n', encoding="utf-8")
    brain = Brain(checks=[Check(
        id="test.check", domain="test", title="Test", cadence="daily", cost="free",
        method_kind="engine", method_run="test",
        records=[{"name": "value", "type": "int"}], thresholds=[], why="test",
    )], state={})

    path = record_observation(
        brain, "test.check", {"value": 1}, fulfillment="engine_api",
        source="evidence/fresh.json", directory=root / "brain" / "observations",
        invariants_dir=root / "evals" / "invariants",
        quarantine_dir=root / "brain" / "quarantine",
    )

    assert path.exists()
    assert not (root / "brain" / "quarantine").exists()


def test_fulfillment_cannot_self_attest_an_unstructured_source_handle(tmp_path: Path):
    from fmd_seo.audit import audit_repository

    root = _engine_root(tmp_path)
    _observation(
        root, "seo.local_visibility", source="invented measurement",
        records={"pairs_tested": 1, "pairs_ranked": 1, "pairs_in_pack": 1},
        source_kind="api",
    )

    findings = audit_repository(root)

    assert any(f.code == "invalid_source_handle" and f.severity == "high"
               for f in findings)


def test_audit_cli_returns_partial_for_high_only_findings(tmp_path: Path, monkeypatch):
    from fmd_seo import cli, paths

    root = _engine_root(tmp_path)
    (root / "CONTRACT.md").write_text(
        "## Failure controls\n\n- Limits: $50 DataForSEO ceiling.\n", encoding="utf-8"
    )
    monkeypatch.setattr(paths, "ENGINE_ROOT", root)
    monkeypatch.setattr(paths, "RECEIPTS_DIR", root / "receipts")
    monkeypatch.setattr(paths, "CONFIG_FILE", root / "config" / "engine.yaml")

    assert cli.main(["audit"]) == 3


def test_grandfathered_allowlist_can_only_shrink():
    root = Path(__file__).resolve().parents[1]
    actual = set(json.loads((root / "evals" / "grandfathered.json").read_text(encoding="utf-8"))["observations"])
    known_pre_audit_observations = {
        "brain/observations/aeo.answer_accuracy/20260714T233645+0000.json",
        "brain/observations/aeo.entity_consistency/20260721T0000000400.json",
        "brain/observations/aeo.share_of_voice/20260719T0000000400.json",
        "brain/observations/competitor.authority_gap/20260714T233645+0000.json",
        "brain/observations/facts.freshness/20260801T060133+0000.json",
        "brain/observations/market.demand/20260714T235004+0000.json",
        "brain/observations/schema.presence/20260714T233645+0000.json",
        "brain/observations/schema.presence/20260715T001019+0000.json",
        "brain/observations/schema.validate/20260801T060133+0000.json",
        "brain/observations/seo.indexation/20260714T233628+0000.json",
        "brain/observations/seo.map_pack/20260719T210317+0000.json",
        "brain/observations/seo.organic_footprint/20260714T233645+0000.json",
        "brain/observations/seo.positions/20260719T221455+0000.json",
        "brain/observations/seo.site_health/20260714T233645+0000.json",
        "brain/observations/topics.related_clusters/20260714T235012+0000.json",
    }
    assert actual <= known_pre_audit_observations
