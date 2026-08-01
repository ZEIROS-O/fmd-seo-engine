#!/usr/bin/env python3
"""Build the canonical Data Analytics artifact for the FMD SEO reconciliation."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _integer(value: str | None) -> int | None:
    return int(value) if value not in (None, "") else None


def _source(source_id: str, label: str, path: str) -> dict:
    return {
        "id": source_id,
        "label": label,
        "path": "evidence/fmd-search-visibility-reconciliation-2026-07-19/report-transformations.sql",
        "href": path,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--semrush-dir", type=Path, required=True)
    parser.add_argument("--pdf-dir", type=Path, required=True)
    parser.add_argument("--geo-dir", type=Path, required=True)
    parser.add_argument("--api-summary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).isoformat()
    semrush = _json(args.semrush_dir / "position-tracking-summary.json")
    pdf_findings = _json(args.pdf_dir / "pdf-findings.json")
    geo = _json(args.geo_dir / "geo-top20-summary.json")
    map_summary = _json(REPO_ROOT / "evidence" / "geo-map-pack-2026-07-19" / "summary.json")
    api_summary = _json(args.api_summary)
    semrush_rows = _csv(args.semrush_dir / "position-tracking-keywords.csv")
    geo_rows = _csv(args.geo_dir / "geo-top20-keywords.csv")

    requested_rows = [row for row in semrush_rows if row["in_requested_467"] == "True"]
    requested_ranked = [row for row in requested_rows if row["fmd_position"]]
    full_ranked = [row for row in semrush_rows if row["fmd_position"]]
    requested_top = {
        threshold: sum(_integer(row["fmd_position"]) <= threshold for row in requested_ranked)
        for threshold in (3, 10, 20, 100)
    }

    sources = [
        _source(
            "semrush_position_pdf",
            "Semrush Position Tracking Overview PDF - July 19, 2026",
            "evidence/semrush-position-tracking-2026-07-19/position-tracking-keywords.csv",
        ),
        _source(
            "semrush_pdf_findings",
            "Semrush PDF visual inspection findings - July 19, 2026",
            "evidence/semrush-pdfs-2026-07-19/pdf-findings.json",
        ),
        _source(
            "semrush_api_summary",
            "Semrush Position Tracking API partial summary - provider date July 20, 2026",
            "evidence/semrush-position-tracking-2026-07-20/partial-summary.json",
        ),
        _source(
            "dataforseo_geo",
            "DataForSEO mobile top-20 SERPs at the FMD operating coordinate",
            "evidence/geo-top20-2026-07-19/geo-top20-keywords.csv",
        ),
        _source(
            "dataforseo_focus_map",
            "DataForSEO two-query live mobile map-pack pull at the FMD operating coordinate",
            "evidence/geo-map-pack-2026-07-19/summary.json",
        ),
        _source(
            "reconciliation_analysis",
            "Reconciliation definitions and data-quality notes",
            "evidence/fmd-search-visibility-reconciliation-2026-07-19/source-notes.md",
        ),
    ]

    competitor_labels = {
        "fmd": "FMD",
        "nathans": "Nathan's",
        "atf": "ATF",
        "refresh": "Refresh",
        "diamond_finish": "Diamond Finish",
    }
    semrush_distribution = pdf_findings["position_tracking"]["competitor_distribution"]
    semrush_coverage = [
        {
            "business": "FMD",
            "domain": "freshmobiledetail.com",
            "top_3": semrush["rank_counts"]["fmd"]["top_3"],
            "top_10": semrush["rank_counts"]["fmd"]["top_10"],
            "top_20": semrush["rank_counts"]["fmd"]["top_20"],
            "top_100": semrush["rank_counts"]["fmd"]["top_100"],
        }
    ]
    for domain, values in semrush_distribution.items():
        name = {
            "nathansdetailing.com": "Nathan's",
            "allthingsfreshcardetailing.com": "ATF",
            "refreshmobiledetailingcle.com": "Refresh",
            "diamondfinishdetailing.com": "Diamond Finish",
        }[domain]
        semrush_coverage.append({"business": name, "domain": domain, **values})
    semrush_coverage.sort(key=lambda row: row["top_100"], reverse=True)

    geo_target_coverage = []
    for key, counts in geo["target_counts"].items():
        geo_target_coverage.append({
            "business": competitor_labels[key],
            "target": key,
            "organic_top_20": counts["organic_top_20"],
            "local_pack": counts["local_pack"],
            "keywords_checked": geo["keywords"],
        })
    geo_target_coverage.sort(key=lambda row: row["organic_top_20"], reverse=True)

    brand_sov = [
        {"business": "FMD", "share_of_voice_percent": 1.9, "scope": "Cleveland / ChatGPT"},
        {"business": "CLE Detailing", "share_of_voice_percent": 16.8, "scope": "Cleveland / ChatGPT"},
        {"business": "Detail Dash", "share_of_voice_percent": 12.4, "scope": "Cleveland / ChatGPT"},
        {"business": "Garrett's", "share_of_voice_percent": 11.3, "scope": "Cleveland / ChatGPT"},
        {"business": "Gould Standard", "share_of_voice_percent": 10.4, "scope": "Cleveland / ChatGPT"},
    ]
    brand_sov.sort(key=lambda row: row["share_of_voice_percent"], reverse=True)

    ranked_table = []
    for row in sorted(full_ranked, key=lambda value: int(value["fmd_position"])):
        segments = [
            label for label in (
                "branded", "near_me", "cleveland", "suburb", "service", "informational"
            ) if row[label] == "True"
        ]
        ranked_table.append({
            "keyword": row["keyword"],
            "position": int(row["fmd_position"]),
            "requested_467": row["in_requested_467"] == "True",
            "segment": ", ".join(segments) or "non-branded",
            "nathans_position": _integer(row["nathans_position"]),
            "refresh_position": _integer(row["refresh_position"]),
            "atf_position": _integer(row["atf_position"]),
        })

    opportunity_rows = []
    for row in geo_rows:
        if row["competitor_ranked_fmd_not"] != "True":
            continue
        competitor_positions = {
            competitor_labels[key]: min(
                [value for value in (
                    _integer(row[f"{key}_organic_position"]),
                    _integer(row[f"{key}_local_pack_position"]),
                ) if value is not None],
                default=None,
            )
            for key in ("nathans", "atf", "refresh", "diamond_finish")
        }
        ranked_competitors = [name for name, value in competitor_positions.items() if value is not None]
        opportunity_rows.append({
            "keyword": row["keyword"],
            "competitors_present": len(ranked_competitors),
            "best_competitor_position": min(
                value for value in competitor_positions.values() if value is not None
            ),
            "competitor_names": ", ".join(ranked_competitors),
            "local_pack_present": row["local_pack_present"] == "True",
            "near_me": row["near_me"] == "True",
            "cleveland_or_suburb": row["cleveland"] == "True" or row["suburb"] == "True",
        })
    opportunity_rows.sort(
        key=lambda row: (
            not row["near_me"], not row["cleveland_or_suburb"],
            -row["competitors_present"], row["best_competitor_position"], row["keyword"],
        )
    )

    local_opportunities = []
    for row in geo_rows:
        if row["local_pack_win"] != "True" and row["local_pack_near_win"] != "True":
            continue
        local_opportunities.append({
            "keyword": row["keyword"],
            "status": "pack win" if row["local_pack_win"] == "True" else "near win",
            "fmd_pack_position": _integer(row["fmd_local_pack_position"]),
            "fmd_organic_position": _integer(row["fmd_organic_position"]),
            "fmd_landing_page": row["fmd_landing_page"] or None,
        })
    local_opportunities.sort(key=lambda row: (row["status"] != "pack win", row["keyword"]))

    focus_pack_rows = []
    for query in map_summary["queries"]:
        for business in query["local_pack"]:
            focus_pack_rows.append({
                "snapshot": "Live 21:03 UTC",
                "keyword": query["keyword"],
                "order": business["order"],
                "business_name": business["business_name"],
                "rating": business["rating"],
                "reviews": business["reviews"],
                "cid": business["cid"],
                "fmd_appears": query["fmd_appears"],
            })
    for keyword in ("car detailing mayfield heights", "car detailing beachwood"):
        row = next(value for value in geo_rows if value["keyword"] == keyword)
        for business in json.loads(row["local_pack_businesses_json"]):
            focus_pack_rows.append({
                "snapshot": "Queued 22:04 UTC",
                "keyword": keyword,
                "order": business["order"],
                "business_name": business["business_name"],
                "rating": business["rating"],
                "reviews": business["reviews"],
                "cid": business["cid"],
                "fmd_appears": bool(row["fmd_local_pack_position"]),
            })

    headline = [{
        "semrush_requested_ranked": len(requested_ranked),
        "semrush_requested_total": len(requested_rows),
        "geo_fmd_organic_top20": geo["target_counts"]["fmd"]["organic_top_20"],
        "geo_fmd_local_pack": geo["target_counts"]["fmd"]["local_pack"],
        "brand_share_of_voice": 0.019,
    }]

    data_quality = [
        {
            "severity": "High",
            "finding": "The daily Position Tracking panel is United States / desktop, not Mayfield Heights / mobile.",
            "impact": "Use it for stable panel trend and competitor breadth, not as a proxy for what a nearby mobile searcher sees.",
        },
        {
            "severity": "High",
            "finding": "The PDF campaign has 479 rows; the requested corpus has 467.",
            "impact": "All 467 requested phrases are present. Twelve extra campaign phrases are preserved separately rather than silently discarded.",
        },
        {
            "severity": "Medium",
            "finding": "The Position Tracking PDF omits landing pages and a machine-readable organic-versus-pack ownership field.",
            "impact": "Landing pages and placement type come from the separate live DataForSEO measurement and must not be relabeled as historical Semrush fields.",
        },
        {
            "severity": "Medium",
            "finding": "Semrush API exposes July 20 while the local date and PDFs are July 19.",
            "impact": "July 19 is the latest user-verifiable completed PDF. July 20 API metrics are retained as a provider-dated provisional snapshot.",
        },
        {
            "severity": "High",
            "finding": "The Mayfield Heights pack changed between two same-coordinate mobile snapshots about one hour apart.",
            "impact": "FMD was third at 21:03 UTC but absent at 22:04 UTC. Treat individual pack ranks as volatile observations and trend repeated identical pulls.",
        },
    ]

    title = "Fresh Mobile Detailing Search Visibility Reconciliation"
    summary_body = f"""## Executive Summary

