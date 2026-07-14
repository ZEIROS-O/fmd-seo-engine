"""Tests for the Semrush client parsing + the pure sync adapters. No network:
adapters are pure functions over parsed CSV, so the parse->records mapping is
verified against fixtures without a live key."""

import pytest

from fmd_seo.semrush import (
    UnitsLedger, SemrushApiFailure, parse_csv, which_checks_are_api_backed,
)
from fmd_seo.sync import (
    adapt_authority_gap, adapt_market_demand, adapt_organic_footprint,
    adapt_related_topics,
)


# ─────────────────────── CSV parsing ───────────────────────

def test_parse_csv_semicolon():
    text = "Ph;Po;Nq\ncar detailing;3;480\nfresh detail;82;90"
    rows = parse_csv(text)
    assert rows == [
        {"Ph": "car detailing", "Po": "3", "Nq": "480"},
        {"Ph": "fresh detail", "Po": "82", "Nq": "90"},
    ]


def test_parse_csv_empty():
    assert parse_csv("") == []
    assert parse_csv("Ph;Po\n") == []  # header only, no rows


def test_parse_csv_positional_ignores_display_header():
    # The real API returns display-name headers, not codes. With `columns` given,
    # rows must be keyed by the requested codes, not the header text.
    text = "Keyword;Search Volume\ncar detailing near me;2400"
    rows = parse_csv(text, columns=["Ph", "Nq"])
    assert rows == [{"Ph": "car detailing near me", "Nq": "2400"}]


# ─────────────────────── units ledger ───────────────────────

def test_units_ledger_caps():
    ledger = UnitsLedger(cap_units=50)
    ledger.reserve(40)
    with pytest.raises(SemrushApiFailure, match="units cap"):
        ledger.reserve(20)


# ─────────────────────── adapters ───────────────────────

def test_adapt_organic_footprint_counts_branded_and_page1():
    rows = [
        {"Ph": "fresh detail", "Po": "82"},      # branded
        {"Ph": "fresh detailing", "Po": "90"},   # branded
        {"Ph": "car detailing near me", "Po": "7"},   # non-branded, page 1
        {"Ph": "auto detailing cleveland", "Po": "15"},  # non-branded, not page 1
    ]
    rec = adapt_organic_footprint(rows)
    assert rec == {"total_keywords": 4, "nonbranded_keywords": 2, "page1_keywords": 1}


def test_adapt_organic_footprint_empty():
    assert adapt_organic_footprint([]) == {
        "total_keywords": 0, "nonbranded_keywords": 0, "page1_keywords": 0}


def test_adapt_authority_gap_median_odd():
    ours = [{"ascore": "2", "total": "211", "domains_num": "106"}]
    rec = adapt_authority_gap(ours, [7, 7, 8, 9, 16])
    assert rec["our_authority_score"] == 2
    assert rec["competitor_median_as"] == 8  # median of 5
    assert rec["our_referring_domains"] == 106


def test_adapt_authority_gap_median_even():
    ours = [{"ascore": "2", "domains_num": "106"}]
    rec = adapt_authority_gap(ours, [7, 9])
    assert rec["competitor_median_as"] == 8  # (7+9)//2


def test_adapt_market_demand_picks_near_me():
    rows = [
        {"Ph": "car detailing", "Nq": "500", "Td": "0.8,0.9"},
        {"Ph": "car detailing near me", "Nq": "2350", "Td": "0.7,1.0,0.9"},
    ]
    rec = adapt_market_demand(rows)
    assert rec["near_me_volume"] == 2350
    assert rec["trend_direction"] == "0.7,1.0,0.9"


def test_adapt_related_topics_volume_filter():
    rows = [
        {"Ph": "how to detail a car", "Nq": "300"},
        {"Ph": "obscure phrase", "Nq": "0"},
    ]
    rec = adapt_related_topics(rows)
    assert rec == {"candidates_found": 2, "candidates_with_volume": 1}


# ─────────────────── api-backing map ───────────────────

def test_api_backed_map_covers_exactly_sync_implemented():
    m = which_checks_are_api_backed()
    assert "seo.organic_footprint" in m
    assert "competitor.authority_gap" in m
    assert "market.demand" in m
    assert "topics.related_clusters" in m
    # Projects-API checks are not wired yet
    assert "seo.positions" not in m
    assert "seo.site_health" not in m
    # serp_movement has a report but needs judgment — must NOT be labeled
    # engine_api, or the planner would promise a fetch sync never does.
    assert "competitor.serp_movement" not in m


def test_sync_no_key_reports_skipped(tmp_path, monkeypatch):
    from fmd_seo.sync import sync_due
    # config points creds at a nonexistent file -> no key -> honest skip
    config = {"creds_env": str(tmp_path / "nope.env")}
    result = sync_due(config, observations_dir=tmp_path / "obs")
    assert result.fetched == []
    assert result.errors == {}
    # the API-backed checks with no prior observation are due -> listed as skipped
    assert "topics.related_clusters" in result.skipped_no_key
