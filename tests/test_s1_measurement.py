from datetime import date
import json

import pytest


def test_gsc_query_footprint_aggregates_near_winners_and_ctr_leaks():
    from fmd_seo.query_footprint import aggregate_rows

    query_rows = [
        {"keys": ["fresh mobile detailing"], "clicks": 3, "impressions": 10, "ctr": 0.3, "position": 2.0},
        {"keys": ["mobile detailing cleveland"], "clicks": 0, "impressions": 20, "ctr": 0.0, "position": 6.0},
        {"keys": ["pet hair car detailing"], "clicks": 0, "impressions": 15, "ctr": 0.0, "position": 14.0},
        {"keys": ["car wash"], "clicks": 0, "impressions": 4, "ctr": 0.0, "position": 30.0},
    ]
    page_rows = [
        {"keys": ["fresh mobile detailing", "/"], "clicks": 3, "impressions": 10, "position": 2.0},
        {"keys": ["mobile detailing cleveland", "/mobile-detailing"], "clicks": 0, "impressions": 20, "position": 6.0},
        {"keys": ["pet hair car detailing", "/interior-detailing"], "clicks": 0, "impressions": 15, "position": 14.0},
        {"keys": ["car wash", "/"], "clicks": 0, "impressions": 4, "position": 30.0},
    ]

    summary = aggregate_rows(query_rows, page_rows, pages_in_sitemap=24)

    assert summary == {
        "total_queries": 4,
        "nonbranded_queries": 3,
        "queries_pos_1_3": 1,
        "queries_pos_4_10": 1,
        "queries_pos_11_20": 1,
        "impressions_pos_1_3": 10,
        "impressions_pos_4_10": 20,
        "impressions_pos_11_20": 15,
        "impressions_pos_4_20": 35,
        "ctr_leak_queries": 2,
        "pages_with_impressions": 3,
        "pages_in_sitemap": 24,
    }


def test_gsc_query_footprint_reads_query_totals_not_summed_page_rows():
    """A query ranking on two pages must not double-count its impressions.

    aggregationType auto aggregates by page, so the query/page dataset carries
    the same query twice. Summing those rows inflated the impression buckets and
    halved CTR, manufacturing a false ctr_leak_queries entry.
    """
    from fmd_seo.query_footprint import aggregate_rows

    query_rows = [
        {"keys": ["mobile detailing cleveland"], "clicks": 3, "impressions": 50, "position": 6.0},
    ]
    page_rows = [
        {"keys": ["mobile detailing cleveland", "/a"], "clicks": 2, "impressions": 30, "position": 5.0},
        {"keys": ["mobile detailing cleveland", "/b"], "clicks": 1, "impressions": 20, "position": 8.0},
    ]

    summary = aggregate_rows(query_rows, page_rows, pages_in_sitemap=24)

    assert summary["total_queries"] == 1
    assert summary["impressions_pos_4_10"] == 50
    assert summary["impressions_pos_4_20"] == 50
    # 3/50 = 0.06, above the 0.03 floor for positions 4-10. Summing the page
    # rows would have read 3/50 against 100 impressions and reported a leak.
    assert summary["ctr_leak_queries"] == 0
    assert summary["pages_with_impressions"] == 2


@pytest.mark.parametrize(
    "polluting_position",
    [0.0, -1.0, float("nan"), float("inf"), float("-inf"), None, "n/a"],
)
def test_gsc_query_footprint_rejects_invalid_position_from_every_bucket(
    polluting_position,
):
    """An invalid position must contribute to no bucket, not just be dropped
    from the position average. The old `position > 0` guard excluded the bad row
    from the weighted mean but still added its impressions, turning 10 real
    impressions at position 5 into impressions_pos_4_20 = 1010.
    """
    from fmd_seo.query_footprint import aggregate_rows

    query_rows = [
        {"keys": ["near winner"], "clicks": 1, "impressions": 10, "position": 5.0},
        {
            "keys": ["near winner"],
            "clicks": 0,
            "impressions": 1_000,
            "position": polluting_position,
        },
    ]

    summary = aggregate_rows(query_rows, [], pages_in_sitemap=24)

    assert summary["queries_pos_4_10"] == 1
    assert summary["impressions_pos_4_10"] == 10
    assert summary["impressions_pos_4_20"] == 10
    assert summary["impressions_pos_1_3"] == 0
    assert summary["impressions_pos_11_20"] == 0
    assert summary["total_queries"] == 1


def test_gsc_query_footprint_infinite_position_cannot_erase_a_near_winner():
    """+inf passed the old `position > 0` guard and poisoned the weighted mean
    to inf, silently deleting a real positions-4-20 query."""
    from fmd_seo.query_footprint import aggregate_rows

    query_rows = [
        {"keys": ["near winner"], "clicks": 0, "impressions": 40, "position": 7.0},
        {"keys": ["near winner"], "clicks": 0, "impressions": 1, "position": float("inf")},
    ]

    summary = aggregate_rows(query_rows, [], pages_in_sitemap=24)

    assert summary["queries_pos_4_10"] == 1
    assert summary["impressions_pos_4_20"] == 40


