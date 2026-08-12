"""Coordinate grid construction and map-pack aggregation."""

from __future__ import annotations

import math
import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import yaml

from . import paths
from .serp_bulk import (
    CHUNK_SIZE,
    POST_ENDPOINT,
    _client,
    _cost,
    _get_one,
    _write_json,
    estimate_cost_usd,
)


@dataclass(frozen=True)
class GridPoint:
    row: int
    column: int
    latitude: float
    longitude: float

    @property
    def coordinate(self) -> str:
        # Organic SERP coordinate radius is millimetres; 200 is the documented
        # minimum practical precision and matches the measured baseline.
        return f"{self.latitude:.7f},{self.longitude:.7f},200"


def build_grid(
    center_latitude: float,
    center_longitude: float,
    *,
    radius_miles: float,
    size: int = 5,
) -> list[GridPoint]:
    if size < 2 or size % 2 == 0:
        raise ValueError("grid size must be an odd integer >= 3")
    if radius_miles <= 0:
        raise ValueError("radius_miles must be positive")
    latitude_delta = radius_miles / 69.0
    longitude_delta = radius_miles / (
        69.172 * math.cos(math.radians(center_latitude))
    )
    offsets = [(-1 + (2 * index / (size - 1))) for index in range(size)]
    return [
        GridPoint(
            row=row,
            column=column,
            latitude=center_latitude + lat_offset * latitude_delta,
            longitude=center_longitude + lon_offset * longitude_delta,
        )
        for row, lat_offset in enumerate(offsets)
        for column, lon_offset in enumerate(offsets)
    ]


def task_specs(queries: list[str], points: list[GridPoint]) -> list[dict]:
    return [{
        "query": query,
        "grid_row": point.row,
        "grid_column": point.column,
        "location_coordinate": point.coordinate,
        "device": "mobile",
        "os": "android",
        "depth": 10,
    } for query in queries for point in points]


def aggregate_map_pack(
    rows: list[dict], *, fmd_aliases: list[str], tasks_posted: int | None = None,
) -> dict:
    aliases = {alias.casefold() for alias in fmd_aliases}
    present_ranks = [
        int(row["fmd_local_pack_position"])
        for row in rows
        if row.get("fmd_local_pack_position") is not None
    ]
    competitors: set[str] = set()
    for row in rows:
        fmd_rank = row.get("fmd_local_pack_position")
        if fmd_rank is None:
            continue
        for business in row.get("local_pack_businesses") or []:
            name = str(business.get("business_name") or "").strip()
            rank = business.get("order")
            if name and name.casefold() not in aliases and rank is not None and int(rank) < int(fmd_rank):
                competitors.add(name.casefold())
    denominator = len(rows) if tasks_posted is None else int(tasks_posted)
    if denominator < len(rows):
        raise ValueError("tasks_posted cannot be smaller than collected rows")
    return {
        "queries": len({str(row.get("query")) for row in rows}),
        "points_sampled": denominator,
        "points_missing": denominator - len(rows),
        "points_present": len(present_ranks),
        "median_rank": float(statistics.median(present_ranks)) if present_ranks else 0.0,
        "competitors_above": len(competitors),
    }


