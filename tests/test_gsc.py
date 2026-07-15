"""Tests for the GSC coverage classifier and tally. No network, no google libs:
the classification logic is pure and is the part that must be correct. Actual API
calls need a service-account key and are exercised by `gsc-sync` against live GSC.
"""

import pytest

from fmd_seo.gsc import classify_coverage, tally


@pytest.mark.parametrize("state,expected", [
    ("Submitted and indexed", "indexed"),
    ("Indexed, not submitted in sitemap", "indexed"),
    ("Indexed", "indexed"),
    ("Discovered - currently not indexed", "discovered_not_indexed"),
    ("Discovered – currently not indexed", "discovered_not_indexed"),  # en-dash
    ("Crawled - currently not indexed", "crawled_not_indexed"),
    ("Page with redirect", "not_indexed"),
    ("URL is unknown to Google", "not_indexed"),
    ("Excluded by 'noindex' tag", "not_indexed"),
    ("", "not_indexed"),
])
def test_classify_coverage(state, expected):
    assert classify_coverage(state) == expected


def test_tally_matches_indexation_record_shape():
    states = [
        "Submitted and indexed",
        "Submitted and indexed",
        "Indexed, not submitted in sitemap",
        "Discovered - currently not indexed",
        "Discovered - currently not indexed",
        "Crawled - currently not indexed",
        "Page with redirect",
        "",  # unknown -> not_indexed bucket
    ]
    rec = tally(states)
    assert rec == {
        "indexed": 3,
        "not_indexed": 5,               # 2 discovered + 1 crawled + 1 redirect + 1 unknown
        "discovered_not_indexed": 2,
        "crawled_not_indexed": 1,
    }
    # not_indexed must equal the sum of its named + unnamed buckets
    assert rec["not_indexed"] >= rec["discovered_not_indexed"] + rec["crawled_not_indexed"]


def test_tally_all_indexed():
    rec = tally(["Submitted and indexed"] * 20)
    assert rec["indexed"] == 20
    assert rec["not_indexed"] == 0


def test_records_validate_against_the_real_check():
    # The tally output must exactly satisfy the seo.indexation check's declared
    # fields — no missing/extra keys — so an engine_api observation records cleanly.
    from fmd_seo.brain import load_brain
    from fmd_seo.observations import record_observation
    import tempfile, pathlib
    brain = load_brain()
    rec = tally(["Submitted and indexed", "Discovered - currently not indexed"])
    # Should not raise (strict field validation in the store).
    record_observation(brain, "seo.indexation", rec, fulfillment="engine_api",
                       source="test", directory=pathlib.Path(tempfile.mkdtemp()))


def test_planner_labels_indexation_headless_when_gsc_present():
    from fmd_seo.brain import load_brain
    from fmd_seo.planner import build_plan
    import tempfile, pathlib
    brain = load_brain()
    empty = pathlib.Path(tempfile.mkdtemp())
    plan = build_plan(brain, has_semrush_key=False, has_gsc=True, observations_dir=empty)
    idx = next(pc for pc in plan.due if pc.check_id == "seo.indexation")
    assert idx.fulfillment == "engine_api"
    assert idx.api_reports == ["gsc:urlInspection"]


def test_planner_indexation_human_without_gsc():
    from fmd_seo.brain import load_brain
    from fmd_seo.planner import build_plan
    import tempfile, pathlib
    brain = load_brain()
    empty = pathlib.Path(tempfile.mkdtemp())
    plan = build_plan(brain, has_semrush_key=False, has_gsc=False, observations_dir=empty)
    idx = next(pc for pc in plan.due if pc.check_id == "seo.indexation")
    assert idx.fulfillment == "human"