def test_gsc_query_footprint_page_coverage_counts_distinct_pages():
    from fmd_seo.query_footprint import aggregate_rows

    page_rows = [
        {"keys": ["a", "/one"], "clicks": 0, "impressions": 5, "position": 9.0},
        {"keys": ["b", "/one"], "clicks": 0, "impressions": 3, "position": 9.0},
        {"keys": ["c", "/two"], "clicks": 0, "impressions": 1, "position": 9.0},
        {"keys": ["d", "/never-seen"], "clicks": 0, "impressions": 0, "position": 9.0},
        {"keys": ["e"], "clicks": 0, "impressions": 9, "position": 9.0},
    ]

    summary = aggregate_rows([], page_rows, pages_in_sitemap=24)

    assert summary["pages_with_impressions"] == 2


def test_gsc_query_fetch_pulls_both_dimension_sets_and_stops_at_25000():
    from fmd_seo.query_footprint import (
        QUERY_DIMENSIONS,
        QUERY_PAGE_DIMENSIONS,
        dataset_rows,
        fetch_top_rows,
    )

    calls = []

    class Query:
        def query(self, *, siteUrl, body):
            calls.append((siteUrl, body))
            start = body["startRow"]
            rows = [{"keys": [f"q-{i}", "/"][: len(body["dimensions"])],
                     "impressions": 1, "clicks": 0, "ctr": 0, "position": 9}
                    for i in range(start, start + 10_000)]
            return type("Request", (), {"execute": lambda self: {"rows": rows}})()

    service = type("Service", (), {"searchanalytics": lambda self: Query()})()
    artifact = fetch_top_rows(
        service,
        site_url="sc-domain:example.com",
        today=date(2026, 8, 12),
        page_size=10_000,
    )

    assert artifact["coverage"] == "top_rows"
    assert artifact["start_date"] == "2026-07-13"
    assert artifact["end_date"] == "2026-08-09"
    assert [dataset["dimensions"] for dataset in artifact["datasets"]] == [
        QUERY_DIMENSIONS, QUERY_PAGE_DIMENSIONS,
    ]
    assert len(dataset_rows(artifact, QUERY_DIMENSIONS)) == 25_000
    assert len(dataset_rows(artifact, QUERY_PAGE_DIMENSIONS)) == 25_000

    # Each dataset pages independently; filter by dimensions or the startRow
    # sequence is ambiguous across the two.
    for dimensions in (QUERY_DIMENSIONS, QUERY_PAGE_DIMENSIONS):
        bodies = [body for _, body in calls if body["dimensions"] == dimensions]
        assert [body["startRow"] for body in bodies] == [0, 10_000, 20_000]
        assert bodies[-1]["rowLimit"] == 5_000
        assert all(body["dataState"] == "final" for body in bodies)


def test_gsc_dataset_rows_raises_rather_than_reading_absent_as_zero():
    from fmd_seo.query_footprint import dataset_rows

    with pytest.raises(KeyError):
        dataset_rows({"datasets": [{"dimensions": ["query"], "rows": []}]},
                     ["query", "page"])


def test_gsc_query_rows_are_content_addressed_and_exclusive(tmp_path):
    from fmd_seo.query_footprint import write_top_rows_artifact

    artifact = {
        "coverage": "top_rows",
        "start_date": "2026-07-13",
        "end_date": "2026-08-09",
        "row_limit": 25_000,
        "datasets": [
            {"dimensions": ["query"],
             "rows": [{"keys": ["mobile detailing"]}]},
            {"dimensions": ["query", "page"],
             "rows": [{"keys": ["mobile detailing", "https://example.test/"]}]},
        ],
    }
    first = write_top_rows_artifact(artifact, directory=tmp_path)
    second = write_top_rows_artifact(artifact, directory=tmp_path)

    assert first == second
    assert json.loads(first.read_text(encoding="utf-8")) == artifact
    assert first.name.startswith("gsc-query-footprint-top-rows-")
    # One artifact, both dimension sets — Observation.source is a single string
    # with a single source_sha256, so a second file could never be cited.
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_review_velocity_uses_nearest_25_to_35_day_reading_and_preserves_null():
    from fmd_seo.reviews import derive_review_velocity

    current = {
        "observed_at": "2026-08-12T12:00:00+00:00",
        "fmd": {"reviews": 16, "rating": 4.9},
        "competitors": [
            {"name": "A", "reviews": 72},
            {"name": "B", "reviews": 129},
            {"name": "C", "reviews": 65},
        ],
    }
    prior = [{
        "observed_at": "2026-07-14T12:00:00+00:00",
        "fmd": {"reviews": 13},
        "competitors": [
            {"name": "A", "reviews": 70},
            {"name": "B", "reviews": 126},
            {"name": "C", "reviews": 64},
        ],
    }]

    result = derive_review_velocity(current, prior)

    assert result["fmd_new_reviews_28d"] == 3
    assert result["competitor_median_new_reviews_28d"] == 2
    assert result["pack_floor_reviews"] == 65
    assert result["reviews_to_floor"] == 49
    assert result["static_months_to_floor"] == pytest.approx(49 / 3)
    assert result["net_months_to_floor"] == pytest.approx(49)

    missing = derive_review_velocity(current, [])
    assert missing["fmd_new_reviews_28d"] is None
    assert missing["net_months_to_floor"] is None


