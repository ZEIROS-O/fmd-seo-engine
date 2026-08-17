import hashlib
import json
from pathlib import Path

import pytest

from fmd_seo.brain import Brain, BrainError, Check, load_brain
from fmd_seo import contracts
from fmd_seo import observations


def _page_package(**overrides):
    values = {
        "intent_key": "interior-detailing-cleveland",
        "tier": "supporting-post",
        "created_at": "2026-08-12T12:00:00+00:00",
        "fact_snapshot": {"source_hash": "facts-hash"},
        "evidence_refs": ["ev-gsc", "ev-consensus"],
        "content": {
            "title": "Interior detailing",
            "slug": "interior-detailing",
            "meta": {},
            "body_blocks": [],
            "schema_jsonld": {},
        },
        "internal_links": [],
        "assets": [],
        "information_gain": {
            "kind": "first_hand",
            "evidence_ref": "ev-consensus",
            "description": "A documented 47-point reset workflow.",
        },
    }
    values.update(overrides)
    return contracts.PagePackage.create(**values)


def _write_brain(tmp_path, checks: str, instruments: str,
                 producers: str = "schema_version: 1\nproducers: []\n") -> None:
    (tmp_path / "checks.yaml").write_text(checks, encoding="utf-8")
    (tmp_path / "instruments.yaml").write_text(instruments, encoding="utf-8")
    (tmp_path / "state.yaml").write_text(
        "schema_version: 1\nsite: {domain: example.com}\ngates: {}\n",
        encoding="utf-8",
    )
    (tmp_path / "gates.yaml").write_text("schema_version: 1\ngates: {}\n", encoding="utf-8")
    (tmp_path / "priorities.yaml").write_text(
        "schema_version: 1\npriorities:\n"
        "  - {id: p1, gate: {GATE-1: CLOSED}, label: blocked work}\n",
        encoding="utf-8",
    )
    (tmp_path / "producers.yaml").write_text(producers, encoding="utf-8")
    (tmp_path / "thesis.md").write_text("# thesis\n", encoding="utf-8")


def test_new_page_packages_require_v2_information_gain():
    package = _page_package()

    assert package.schema_version == contracts.PAGE_PACKAGE_SCHEMA_VERSION == 2
    assert package.information_gain["kind"] == "first_hand"

    with pytest.raises(contracts.ContractError, match="information_gain"):
        _page_package(information_gain={})

    with pytest.raises(contracts.ContractError, match="evidence_ref"):
        _page_package(
            information_gain={
                "kind": "benchmark",
                "evidence_ref": "ev-not-attached",
                "description": "A local benchmark.",
            }
        )


def test_historical_page_package_v1_remains_readable(tmp_path):
    historical = json.loads(
        (Path(__file__).parents[1] / "packages" / "pp-8aaa01ea7efaad48.json").read_text(
            encoding="utf-8"
        )
    )
    assert historical["schema_version"] == 1
    path = tmp_path / "historical.json"
    path.write_text(json.dumps(historical), encoding="utf-8")

    package = contracts.load_package(path)

    assert package.schema_version == 1
    assert package.information_gain is None


def test_patch_package_is_content_addressed_modify_only_and_immutable(tmp_path):
    before = "old content\n"
    after = "new content\n"
    package = contracts.PatchPackage.create(
        generator="sitemap",
        created_at="2026-08-12T12:00:00+00:00",
        site_base_commit="a" * 40,
        fact_snapshot_hash="facts-hash",
        evidence_refs=["ev-sitemap"],
        modifications=[{
            "operation": "modify",
            "path": "public/sitemap.xml",
            "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
            "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
            "replacement_content": after,
        }],
    )

    assert package.schema_version == contracts.PATCH_PACKAGE_SCHEMA_VERSION == 1
    assert package.package_id.startswith("patch-")
    path = contracts.write_patch_package(package, tmp_path)
    assert contracts.load_patch_package(path) == package
    assert contracts.write_patch_package(package, tmp_path) == path

    with pytest.raises(contracts.ContractError, match="modify"):
        contracts.PatchPackage.create(
            generator="sitemap",
            created_at="2026-08-12T12:00:00+00:00",
            site_base_commit="a" * 40,
            fact_snapshot_hash="facts-hash",
            evidence_refs=["ev-sitemap"],
            modifications=[{
                "operation": "create",
                "path": "public/new.xml",
                "before_sha256": "",
                "after_sha256": hashlib.sha256(after.encode()).hexdigest(),
                "replacement_content": after,
            }],
        )


