"""Resumable, capped DataForSEO standard-queue SERP tracking.

Posting and collection stay separate: a task manifest is the durable resume
point, raw provider payloads remain in ``.run/raw``, and only normalized rows
and observations become committed evidence.
"""

from __future__ import annotations

import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths
from .dataforseo import DataForSeoClient
from .keyword_seeds import classify
from .spend import SpendLedger

POST_ENDPOINT = "/v3/serp/google/organic/task_post"
GET_ENDPOINT = "/v3/serp/google/organic/task_get/advanced/{task_id}"
DEFAULT_PAGE_PRICE_USD = 0.0006
DEFAULT_DEPTH = 20
CHUNK_SIZE = 100  # provider hard limit per POST


def load_keywords(path: Path) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        keyword = " ".join(line.split())
        folded = keyword.casefold()
        if keyword and folded not in seen:
            seen.add(folded)
            values.append(keyword)
    if not values:
        raise ValueError(f"no keywords found in {path}")
    return values


def estimate_cost_usd(
    keyword_count: int,
    *,
    depth: int = DEFAULT_DEPTH,
    page_price_usd: float = DEFAULT_PAGE_PRICE_USD,
) -> float:
    if keyword_count < 0 or depth <= 0 or page_price_usd < 0:
        raise ValueError("keyword_count, depth, and page price must be non-negative")
    pages = math.ceil(depth / 10)
    return round(keyword_count * pages * page_price_usd, 6)


def _normalize_domain(value: str | None) -> str:
    return (value or "").casefold().removeprefix("www.")


def _normalize_title(value: str | None) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (value or "").casefold()).split())


def matches_target(item: dict, target: dict) -> bool:
    domain = _normalize_domain(item.get("domain"))
    url = (item.get("url") or "").casefold()
    title = _normalize_title(item.get("title"))
    target_domain = _normalize_domain(target["domain"])
    title_matches = any(
        title == _normalize_title(alias)
        or title.startswith(_normalize_title(alias) + " ")
        for alias in target.get("aliases", [])
    )
    return (
        domain == target_domain
        or domain.endswith("." + target_domain)
        or target_domain in url
        or title_matches
    )


def build_task_payload(
    keywords: list[str],
    *,
    coordinate: str,
    targets: dict[str, dict],
    depth: int = DEFAULT_DEPTH,
    tag_prefix: str = "fmd-serp",
) -> list[dict]:
    payload: list[dict] = []
    stop_targets = [
        {"match_value": target["domain"], "match_type": "with_subdomains"}
        for target in targets.values()
    ]
    for index, keyword in enumerate(keywords, start=1):
        payload.append({
            "keyword": keyword,
            "language_code": "en",
            "location_coordinate": coordinate,
            "device": "mobile",
            "os": "android",
            "depth": depth,
            "tag": f"{tag_prefix}-{index:03d}",
            "stop_crawl_on_match": stop_targets,
            "target_search_mode": "all",
            "find_targets_in": ["organic", "local_pack"],
        })
    return payload


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def _cost(body: dict, fallback: float) -> float:
    if body.get("cost") is not None:
        return float(body["cost"])
    task_costs = [float(task.get("cost") or 0.0) for task in body.get("tasks") or []]
    return sum(task_costs) if any(task_costs) else fallback


def _settings(config: dict) -> tuple[Path, dict, int, float, str]:
    bulk = config["serp_bulk"]
    keyword_file = Path(config["paths"]["position_keywords"])
    return (
        keyword_file,
        bulk["targets"],
        int(bulk.get("depth", DEFAULT_DEPTH)),
        float(bulk.get("page_price_usd", DEFAULT_PAGE_PRICE_USD)),
        str(bulk["coordinate"]),
    )


