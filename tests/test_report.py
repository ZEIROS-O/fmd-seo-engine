import json

from fmd_seo.report import build_report


def _observation(root, check_id, stamp, records):
    directory = root / check_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{stamp}.json").write_text(json.dumps({
        "check_id": check_id,
        "observed_at": stamp,
        "fulfillment": "engine_api",
        "source": "fixture",
        "note": "",
        "records": records,
    }), encoding="utf-8")


def test_report_computes_deltas_without_fetching_and_aligns_interventions(tmp_path):
    observations = tmp_path / "observations"
    _observation(observations, "seo.indexation", "2026-08-01T00:00:00+00:00", {
        "indexed": 4, "not_indexed": 18,
    })
    _observation(observations, "seo.indexation", "2026-08-08T00:00:00+00:00", {
        "indexed": 9, "not_indexed": 11,
    })
    _observation(observations, "seo.positions", "2026-08-01T00:00:00+00:00", {
        "top3_count": 1, "top10_count": 8, "top20_count": 41,
    })
    _observation(observations, "seo.positions", "2026-08-08T00:00:00+00:00", {
        "top3_count": 2, "top10_count": 12, "top20_count": 50,
    })
    interventions = tmp_path / "interventions.jsonl"
    interventions.write_text(json.dumps({
        "occurred_at": "2026-08-04T12:00:00+00:00",
        "change": "schema finish",
        "thesis_priority": "T2",
        "sha": "abc123",
    }) + "\n", encoding="utf-8")

    report = build_report(
        "2026-08-01",
        observations_dir=observations,
        interventions_path=interventions,
    )

    assert report["metrics"]["indexed"]["delta"] == 5
    assert report["metrics"]["not_indexed"]["delta"] == -7
    assert report["metrics"]["top10_count"]["delta"] == 4
    assert report["interventions"][0]["change"] == "schema finish"
    assert report["interventions"][0]["metric_movement"]["indexed"] == 5


def test_report_does_not_call_one_observation_a_zero_delta(tmp_path):
    observations = tmp_path / "observations"
    _observation(observations, "seo.indexation", "2026-08-01T00:00:00+00:00", {
        "indexed": 4, "not_indexed": 18,
    })

    report = build_report(
        "2026-08-01",
        observations_dir=observations,
        interventions_path=tmp_path / "missing.jsonl",
    )

    assert report["metrics"]["indexed"]["status"] == "BASELINE_ONLY"
    assert report["metrics"]["indexed"]["delta"] is None


def test_report_excludes_unmerged_proposed_actions(tmp_path):
    interventions = tmp_path / "interventions.jsonl"
    interventions.write_text(json.dumps({
        "occurred_at": "2026-08-02T00:00:00+00:00",
        "change": "draft PR",
        "merged_at": None,
    }) + "\n", encoding="utf-8")

    report = build_report(
        "2026-08-01",
        observations_dir=tmp_path / "observations",
        interventions_path=interventions,
    )

    assert report["interventions"] == []


def test_report_bounds_each_intervention_at_the_next_merge(tmp_path):
    observations = tmp_path / "observations"
    for stamp, indexed in (
        ("2026-08-01T00:00:00+00:00", 4),
        ("2026-08-04T00:00:00+00:00", 6),
        ("2026-08-08T00:00:00+00:00", 11),
    ):
        _observation(observations, "seo.indexation", stamp, {
            "indexed": indexed, "not_indexed": 20 - indexed,
        })
    interventions = tmp_path / "interventions.jsonl"
    interventions.write_text("\n".join([
        json.dumps({"merged_at": "2026-08-02T00:00:00+00:00", "change": "first"}),
        json.dumps({"merged_at": "2026-08-05T00:00:00+00:00", "change": "second"}),
    ]) + "\n", encoding="utf-8")

    report = build_report(
        "2026-08-01", observations_dir=observations, interventions_path=interventions,
    )

    assert report["interventions"][0]["metric_movement"]["indexed"] == 2
    assert report["interventions"][1]["metric_movement"]["indexed"] == 5
