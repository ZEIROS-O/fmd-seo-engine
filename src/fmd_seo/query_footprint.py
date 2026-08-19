"""Finalized GSC query and query/page rows, and near-winner aggregation.

Two datasets, one artifact. GSC's `aggregationType: auto` aggregates by page, so
a query ranking on two site pages appears twice in a query+page pull and its
impressions double-count. Summing those rows to a query total inflates the
near-winner impression buckets and *understates* CTR, which manufactures false
`ctr_leak_queries`. So the query totals, CTR, and GSC's own aggregated position
come from a query-only pull; the query+page pull is kept only for page coverage
and evidence mapping.

`Observation.source` is a single string with a single `source_sha256`, so two
evidence files cannot both be cited — one would be silently orphaned. Both
datasets therefore live in one content-addressed artifact, each labelled with
its own `dimensions`.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any


MAX_TOP_ROWS = 25_000

QUERY_DIMENSIONS = ["query"]
QUERY_PAGE_DIMENSIONS = ["query", "page"]

ARTIFACT_PREFIX = "gsc-query-footprint-top-rows-"


def write_top_rows_artifact(artifact: dict[str, Any], *, directory: Path) -> Path:
    """Persist immutable normalized rows without pretending the result is exhaustive.

    The content address is the digest of the *compact* encoding while the file is
    written pretty-printed, so `file_sha256(path)` deliberately does not equal the
    digest in the filename. The address identifies the JSON value, not the bytes;
    verify by re-encoding the parsed body, not by hashing the file.
    """
    encoded = json.dumps(
        artifact, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ARTIFACT_PREFIX}{digest}.json"
    rendered = json.dumps(artifact, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(rendered)
    except FileExistsError:
        if json.loads(path.read_text(encoding="utf-8")) != artifact:
            raise ValueError(f"content-address collision at {path}") from None
    return path


def _page_search_analytics(
    service,
    *,
    site_url: str,
    dimensions: list[str],
    start: date,
    end: date,
    page_size: int,
) -> list[dict[str, Any]]:
    """Page one Search Analytics dimension set up to MAX_TOP_ROWS."""
    rows: list[dict[str, Any]] = []
    searchanalytics = service.searchanalytics()
    while len(rows) < MAX_TOP_ROWS:
        limit = min(page_size, MAX_TOP_ROWS - len(rows))
        body = {
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            "dimensions": list(dimensions),
            "dataState": "final",
            "aggregationType": "auto",
            "rowLimit": limit,
            "startRow": len(rows),
        }
        batch = searchanalytics.query(siteUrl=site_url, body=body).execute().get("rows") or []
        rows.extend(batch[:limit])
        if len(batch) < limit:
            break
    return rows


def fetch_top_rows(
    service,
    *,
    site_url: str,
    today: date | None = None,
    page_size: int = 5_000,
) -> dict[str, Any]:
    """Pull both dimension sets over the finalized 28-day window into one artifact."""
    current = today or date.today()
    end = current - timedelta(days=3)
    start = end - timedelta(days=27)
    datasets = [
        {
            "dimensions": list(dimensions),
            "rows": _page_search_analytics(
                service,
                site_url=site_url,
                dimensions=dimensions,
                start=start,
                end=end,
                page_size=page_size,
            ),
        }
        for dimensions in (QUERY_DIMENSIONS, QUERY_PAGE_DIMENSIONS)
    ]
    return {
        "coverage": "top_rows",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "row_limit": MAX_TOP_ROWS,
        "datasets": datasets,
    }


def dataset_rows(artifact: dict[str, Any], dimensions: list[str]) -> list[dict[str, Any]]:
    """Return the rows of one labelled dataset. Missing is an error, not empty —
    an absent dataset must never read as "measured zero" (GATE-4)."""
    for dataset in artifact.get("datasets") or []:
        if list(dataset.get("dimensions") or []) == list(dimensions):
            return list(dataset.get("rows") or [])
    raise KeyError(f"artifact carries no {dimensions} dataset")


def _finite_float(value: Any) -> float | None:
    """Coerce to a finite float, or None. NaN and ±inf are not measurements."""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _count(value: Any) -> int:
    """Coerce a non-negative integer count. Anything uncoercible reads as zero."""
    parsed = _finite_float(value)
    if parsed is None:
        return 0
    return max(int(parsed), 0)


def _valid_position(value: Any) -> float | None:
    """A usable SERP position: finite and strictly positive. Position 0, a
    negative, NaN and ±inf are all provider pollution — they are rejected here,
    *before* impressions are accumulated, so an invalid row contributes to no
    bucket at all rather than only being dropped from the position average."""
    parsed = _finite_float(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _band(position: float) -> str | None:
    if position <= 3:
        return "one_three"
    if position <= 10:
        return "four_ten"
    if position <= 20:
        return "eleven_twenty"
    return None


_CTR_FLOOR = {"one_three": 0.10, "four_ten": 0.03, "eleven_twenty": 0.01}

# Substring tokens, lowercased at use. These are navigational / brand-name
# queries, not discovery. "fresh" alone is not the brand — All Things Fresh
# is a competitor and "showroom fresh" / "fresh finish" are generic.
BRAND_TOKENS = (
    "fresh mobile",       # current name stem
    "freshmobiledetail",  # domain / handle
    "fresh detail",       # shorthand; also covers drive fresh detail(ing)
    "drive fresh",        # retired brand
)


def aggregate_rows(
    query_rows: list[dict[str, Any]],
    page_rows: list[dict[str, Any]],
    *,
    pages_in_sitemap: int,
    brand_tokens: tuple[str, ...] = BRAND_TOKENS,
) -> dict[str, int]:
    """Near-winner inventory from the query dataset; page coverage from the pair."""
    grouped: dict[str, dict[str, float]] = {}
    for row in query_rows:
        keys = row.get("keys") or []
        if not keys:
            continue
        position = _valid_position(row.get("position", 0))
        if position is None:
            continue
        query = str(keys[0])
        impressions = _count(row.get("impressions", 0))
        clicks = _count(row.get("clicks", 0))
        current = grouped.setdefault(
            query,
            {
                "impressions": 0.0,
                "clicks": 0.0,
                "position_impressions": 0.0,
                "position_weighted_sum": 0.0,
                "position_sum": 0.0,
                "position_rows": 0.0,
            },
        )
        current["impressions"] += impressions
        current["clicks"] += clicks
        current["position_sum"] += position
        current["position_rows"] += 1
        if impressions > 0:
            current["position_impressions"] += impressions
            current["position_weighted_sum"] += position * impressions

    # A query-only pull returns one row per query, so this normally reads GSC's
    # own aggregated position straight through. The weighting only matters if
    # the provider ever splits a query across rows.
    queries = {"one_three": 0, "four_ten": 0, "eleven_twenty": 0}
    impressions_by_band = {"one_three": 0, "four_ten": 0, "eleven_twenty": 0}
    ctr_leaks = 0
    for values in grouped.values():
        if values["position_impressions"]:
            position = values["position_weighted_sum"] / values["position_impressions"]
        else:
            position = values["position_sum"] / values["position_rows"]
        impressions = int(values["impressions"])
        ctr = values["clicks"] / impressions if impressions else 0.0
        band = _band(position)
        if band is None:
            continue
        queries[band] += 1
        impressions_by_band[band] += impressions
        if impressions >= 10 and ctr < _CTR_FLOOR[band]:
            ctr_leaks += 1

    pages: set[str] = set()
    for row in page_rows:
        keys = row.get("keys") or []
        if len(keys) < 2:
            continue
        if _count(row.get("impressions", 0)) > 0:
            pages.add(str(keys[1]))

    lowered_tokens = tuple(token.lower() for token in brand_tokens)
    nonbranded = sum(
        1 for query in grouped
        if not any(token in query.lower() for token in lowered_tokens)
    )
    return {
        "total_queries": len(grouped),
        "nonbranded_queries": nonbranded,
        "queries_pos_1_3": queries["one_three"],
        "queries_pos_4_10": queries["four_ten"],
        "queries_pos_11_20": queries["eleven_twenty"],
        "impressions_pos_1_3": impressions_by_band["one_three"],
        "impressions_pos_4_10": impressions_by_band["four_ten"],
        "impressions_pos_11_20": impressions_by_band["eleven_twenty"],
        "impressions_pos_4_20": (
            impressions_by_band["four_ten"] + impressions_by_band["eleven_twenty"]
        ),
        "ctr_leak_queries": ctr_leaks,
        "pages_with_impressions": len(pages),
        "pages_in_sitemap": pages_in_sitemap,
    }