def dry_run(config: dict) -> dict:
    keyword_file, _targets, depth, page_price, coordinate = _settings(config)
    keywords = load_keywords(keyword_file)
    estimate = estimate_cost_usd(len(keywords), depth=depth, page_price_usd=page_price)
    cap = float(config["budget"]["endpoint_caps_usd"]["serp_bulk"])
    return {
        "command": "serp-bulk",
        "mode": "dry-run",
        "keyword_file": str(keyword_file),
        "tasks": len(keywords),
        "depth": depth,
        "coordinate": coordinate,
        "estimated_cost_usd": estimate,
        "endpoint_cap_usd": cap,
        "within_cap": estimate <= cap,
        "posted": 0,
    }


def _manifest_path(config: dict) -> Path:
    configured = (config.get("serp_bulk") or {}).get("manifest")
    return Path(configured) if configured else paths.SERP_BULK_MANIFEST


def _load_manifest(config: dict, keyword_file: Path) -> dict:
    path = _manifest_path(config)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    bulk = config["serp_bulk"]
    return {
        "schema_version": 1,
        "source_keyword_file": str(keyword_file),
        "location_coordinate": bulk["coordinate"],
        "device": "mobile",
        "os": "android",
        "depth": int(bulk.get("depth", DEFAULT_DEPTH)),
        "approved_run_cap_usd": float(
            config["budget"]["endpoint_caps_usd"]["serp_bulk"]
        ),
        "posted_at": None,
        "completed_at": None,
        "post_cost_usd": 0.0,
        "tasks": [],
    }


def _client(config: dict) -> DataForSeoClient:
    ledger = SpendLedger(
        paths.SPEND_LEDGER,
        config["budget"]["total_usd"],
        config["budget"]["endpoint_caps_usd"],
    )
    return DataForSeoClient(
        Path(config["creds_env"]),
        ledger,
        systemic_failures_to_kill=config["limits"]["systemic_failures_to_kill"],
        timeout_s=60,
    )


def post_tasks(config: dict) -> dict:
    keyword_file, targets, depth, page_price, coordinate = _settings(config)
    keywords = load_keywords(keyword_file)
    manifest_path = _manifest_path(config)
    manifest = _load_manifest(config, keyword_file)
    completed = {task["keyword"].casefold() for task in manifest["tasks"]}
    pending = [keyword for keyword in keywords if keyword.casefold() not in completed]
    if not pending:
        return {
            "command": "serp-bulk", "mode": "post", "posted": 0,
            "total_tasks": len(manifest["tasks"]), "status": "already_posted",
            "manifest": str(manifest_path),
        }

    maximum_remaining = estimate_cost_usd(
        len(pending), depth=depth, page_price_usd=page_price,
    )
    cap = float(config["budget"]["endpoint_caps_usd"]["serp_bulk"])
    if float(manifest["post_cost_usd"]) + maximum_remaining > cap:
        raise ValueError(
            f"SERP bulk estimate ${maximum_remaining:.4f} plus prior manifest spend "
            f"would exceed ${cap:.2f} cap"
        )
    client = _client(config)
    balance = float(client.probe().get("balance_usd") or 0.0)
    if balance < maximum_remaining:
        raise ValueError(
            f"provider balance ${balance:.4f} is below bounded estimate "
            f"${maximum_remaining:.4f}"
        )

    posted_now = 0
    tag_prefix = "fmd-serp-" + datetime.now(timezone.utc).strftime("%Y%m%d")
    for offset in range(0, len(pending), CHUNK_SIZE):
        chunk = pending[offset:offset + CHUNK_SIZE]
        payload = build_task_payload(
            chunk,
            coordinate=coordinate,
            targets=targets,
            depth=depth,
            tag_prefix=f"{tag_prefix}-{offset:03d}",
        )
        estimate = estimate_cost_usd(len(chunk), depth=depth, page_price_usd=page_price)
        reservation = client.ledger.reserve("serp_bulk", estimate)
        body = client._request(POST_ENDPOINT, payload)
        actual = _cost(body, estimate)
        client.ledger.settle(reservation, actual, POST_ENDPOINT)
        receipts = body.get("tasks") or []
        if len(receipts) != len(chunk):
            raise RuntimeError(
                f"posted {len(chunk)} tasks but provider returned {len(receipts)} receipts"
            )
        for keyword, receipt in zip(chunk, receipts):
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
    return {
        "command": "serp-bulk", "mode": "post", "posted": posted_now,
        "total_tasks": len(manifest["tasks"]),
        "cost_usd": manifest["post_cost_usd"], "manifest": str(manifest_path),
    }


