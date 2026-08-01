#!/usr/bin/env python3
"""Preserve and normalize a Semrush Position Tracking campaign snapshot.

Raw provider responses go to ignored ``.run/raw`` state. The durable evidence
directory receives normalized CSV/JSON only; credentials are never serialized.
"""

from __future__ import annotations

import argparse
import csv
import json
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime
from pathlib import Path

from fmd_seo.semrush import load_key


PROJECT_ID = 30426612
CAMPAIGN_ID = "30426612_5133685"
BUSINESS_NAME = "Fresh Mobile Detailing"
EXPECTED_UNIQUE_KEYWORDS = 467

DOMAINS = {
    "fmd": "*.freshmobiledetail.com/*",
    "atf": "*.allthingsfreshcardetailing.com/*",
    "refresh": "*.refreshmobiledetailingcle.com/*",
    "nathans": "*.nathansdetailing.com/*",
    "diamond_finish": "*.diamondfinishdetailing.com/*",
}

SUBURBS = (
    "beachwood", "mayfield heights", "lyndhurst", "pepper pike", "orange",
    "solon", "shaker heights", "university heights", "cleveland heights",
    "chagrin falls", "moreland hills", "gates mills", "highland heights",
    "south euclid", "mentor", "willoughby", "euclid", "wickliffe", "bedford",
    "twinsburg", "hudson",
)

SERVICE_TERMS = (
    "detail", "car wash", "car clean", "interior clean", "exterior clean",
    "ceramic coat", "paint correction", "stain remov", "odor remov",
    "pet hair", "shampoo", "wax", "polish", "scratch remov", "headlight",
    "engine bay", "rv wash", "boat clean",
)

INTENT_LABELS = {
    "i": "informational",
    "n": "navigational",
    "c": "commercial",
    "t": "transactional",
}


def _api_json(url: str, *, timeout_s: int = 90) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout_s) as response:
        return json.loads(response.read().decode("utf-8"))


def _report(key: str, campaign_id: str, report_type: str, **params) -> dict:
    query = {"type": report_type, "key": key, "action": "report", **params}
    url = (
        f"https://api.semrush.com/reports/v1/projects/{campaign_id}/tracking/?"
        + urllib.parse.urlencode(query)
    )
    return _api_json(url)


def _campaigns(key: str, project_id: int) -> dict:
    url = (
        f"https://api.semrush.com/management/v1/projects/{project_id}/tracking/campaigns?"
        + urllib.parse.urlencode({"key": key})
    )
    return _api_json(url)


def _data_rows(report: dict) -> list[dict]:
    data = report.get("data") or {}
    if isinstance(data, list):
        return data
    return [data[key] for key in sorted(data, key=lambda value: int(value))]


def _position(value) -> int | None:
    if value in (None, "", "-"):
        return None
    return int(value)


def _dated_domain(row: dict, field: str, date: str, domain: str, default=None):
    by_date = row.get(field) or {}
    values = by_date.get(date) or {}
    return values.get(domain, default)


def _intent_codes(row: dict) -> list[str]:
    intent = row.get("In") or {}
    values = intent.values() if isinstance(intent, dict) else intent
    return sorted({str(value).lower() for value in values if value})


def _tag_values(row: dict) -> list[str]:
    tags = row.get("Tg") or {}
    values = tags.values() if isinstance(tags, dict) else tags
    return sorted({str(value) for value in values if value})


def _classify(keyword: str, intent_codes: list[str]) -> dict[str, bool]:
    phrase = " ".join(keyword.lower().split())
    branded = "fresh mobile detailing" in phrase or "freshmobiledetail" in phrase
    return {
        "cut_branded": branded,
        "cut_non_branded": not branded,
        "cut_near_me": "near me" in phrase,
        "cut_cleveland": "cleveland" in phrase,
        "cut_suburb": any(place in phrase for place in SUBURBS),
        "cut_service": any(term in phrase for term in SERVICE_TERMS),
        "cut_informational": "i" in intent_codes,
    }


