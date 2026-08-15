"""Read-only outcome reporting over committed observation time series."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .observations import load_observations


METRICS: dict[str, tuple[str, str]] = {
    "indexed": ("seo.indexation", "indexed"),
    "not_indexed": ("seo.indexation", "not_indexed"),
    "points_present": ("seo.map_pack", "points_present"),
    "points_sampled": ("seo.map_pack", "points_sampled"),
    "median_rank": ("seo.map_pack", "median_rank"),
    "top3_count": ("seo.positions", "top3_count"),
    "top10_count": ("seo.positions", "top10_count"),
    "top20_count": ("seo.positions", "top20_count"),
    "nonbranded_queries": ("seo.query_footprint", "nonbranded_queries"),
    "impressions_pos_4_20": ("seo.query_footprint", "impressions_pos_4_20"),
    "aeo_ranked_mentions": ("aeo.recommendation_share", "fmd_ranked_mentions"),
    "searches_discovery": ("gbp.performance", "searches_discovery"),
    "calls": ("gbp.performance", "calls"),
    "our_authority_score": ("competitor.authority_gap", "our_authority_score"),
    "competitor_median_as": ("competitor.authority_gap", "competitor_median_as"),
}


def _stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _event_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _series(check_id: str, field: str, directory: Path) -> list[tuple[datetime, str, float]]:
    rows: list[tuple[datetime, str, float]] = []
    for observation in load_observations(check_id, directory):
        value = observation.records.get(field)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            rows.append((_stamp(observation.observed_at), observation.observed_at, value))
    return rows


def build_report(
    since: str,
    *,
    observations_dir: Path,
    interventions_path: Path,
) -> dict:
    since_at = _stamp(since)
    metric_series = {
        name: _series(check_id, field, observations_dir)
        for name, (check_id, field) in METRICS.items()
    }
    metrics: dict[str, dict] = {}
    for name, rows in metric_series.items():
        window = [row for row in rows if row[0] >= since_at]
        if not window:
            metrics[name] = {"status": "NO_DATA", "first": None, "latest": None, "delta": None}
            continue
        first, latest = window[0], window[-1]
        metrics[name] = {
            "status": "MEASURED" if len(window) > 1 else "BASELINE_ONLY",
            "first": {"observed_at": first[1], "value": first[2]},
            "latest": {"observed_at": latest[1], "value": latest[2]},
            "delta": latest[2] - first[2] if len(window) > 1 else None,
        }

    eligible_events: list[tuple[datetime, dict]] = []
    for event in _event_rows(interventions_path):
        if "merged_at" in event and event["merged_at"] is None:
            continue
        occurred = event.get("merged_at") or event.get("occurred_at")
        if not occurred or _stamp(occurred) < since_at:
            continue
        eligible_events.append((_stamp(occurred), event))
    eligible_events.sort(key=lambda row: row[0])

    interventions: list[dict] = []
    for index, (event_at, event) in enumerate(eligible_events):
        next_event_at = (
            eligible_events[index + 1][0] if index + 1 < len(eligible_events) else None
        )
        movement: dict[str, float | None] = {}
        for name, rows in metric_series.items():
            before = [row for row in rows if row[0] <= event_at]
            after = [
                row for row in rows
                if row[0] > event_at and (next_event_at is None or row[0] <= next_event_at)
            ]
            movement[name] = (
                after[-1][2] - before[-1][2]
                if before and after
                else None
            )
        interventions.append({**event, "metric_movement": movement})

    return {
        "command": "report",
        "since": since,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fetches_performed": 0,
        "metrics": metrics,
        "interventions": interventions,
    }


def append_intervention(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