def _task_result(body: dict) -> tuple[str, dict | None]:
    tasks = body.get("tasks") or []
    if not tasks:
        return "pending", None
    task = tasks[0]
    if task.get("status_code") != 20000 or not task.get("result"):
        return "pending", None
    return "ready", task["result"][0]


def normalize_result(keyword: str, result: dict, targets: dict[str, dict]) -> dict:
    items = result.get("items") or []
    organic = [item for item in items if item.get("type") == "organic"]
    local_pack = [item for item in items if item.get("type") == "local_pack"]
    row: dict[str, Any] = {
        "keyword": keyword,
        "provider_datetime": result.get("datetime"),
        "check_url": result.get("check_url"),
        "se_results_count": result.get("se_results_count"),
        "serp_features": sorted(set(result.get("item_types") or [
            item.get("type") for item in items if item.get("type")
        ])),
        "organic_top10": [
            {
                "rank": item.get("rank_group"),
                "rank_absolute": item.get("rank_absolute"),
                "result_type": item.get("type"),
                "url": item.get("url"),
                "title": item.get("title"),
                "snippet": item.get("description") or item.get("snippet"),
            }
            for item in sorted(
                organic,
                key=lambda value: value.get("rank_group") or value.get("rank_absolute") or 999,
            )
            if int(item.get("rank_group") or item.get("rank_absolute") or 999) <= 10
        ][:10],
        "local_pack_present": bool(local_pack),
        "page1_domains": sorted({
            _normalize_domain(item.get("domain"))
            for item in organic
            if item.get("domain") and int(item.get("rank_group") or 999) <= 10
        }),
        "local_pack_businesses": [{
            "order": item.get("rank_group"),
            "rank_absolute": item.get("rank_absolute"),
            "business_name": item.get("title"),
            "cid": item.get("cid"),
            "domain": item.get("domain"),
            "url": item.get("url"),
            "phone": item.get("phone"),
            "rating": (item.get("rating") or {}).get("value"),
            "reviews": (item.get("rating") or {}).get("votes_count"),
        } for item in local_pack],
        **classify(keyword),
    }
    for key, target in targets.items():
        organic_matches = [item for item in organic if matches_target(item, target)]
        local_matches = [item for item in local_pack if matches_target(item, target)]
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
        row[f"{key}_organic_position"] = (
            organic_match.get("rank_group") if organic_match else None
        )
        row[f"{key}_organic_rank_absolute"] = (
            organic_match.get("rank_absolute") if organic_match else None
        )
        row[f"{key}_landing_page"] = organic_match.get("url") if organic_match else None
        row[f"{key}_local_pack_position"] = (
            local_match.get("rank_group") if local_match else None
        )
    return row


def position_records(rows: list[dict], *, expected_keywords: int | None = None) -> dict:
    expected = len(rows) if expected_keywords is None else expected_keywords
    positions = [
        int(row["fmd_organic_position"])
        for row in rows
        if row.get("fmd_organic_position") is not None
    ]
    return {
        "blocked": len(rows) != expected,
        "keywords_tracked": expected,
        "keywords_missing": max(expected - len(rows), 0),
        "top10_count": sum(position <= 10 for position in positions),
        "top3_count": sum(position <= 3 for position in positions),
        "top20_count": sum(position <= 20 for position in positions),
    }


