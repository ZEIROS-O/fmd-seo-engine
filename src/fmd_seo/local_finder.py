"""Local Finder (Places tab) depth sampling across a keyword x location matrix.

Why this exists separately from `geogrid`: Google's local pack holds exactly
three slots, so pack-only sampling cannot distinguish "rank 4" from "not in the
index at all". Measured 2026-08-03, that flattened a business sitting at rank 2
in its own strongest suburb into `points_present: 0` across 181 samples.

Local Finder returns the ranked list behind the pack (depth 20 here), so a
business's real position is recorded whether it is 2nd or 19th. Rank <= 3 is
what actually surfaces in the embedded pack on a normal web search; 4-20 is
visible only to someone who opens the Places tab.

The endpoint is live (not the standard queue): the matrix is small, results are
needed in one pass, and every call reserves and settles against the committed
spend ledger under the `local_finder` cap.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths
from .serp_bulk import _client, _write_json, matches_target

LIVE_ENDPOINT = "/v3/serp/google/local_finder/live/advanced"
DEFAULT_DEPTH = 20
# Measured 2026-08-03: $0.004 per live advanced task at depth 20.
DEFAULT_TASK_PRICE_USD = 0.004
PACK_SLOTS = 3


def estimate_cost_usd(task_count: int, *,
                      task_price_usd: float = DEFAULT_TASK_PRICE_USD) -> float:
    if task_count < 0 or task_price_usd < 0:
        raise ValueError("task_count and task_price_usd must be non-negative")
    return round(task_count * task_price_usd, 6)


def expand_queries(templates: list[str], location: dict) -> list[str]:
    """Render `{suburb}` templates for one location, keeping literals as-is."""
    suburb = str(location.get("suburb") or location.get("name") or "")
    out: list[str] = []
    for template in templates:
        rendered = template.format(suburb=suburb) if "{suburb}" in template else template
        if rendered not in out:
            out.append(rendered)
    return out


def build_matrix(config: dict) -> list[dict]:
    """Every (query, location) pair the configured matrix asks for."""
    section = config["local_finder"]
    locations = section["locations"]
    if not locations:
        raise ValueError("local_finder.locations is empty")
    templates = list(section["queries"])
    if not templates:
        raise ValueError("local_finder.queries is empty")
    depth = int(section.get("depth", DEFAULT_DEPTH))
    specs: list[dict] = []
    for location in locations:
        for query in expand_queries(templates, location):
            specs.append({
                "query": query,
                "location_name": location["name"],
                "location_coordinate": f"{float(location['latitude']):.7f},"
                                       f"{float(location['longitude']):.7f}",
                "device": "mobile",
                "os": "android",
                "depth": depth,
            })
    return specs


def _rating(item: dict) -> tuple[float | None, int | None]:
    rating = item.get("rating") or {}
    return rating.get("value"), rating.get("votes_count")


def parse_result(spec: dict, items: list[dict], targets: dict) -> dict:
    """One matrix cell: our rank plus everyone ranked above us."""
    row: dict[str, Any] = {
        "query": spec["query"],
        "location_name": spec["location_name"],
        "location_coordinate": spec["location_coordinate"],
        "results_returned": len(items),
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    for key, target in targets.items():
        match = next((item for item in items if matches_target(item, target)), None)
        rank = int(match["rank_absolute"]) if match and match.get("rank_absolute") else None
        row[f"{key}_rank"] = rank
        if key == "fmd" and match is not None:
            value, votes = _rating(match)
            row["fmd_rating"] = value
            row["fmd_reviews"] = votes
            row["fmd_in_pack"] = bool(rank and rank <= PACK_SLOTS)
    if "fmd_in_pack" not in row:
        row["fmd_in_pack"] = False
        row["fmd_rating"] = None
        row["fmd_reviews"] = None
    fmd_rank = row.get("fmd_rank")
    row["competitors_above"] = [
        {
            "rank": item.get("rank_absolute"),
            "name": item.get("title"),
            "reviews": _rating(item)[1],
            "rating": _rating(item)[0],
        }
        for item in items
        if item.get("rank_absolute") is not None
        and (fmd_rank is None or int(item["rank_absolute"]) < fmd_rank)
    ][:PACK_SLOTS]
    return row


def aggregate(rows: list[dict]) -> dict:
    """Records for the `seo.local_visibility` check."""
    ranked = [row for row in rows if row.get("fmd_rank")]
    packed = [row for row in ranked if row["fmd_in_pack"]]
    reviews = [row["fmd_reviews"] for row in ranked if row.get("fmd_reviews") is not None]
    return {
        "pairs_tested": len(rows),
        "pairs_ranked": len(ranked),
        "pairs_in_pack": len(packed),
        "best_rank": min((row["fmd_rank"] for row in ranked), default=0),
        "reviews": int(reviews[0]) if reviews else 0,
    }


def dry_run(config: dict) -> dict:
    specs = build_matrix(config)
    section = config["local_finder"]
    estimate = estimate_cost_usd(
        len(specs),
        task_price_usd=float(section.get("task_price_usd", DEFAULT_TASK_PRICE_USD)),
    )
    cap = float(config["budget"]["endpoint_caps_usd"]["local_finder"])
    return {
        "command": "local-finder",
        "mode": "dry-run",
        "tasks": len(specs),
        "queries": len({spec["query"] for spec in specs}),
        "locations": len({spec["location_name"] for spec in specs}),
        "depth": int(section.get("depth", DEFAULT_DEPTH)),
        "estimated_cost_usd": estimate,
        "endpoint_cap_usd": cap,
        "within_cap": estimate <= cap,
    }


def run(config: dict, *, observations_dir: Path | None = None,
        evidence_dir: Path | None = None,
        client=None, sleep_s: float = 0.4) -> tuple[dict, list[dict]]:
    """Execute the matrix. A failed cell is recorded, never silently dropped."""
    specs = build_matrix(config)
    section = config["local_finder"]
    price = float(section.get("task_price_usd", DEFAULT_TASK_PRICE_USD))
    cap = float(config["budget"]["endpoint_caps_usd"]["local_finder"])
    estimate = estimate_cost_usd(len(specs), task_price_usd=price)
    if estimate > cap:
        return ({
            "command": "local-finder", "mode": "run", "status": "BLOCK",
            "tasks": len(specs), "estimated_cost_usd": estimate,
            "endpoint_cap_usd": cap,
            "blockers": [f"estimated ${estimate:.4f} exceeds local_finder cap ${cap:.2f}"],
        }, [])

    api = client or _client(config)
    targets = config["serp_bulk"]["targets"]
    rows: list[dict] = []
    failures: list[dict] = []
    spent = 0.0
    for index, spec in enumerate(specs):
        reservation = api.ledger.reserve("local_finder", price)
        try:
            body = api._request(LIVE_ENDPOINT, [{
                "keyword": spec["query"],
                "location_coordinate": spec["location_coordinate"],
                "language_code": "en",
                "device": spec["device"],
                "os": spec["os"],
                "depth": spec["depth"],
            }])
            task = body["tasks"][0]
            cost = float(task.get("cost") or 0.0)
            spent += cost
            api.ledger.settle(reservation, cost,
                              f"{LIVE_ENDPOINT} {spec['query']} @{spec['location_name']}")
            result = (task.get("result") or [{}])[0]
            rows.append(parse_result(spec, result.get("items") or [], targets))
        except Exception as err:  # noqa: BLE001 - a dead cell must stay visible
            api.ledger.settle(reservation, 0.0, f"local_finder failed: {err}")
            failures.append({
                "query": spec["query"],
                "location_name": spec["location_name"],
                "error": f"{type(err).__name__}: {err}",
            })
        if sleep_s and index < len(specs) - 1:
            time.sleep(sleep_s)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # evidence_dir is injectable so a test can never write over committed
    # evidence: an earlier version defaulted straight to paths.EVIDENCE_DIR and
    # two test cases overwrote a real measured run with fixture output.
    out_dir = (evidence_dir or paths.EVIDENCE_DIR) / f"local-finder-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / "results.jsonl"
    suffix = 1
    while True:
        results_path = base if suffix == 1 else base.with_name(f"results~{suffix}.jsonl")
        try:
            with results_path.open("x", encoding="utf-8") as handle:
                handle.write("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))
            break
        except FileExistsError:
            suffix += 1
    records = aggregate(rows)
    payload = {
        "command": "local-finder",
        "mode": "run",
        "status": "PARTIAL" if failures else "DONE",
        "tasks": len(specs),
        "collected": len(rows),
        "failed": len(failures),
        "failures": failures,
        "cost_usd": round(spent, 6),
        "results": str(results_path),
        "records": records,
    }
    if failures:
        # A partial matrix is not a measurement of the matrix. Record nothing
        # rather than let a half-run reset the check's freshness clock.
        _write_json(out_dir / "failures.json", failures)
        return payload, rows

    from .brain import load_brain
    from .observations import record_observation
    observation = record_observation(
        load_brain(),
        "seo.local_visibility",
        records,
        fulfillment="engine_api",
        source=str(results_path),
        note=f"Local Finder depth {section.get('depth', DEFAULT_DEPTH)}, "
             f"{records['pairs_tested']} keyword x location pairs.",
        directory=observations_dir,
    )
    payload["observation"] = str(observation)
    return payload, rows
