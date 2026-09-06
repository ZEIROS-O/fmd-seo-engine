import json
from pathlib import Path

from fmd_seo.serp_bulk import (
    build_task_payload,
    competitor_records,
    estimate_cost_usd,
    load_keywords,
    matches_target,
    normalize_result,
    position_records,
)
from fmd_seo.keyword_seeds import classify


def test_467_keyword_depth_20_estimate_stays_under_approved_cap():
    assert estimate_cost_usd(467, depth=20, page_price_usd=0.0006) == 0.5604


def test_load_keywords_deduplicates_case_insensitively(tmp_path: Path):
    source = tmp_path / "keywords.txt"
    source.write_text("Car Detailing\ncar detailing\nmobile detailing\n", encoding="utf-8")

    assert load_keywords(source) == ["Car Detailing", "mobile detailing"]


def test_shared_taxonomy_classifies_canonical_orange_place():
    assert classify("car detailing orange ohio")["suburb"] is True


def test_build_task_payload_is_coordinate_accurate_mobile_and_bounded():
    payload = build_task_payload(
        ["car detailing near me"],
        coordinate="41.4645,-81.5087,200",
        targets={"fmd": {"domain": "freshmobiledetail.com", "aliases": []}},
        depth=20,
        tag_prefix="test",
    )

    assert payload == [{
        "keyword": "car detailing near me",
        "language_code": "en",
        "location_coordinate": "41.4645,-81.5087,200",
        "device": "mobile",
        "os": "android",
        "depth": 20,
        "tag": "test-001",
        "stop_crawl_on_match": [{
            "match_value": "freshmobiledetail.com",
            "match_type": "with_subdomains",
        }],
        "target_search_mode": "all",
        "find_targets_in": ["organic", "local_pack"],
    }]


def test_target_matching_handles_subdomain_url_and_business_title():
    target = {
        "domain": "freshmobiledetail.com",
        "aliases": ["Fresh Mobile Detailing"],
    }
    assert matches_target({"domain": "www.freshmobiledetail.com"}, target)
    assert matches_target({"url": "https://freshmobiledetail.com/areas"}, target)
    assert matches_target({"title": "Fresh Mobile Detailing - Cleveland"}, target)


def test_position_records_count_top3_top10_and_top20():
    rows = [
        {"fmd_organic_position": 1},
        {"fmd_organic_position": 8},
        {"fmd_organic_position": 20},
        {"fmd_organic_position": None},
    ]
    assert position_records(rows, expected_keywords=4) == {
        "blocked": False,
        "keywords_tracked": 4,
        "keywords_missing": 0,
        "top10_count": 2,
        "top3_count": 1,
        "top20_count": 3,
    }


def test_normalized_serp_preserves_top_ten_consensus_inputs():
    result = {
        "datetime": "2026-08-12T12:00:00Z",
        "item_types": ["organic", "people_also_ask"],
        "items": [
            {
                "type": "organic",
                "rank_group": rank,
                "rank_absolute": rank,
                "domain": f"example{rank}.test",
                "url": f"https://example{rank}.test/page",
                "title": f"Winner {rank}",
                "description": f"Snippet {rank}",
            }
            for rank in range(1, 12)
        ],
    }
    row = normalize_result(
        "mobile detailing cleveland",
        result,
        {"fmd": {"domain": "freshmobiledetail.com", "aliases": []}},
    )

    assert len(row["organic_top10"]) == 10
    assert row["organic_top10"][0] == {
        "rank": 1,
        "rank_absolute": 1,
        "result_type": "organic",
        "url": "https://example1.test/page",
        "title": "Winner 1",
        "snippet": "Snippet 1",
    }
    assert row["serp_features"] == ["organic", "people_also_ask"]


def test_competitor_records_reuses_same_dataset_and_detects_new_domains():
    rows = [{
        "keyword": "car detailing",
        "fmd_organic_position": 8,
        "page1_domains": ["freshmobiledetail.com", "newdetailer.com"],
    }]
    previous = [{
        "keyword": "car detailing",
        "page1_domains": ["freshmobiledetail.com", "old-detailer.com"],
    }]

    assert competitor_records(
        rows,
        head_terms=["car detailing"],
        previous_rows=previous,
    ) == {
        "head_terms_checked": 1,
        "fmd_page1_count": 1,
        "new_entrants": 1,
    }


def test_cli_serp_bulk_dry_run_posts_nothing(tmp_path: Path):
    import os
    import subprocess
    import yaml

    engine_root = Path(__file__).resolve().parents[1]
    keywords = tmp_path / "keywords.txt"
    keywords.write_text("one\ntwo\n", encoding="utf-8")
    config = {
        "schema_version": 1,
        "budget": {
            "total_usd": 50,
            "endpoint_caps_usd": {"serp_bulk": 0.60},
        },
        "paths": {"position_keywords": str(keywords)},
        "creds_env": str(tmp_path / "missing.env"),
        "serp_bulk": {
            "coordinate": "41.4645,-81.5087,200",
            "depth": 20,
            "page_price_usd": 0.0006,
            "targets": {"fmd": {"domain": "freshmobiledetail.com", "aliases": []}},
        },
    }
    cfg = tmp_path / "engine.yaml"
    cfg.write_text(yaml.safe_dump(config), encoding="utf-8")

    result = subprocess.run(
        ["python3", "-m", "fmd_seo", "--config", str(cfg), "serp-bulk", "--dry-run"],
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PYTHONPATH": str(engine_root / "src"),
            "FMD_SEO_ROOT": str(tmp_path / "engine-root"),
        },
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["tasks"] == 2
    assert payload["estimated_cost_usd"] == 0.0024
    assert payload["posted"] == 0
    assert not (tmp_path / "engine-root" / ".run" / "spend.json").exists()