- **The Semrush export is now complete for the requested corpus.** The PDF contains 479 unique campaign rows, and all 467 requested keywords match exactly. FMD ranks in the top 100 for **{len(requested_ranked)} of the requested 467**; one additional ranked branded phrase belongs to the 12-row campaign-only set.
- **The national campaign shows a large competitive coverage gap.** On July 19, FMD has 17 top-100 rankings across all 479 rows, versus 169 for Nathan's, 88 for All Things Fresh, 73 for Diamond Finish, and 27 for Refresh.
- **The live operating-coordinate pull answers a different question.** It checks mobile results at 41.4645,-81.5087 for all 467 phrases and preserves organic landing pages, local-pack identities, and named-competitor gaps. It cost **${geo['cost_usd']:.4f}**, within the approved $0.60 cap.
- **Local-pack membership is visibly volatile.** FMD was third for the Mayfield Heights focus query at 21:03 UTC, then absent from the pack in a same-coordinate queued snapshot at 22:04 UTC. Beachwood omitted FMD in both snapshots.
- **FMD's AI answer quality is stronger than its reach.** The Cleveland/ChatGPT Brand Performance report shows 1.9% share of voice, eight mentions, and a strong 1.75 average position when mentioned.
"""

    manifest = {
        "version": 1,
        "surface": "report",
        "title": title,
        "description": "Reconciles Semrush campaign PDFs, Semrush API aggregates, Map Rank Tracker, Brand Performance, and coordinate-level mobile SERPs.",
        "generatedAt": generated_at,
        "sources": sources,
        "cards": [
            {
                "id": "card-semrush-ranked",
                "description": "Requested keyword phrases with an FMD position from 1 through 100 on July 19.",
                "dataset": "headline",
                "sourceId": "semrush_position_pdf",
                "metrics": [
                    {"label": "Semrush ranked", "field": "semrush_requested_ranked", "format": "number"},
                    {"label": "Requested corpus", "field": "semrush_requested_total", "format": "number"},
                ],
            },
            {
                "id": "card-geo-organic",
                "description": "Keywords where FMD appears organically in the first 20 mobile results at the operating coordinate.",
                "dataset": "headline",
                "sourceId": "dataforseo_geo",
                "metrics": [{"label": "Live organic top 20", "field": "geo_fmd_organic_top20", "format": "number"}],
            },
            {
                "id": "card-geo-pack",
                "description": "Keywords where FMD appears in the returned three-business local pack.",
                "dataset": "headline",
                "sourceId": "dataforseo_geo",
                "metrics": [{"label": "Live local-pack wins", "field": "geo_fmd_local_pack", "format": "number"}],
            },
            {
                "id": "card-ai-sov",
                "description": "Fresh Mobile Detail share of voice in the Cleveland/ChatGPT Brand Performance query set.",
                "dataset": "headline",
                "sourceId": "semrush_pdf_findings",
                "metrics": [{"label": "AI share of voice", "field": "brand_share_of_voice", "format": "percent"}],
            },
        ],
        "charts": [
            {
                "id": "chart-semrush-top100",
                "title": "Semrush top-100 keyword coverage",
                "subtitle": "All 479 national desktop campaign rows on July 19, 2026",
                "type": "bar",
                "dataset": "semrush_coverage",
                "sourceId": "semrush_position_pdf",
                "encodings": {
                    "x": {"field": "business", "type": "nominal", "label": "Business"},
                    "y": {"field": "top_100", "type": "quantitative", "label": "Keywords in top 100"},
                    "tooltip": [
                        {"field": "top_3", "type": "quantitative", "label": "Top 3"},
                        {"field": "top_10", "type": "quantitative", "label": "Top 10"},
                        {"field": "top_20", "type": "quantitative", "label": "Top 20"},
                    ],
                },
                "layout": "full",
            },
            {
                "id": "chart-geo-coverage",
                "title": "Live organic top-20 coverage",
                "subtitle": "467 mobile searches at 41.4645,-81.5087; local-pack counts retained in the source data",
                "type": "bar",
                "dataset": "geo_target_coverage",
                "sourceId": "dataforseo_geo",
                "encodings": {
                    "x": {"field": "business", "type": "nominal", "label": "Business"},
                    "y": {"field": "organic_top_20", "type": "quantitative", "label": "Keywords with an organic top-20 result"},
                    "tooltip": [
                        {"field": "local_pack", "type": "quantitative", "label": "Local-pack appearances"},
                        {"field": "keywords_checked", "type": "quantitative", "label": "Keywords checked"},
                    ],
                },
                "layout": "full",
            },
            {
                "id": "chart-brand-sov",
                "title": "Cleveland ChatGPT share of voice",
                "subtitle": "Brand Performance query set, July 19, 2026",
                "type": "bar",
                "dataset": "brand_sov",
                "sourceId": "semrush_pdf_findings",
                "encodings": {
                    "x": {"field": "business", "type": "nominal", "label": "Business"},
                    "y": {"field": "share_of_voice_percent", "type": "quantitative", "label": "Share of voice", "unit": "%"},
                    "tooltip": [{"field": "scope", "type": "text", "label": "Scope"}],
                },
                "valueFormat": "number",
                "unit": "%",
                "layout": "full",
            },
        ],
        "tables": [
            {
                "id": "table-fmd-ranked",
                "title": "FMD-ranked Semrush keywords",
                "subtitle": "Exact July 19 positions; the campaign-only Fresh Detailing row is retained and flagged",
                "dataset": "ranked_table",
                "defaultSort": {"field": "position", "direction": "asc"},
                "density": "spacious",
                "sourceId": "semrush_position_pdf",
                "layout": "full",
                "columns": [
                    {"field": "keyword", "label": "Keyword", "type": "text"},
                    {"field": "position", "label": "FMD position", "format": "number"},
                    {"field": "requested_467", "label": "In requested 467", "type": "text"},
                    {"field": "segment", "label": "Cuts", "type": "text"},
                    {"field": "nathans_position", "label": "Nathan's", "format": "number"},
                    {"field": "refresh_position", "label": "Refresh", "format": "number"},
                    {"field": "atf_position", "label": "ATF", "format": "number"},
                ],
            },
            {
                "id": "table-focus-pack",
                "title": "Focus-query local-pack identities across two snapshots",
                "subtitle": "Same coordinate and mobile device; the Mayfield pack changed within about one hour",
                "dataset": "focus_pack_rows",
                "defaultSort": {"field": "keyword", "direction": "asc"},
                "density": "spacious",
                "sourceId": "reconciliation_analysis",
                "layout": "full",
                "columns": [
                    {"field": "snapshot", "label": "Snapshot", "type": "text"},
                    {"field": "keyword", "label": "Keyword", "type": "text"},
                    {"field": "order", "label": "Pack order", "format": "number"},
                    {"field": "business_name", "label": "Business / GBP identity", "type": "text"},
                    {"field": "rating", "label": "Rating", "format": "number"},
                    {"field": "reviews", "label": "Reviews", "format": "number"},
                    {"field": "cid", "label": "Google CID", "type": "text"},
                    {"field": "fmd_appears", "label": "FMD in pack", "type": "text"},
                ],
            },
            {
                "id": "table-local-opportunities",
                "title": "Local-pack wins and near-wins",
                "subtitle": "Near-win means FMD is organic top 10 when a local pack is present but FMD is absent from that pack",
                "dataset": "local_opportunities",
                "defaultSort": {"field": "status", "direction": "asc"},
                "density": "spacious",
                "sourceId": "dataforseo_geo",
                "layout": "full",
                "columns": [
                    {"field": "keyword", "label": "Keyword", "type": "text"},
                    {"field": "status", "label": "Status", "type": "text"},
                    {"field": "fmd_pack_position", "label": "Pack position", "format": "number"},
                    {"field": "fmd_organic_position", "label": "Organic position", "format": "number"},
                    {"field": "fmd_landing_page", "label": "FMD landing page", "type": "text"},
                ],
            },
            {
                "id": "table-opportunities",
                "title": "Highest-priority competitor-only gaps",
                "subtitle": "Near-me and Cleveland/suburb phrases first; full detail remains in the 467-row CSV",
                "dataset": "opportunity_rows",
                "defaultSort": {"field": "competitors_present", "direction": "desc"},
                "density": "dense",
                "sourceId": "dataforseo_geo",
                "layout": "full",
                "columns": [
                    {"field": "keyword", "label": "Keyword", "type": "text"},
                    {"field": "competitors_present", "label": "Competitors present", "format": "number"},
                    {"field": "best_competitor_position", "label": "Best competitor position", "format": "number"},
                    {"field": "competitor_names", "label": "Competitors", "type": "text"},
                    {"field": "local_pack_present", "label": "Local pack", "type": "text"},
                ],
            },
            {
                "id": "table-data-quality",
                "title": "Source and comparability checks",
                "subtitle": "Issues that materially change how the evidence should be used",
                "dataset": "data_quality",
                "defaultSort": {"field": "severity", "direction": "asc"},
                "density": "spacious",
                "sourceId": "reconciliation_analysis",
                "layout": "full",
                "columns": [
                    {"field": "severity", "label": "Severity", "type": "text"},
                    {"field": "finding", "label": "Finding", "type": "text"},
                    {"field": "impact", "label": "How to use it", "type": "text"},
                ],
            },
        ],
        "blocks": [
            {"id": "title", "type": "markdown", "body": f"# {title}"},
            {"id": "executive-summary", "type": "markdown", "body": summary_body},
            {
                "id": "layout-guard",
                "type": "html",
                "body": """<style>html,body,#root{max-width:100%;overflow-x:hidden}.table-card{max-width:100%}</style><div role="note" style="padding:10px 14px;border:1px solid #dbe4ef;border-radius:10px;background:#f8fafc;color:#334155;font:13px/1.45 system-ui,sans-serif">Measurement rule: compare sources at their own grain; do not average national desktop, local-grid, coordinate-mobile, and AI visibility ranks.</div>""",
            },
            {
                "id": "measurement-roles",
                "type": "markdown",
                "body": """## Three measurements answer three different questions

**Semrush Position Tracking** is the repeatable national desktop panel. **Semrush Map Rank Tracker** is a multi-point local grid. **DataForSEO** is the live mobile view anchored to FMD's operating coordinate. Their ranks should be compared as complementary evidence, never averaged into one score.

The visible July 19 PDF is the completed local-day authority. The provider API also exposes a July 20 snapshot with 0.45889% visibility, 0.63373 estimated traffic, and 98.29019 average position; because that date was ahead of the local extraction date, it remains provisional rather than replacing the PDF.""",
            },
            {"id": "headline-strip", "type": "metric-strip", "cardIds": [
                "card-semrush-ranked", "card-geo-organic", "card-geo-pack", "card-ai-sov"
            ]},
            {
                "id": "semrush-section",
                "type": "markdown",
                "body": f"""## FMD has breadth in only {len(requested_ranked)} of the requested 467 phrases

The campaign table contains {len(semrush_rows)} unique rows. Every requested phrase is present, while 12 additional campaign phrases are preserved separately. Within the requested corpus, FMD has {requested_top[3]} top-three, {requested_top[10]} top-ten, {requested_top[20]} top-twenty, and {requested_top[100]} top-100 rankings. The full campaign adds one ranked phrase, **fresh detailing**, at position 72.""",
                "sourceId": "semrush_position_pdf",
            },
            {"id": "semrush-chart", "type": "chart", "chartId": "chart-semrush-top100"},
            {
                "id": "semrush-chart-note",
                "type": "markdown",
                "body": "Nathan's coverage is the dominant competitive fact: its 169 top-100 keywords are almost ten times FMD's 17. ATF and Diamond Finish also carry much broader national visibility, while Refresh has fewer top-100 keywords but still exceeds FMD.",
                "sourceId": "semrush_position_pdf",
            },
            {"id": "semrush-table", "type": "table", "tableId": "table-fmd-ranked"},
            {
                "id": "geo-section",
                "type": "markdown",
                "body": f"""## The coordinate pull turns broad rankings into local actions

All {geo['keywords']} searches used mobile Google results at {geo['location_coordinate']}. This source owns landing pages, local-pack businesses, named competitor placement, pack wins, near-wins, and competitor-only gaps. Those fields are live observations, not backfilled Semrush history.""",
                "sourceId": "dataforseo_geo",
            },
            {"id": "geo-chart", "type": "chart", "chartId": "chart-geo-coverage"},
            {
                "id": "geo-chart-note",
                "type": "markdown",
                "body": "The chart compares how often each named business appears organically in the first 20 results. Local-pack appearances remain available in the chart source and the detail tables because pack presence is a different placement type, not another organic rank.",
            },
            {
                "id": "focus-pack-section",
                "type": "markdown",
                "body": """## The focus-query re-pull confirms Beachwood weakness and Mayfield volatility

At 21:03 UTC, the live Mayfield Heights pack was Refresh, Geauga, then FMD. At 22:04 UTC, the queued observation was Refresh, Geauga, then Zoom Express; FMD was absent. Beachwood omitted FMD in both observations, while its third listing also changed. This is not a reconciliation failure: it is direct evidence that local packs can rotate even when coordinate, device, and query are held constant.""",
                "sourceId": "reconciliation_analysis",
            },
            {"id": "focus-pack-table", "type": "table", "tableId": "table-focus-pack"},
            {"id": "local-table", "type": "table", "tableId": "table-local-opportunities"},
            {"id": "opportunity-table", "type": "table", "tableId": "table-opportunities"},
            {
                "id": "map-section",
                "type": "markdown",
                "body": """## The heatmap confirms a tight mobile-service core, not broad dominance

Visual inspection of all 23 Map Rank Tracker grids shows the strongest green points around **mobile car detailing**, **mobile detailing near me**, **mobile detailing service**, and **mobile car detailing near me**, with best visible ranks around 3 near the center/east-side operating area. Broad car-detailing terms are mostly yellow or red, while interior-detailing grids are unexpectedly sparse despite FMD's interior-first positioning.

That mismatch is actionable: FMD's strongest real-world proposition is not yet producing broad local-grid ownership for the corresponding interior-intent phrases.""",
                "sourceId": "semrush_pdf_findings",
            },
            {
                "id": "ai-section",
                "type": "markdown",
                "body": """## AI visibility is a reach problem more than an answer-quality problem

The Cleveland/ChatGPT Brand Performance report gives FMD 1.9% share of voice, eight mentions, 4.6% mention coverage, and a 1.75 average position when mentioned. The report's recurring strengths are family-interior specialization, documented process, before-and-after proof, low upsell pressure, and east-side trust. Those signals are strong but appear in too few answers.""",
                "sourceId": "semrush_pdf_findings",
            },
            {"id": "brand-chart", "type": "chart", "chartId": "chart-brand-sov"},
            {
                "id": "brand-chart-note",
                "type": "markdown",
                "body": "FMD's 1.9% share is far below the selected peers even though its average position is strong when it appears. The practical priority is expanding the number of relevant contexts that mention FMD without diluting its family-interior and east-side positioning.",
                "sourceId": "semrush_pdf_findings",
            },
            {
                "id": "recommendations",
                "type": "markdown",
                "body": """## Recommended next steps

1. **Make the local mobile panel the operating scorecard.** Repeat the same 467-keyword coordinate/device pull on a fixed cadence and compare like with like.
2. **Prioritize competitor-only gaps with local intent.** Start with near-me and named east-side suburb phrases where a named competitor appears and FMD does not.
3. **Strengthen the interior-intent grid.** Build or improve pages and GBP/service language for interior detailing, interior car detailing, pet hair, odor, salt, and family-mess use cases.
4. **Standardize the trust narrative.** Use consistent names for the checklist, photo quote, before-and-after proof, arrival communication, and low-upsell promise across the site, GBP, reviews, and third-party mentions.
5. **Correct the Semrush campaign target before using it as a local KPI.** A Mayfield Heights/44124 mobile campaign would create a stable daily panel that is comparable to the live local search context.""",
            },
            {
                "id": "further-questions",
                "type": "markdown",
                "body": """## Further questions

- Which competitor-only gaps have enough search volume and commercial intent to justify a dedicated page rather than an FAQ or GBP update?
- Do the live landing pages align with the intended service/suburb page, or is ranking equity landing on a generic page?
- After correcting the Semrush target, how much of the national/desktop gap persists in a Mayfield Heights mobile panel?""",
            },
            {
                "id": "quality-section",
                "type": "markdown",
                "body": """## Caveats and assumptions

The sources are trustworthy for their own grain but not interchangeable. The PDF table supplies exact July 19 national desktop positions. DataForSEO supplies live mobile top-20 and pack observations at one coordinate. Map Rank Tracker supplies multi-point grid evidence. Brand Performance and Competitor Research use different AI platforms, geographies, and query universes, so their visibility values cannot be directly reconciled.""",
            },
            {"id": "quality-table", "type": "table", "tableId": "table-data-quality"},
        ],
    }

    artifact = {
        "surface": "report",
        "manifest": manifest,
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "ready",
            "datasets": {
                "headline": headline,
                "semrush_coverage": semrush_coverage,
                "geo_target_coverage": geo_target_coverage,
                "brand_sov": brand_sov,
                "ranked_table": ranked_table,
                "local_opportunities": local_opportunities,
                "focus_pack_rows": focus_pack_rows,
                "opportunity_rows": opportunity_rows[:60],
                "data_quality": data_quality,
            },
        },
        "sources": sources,
    }
    (args.output_dir / "artifact.json").write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    transformation_sql = """-- Canonical report transformations, expressed in DuckDB SQL.
-- Paths are repository-relative; the Python report builder applies equivalent
-- typed transformations and embeds the reviewed result rows in artifact.json.

WITH semrush AS (
  SELECT * FROM read_csv_auto('evidence/semrush-position-tracking-2026-07-19/position-tracking-keywords.csv', header=true)
)
SELECT
  COUNT(*) FILTER (WHERE in_requested_467) AS requested_keywords,
  COUNT(*) FILTER (WHERE in_requested_467 AND fmd_position IS NOT NULL) AS requested_ranked,
  COUNT(*) FILTER (WHERE fmd_position BETWEEN 1 AND 3) AS fmd_top_3,
  COUNT(*) FILTER (WHERE fmd_position BETWEEN 1 AND 10) AS fmd_top_10,
  COUNT(*) FILTER (WHERE fmd_position BETWEEN 1 AND 20) AS fmd_top_20,
  COUNT(*) FILTER (WHERE fmd_position BETWEEN 1 AND 100) AS fmd_top_100
FROM semrush;

WITH geo AS (
  SELECT * FROM read_csv_auto('evidence/geo-top20-2026-07-19/geo-top20-keywords.csv', header=true)
)
SELECT
  COUNT(*) AS keywords_checked,
  COUNT(*) FILTER (WHERE fmd_organic_position BETWEEN 1 AND 20) AS fmd_organic_top_20,
  COUNT(*) FILTER (WHERE fmd_local_pack_position IS NOT NULL) AS fmd_local_pack,
  COUNT(*) FILTER (WHERE competitor_ranked_fmd_not) AS competitor_only_gaps,
  COUNT(*) FILTER (WHERE local_pack_near_win) AS local_pack_near_wins
FROM geo;

SELECT *
FROM read_json_auto('evidence/semrush-pdfs-2026-07-19/pdf-findings.json');

SELECT *
FROM read_json_auto('evidence/geo-map-pack-2026-07-19/summary.json');
"""
    (args.output_dir / "report-transformations.sql").write_text(
        transformation_sql, encoding="utf-8"
    )

    source_notes = f"""# Source notes

## Audience and structure

- Audience: product stakeholders / owner-operator.
- Delivery mode: portable HTML.
- Required structure mapping: title; Executive Summary; Semrush, live geo, map-grid, and AI findings; recommendations; further questions; caveats.

## Metric and grain definitions

- Semrush requested-ranked count: requested 467-keyword rows with FMD position 1-100 on July 19, 2026.
- DataForSEO organic top 20: target domain appears in an organic item with rank_group 1-20 at the operating coordinate on mobile.
- Local-pack win: FMD appears in the returned three-business local pack.
- Near-win: a local pack is present, FMD is absent from it, and FMD is organic top 10.
- Competitor-only gap: at least one of ATF, Refresh, Nathan's, or Diamond Finish appears organic top 20 or in the local pack while FMD appears in neither.

## Chart map

- Semrush coverage: category comparison / bar; top-100 counts by business; blue single-root palette; supports competitor-breadth finding.
- Live organic coverage: category comparison / bar; 467-keyword organic top-20 counts; blue single-root palette; supports coordinate-level competitive comparison.
- AI share of voice: category comparison / bar; Cleveland ChatGPT SOV; blue single-root palette; supports reach-gap finding.

## Omitted or qualified fields

- Semrush PDF does not contain landing pages or a machine-readable organic-versus-local ownership field.
- Diamond Finish has Semrush distribution counts but no keyword-level PDF column.
- The PDF text layer loses the color-coded sign of position changes. Absolute positions are preserved and validated; change magnitudes are retained with direction marked unavailable.
- The provisional July 20 Semrush API values are disclosed but do not replace the user-verifiable July 19 PDF.
- Heatmap grid ranks were visually reviewed rather than transcribed into a synthetic coordinate table.
- The Mayfield focus-query local pack changed between 21:03 and 22:04 UTC even though coordinate, device, and query were held constant; both observations are preserved.

## Reproducibility

- Semrush PDF rows: `scripts/extract_semrush_position_pdf.py`.
- Geo batch: `scripts/reconstruct_geo_serps.py`.
- Report artifact: `scripts/build_fmd_reconciliation_report.py`.
- DataForSEO paid POST cost: ${geo['cost_usd']:.4f}; GET collection was free.
"""
    (args.output_dir / "source-notes.md").write_text(source_notes, encoding="utf-8")
    print(json.dumps({
        "artifact": str(args.output_dir / "artifact.json"),
        "source_notes": str(args.output_dir / "source-notes.md"),
        "requested_ranked": len(requested_ranked),
        "opportunity_rows": len(opportunity_rows),
        "local_opportunities": len(local_opportunities),
        "api_latest": api_summary["latest_available_date"],
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
