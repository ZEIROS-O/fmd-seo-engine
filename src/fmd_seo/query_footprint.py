"""Finalized GSC query/page rows and near-winner aggregation."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any


MAX_TOP_ROWS = 25_000


def write_top_rows_artifact(artifact: dict[str, Any], *, directory: Path) -> Path:
    """Persist immutable normalized rows without pretending the result is exhaustive."""
    encoded = json.dumps(
        artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"gsc-query-page-top-rows-{digest}.json"
    rendered = json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    except FileExistsError:
        if json.loads(path.read_text(encoding="utf-8")) != artifact:
            raise ValueError(f"content-address collision at {path}") from None
    return path


def fetch_top_rows(
    service,
    *,
    site_url: str,
    today: date | None = None,
    page_size: int = 5_000,
) -> dict[str, Any]:
    current = today or date.today()
    end = current - timedelta(days=3)
    start = end - timedelta(days=27)
    rows: list[dict[str, Any]] = []
    searchanalytics = service.searchanalytics()
    while len(rows) < MAX_TOP_ROWS:
        limit = min(page_size, MAX_TOP_ROWS - len(rows))
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": ["query", "page"],
            "dataState": "final",
            "aggregationType": "auto",
            "rowLimit": limit,
            "startRow": len(rows),
        }
        batch = searchanalytics.query(siteUrl=site_url, body=body).execute().get("rows") or []
        rows.extend(batch[:limit])
        if len(batch) < limit:
            break
    return {
        "coverage": "top_rows",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "dimensions": ["query", "page"],
        "row_limit": MAX_TOP_ROWS,
        "rows": rows,
    }


def aggregate_rows(
    rows: list[dict[str, Any]],
    *,
    pages_in_sitemap: int,
    brand_tokens: tuple[str, ...] = ("fresh mobile detailing", "fresh mobile detail"),
) -> dict[str, int]:
    grouped: dict[str, dict[str, float]] = {}
    pages: set[str] = set()
    for row in rows:
        keys = row.get("keys") or []
        if len(keys) < 2:
            continue
        query, page = str(keys[0]), str(keys[1])
        impressions = max(int(row.get("impressions", 0)), 0)
        clicks = max(int(row.get("clicks", 0)), 0)
        position = float(row.get("position", 0))
        current = grouped.setdefault(
            query,
            {
                "impressions": 0.0,
                "clicks": 0.0,
                "position_impressions": 0.0,
                "position_weighted_sum": 0.0,
            },
        )
        current["impressions"] += impressions
        current["clicks"] += clicks
        if position > 0 and impressions > 0:
            current["position_impressions"] += impressions
            current["position_weighted_sum"] += position * impressions
        if impressions > 0:
            pages.add(page)

    buckets = {"one_three": 0, "four_ten": 0, "eleven_twenty": 0}
    impressions_pos_4_20 = 0
    ctr_leaks = 0
    for values in grouped.values():
        position = (
            values["position_weighted_sum"] / values["position_impressions"]
            if values["position_impressions"]
            else 0.0
        )
        impressions = int(values["impressions"])
        ctr = values["clicks"] / impressions if impressions else 0.0
        threshold = None
        if 0 < position <= 3:
            buckets["one_three"] += 1
            threshold = 0.10
        elif 0 < position <= 10:
            buckets["four_ten"] += 1
            impressions_pos_4_20 += impressions
            threshold = 0.03
        elif 0 < position <= 20:
            buckets["eleven_twenty"] += 1
            impressions_pos_4_20 += impressions
            threshold = 0.01
        if threshold is not None and impressions >= 10 and ctr < threshold:
            ctr_leaks += 1

    lowered_tokens = tuple(token.lower() for token in brand_tokens)
    nonbranded = sum(
        1 for query in grouped
        if not any(token in query.lower() for token in lowered_tokens)
    )
    return {
        "total_queries": len(grouped),
        "nonbranded_queries": nonbranded,
        "queries_pos_1_3": buckets["one_three"],
        "queries_pos_4_10": buckets["four_ten"],
        "queries_pos_11_20": buckets["eleven_twenty"],
        "impressions_pos_4_20": impressions_pos_4_20,
        "ctr_leak_queries": ctr_leaks,
        "pages_with_impressions": len(pages),
        "pages_in_sitemap": pages_in_sitemap,
    }