def test_loader_rejects_nullable_threshold_without_boolean_guard(tmp_path):
    checks = """\
schema_version: 2
checks:
  - id: local.review_velocity
    domain: local
    title: Review velocity
    cadence: weekly
    cost: free
    execution_mode: scheduled
    thesis_refs: [T7]
    instrument_ref: local-finder-v1
    method: {kind: engine, run: measure}
    records:
      - {name: velocity_measured, type: bool}
      - {name: fmd_new_reviews_28d, type: int, nullable: true}
    thresholds:
      - {expr: "fmd_new_reviews_28d == 0", severity: critical, finding: stalled, action: review}
    why: measured priority
"""
    instruments = """\
schema_version: 1
instruments:
  - {id: local-finder-v1, status: active, purpose: reviews, source: dataforseo}
"""
    _write_brain(tmp_path, checks, instruments)

    with pytest.raises(BrainError, match="measurability guard"):
        load_brain(tmp_path)


def test_loader_accepts_guarded_nullable_threshold_and_rejects_retired_instrument(tmp_path):
    checks = """\
schema_version: 2
checks:
  - id: local.review_velocity
    domain: local
    title: Review velocity
    cadence: weekly
    cost: free
    execution_mode: scheduled
    thesis_refs: [T7]
    instrument_ref: local-finder-v1
    method: {kind: engine, run: measure}
    records:
      - {name: velocity_measured, type: bool}
      - {name: fmd_new_reviews_28d, type: int, nullable: true}
    thresholds:
      - {expr: "velocity_measured == true and fmd_new_reviews_28d == 0", severity: critical, finding: stalled, action: review}
    why: measured priority
"""
    active = """\
schema_version: 1
instruments:
  - {id: local-finder-v1, status: active, purpose: reviews, source: dataforseo}
"""
    producers = """\
schema_version: 1
producers:
  - {id: local.review_velocity, command: fmd-seo local-finder --run, entrypoint: fmd_seo.local_finder:run}
"""
    _write_brain(tmp_path, checks, active, producers)
    brain = load_brain(tmp_path)
    assert brain.check("local.review_velocity").execution_mode == "scheduled"

    retired = """\
schema_version: 1
instruments:
  - id: local-finder-v1
    status: retired
    purpose: reviews
    source: dataforseo
    retired_at: 2026-08-12
    rationale: superseded
"""
    _write_brain(tmp_path, checks, retired, producers)
    with pytest.raises(BrainError, match="retired instrument"):
        load_brain(tmp_path)


def test_observation_v2_accepts_null_only_for_declared_nullable_records(tmp_path):
    check = Check(
        id="local.review_velocity",
        domain="local",
        title="Review velocity",
        cadence="weekly",
        cost="free",
        method_kind="engine",
        method_run="measure",
        records=[
            {"name": "velocity_measured", "type": "bool"},
            {"name": "fmd_new_reviews_28d", "type": "int", "nullable": True},
        ],
        thresholds=[],
        why="test",
    )
    brain = Brain(checks=[check], state={})
    directory = tmp_path / "observations"

    path = observations.record_observation(
        brain,
        check.id,
        {"velocity_measured": False, "fmd_new_reviews_28d": None},
        fulfillment="engine",
        source="agent:test-review-velocity",
        directory=directory,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == observations.OBSERVATION_SCHEMA_VERSION == 2
    assert observations.load_observations(
        check.id, directory
    )[0].records["fmd_new_reviews_28d"] is None

    strict = Check(
        id="strict.check",
        domain="test",
        title="Strict",
        cadence="weekly",
        cost="free",
        method_kind="engine",
        method_run="measure",
        records=[{"name": "count", "type": "int"}],
        thresholds=[],
        why="test",
    )
    with pytest.raises(ValueError, match="must be int"):
        observations.record_observation(
            Brain(checks=[strict], state={}),
            strict.id,
            {"count": None},
            fulfillment="engine",
            source="agent:test-strict",
            directory=directory,
        )


def test_query_evidence_round_trip_preserves_new_measurement_panels():
    evidence = contracts.QueryEvidence(
        evidence_id="ev-composite",
        kind="serp_snapshot",
        query="mobile detailing cleveland",
        captured_at="2026-08-12T12:00:00+00:00",
        endpoint="gsc+serp",
        normalized={"rows": 3},
        raw_ref="raw-hash",
        cost_usd=0.0,
        gsc_query_footprint={"position": 7.2, "impressions": 30},
        serp_consensus={"accessible_winners": 7, "weakness_score": 62},
        aeo_response_panel={"engine": "chatgpt", "run": 1},
        review_language={"phrases": ["pet hair"]},
        citation_source={"domain": "example.com", "frequency": 2},
    )

    restored = contracts.from_dict("QueryEvidence", evidence.to_dict())

    assert restored == evidence
    assert restored.serp_consensus["accessible_winners"] == 7


@pytest.mark.parametrize(
    "check_id",
    [
        "schema.presence",
        "schema.validate",
        "seo.local_visibility",
        "seo.internal_links",
        "local.review_velocity",
        "local.review_language",
        "aeo.answer_accuracy",
        "aeo.recommendation_share",
        "aeo.review_floor",
        "aeo.citation_sources",
    ],
)
def test_checks_without_autonomous_producers_are_session_only(check_id):
    assert load_brain().check(check_id).execution_mode == "session"