def competitor_records(
    rows: list[dict],
    *,
    head_terms: list[str],
    previous_rows: list[dict] | None = None,
) -> dict[str, int]:
    wanted = {term.casefold() for term in head_terms}
    selected = [row for row in rows if str(row.get("keyword", "")).casefold() in wanted]
    previous = [
        row for row in (previous_rows or [])
        if str(row.get("keyword", "")).casefold() in wanted
    ]
    current_domains = {
        _normalize_domain(domain)
        for row in selected
        for domain in row.get("page1_domains") or []
        if _normalize_domain(domain) != "freshmobiledetail.com"
    }
    previous_domains = {
        _normalize_domain(domain)
        for row in previous
        for domain in row.get("page1_domains") or []
        if _normalize_domain(domain) != "freshmobiledetail.com"
    }
    return {
        "head_terms_checked": len(selected),
        "fmd_page1_count": sum(
            row.get("fmd_organic_position") is not None
            and int(row["fmd_organic_position"]) <= 10
            for row in selected
        ),
        # The first complete run establishes the baseline; nothing is called
        # "new" until there is a prior comparable panel.
        "new_entrants": len(current_domains - previous_domains) if previous else 0,
    }


def _get_one(
    client: DataForSeoClient,
    task: dict,
    raw_dir: Path,
    targets: dict[str, dict],
) -> tuple[str, dict | None]:
    raw_path = raw_dir / f"{task['task_id']}.json"
    if raw_path.exists():
        body = json.loads(raw_path.read_text(encoding="utf-8"))
    else:
        body = client._request(GET_ENDPOINT.format(task_id=task["task_id"]))
        status, _ = _task_result(body)
        if status == "ready":
            _write_json(raw_path, body)
    status, result = _task_result(body)
    return status, normalize_result(task["keyword"], result, targets) if result else None


def _exclusive_results_path(output_dir: Path) -> Path:
    base = output_dir / "results.jsonl"
    suffix = 1
    while True:
        candidate = base if suffix == 1 else base.with_name(f"results~{suffix}.jsonl")
        try:
            candidate.touch(exist_ok=False)
            return candidate
        except FileExistsError:
            suffix += 1


def collect_tasks(
    config: dict, *, evidence_dir: Path | None = None, raw_dir: Path | None = None,
) -> tuple[dict, list[dict]]:
    manifest_path = _manifest_path(config)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tasks = manifest.get("tasks") or []
    expected = len(load_keywords(Path(config["paths"]["position_keywords"])))
    if len(tasks) != expected:
        raise ValueError(f"manifest has {len(tasks)} tasks; expected {expected}")
    raw_dir = raw_dir or (paths.RAW_DIR / "serp-bulk")
    raw_dir.mkdir(parents=True, exist_ok=True)
    client = _client(config)
    targets = config["serp_bulk"]["targets"]
    rows: list[dict] = []
    pending = 0
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {
            pool.submit(_get_one, client, task, raw_dir, targets): task
            for task in tasks
        }
        for future in as_completed(futures):
            status, row = future.result()
            if status == "ready" and row is not None:
                rows.append(row)
            else:
                pending += 1
    order = {task["keyword"].casefold(): index for index, task in enumerate(tasks)}
    rows.sort(key=lambda row: order[row["keyword"].casefold()])
    evidence_root = evidence_dir or paths.EVIDENCE_DIR
    prior_paths = sorted(evidence_root.glob("serp-bulk-*/results*.jsonl"))
    previous_rows = []
    if prior_paths:
        previous_rows = [
            json.loads(line)
            for line in prior_paths[-1].read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    output_dir = evidence_root / (
        "serp-bulk-" + datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = _exclusive_results_path(output_dir)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    records = position_records(rows, expected_keywords=expected)
    competitor = competitor_records(
        rows,
        head_terms=list(config.get("serp_bulk", {}).get("head_terms") or []),
        previous_rows=previous_rows,
    )
    if not pending:
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(manifest_path, manifest)
    return ({
        "command": "serp-bulk", "mode": "collect", "ready": len(rows),
        "pending": pending, "results": str(output_path), "records": records,
        "competitor_records": competitor,
        "manifest": str(manifest_path),
    }, rows)
