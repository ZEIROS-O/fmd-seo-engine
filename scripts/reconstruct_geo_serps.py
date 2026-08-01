#!/usr/bin/env python3
"""Queue and collect a bounded 467-keyword geo-anchored mobile SERP pull.

The standard DataForSEO queue is used instead of the higher-cost live endpoint.
Posting and collection are separate commands so callers can do useful work while
the provider processes tasks.  The existing spend ledger enforces the approved
run ceiling before each paid POST.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_semrush_position_pdf import classify  # noqa: E402
from fmd_seo.dataforseo import DataForSeoClient  # noqa: E402
from fmd_seo.spend import SpendLedger  # noqa: E402


POST_ENDPOINT = "/v3/serp/google/organic/task_post"
GET_ENDPOINT = "/v3/serp/google/organic/task_get/advanced/{task_id}"
COORDINATE = "41.4645,-81.5087,200"
DEPTH = 20
PAGE_PRICE_USD = 0.0006
MAX_RUN_USD = 0.60
CHUNK_SIZE = 100

TARGETS = {
    "fmd": {
        "domain": "freshmobiledetail.com",
        "aliases": ("fresh mobile detailing", "fresh mobile detail"),
    },
    "atf": {
        "domain": "allthingsfreshcardetailing.com",
        "aliases": ("all things fresh car detailing", "all things fresh"),
    },
    "refresh": {
        "domain": "refreshmobiledetailingcle.com",
        "aliases": ("refresh mobile detailing",),
    },
    "nathans": {
        "domain": "nathansdetailing.com",
        "aliases": ("nathan's detailing", "nathans detailing"),
    },
    "diamond_finish": {
        "domain": "diamondfinishdetailing.com",
        "aliases": ("diamond finish detailing", "diamond finish"),
    },
}


def _load_keywords(path: Path) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        keyword = line.strip()
        if not keyword or keyword.casefold() in seen:
            continue
        seen.add(keyword.casefold())
        values.append(keyword)
    if len(values) != 467:
        raise RuntimeError(f"expected 467 unique keywords; got {len(values)}")
    return values


def _load_manifest(path: Path, keyword_file: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema_version": 1,
        "source_keyword_file": str(keyword_file.resolve().relative_to(REPO_ROOT)),
        "location_coordinate": COORDINATE,
        "device": "mobile",
        "os": "android",
        "depth": DEPTH,
        "approved_run_cap_usd": MAX_RUN_USD,
        "posted_at": None,
        "completed_at": None,
        "post_cost_usd": 0.0,
        "tasks": [],
    }


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _cost(body: dict, fallback: float) -> float:
    if body.get("cost") is not None:
        return float(body["cost"])
    task_costs = [float(task.get("cost") or 0.0) for task in body.get("tasks") or []]
    return sum(task_costs) if any(task_costs) else fallback


def _client() -> DataForSeoClient:
    ledger = SpendLedger(
        REPO_ROOT / ".run" / "spend.json",
        total_cap_usd=0.95,
        endpoint_caps_usd={"probe": 0.05, "serp_bulk": MAX_RUN_USD},
    )
    return DataForSeoClient(Path("/home/lucascoh/.dataforseo.env"), ledger, timeout_s=60)


def post_tasks(keyword_file: Path, manifest_path: Path) -> int:
    keywords = _load_keywords(keyword_file)
    manifest = _load_manifest(manifest_path, keyword_file)
    completed = {task["keyword"].casefold() for task in manifest["tasks"]}
    pending = [keyword for keyword in keywords if keyword.casefold() not in completed]
    if not pending:
        print(json.dumps({"posted": 0, "total_tasks": len(manifest["tasks"]), "status": "already_posted"}))
        return 0

    client = _client()
    balance = client.probe()["balance_usd"]
    maximum_remaining = len(pending) * (DEPTH // 10) * PAGE_PRICE_USD
    if float(balance or 0.0) < maximum_remaining:
        raise RuntimeError(
            f"provider balance ${float(balance or 0.0):.6f} is below bounded "
            f"maximum ${maximum_remaining:.6f}"
        )

    posted_now = 0
    for offset in range(0, len(pending), CHUNK_SIZE):
        chunk = pending[offset:offset + CHUNK_SIZE]
        payload = []
        for keyword in chunk:
            absolute_index = keywords.index(keyword) + 1
            payload.append({
                "keyword": keyword,
                "language_code": "en",
                "location_coordinate": COORDINATE,
                "device": "mobile",
                "os": "android",
                "depth": DEPTH,
                "tag": f"fmd-geo-20260719-{absolute_index:03d}",
                "stop_crawl_on_match": [
                    {"match_value": target["domain"], "match_type": "with_subdomains"}
                    for target in TARGETS.values()
                ],
                "target_search_mode": "all",
                "find_targets_in": ["organic", "local_pack"],
            })

        estimate = len(chunk) * (DEPTH // 10) * PAGE_PRICE_USD
        reservation = client.ledger.reserve("serp_bulk", estimate)
        try:
            body = client._request(POST_ENDPOINT, payload)
        except Exception:
            # The reservation remains open so a retry cannot exceed the cap if
            # the provider accepted the request before the transport failed.
            raise
        actual = _cost(body, estimate)
        client.ledger.settle(reservation, actual, POST_ENDPOINT)

        tasks = body.get("tasks") or []
        if len(tasks) != len(chunk):
            raise RuntimeError(f"posted {len(chunk)} tasks but provider returned {len(tasks)} task receipts")
        for keyword, receipt in zip(chunk, tasks):
            if not receipt.get("id"):
                raise RuntimeError(
                    f"task was not created for {keyword!r}: "
                    f"{receipt.get('status_code')} {receipt.get('status_message')}"
                )
            manifest["tasks"].append({
                "keyword": keyword,
                "tag": (receipt.get("data") or {}).get("tag"),
                "task_id": receipt["id"],
                "post_status_code": receipt.get("status_code"),
                "post_status_message": receipt.get("status_message"),
                "post_cost_usd": float(receipt.get("cost") or 0.0),
            })
        manifest["post_cost_usd"] = round(float(manifest["post_cost_usd"]) + actual, 6)
        manifest["posted_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(manifest_path, manifest)
        posted_now += len(chunk)
        print(json.dumps({
            "posted_chunk": len(chunk),
            "posted_now": posted_now,
            "total_tasks": len(manifest["tasks"]),
            "actual_cost_usd": actual,
            "cumulative_cost_usd": manifest["post_cost_usd"],
        }), flush=True)

    return 0


def _normalize_domain(value: str | None) -> str:
    return (value or "").casefold().removeprefix("www.")


def _normalize_title(value: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).split())


def _matches_target(item: dict, target: dict) -> bool:
    domain = _normalize_domain(item.get("domain"))
    url = (item.get("url") or "").casefold()
    title = _normalize_title(item.get("title"))
    target_domain = target["domain"]
    title_matches = any(
        title == _normalize_title(alias)
        or title.startswith(_normalize_title(alias) + " ")
        for alias in target["aliases"]
    )
    return (
        domain == target_domain
        or domain.endswith("." + target_domain)
        or target_domain in url
        or title_matches
    )


def _task_result(body: dict) -> tuple[str, dict | None]:
    tasks = body.get("tasks") or []
    if not tasks:
        return "pending", None
    task = tasks[0]
    if task.get("status_code") != 20000 or not task.get("result"):
        return "pending", None
    return "ready", task["result"][0]


def _normalize(keyword: str, result: dict) -> dict:
    items = result.get("items") or []
    organic = [item for item in items if item.get("type") == "organic"]
    local_pack = [item for item in items if item.get("type") == "local_pack"]
    row: dict[str, object] = {
        "keyword": keyword,
        "provider_datetime": result.get("datetime"),
        "check_url": result.get("check_url"),
        "se_results_count": result.get("se_results_count"),
        "local_pack_present": bool(local_pack),
        "local_pack_businesses": [
            {
                "order": item.get("rank_group"),
                "rank_absolute": item.get("rank_absolute"),
                "business_name": item.get("title"),
                "cid": item.get("cid"),
                "domain": item.get("domain"),
                "url": item.get("url"),
                "phone": item.get("phone"),
                "rating": (item.get("rating") or {}).get("value"),
                "reviews": (item.get("rating") or {}).get("votes_count"),
            }
            for item in local_pack
        ],
    }
    row.update(classify(keyword))

    for key, target in TARGETS.items():
        organic_matches = [item for item in organic if _matches_target(item, target)]
        local_matches = [item for item in local_pack if _matches_target(item, target)]
        organic_match = min(
            organic_matches,
            key=lambda item: item.get("rank_group") or item.get("rank_absolute") or 999,
            default=None,
        )
        local_match = min(
            local_matches,
            key=lambda item: item.get("rank_group") or item.get("rank_absolute") or 999,
            default=None,
        )
        row[f"{key}_organic_position"] = organic_match.get("rank_group") if organic_match else None
        row[f"{key}_organic_rank_absolute"] = organic_match.get("rank_absolute") if organic_match else None
        row[f"{key}_landing_page"] = organic_match.get("url") if organic_match else None
        row[f"{key}_local_pack_position"] = local_match.get("rank_group") if local_match else None

    fmd_present = row["fmd_organic_position"] is not None or row["fmd_local_pack_position"] is not None
    competitor_present = any(
        row[f"{key}_organic_position"] is not None or row[f"{key}_local_pack_position"] is not None
        for key in ("atf", "refresh", "nathans", "diamond_finish")
    )
    row["local_pack_win"] = row["fmd_local_pack_position"] is not None
    row["local_pack_near_win"] = (
        bool(row["local_pack_present"])
        and row["fmd_local_pack_position"] is None
        and row["fmd_organic_position"] is not None
        and int(row["fmd_organic_position"]) <= 10
    )
    row["competitor_ranked_fmd_not"] = competitor_present and not fmd_present
    return row


def _get_one(client: DataForSeoClient, task: dict, raw_dir: Path) -> tuple[str, dict | None]:
    raw_path = raw_dir / f"{task['task_id']}.json"
    if raw_path.exists():
        body = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        body = client._request(GET_ENDPOINT.format(task_id=task["task_id"]))
        status, _ = _task_result(body)
        if status == "ready":
            _write_json(raw_path, body)
    status, result = _task_result(body)
    return status, _normalize(task["keyword"], result) if result else None


def collect_tasks(manifest_path: Path, output_dir: Path) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tasks = manifest["tasks"]
    if len(tasks) != 467:
        raise RuntimeError(f"manifest has {len(tasks)} tasks; expected 467")
    raw_dir = REPO_ROOT / ".run" / "raw" / "geo-top20-2026-07-19"
    raw_dir.mkdir(parents=True, exist_ok=True)
    client = _client()

    rows: list[dict] = []
    pending = 0
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(_get_one, client, task, raw_dir): task for task in tasks}
        for future in as_completed(futures):
            status, row = future.result()
            if status == "ready" and row is not None:
                rows.append(row)
            else:
                pending += 1

    print(json.dumps({"ready": len(rows), "pending": pending}), flush=True)
    if pending:
        return 2

    order = {task["keyword"].casefold(): index for index, task in enumerate(tasks)}
    rows.sort(key=lambda row: order[row["keyword"].casefold()])
    output_dir.mkdir(parents=True, exist_ok=True)

    jsonl_path = output_dir / "geo-top20-results.jsonl"
    jsonl_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )

    csv_rows = []
    for row in rows:
        flat = {key: value for key, value in row.items() if key != "local_pack_businesses"}
        flat["local_pack_businesses_json"] = json.dumps(row["local_pack_businesses"], sort_keys=True)
        csv_rows.append(flat)
    csv_path = output_dir / "geo-top20-keywords.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(csv_rows[0]))
        writer.writeheader()
        writer.writerows(csv_rows)

    target_counts = {}
    for key in TARGETS:
        target_counts[key] = {
            "organic_top_20": sum(row[f"{key}_organic_position"] is not None for row in rows),
            "local_pack": sum(row[f"{key}_local_pack_position"] is not None for row in rows),
        }
    summary = {
        "source": "DataForSEO Google Organic Standard Queue Advanced",
        "captured_at": max((row["provider_datetime"] or "") for row in rows),
        "location_coordinate": manifest["location_coordinate"],
        "device": manifest["device"],
        "depth": manifest["depth"],
        "keywords": len(rows),
        "cost_usd": manifest["post_cost_usd"],
        "target_counts": target_counts,
        "local_pack_wins": [row["keyword"] for row in rows if row["local_pack_win"]],
        "local_pack_near_wins": [row["keyword"] for row in rows if row["local_pack_near_win"]],
        "competitor_ranked_fmd_not": [
            row["keyword"] for row in rows if row["competitor_ranked_fmd_not"]
        ],
        "cuts": {
            cut: {
                "keywords": sum(bool(row[cut]) for row in rows),
                "fmd_organic_top_20": sum(
                    bool(row[cut]) and row["fmd_organic_position"] is not None for row in rows
                ),
                "fmd_local_pack": sum(
                    bool(row[cut]) and row["fmd_local_pack_position"] is not None for row in rows
                ),
                "competitor_ranked_fmd_not": sum(
                    bool(row[cut]) and bool(row["competitor_ranked_fmd_not"]) for row in rows
                ),
            }
            for cut in (
                "branded", "non_branded", "near_me", "cleveland",
                "suburb", "service", "informational",
            )
        },
        "definitions": {
            "local_pack_win": "FMD appears in the returned three-business local pack.",
            "local_pack_near_win": (
                "A local pack is present, FMD is absent from it, and FMD has an organic top-10 result."
            ),
            "competitor_ranked_fmd_not": (
                "At least one named competitor appears organically in the top 20 or in the local pack, "
                "while FMD appears in neither."
            ),
        },
        "raw_payload_manifest_sha256": hashlib.sha256(
            "".join(sorted(path.name for path in raw_dir.glob("*.json"))).encode()
        ).hexdigest(),
    }
    _write_json(output_dir / "geo-top20-summary.json", summary)
    manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
    _write_json(manifest_path, manifest)
    print(json.dumps({
        "csv": str(csv_path),
        "jsonl": str(jsonl_path),
        "summary": str(output_dir / "geo-top20-summary.json"),
    }))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    post = subparsers.add_parser("post")
    post.add_argument("--keywords", type=Path, required=True)
    post.add_argument("--manifest", type=Path, required=True)
    collect = subparsers.add_parser("collect")
    collect.add_argument("--manifest", type=Path, required=True)
    collect.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "post":
        return post_tasks(args.keywords, args.manifest)
    return collect_tasks(args.manifest, args.output_dir)


if __name__ == "__main__":
    raise SystemExit(main())
