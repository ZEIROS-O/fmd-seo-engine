import json
import os
import subprocess
from pathlib import Path

import yaml

from fmd_seo.geogrid import aggregate_map_pack, build_grid, task_specs


def test_five_by_five_grid_spans_service_radius():
    points = build_grid(41.4645, -81.5087, radius_miles=30, size=5)

    assert len(points) == 25
    assert len({round(point.latitude, 7) for point in points}) == 5
    assert len({round(point.longitude, 7) for point in points}) == 5
    assert min(point.latitude for point in points) < 41.1
    assert max(point.latitude for point in points) > 41.8


def test_grid_task_specs_are_query_by_point_and_costable():
    points = build_grid(41.4645, -81.5087, radius_miles=30, size=5)
    specs = task_specs(["car detailing near me", "mobile detailing near me"], points)

    assert len(specs) == 50
    assert specs[0]["location_coordinate"].endswith(",200")
    assert specs[0]["depth"] == 10


def test_map_pack_aggregation_uses_median_present_rank_and_unique_competitors():
    rows = [
        {
            "query": "car detailing near me",
            "fmd_local_pack_position": 3,
            "local_pack_businesses": [
                {"business_name": "A", "order": 1},
                {"business_name": "B", "order": 2},
                {"business_name": "Fresh Mobile Detailing", "order": 3},
            ],
        },
        {
            "query": "car detailing near me",
            "fmd_local_pack_position": 1,
            "local_pack_businesses": [
                {"business_name": "Fresh Mobile Detailing", "order": 1},
            ],
        },
        {
            "query": "mobile detailing near me",
            "fmd_local_pack_position": None,
            "local_pack_businesses": [{"business_name": "A", "order": 1}],
        },
    ]

    assert aggregate_map_pack(rows, fmd_aliases=["Fresh Mobile Detailing"]) == {
        "queries": 2,
        "points_sampled": 3,
        "points_present": 2,
        "median_rank": 2.0,
        "competitors_above": 2,
    }


def test_cli_geogrid_dry_run_is_exactly_200_tasks_and_12_cents(tmp_path: Path):
    engine_root = Path(__file__).resolve().parents[1]
    facts = tmp_path / "facts.yaml"
    facts.write_text(
        "schema_version: 1\nreviewed_at: 2026-08-01\nreview_after_days: 30\n"
        "service_area:\n  base: Beachwood / Mayfield Heights\n  radius_miles: 30\n",
        encoding="utf-8",
    )
    config = {
        "schema_version": 1,
        "budget": {"total_usd": 50, "endpoint_caps_usd": {"geogrid": 0.12}},
        "paths": {"facts_file": str(facts)},
        "geogrid": {
            "center": [41.4645, -81.5087],
            "size": 5,
            "queries": [f"query {index}" for index in range(8)],
        },
    }
    cfg = tmp_path / "engine.yaml"
    cfg.write_text(yaml.safe_dump(config), encoding="utf-8")

    result = subprocess.run(
        ["python3", "-m", "fmd_seo", "--config", str(cfg), "geogrid", "--dry-run"],
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
    assert payload["tasks"] == 200
    assert payload["estimated_cost_usd"] == 0.12
    assert payload["posted"] == 0
