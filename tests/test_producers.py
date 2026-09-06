"""The producer registry: every scheduled check must name something that runs.

`execution_mode: scheduled` used to be an unverified claim. These tests hold the
correspondence in both directions and prove the entrypoints are real code.
"""

import pytest

from fmd_seo.brain import BrainError, load_brain, resolve_producer


CHECKS_BODY = """\
schema_version: 1
checks:
  - id: engine.thing
    domain: engine
    title: A scheduled thing
    cadence: daily
    cost: free
    execution_mode: {mode}
    method: {{kind: engine, run: measure}}
    records:
      - {{name: count, type: int}}
    thresholds:
      - {{expr: "count > 0", severity: info, finding: f, action: a}}
    why: because
"""


def _write_brain(tmp_path, *, mode: str, producers: str):
    (tmp_path / "checks.yaml").write_text(
        CHECKS_BODY.format(mode=mode), encoding="utf-8",
    )
    (tmp_path / "state.yaml").write_text(
        "schema_version: 1\nsite: {domain: x.com}\ngates: {}\n", encoding="utf-8",
    )
    (tmp_path / "gates.yaml").write_text(
        "schema_version: 1\ngates: {}\n", encoding="utf-8",
    )
    (tmp_path / "priorities.yaml").write_text(
        "schema_version: 1\npriorities:\n"
        "  - {id: p1, gate: {GATE-1: CLOSED}, label: work}\n",
        encoding="utf-8",
    )
    (tmp_path / "thesis.md").write_text("# thesis\n", encoding="utf-8")
    (tmp_path / "producers.yaml").write_text(producers, encoding="utf-8")
    return tmp_path


REAL_PRODUCER = (
    "schema_version: 1\nproducers:\n"
    "  - {id: engine.thing, command: fmd-seo tick, "
    "entrypoint: fmd_seo.freshness:record_daily_engine_checks}\n"
)


def test_loader_requires_a_producers_file(tmp_path):
    _write_brain(tmp_path, mode="session", producers=REAL_PRODUCER)
    (tmp_path / "producers.yaml").unlink()

    with pytest.raises(BrainError, match="producers.yaml"):
        load_brain(tmp_path)


def test_scheduled_check_without_a_producer_is_a_load_error(tmp_path):
    _write_brain(
        tmp_path, mode="scheduled",
        producers="schema_version: 1\nproducers: []\n",
    )

    with pytest.raises(BrainError, match="no registered producer"):
        load_brain(tmp_path)


def test_producer_for_a_session_check_is_a_load_error(tmp_path):
    """The direction that catches a check with a real autonomous producer that
    is nonetheless marked `session` — which is how three Semrush checks sat on
    the human path while sync.py was already fetching them."""
    _write_brain(tmp_path, mode="session", producers=REAL_PRODUCER)

    with pytest.raises(BrainError, match="execution_mode != scheduled"):
        load_brain(tmp_path)


def test_producer_for_an_undeclared_check_is_a_load_error(tmp_path):
    _write_brain(
        tmp_path, mode="scheduled",
        producers=REAL_PRODUCER + (
            "  - {id: engine.ghost, command: nothing, entrypoint: fmd_seo.freshness:x}\n"
        ),
    )

    with pytest.raises(BrainError, match="undeclared check id"):
        load_brain(tmp_path)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("schema_version: 9\nproducers: []\n", "unsupported producers schema"),
        (
            "schema_version: 1\nproducers:\n  - {id: engine.thing, command: c}\n",
            "missing keys",
        ),
        (
            "schema_version: 1\nproducers:\n"
            "  - {id: engine.thing, command: c, entrypoint: no_colon}\n",
            "module:callable",
        ),
        (REAL_PRODUCER + REAL_PRODUCER.split("producers:\n")[1], "duplicate producer id"),
    ],
)
def test_producers_file_fails_closed_on_bad_shape(tmp_path, body, message):
    _write_brain(tmp_path, mode="scheduled", producers=body)

    with pytest.raises(BrainError, match=message):
        load_brain(tmp_path)


def test_every_registered_producer_entrypoint_resolves():
    """A rename cannot silently orphan a scheduled check. This is the binding
    `load_brain` cannot do itself — every producer module imports brain."""
    brain = load_brain()

    assert brain.producers, "the live registry declares no producers"
    for check_id in brain.producers:
        producer = resolve_producer(brain, check_id)
        assert callable(producer), f"{check_id} entrypoint is not callable"


def test_resolve_producer_reports_a_missing_callable(tmp_path):
    directory = _write_brain(
        tmp_path, mode="scheduled",
        producers=(
            "schema_version: 1\nproducers:\n"
            "  - {id: engine.thing, command: c, "
            "entrypoint: fmd_seo.freshness:no_such_function}\n"
        ),
    )
    brain = load_brain(directory)

    with pytest.raises(BrainError, match="missing callable"):
        resolve_producer(brain, "engine.thing")


def test_live_registry_has_a_producer_for_every_scheduled_check():
    """The gate, asserted against the real brain rather than a fixture."""
    brain = load_brain()

    scheduled = {c.id for c in brain.checks if c.execution_mode == "scheduled"}
    assert scheduled == set(brain.producers)


def test_gbp_performance_is_session_until_api_access_lands():
    """It has no possible producer: the Business Profile APIs are disabled in
    the Cloud project and the location id the Performance API needs is only
    obtainable from one of them. Leaving it scheduled left a weekly check that
    nothing could ever write. See brain/blockers/gbp-performance.md."""
    brain = load_brain()

    assert brain.check("gbp.performance").execution_mode == "session"
    assert "gbp.performance" not in brain.producers


@pytest.mark.parametrize(
    "check_id",
    ["competitor.authority_gap", "market.demand", "topics.related_clusters"],
)
def test_semrush_checks_with_an_autonomous_producer_are_scheduled(check_id):
    """sync.sync_due has recorded these headlessly since the Semrush adapters
    landed; `session` kept them off the freshness watchdog."""
    brain = load_brain()

    assert brain.check(check_id).execution_mode == "scheduled"
    assert brain.producers[check_id]["entrypoint"] == "fmd_seo.sync:sync_due"
