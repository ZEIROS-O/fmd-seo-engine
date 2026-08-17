import json
from datetime import datetime, timezone

import pytest

from fmd_seo.brain import Brain, Check


NOW = datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc)


def _check(
    check_id: str, *, cadence: str = "daily", execution_mode: str = "scheduled",
) -> Check:
    return Check(
        id=check_id,
        domain="engine",
        title=check_id,
        cadence=cadence,
        cost="free",
        method_kind="engine",
        method_run="test",
        records=[],
        thresholds=[],
        why="test",
        execution_mode=execution_mode,
    )


def _write_observation(root, check_id: str, observed_at: str, *, name="odd-name.json"):
    path = root / check_id / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "check_id": check_id,
                "observed_at": observed_at,
                "fulfillment": "engine",
                "records": {},
                "source": "test",
            }
        ),
        encoding="utf-8",
    )
    return path


def test_freshness_report_refuses_missing_store(tmp_path):
    from fmd_seo.freshness import FreshnessDataError, freshness_report

    with pytest.raises(FreshnessDataError, match="observations directory missing"):
        freshness_report(Brain(checks=[] , state={}), tmp_path / "missing", now=NOW)


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("not json", "malformed observation"),
        ("[]", "observation must be an object"),
    ],
)
def test_freshness_report_refuses_malformed_or_wrong_shape(tmp_path, contents, message):
    from fmd_seo.freshness import FreshnessDataError, freshness_report

    path = tmp_path / "observations" / "check.one" / "row.json"
    path.parent.mkdir(parents=True)
    path.write_text(contents, encoding="utf-8")

    with pytest.raises(FreshnessDataError, match=message):
        freshness_report(Brain(checks=[_check("check.one")], state={}), path.parents[1], now=NOW)


def test_freshness_report_present_empty_store_reports_zero(tmp_path):
    from fmd_seo.freshness import freshness_report

    observations = tmp_path / "observations"
    observations.mkdir()

    report = freshness_report(Brain(checks=[], state={}), observations, now=NOW)

    assert report == {
        "state": "no_observations_found",
        "observations_found": 0,
        "stalest_check_age_days": 0,
        "checks_overdue": 0,
        "never_observed": [],
        "unregistered_observations": [],
    }


def test_freshness_report_reads_body_timestamp_not_filename(tmp_path):
    from fmd_seo.freshness import freshness_report

    observations = tmp_path / "observations"
    _write_observation(observations, "check.one", "2026-08-14T06:00:00+00:00")

    report = freshness_report(
        Brain(checks=[_check("check.one")], state={}), observations, now=NOW
    )

    assert report["state"] == "observations_current"
    assert report["observations_found"] == 1
    assert report["checks_overdue"] == 0


def test_freshness_report_gives_one_day_of_grace_past_the_cadence(tmp_path):
    """Due is not the same instant as overdue.

    The producer runs on a daily cron, so a daily check is always ~24h old at the
    moment the watchdog asks. With zero slack it read as neglected every single
    day and engine.freshness fired a permanent critical finding.
    """
    from fmd_seo.freshness import freshness_report

    observations = tmp_path / "observations"
    _write_observation(observations, "check.one", "2026-08-13T12:00:00+00:00")

    report = freshness_report(
        Brain(checks=[_check("check.one")], state={}), observations, now=NOW
    )

    assert report["state"] == "observations_current"
    assert report["stalest_check_age_days"] == 1
    assert report["checks_overdue"] == 0
    assert report["never_observed"] == []


def test_freshness_report_blocks_once_the_grace_is_spent(tmp_path):
    from fmd_seo.freshness import freshness_report

    observations = tmp_path / "observations"
    _write_observation(observations, "check.one", "2026-08-12T12:00:00+00:00")

    report = freshness_report(
        Brain(checks=[_check("check.one")], state={}), observations, now=NOW
    )

    assert report["state"] == "observations_stale"
    assert report["stalest_check_age_days"] == 2
    assert report["checks_overdue"] == 1


def test_freshness_surfaces_agree_on_the_same_store(tmp_path):
    """The §2.3 invariant. The two used to disagree 9 vs 3 on live data."""
    from fmd_seo.freshness import freshness_records, freshness_report

    observations = tmp_path / "observations"
    _write_observation(observations, "check.current", "2026-08-14T11:00:00+00:00")
    _write_observation(observations, "check.stale", "2026-08-01T12:00:00+00:00")
    brain = Brain(
        checks=[
            _check("check.current"),
            _check("check.stale"),
            _check("check.never"),
            _check("check.session", execution_mode="session"),
        ],
        state={},
    )

    report = freshness_report(brain, observations, now=NOW)
    records = freshness_records(brain, observations, now=NOW)

    assert report["checks_overdue"] == records["checks_overdue"] == 2
    assert (
        report["stalest_check_age_days"] == records["stalest_check_age_days"] == 13
    )
    assert report["never_observed"] == ["check.never"]


def test_freshness_records_count_never_observed_scheduled_checks(tmp_path):
    """`engine.freshness` reads this surface; it used to `continue` past a check
    with no observation, so it was blind to every never-observed scheduled
    check."""
    from fmd_seo.freshness import freshness_records

    observations = tmp_path / "observations"
    _write_observation(observations, "check.current", "2026-08-14T11:00:00+00:00")
    brain = Brain(
        checks=[_check("check.current"), _check("check.never")], state={},
    )

    assert freshness_records(brain, observations, now=NOW)["checks_overdue"] == 1