def _normalize_rows(combined: dict, organic: dict, local: dict, date: str) -> list[dict]:
    combined_rows = _data_rows(combined)
    organic_by_id = {str(row["Pi"]): row for row in _data_rows(organic)}
    local_by_id = {str(row["Pi"]): row for row in _data_rows(local)}
    fmd = DOMAINS["fmd"]
    rows = []

    for source in combined_rows:
        keyword_id = str(source["Pi"])
        organic_source = organic_by_id.get(keyword_id, {})
        local_source = local_by_id.get(keyword_id, {})
        fmd_position = _position(_dated_domain(source, "Dt", date, fmd))
        fmd_organic = _position(_dated_domain(organic_source, "Dt", date, fmd))
        fmd_local = _position(_dated_domain(local_source, "Dt", date, fmd))
        if fmd_organic is not None and fmd_local is not None:
            placement = "organic+local_pack"
        elif fmd_local is not None:
            placement = "local_pack"
        elif fmd_organic is not None:
            placement = "organic"
        elif fmd_position is not None:
            placement = "other_serp_feature"
        else:
            placement = "unranked"

        intent_codes = _intent_codes(source)
        row = {
            "keyword_id": keyword_id,
            "keyword": source.get("Ph", ""),
            "keyword_added_date": str(source.get("Kb") or ""),
            "tags": "|".join(_tag_values(source)),
            "intent_codes": "|".join(intent_codes),
            "intent_labels": "|".join(INTENT_LABELS.get(code, code) for code in intent_codes),
            "search_volume": int(float(source.get("Nq") or 0)),
            "cpc_usd": float(source.get("Cp") or 0),
            "serp_features": "|".join((source.get("Sf") or {}).get(date) or []),
            "fmd_position": fmd_position,
            "fmd_placement": placement,
            "fmd_organic_position": fmd_organic,
            "fmd_local_pack_position": fmd_local,
            "fmd_landing_page": _dated_domain(source, "Lu", date, fmd, "") or "",
            "fmd_link_types": "|".join(_dated_domain(source, "Lt", date, fmd, []) or []),
            "atf_position": _position(_dated_domain(source, "Dt", date, DOMAINS["atf"])),
            "refresh_position": _position(_dated_domain(source, "Dt", date, DOMAINS["refresh"])),
            "nathans_position": _position(_dated_domain(source, "Dt", date, DOMAINS["nathans"])),
            "diamond_finish_position": _position(
                _dated_domain(source, "Dt", date, DOMAINS["diamond_finish"])
            ),
        }
        row.update(_classify(row["keyword"], intent_codes))
        competitor_positions = [
            row["atf_position"], row["refresh_position"], row["nathans_position"],
            row["diamond_finish_position"],
        ]
        row["local_pack_win"] = fmd_local is not None and fmd_local <= 3
        row["local_pack_near_win"] = fmd_local is not None and 4 <= fmd_local <= 10
        row["near_win"] = fmd_position is not None and 4 <= fmd_position <= 10
        row["competitor_only"] = fmd_position is None and any(
            position is not None for position in competitor_positions
        )
        rows.append(row)

    return rows


def _write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _cut_summary(rows: list[dict], cut: str) -> dict:
    selected = [row for row in rows if row[cut]]
    return {
        "keywords": len(selected),
        "fmd_ranked": sum(row["fmd_position"] is not None for row in selected),
        "fmd_top_10": sum(
            row["fmd_position"] is not None and row["fmd_position"] <= 10 for row in selected
        ),
        "fmd_organic_ranked": sum(row["fmd_organic_position"] is not None for row in selected),
        "fmd_local_pack_ranked": sum(
            row["fmd_local_pack_position"] is not None for row in selected
        ),
        "competitor_only": sum(row["competitor_only"] for row in selected),
    }


def _dated_metrics(report: dict, date: str) -> dict:
    for row in _data_rows(report):
        if str(row.get("Dt")) == date:
            return row
    return {}


