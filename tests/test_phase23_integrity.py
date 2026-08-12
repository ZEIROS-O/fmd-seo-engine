"""Regression tests for the concrete defects exposed by the integrity audit."""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import yaml

from fmd_seo import geogrid, serp_bulk
from fmd_seo import act, preflight
from fmd_seo.contracts import FactSnapshot
from fmd_seo.paths import load_config
from fmd_seo.receipts import ReceiptBuilder


def test_geogrid_denominator_comes_from_manifest_task_count():
    rows = [
        {"query": "q1", "fmd_local_pack_position": 2, "local_pack_businesses": []},
        {"query": "q2", "fmd_local_pack_position": None, "local_pack_businesses": []},
    ]

    records = geogrid.aggregate_map_pack(
        rows,
        fmd_aliases=["Fresh Mobile Detailing"],
        tasks_posted=3,
    )

    assert records["points_sampled"] == 3
    assert records["points_missing"] == 1
    assert records["points_present"] == 1


def test_bulk_position_denominator_reports_missing_tasks():
    records = serp_bulk.position_records(
        [{"fmd_organic_position": 2}],
        expected_keywords=3,
    )

    assert records["keywords_tracked"] == 3
    assert records["keywords_missing"] == 2


def test_geogrid_sampling_radius_is_separate_from_service_area(tmp_path: Path):
    facts = tmp_path / "facts.yaml"
    facts.write_text(
        "schema_version: 1\nservice_area:\n"
        "  base: Beachwood / Mayfield Heights\n"
        "  radius_miles: 30\n",
        encoding="utf-8",
    )
    config = {
        "paths": {"facts_file": str(facts)},
        "geogrid": {
            "center": [41.4645, -81.5087],
            "radius_miles": 6,
            "size": 5,
            "queries": ["mobile detailing near me"],
        },
    }

    _base, specs = geogrid._specs(config)
    latitudes = [float(spec["location_coordinate"].split(",")[0]) for spec in specs]

    assert min(latitudes) > 41.37
    assert max(latitudes) < 41.56


def test_collectors_require_injectable_evidence_directories():
    assert "evidence_dir" in inspect.signature(geogrid.collect_tasks).parameters
    assert "evidence_dir" in inspect.signature(serp_bulk.collect_tasks).parameters


def test_receipt_builder_derives_spend_from_ledger_delta(tmp_path: Path):
    ledger = tmp_path / "spend.json"
    ledger.write_text("[]\n", encoding="utf-8")
    builder = ReceiptBuilder("measure", ledger_file=ledger)
    ledger.write_text(
        json.dumps([
            {
                "id": "reservation-1",
                "ts": builder.started_at,
                "endpoint": "geogrid",
                "reserved_usd": 0.12,
                "actual_usd": 0.11,
                "note": "measured",
            }
        ]),
        encoding="utf-8",
    )

    assert builder.finish().spend_usd == 0.11


def test_contract_budget_and_geogrid_radius_are_reconciled():
    config = load_config()

    assert config["budget"]["total_usd"] == 10.0
    assert config["geogrid"]["radius_miles"] == 6


def test_gbp_performance_has_at_least_one_decision_threshold():
    checks = yaml.safe_load(
        (Path(__file__).resolve().parents[1] / "brain" / "checks.yaml").read_text(
            encoding="utf-8"
        )
    )["checks"]
    gbp = next(check for check in checks if check["id"] == "gbp.performance")

    assert gbp["thresholds"]


def _snapshot(path: Path) -> FactSnapshot:
    return FactSnapshot(
        canonical_path=str(path),
        source_hash="a" * 64,
        source_last_updated="2026-08-01",
        reviewed_at="2026-08-01",
        review_after_days=30,
        captured_at="2026-08-03T12:00:00+00:00",
        facts_used={"identity.name": "Fresh Mobile Detailing"},
    )


def test_act_calls_fact_binding_verifier_before_accepting_package(tmp_path, monkeypatch):
    facts = tmp_path / "facts.yaml"
    facts.write_text("changed\n", encoding="utf-8")
    snapshot = _snapshot(facts)
    package = SimpleNamespace(fact_snapshot=snapshot.to_dict())
    monkeypatch.setattr(act, "load_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(act, "verify_binding", lambda _snapshot: False)

    _name, verdict, detail = act.validate_current_fact_binding(package, facts)

    assert verdict == "BLOCK"
    assert "binding" in detail.lower()


def test_preflight_calls_fact_binding_verifier(tmp_path, monkeypatch):
    facts = tmp_path / "facts.yaml"
    facts.write_text("changed\n", encoding="utf-8")
    snapshot = _snapshot(facts)
    snapshot = FactSnapshot(
        **{
            **snapshot.to_dict(),
            "facts_used": {
                "identity.name": "Fresh Mobile Detailing",
                "autonomy.posting": "human_only",
            },
        }
    )
    monkeypatch.setattr(preflight, "load_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(preflight, "verify_binding", lambda _snapshot: False)
    monkeypatch.setattr(preflight.killswitch, "engaged", lambda: False)
    operator = tmp_path / "operator"
    zeiros = tmp_path / "zeiros"
    site = tmp_path / "site"
    for repo in (operator, zeiros, site):
        (repo / ".git").mkdir(parents=True)
    config = {
        "paths": {
            "facts_file": str(facts),
            "operator_repo": str(operator),
            "zeiros_repo": str(zeiros),
            "site_worktree": str(site),
        },
        "creds_env": str(tmp_path / "missing.env"),
        "budget": {"total_usd": 10.0, "endpoint_caps_usd": {}},
        "limits": {"systemic_failures_to_kill": 2},
    }

    receipt = preflight.run_preflight(config)

    facts_check = next(check for check in receipt.checks if check["name"] == "facts")
    assert facts_check["verdict"] == "BLOCK"
    assert "binding" in facts_check["detail"].lower()