def _radius_from_facts(config: dict) -> tuple[str, float]:
    facts_file = Path(config["paths"]["facts_file"])
    data = yaml.safe_load(facts_file.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError(f"unsupported business-facts schema: {facts_file}")
    service_area = data.get("service_area") or {}
    return str(service_area["base"]), float(service_area["radius_miles"])


def _specs(config: dict) -> tuple[str, list[dict]]:
    base, _service_radius = _radius_from_facts(config)
    grid = config["geogrid"]
    center_latitude, center_longitude = map(float, grid["center"])
    points = build_grid(
        center_latitude,
        center_longitude,
        radius_miles=float(grid["radius_miles"]),
        size=int(grid.get("size", 5)),
    )
    return base, task_specs(list(grid["queries"]), points)


def dry_run(config: dict) -> dict:
    base, specs = _specs(config)
    estimate = estimate_cost_usd(len(specs), depth=10, page_price_usd=0.0006)
    cap = float(config["budget"]["endpoint_caps_usd"]["geogrid"])
    return {
        "command": "geogrid",
        "mode": "dry-run",
        "service_area_base": base,
        "tasks": len(specs),
        "queries": len(config["geogrid"]["queries"]),
        "points": int(config["geogrid"].get("size", 5)) ** 2,
        "estimated_cost_usd": estimate,
        "endpoint_cap_usd": cap,
        "within_cap": estimate <= cap,
        "posted": 0,
    }


def _manifest_path(config: dict) -> Path:
    configured = config.get("geogrid", {}).get("manifest")
    return Path(configured) if configured else paths.GEOGRID_MANIFEST


def post_tasks(config: dict) -> dict:
    base, specs = _specs(config)
    manifest_path = _manifest_path(config)
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "schema_version": 1,
            "service_area_base": base,
            "posted_at": None,
            "completed_at": None,
            "post_cost_usd": 0.0,
            "tasks": [],
        }
    completed = {
        (task["query"].casefold(), task["grid_row"], task["grid_column"])
        for task in manifest["tasks"]
    }
    pending = [
        spec for spec in specs
        if (spec["query"].casefold(), spec["grid_row"], spec["grid_column"])
        not in completed
    ]
    if not pending:
        return {
            "command": "geogrid", "mode": "post", "posted": 0,
            "total_tasks": len(manifest["tasks"]), "status": "already_posted",
            "manifest": str(manifest_path),
        }
    estimate = estimate_cost_usd(len(pending), depth=10, page_price_usd=0.0006)
    cap = float(config["budget"]["endpoint_caps_usd"]["geogrid"])
    if float(manifest["post_cost_usd"]) + estimate > cap:
        raise ValueError(f"geogrid estimate ${estimate:.4f} exceeds ${cap:.2f} cap")
    client = _client(config)
    balance = float(client.probe().get("balance_usd") or 0.0)
    if balance < estimate:
        raise ValueError(f"provider balance ${balance:.4f} is below ${estimate:.4f} estimate")
    targets = config["serp_bulk"]["targets"]
    stop_targets = [
        {"match_value": target["domain"], "match_type": "with_subdomains"}
        for target in targets.values()
    ]
    posted_now = 0
    for offset in range(0, len(pending), CHUNK_SIZE):
        chunk = pending[offset:offset + CHUNK_SIZE]
        payload = [{
            "keyword": spec["query"],
            "language_code": "en",
            "location_coordinate": spec["location_coordinate"],
            "device": "mobile",
            "os": "android",
            "depth": 10,
            "tag": f"fmd-grid-{offset + index:03d}",
            "stop_crawl_on_match": stop_targets,
            "target_search_mode": "all",
            "find_targets_in": ["organic", "local_pack"],
        } for index, spec in enumerate(chunk, start=1)]
        chunk_estimate = estimate_cost_usd(len(chunk), depth=10, page_price_usd=0.0006)
        reservation = client.ledger.reserve("geogrid", chunk_estimate)
        body = client._request(POST_ENDPOINT, payload)
        actual = _cost(body, chunk_estimate)
        client.ledger.settle(reservation, actual, POST_ENDPOINT)
        receipts = body.get("tasks") or []
        if len(receipts) != len(chunk):
            raise RuntimeError(
                f"posted {len(chunk)} grid tasks but provider returned {len(receipts)} receipts"
            )
        for spec, receipt in zip(chunk, receipts):
            if not receipt.get("id"):
                raise RuntimeError(
                    f"grid task was not created: {receipt.get('status_message')}"
                )
            manifest["tasks"].append({**spec, "keyword": spec["query"], "task_id": receipt["id"]})
        manifest["post_cost_usd"] = round(float(manifest["post_cost_usd"]) + actual, 6)
        manifest["posted_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(manifest_path, manifest)
        posted_now += len(chunk)
    return {
        "command": "geogrid", "mode": "post", "posted": posted_now,
        "total_tasks": len(manifest["tasks"]), "cost_usd": manifest["post_cost_usd"],
        "manifest": str(manifest_path),
    }


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
    _base, specs = _specs(config)
    tasks = manifest.get("tasks") or []
    if len(tasks) != len(specs):
        raise ValueError(f"manifest has {len(tasks)} grid tasks; expected {len(specs)}")
    raw_dir = raw_dir or (paths.RAW_DIR / "geogrid")
    raw_dir.mkdir(parents=True, exist_ok=True)
    client = _client(config)
    targets = config["serp_bulk"]["targets"]
    rows: list[dict] = []
    pending = 0
    # Sequential collection avoids racing persistent provider-health writes;
    # 200 free GETs are bounded and normally complete quickly.
    for task in tasks:
        status, row = _get_one(client, task, raw_dir, targets)
        if status != "ready" or row is None:
            pending += 1
            continue
        row.update({
            "query": task["query"],
            "grid_row": task["grid_row"],
            "grid_column": task["grid_column"],
            "location_coordinate": task["location_coordinate"],
        })
        rows.append(row)
    output_dir = (evidence_dir or paths.EVIDENCE_DIR) / (
        "geogrid-" + datetime.now(timezone.utc).strftime("%Y-%m-%d")
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = _exclusive_results_path(output_dir)
    with output_path.open("w", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
    aliases = config["serp_bulk"]["targets"]["fmd"].get("aliases") or []
    records = aggregate_map_pack(rows, fmd_aliases=aliases, tasks_posted=len(tasks))
    if not pending:
        manifest["completed_at"] = datetime.now(timezone.utc).isoformat()
        _write_json(manifest_path, manifest)
    return ({
        "command": "geogrid", "mode": "collect", "ready": len(rows),
        "pending": pending, "results": str(output_path), "records": records,
        "manifest": str(manifest_path),
    }, rows)