def extract(*, key_file: Path, output_dir: Path, raw_dir: Path,
            project_id: int = PROJECT_ID, campaign_id: str = CAMPAIGN_ID) -> dict:
    key = load_key(key_file)
    campaigns = _campaigns(key, project_id)
    campaign = next(
        (item for item in campaigns.get("campaigns") or [] if item.get("id") == campaign_id),
        None,
    )
    if campaign is None:
        raise RuntimeError(f"campaign {campaign_id} not found in project {project_id}")

    dates = _report(key, campaign_id, "tracking_campaign_dates")
    available_dates = sorted(str(row["Dt"]) for row in _data_rows(dates))
    if not available_dates:
        raise RuntimeError(f"campaign {campaign_id} has no harvested dates")
    latest = available_dates[-1]

    shared = {
        "date_begin": latest,
        "date_end": latest,
        "display_limit": 500,
        "business_name": BUSINESS_NAME,
    }
    combined = _report(
        key, campaign_id, "tracking_position_organic",
        url=":".join(DOMAINS.values()), linktype_filter=0, **shared,
    )
    organic = _report(
        key, campaign_id, "tracking_position_organic",
        url=DOMAINS["fmd"], linktype_filter=2, **shared,
    )
    local = _report(
        key, campaign_id, "tracking_position_organic",
        url=DOMAINS["fmd"], linktype_filter=1, **shared,
    )
    overview = _report(
        key, campaign_id, "tracking_overview_organic",
        url=DOMAINS["fmd"], date_begin=latest, date_end=latest,
        business_name=BUSINESS_NAME, linktype_filter=0,
    )
    visibility = _report(
        key, campaign_id, "tracking_visibility_organic",
        url=DOMAINS["fmd"], date_begin=latest, date_end=latest,
        business_name=BUSINESS_NAME, linktype_filter=0,
    )

    rows = _normalize_rows(combined, organic, local, latest)
    keyword_counts = Counter(" ".join(row["keyword"].lower().split()) for row in rows)
    duplicate_phrases = sorted(
        ({"keyword": keyword, "rows": count} for keyword, count in keyword_counts.items() if count > 1),
        key=lambda item: (-item["rows"], item["keyword"]),
    )
    unique_keyword_count = len(keyword_counts)

    overview_total = int(overview.get("total") or 0)
    overview_ranked = int(overview.get("all") or 0)
    visibility_metrics = _dated_metrics(visibility, latest)
    derived = {
        "top_3": sum(row["fmd_position"] is not None and row["fmd_position"] <= 3 for row in rows),
        "top_10": sum(row["fmd_position"] is not None and row["fmd_position"] <= 10 for row in rows),
        "top_20": sum(row["fmd_position"] is not None and row["fmd_position"] <= 20 for row in rows),
        "top_100": sum(row["fmd_position"] is not None and row["fmd_position"] <= 100 for row in rows),
    }
    provider = {
        "visibility_percent": float(visibility_metrics.get("Vr") or overview.get("visibility") or 0),
        "estimated_traffic": float(visibility_metrics.get("Tr") or 0),
        "average_position": float(visibility_metrics.get("Av") or 0),
        "top_3": int(overview.get("top3") or 0),
        "top_10": int(overview.get("top10") or 0),
        "top_20": int(overview.get("top20") or 0),
        "top_100": overview_ranked,
        "unranked": overview_total - overview_ranked,
    }

    cuts = {
        cut.removeprefix("cut_"): _cut_summary(rows, cut)
        for cut in (
            "cut_branded", "cut_non_branded", "cut_near_me", "cut_cleveland",
            "cut_suburb", "cut_service", "cut_informational",
        )
    }
    summary = {
        "source": "Semrush Position Tracking Projects API",
        "extracted_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "project_id": project_id,
        "campaign_id": campaign_id,
        "campaign": campaign,
        "business_name_query": BUSINESS_NAME,
        "business_name_note": (
            "Used as the report parameter that includes Google Business Profile/local-pack "
            "rankings; the campaign-list endpoint does not expose a stored business name."
        ),
        "available_dates": available_dates,
        "latest_available_date": latest,
        "keyword_counts": {
            "campaign_configured_rows": int(campaign.get("keywords_count") or 0),
            "report_rows": len(rows),
            "unique_normalized_keywords": unique_keyword_count,
            "expected_unique_keywords": EXPECTED_UNIQUE_KEYWORDS,
            "duplicate_phrase_groups": len(duplicate_phrases),
            "duplicate_rows_beyond_unique": len(rows) - unique_keyword_count,
        },
        "provider_metrics": provider,
        "derived_distribution": derived,
        "metric_reconciliation": {
            "top_3_matches": provider["top_3"] == derived["top_3"],
            "top_10_matches": provider["top_10"] == derived["top_10"],
            "top_20_matches": provider["top_20"] == derived["top_20"],
            "top_100_matches": provider["top_100"] == derived["top_100"],
        },
        "cuts": cuts,
        "opportunity_counts": {
            "local_pack_wins": sum(row["local_pack_win"] for row in rows),
            "local_pack_near_wins": sum(row["local_pack_near_win"] for row in rows),
            "near_wins_positions_4_to_10": sum(row["near_win"] for row in rows),
            "competitors_rank_fmd_unranked": sum(row["competitor_only"] for row in rows),
        },
        "duplicate_phrases": duplicate_phrases,
        "cut_definitions": {
            "branded": "Contains 'fresh mobile detailing' or 'freshmobiledetail'.",
            "non_branded": "Does not match the branded rule.",
            "near_me": "Contains the literal phrase 'near me'.",
            "cleveland": "Contains 'cleveland', including Cleveland Heights.",
            "suburb": "Contains one of the configured east-side/service-area suburb names.",
            "service": "Contains a detailing, cleaning, coating, wash, restoration, or care service term.",
            "informational": "Semrush intent includes the informational code 'i'.",
            "near_win": "FMD's combined Semrush position is 4 through 10.",
            "local_pack_win": "FMD's local-pack-only position is 1 through 3.",
            "local_pack_near_win": "FMD's local-pack-only position is 4 through 10.",
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw_path = raw_dir / f"semrush-position-tracking-{latest}.json"
    raw_path.write_text(json.dumps({
        "campaigns": campaigns,
        "dates": dates,
        "positions_combined": combined,
        "positions_organic": organic,
        "positions_local_pack": local,
        "overview": overview,
        "visibility": visibility,
    }, indent=2, sort_keys=True), encoding="utf-8")

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    fields = list(rows[0].keys()) if rows else []
    _write_csv(output_dir / "keyword-positions.csv", rows, fields)
    _write_csv(
        output_dir / "local-pack-wins.csv",
        [row for row in rows if row["local_pack_win"]], fields,
    )
    _write_csv(
        output_dir / "near-wins.csv",
        [row for row in rows if row["near_win"] or row["local_pack_near_win"]], fields,
    )
    competitor_only = sorted(
        (row for row in rows if row["competitor_only"]),
        key=lambda row: (-row["search_volume"], row["keyword"]),
    )
    _write_csv(output_dir / "competitor-only.csv", competitor_only, fields)

    return {
        "summary": str(summary_path),
        "keyword_positions": str(output_dir / "keyword-positions.csv"),
        "raw": str(raw_path),
        "latest_available_date": latest,
        "report_rows": len(rows),
        "unique_normalized_keywords": unique_keyword_count,
        "provider_metrics": provider,
        "opportunity_counts": summary["opportunity_counts"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--key-file", type=Path, default=Path("/home/lucascoh/.dataforseo.env"))
    parser.add_argument("--output-dir", type=Path, default=Path("evidence/semrush-position-tracking"))
    parser.add_argument("--raw-dir", type=Path, default=Path(".run/raw"))
    args = parser.parse_args()
    print(json.dumps(extract(
        key_file=args.key_file,
        output_dir=args.output_dir,
        raw_dir=args.raw_dir,
    ), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