def test_freshness_report_ignores_session_checks_entirely(tmp_path):
    """A session check is not the watchdog's business — it must appear in
    neither `overdue` nor `never_observed`."""
    from fmd_seo.freshness import freshness_report

    observations = tmp_path / "observations"
    _write_observation(observations, "check.current", "2026-08-14T11:00:00+00:00")
    brain = Brain(
        checks=[
            _check("check.current"),
            _check("session.never", execution_mode="session"),
            _check("session.ancient", execution_mode="session"),
        ],
        state={},
    )
    _write_observation(observations, "session.ancient", "2026-01-01T00:00:00+00:00")

    report = freshness_report(brain, observations, now=NOW)

    assert report["checks_overdue"] == 0
    assert report["never_observed"] == []
    assert report["state"] == "observations_current"
    # Still counted as committed data, just not the watchdog's responsibility.
    assert report["observations_found"] == 2


def test_freshness_surfaces_accept_a_naive_now_as_utc(tmp_path):
    """`freshness_report` reinterpreted a naive `now` as local time while
    `freshness_records` raised TypeError on the identical input."""
    from fmd_seo.freshness import freshness_records, freshness_report

    observations = tmp_path / "observations"
    _write_observation(observations, "check.one", "2026-08-14T11:00:00+00:00")
    brain = Brain(checks=[_check("check.one")], state={})
    naive = datetime(2026, 8, 14, 12, 0)

    assert freshness_report(brain, observations, now=naive)["checks_overdue"] == 0
    assert freshness_records(brain, observations, now=naive) == {
        "stalest_check_age_days": 0,
        "checks_overdue": 0,
    }


def test_freshness_report_names_orphaned_observation_ids(tmp_path):
    """A check rename leaves its old observation directory behind. Counting it
    made a dead directory read as live coverage."""
    from fmd_seo.freshness import freshness_report

    observations = tmp_path / "observations"
    _write_observation(observations, "check.one", "2026-08-14T11:00:00+00:00")
    _write_observation(observations, "check.renamed_away", "2026-08-14T11:00:00+00:00")

    report = freshness_report(
        Brain(checks=[_check("check.one")], state={}), observations, now=NOW
    )

    assert report["observations_found"] == 1
    assert report["unregistered_observations"] == ["check.renamed_away"]


def test_freshness_report_never_observed_check_is_stale(tmp_path):
    from fmd_seo.freshness import freshness_report

    observations = tmp_path / "observations"
    _write_observation(observations, "check.current", "2026-08-14T11:00:00+00:00")

    report = freshness_report(
        Brain(checks=[_check("check.current"), _check("check.never")], state={}),
        observations,
        now=NOW,
    )

    assert report["state"] == "observations_stale"
    assert report["checks_overdue"] == 1
    assert report["never_observed"] == ["check.never"]


def test_freshness_report_ignores_self_observation(tmp_path):
    from fmd_seo.freshness import freshness_report

    observations = tmp_path / "observations"
    _write_observation(observations, "engine.freshness", "2026-08-14T11:59:00+00:00")

    report = freshness_report(
        Brain(
            checks=[_check("engine.freshness"), _check("check.never")],
            state={},
        ),
        observations,
        now=NOW,
    )

    assert report["observations_found"] == 0
    assert report["state"] == "no_observations_found"
    assert report["checks_overdue"] == 1
    assert report["never_observed"] == ["check.never"]


def test_engine_freshness_records_ignore_session_cadence(tmp_path):
    from fmd_seo.freshness import freshness_records

    observations = tmp_path / "observations"
    _write_observation(
        observations, "scheduled.current", "2026-08-14T11:00:00+00:00",
    )
    _write_observation(
        observations, "session.old", "2026-07-01T00:00:00+00:00",
    )
    brain = Brain(
        checks=[
            _check("scheduled.current"),
            _check("session.old", execution_mode="session"),
        ],
        state={},
    )

    records = freshness_records(brain, observations, now=NOW)

    assert records == {"stalest_check_age_days": 0, "checks_overdue": 0}


def test_freshness_cli_is_read_only_and_zero_for_empty_registry(
    tmp_path, monkeypatch, capsys
):
    from fmd_seo import brain as brain_module
    from fmd_seo import cli, killswitch, paths

    observations = tmp_path / "brain" / "observations"
    observations.mkdir(parents=True)
    receipts = tmp_path / "receipts"
    monkeypatch.setattr(paths, "ENGINE_ROOT", tmp_path)
    monkeypatch.setattr(paths, "RECEIPTS_DIR", receipts)
    monkeypatch.setattr(brain_module, "load_brain", lambda: Brain(checks=[], state={}))
    monkeypatch.setattr(
        killswitch,
        "assert_not_engaged",
        lambda: (_ for _ in ()).throw(AssertionError("freshness consulted kill switch")),
    )

    code = cli.main(["freshness"])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "DONE"
    assert payload["state"] == "no_observations_found"
    assert not receipts.exists()


def test_freshness_cli_returns_block_for_never_observed_check(
    tmp_path, monkeypatch, capsys
):
    from fmd_seo import brain as brain_module
    from fmd_seo import cli, paths

    observations = tmp_path / "brain" / "observations"
    observations.mkdir(parents=True)
    monkeypatch.setattr(paths, "ENGINE_ROOT", tmp_path)
    monkeypatch.setattr(
        brain_module,
        "load_brain",
        lambda: Brain(checks=[_check("check.never")], state={}),
    )

    code = cli.main(["freshness"])

    payload = json.loads(capsys.readouterr().out)
    assert code == 4
    assert payload["status"] == "BLOCK"
    assert payload["state"] == "no_observations_found"
    assert payload["never_observed"] == ["check.never"]