@pytest.mark.parametrize("with_prior", [True, False])
def test_review_velocity_deriver_output_records_and_assesses(tmp_path, with_prior):
    """A deriver whose output the check's own contract rejects can never record.

    Unit-testing the deriver in isolation cannot catch that -- only the full
    trip through record_observation's validation and back out through
    assess_check proves the two halves agree.
    """
    from fmd_seo.assess import assess_check
    from fmd_seo.brain import load_brain
    from fmd_seo.observations import record_observation
    from fmd_seo.reviews import derive_review_velocity

    current = {
        "observed_at": "2026-08-12T12:00:00+00:00",
        "fmd": {"reviews": 16, "rating": 4.9},
        "competitors": [
            {"name": "A", "reviews": 72},
            {"name": "B", "reviews": 129},
            {"name": "C", "reviews": 65},
        ],
    }
    # FMD gains 1 while the competitor median gains 2 -- net velocity is
    # negative, so the floor is receding and months-to-floor is unmeasurable.
    history = [{
        "observed_at": "2026-07-14T12:00:00+00:00",
        "fmd": {"reviews": 15},
        "competitors": [
            {"name": "A", "reviews": 70},
            {"name": "B", "reviews": 127},
            {"name": "C", "reviews": 63},
        ],
    }] if with_prior else []

    records = derive_review_velocity(current, history)
    assert records["prior_measured"] is with_prior
    assert records["net_velocity_positive"] is False

    observations = tmp_path / "observations"
    brain = load_brain()
    record_observation(
        brain, "local.review_velocity", records,
        fulfillment="engine", source="engine", note="round-trip",
        observed_at=current["observed_at"], directory=observations,
        verify=False,
    )

    _, findings = assess_check(brain, "local.review_velocity", observations)
    severities = {f.severity for f in findings}
    assert "high" in severities  # below the observed review floor
    if with_prior:
        assert records["net_months_to_floor"] is None
        assert any("not closing the review floor" in f.finding for f in findings)
    else:
        # A missing prior must not be read as a measured zero.
        assert not any("velocity is zero" in f.finding for f in findings)
        assert not any("not closing the review floor" in f.finding for f in findings)


def test_aeo_v1_panel_and_canary_plan_are_frozen_and_cost_gated():
    from fmd_seo.aeo_panel import AEO_PANEL_V1, build_plan

    assert len(AEO_PANEL_V1) == 25
    assert len(set(AEO_PANEL_V1)) == 25
    plan = build_plan(canary=True, unit_cost_usd=0.0063, endpoint_cap_usd=0.20)
    assert plan["responses"] == 20
    assert plan["engines"] == ["chatgpt", "perplexity"]
    assert plan["runs_per_query"] == 2
    assert plan["projected_cost_usd"] == pytest.approx(0.126)
    assert plan["within_cap"] is True
    assert plan["scheduling_enabled"] is False
    assert plan["approval_required"] is True


def test_serp_consensus_requires_six_accessible_winners_and_uses_majority_features():
    from fmd_seo.serp_consensus import ConsensusUnavailable, build_consensus

    winners = [
        {
            "url": f"https://example{i}.com/page",
            "rank": i,
            "result_type": "organic",
            "accessible": True,
            "page_type": "service" if i < 6 else "listicle",
            "headings": ["Pricing", "What is included"] if i < 6 else ["Pricing"],
            "entities": ["interior detailing", "pet hair"],
            "schema": ["Service"],
            "surfaces": ["map_pack"],
            "word_count": 800 + i * 10,
            "last_modified": None,
            "weak": i in {1, 2, 3},
        }
        for i in range(1, 8)
    ]

    consensus = build_consensus("mobile detailing cleveland", winners)

    assert consensus["accessible_winners"] == 7
    assert consensus["dominant_page_type"] == "service"
    assert consensus["repeated_headings"] == ["Pricing", "What is included"]
    assert consensus["repeated_entities"] == ["interior detailing", "pet hair"]
    assert consensus["freshness"]["known_dates"] == 0
    assert consensus["weakness_score"] == 43

    with pytest.raises(ConsensusUnavailable, match="at least 6"):
        build_consensus("q", winners[:5])
