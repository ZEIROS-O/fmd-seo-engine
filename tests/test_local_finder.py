import json
from pathlib import Path

import pytest

from fmd_seo import local_finder


TARGETS = {
    "fmd": {"domain": "freshmobiledetail.com", "aliases": ["Fresh Mobile Detailing"]},
    "nathans": {"domain": "nathansdetailing.com", "aliases": ["Nathan's Detailing"]},
}


def _config(tmp_path, **overrides):
    config = {
        "budget": {"total_usd": 50.0, "endpoint_caps_usd": {"local_finder": 0.25}},
        "serp_bulk": {"targets": TARGETS},
        "local_finder": {
            "depth": 20,
            "task_price_usd": 0.004,
            "queries": ["mobile detailing {suburb}", "car detailing near me"],
            "locations": [
                {"name": "Beachwood", "suburb": "beachwood",
                 "latitude": 41.4645, "longitude": -81.5087},
                {"name": "Solon", "suburb": "solon",
                 "latitude": 41.3897, "longitude": -81.4412},
            ],
        },
    }
    config["local_finder"].update(overrides)
    return config


def _item(rank, title, domain, votes=None):
    return {
        "rank_absolute": rank,
        "title": title,
        "domain": domain,
        "rating": {"value": 5, "votes_count": votes} if votes is not None else {},
    }


def test_matrix_expands_suburb_templates_per_location(tmp_path):
    specs = local_finder.build_matrix(_config(tmp_path))

    queries = {spec["query"] for spec in specs}
    assert "mobile detailing beachwood" in queries
    assert "mobile detailing solon" in queries
    # A literal (non-template) query is asked once per location, not mangled.
    assert sum(1 for s in specs if s["query"] == "car detailing near me") == 2
    assert len(specs) == 4


def test_rank_beyond_the_pack_is_recorded_not_flattened():
    """The whole reason this module exists: rank 6 must not read as absent."""
    items = [
        _item(1, "Joel's Mobile Detailing", "joels.com"),
        _item(2, "Mavics Mobile Auto Detailing", "mavics.com"),
        _item(3, "Cleo's Mobile Detailing", "cleos.com"),
        _item(4, "Rehab Detailing", "rehab.com"),
        _item(5, "Car Care Co.", "carcareco.com"),
        _item(6, "Fresh Mobile Detailing", "freshmobiledetail.com", votes=16),
    ]
    spec = {"query": "mobile detailing beachwood", "location_name": "Beachwood",
            "location_coordinate": "41.4645000,-81.5087000"}

    row = local_finder.parse_result(spec, items, TARGETS)

    assert row["fmd_rank"] == 6
    assert row["fmd_in_pack"] is False
    assert row["fmd_reviews"] == 16
    assert len(row["competitors_above"]) == 3


def test_pack_rank_is_flagged_distinctly():
    items = [
        _item(1, "Refresh Mobile Detailing", "refreshmobiledetailingcle.com"),
        _item(2, "Fresh Mobile Detailing", "freshmobiledetail.com", votes=16),
    ]
    spec = {"query": "mobile detailing mayfield heights", "location_name": "Mayfield Heights",
            "location_coordinate": "41.5192000,-81.4390000"}

    row = local_finder.parse_result(spec, items, TARGETS)

    assert row["fmd_rank"] == 2
    assert row["fmd_in_pack"] is True


def test_absent_target_records_none_without_inventing_a_rank():
    items = [_item(1, "Nathan's Detailing", "nathansdetailing.com")]
    spec = {"query": "car detailing solon", "location_name": "Solon",
            "location_coordinate": "41.3897000,-81.4412000"}

    row = local_finder.parse_result(spec, items, TARGETS)

    assert row["fmd_rank"] is None
    assert row["fmd_in_pack"] is False
    assert row["nathans_rank"] == 1


def test_aggregate_separates_ranked_from_packed():
    rows = [
        {"fmd_rank": 2, "fmd_in_pack": True, "fmd_reviews": 16},
        {"fmd_rank": 6, "fmd_in_pack": False, "fmd_reviews": 16},
        {"fmd_rank": None, "fmd_in_pack": False, "fmd_reviews": None},
    ]

    records = local_finder.aggregate(rows)

    assert records == {"pairs_tested": 3, "pairs_ranked": 2, "pairs_in_pack": 1,
                       "best_rank": 2, "reviews": 16}


def test_estimate_and_cap_block_an_oversized_matrix(tmp_path):
    config = _config(tmp_path)
    config["budget"]["endpoint_caps_usd"]["local_finder"] = 0.001

    payload, rows = local_finder.run(config, client=object())

    assert payload["status"] == "BLOCK"
    assert rows == []
    assert "exceeds local_finder cap" in payload["blockers"][0]


class _FakeLedger:
    def __init__(self): self.settled = []
    def reserve(self, endpoint, amount): return {"endpoint": endpoint, "amount": amount}
    def settle(self, reservation, actual, note): self.settled.append((actual, note))


class _FakeClient:
    """Fails one cell so the partial-run path is exercised for real."""
    def __init__(self, fail_on=None):
        self.ledger = _FakeLedger()
        self.fail_on = fail_on
        self.calls = []

    def _request(self, endpoint, payload):
        keyword = payload[0]["keyword"]
        self.calls.append(keyword)
        if keyword == self.fail_on:
            raise RuntimeError("transport blew up")
        return {"tasks": [{"cost": 0.004, "result": [{"items": [
            _item(2, "Fresh Mobile Detailing", "freshmobiledetail.com", votes=16),
        ]}]}]}


def test_failed_cell_is_reported_and_blocks_the_observation(tmp_path):
    client = _FakeClient(fail_on="car detailing near me")

    payload, rows = local_finder.run(
        _config(tmp_path), client=client, sleep_s=0,
        observations_dir=tmp_path / "obs", evidence_dir=tmp_path / "evidence",
    )

    assert payload["status"] == "PARTIAL"
    assert payload["failed"] == 2       # the literal query runs at both locations
    assert "observation" not in payload  # a half-run must not reset the clock
    # The failed cells still settled at zero, so a dead call cannot bill.
    assert (0.0, ) in {(amount,) for amount, _note in client.ledger.settled}


def test_clean_run_settles_every_call_against_the_ledger(tmp_path):
    client = _FakeClient()

    payload, rows = local_finder.run(
        _config(tmp_path), client=client, sleep_s=0,
        observations_dir=tmp_path / "obs", evidence_dir=tmp_path / "evidence",
    )

    assert payload["failed"] == 0
    assert len(rows) == 4
    assert payload["cost_usd"] == pytest.approx(0.016)
    assert len(client.ledger.settled) == 4


def test_same_day_runs_preserve_both_evidence_files(tmp_path):
    evidence_dir = tmp_path / "evidence"
    first, _ = local_finder.run(
        _config(tmp_path), client=_FakeClient(), sleep_s=0,
        observations_dir=tmp_path / "obs", evidence_dir=evidence_dir,
    )
    first_bytes = Path(first["results"]).read_bytes()
    second, _ = local_finder.run(
        _config(tmp_path), client=_FakeClient(), sleep_s=0,
        observations_dir=tmp_path / "obs", evidence_dir=evidence_dir,
    )

    assert first["results"] != second["results"]
    assert Path(first["results"]).read_bytes() == first_bytes
