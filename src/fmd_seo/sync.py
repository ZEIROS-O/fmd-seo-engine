"""Headless Semrush sync: fetch the API-backed due checks and record
observations without a session or Lou. This is the cron path — the thing that
removes the middleman for Semrush data.

Each adapter is a pure function `rows -> records` over parsed Semrush CSV, so
the parse-and-map logic is unit-testable against fixtures with no live key. The
orchestrator (`sync_due`) wires adapters to the client; its network calls can
only be exercised with a real key, and it degrades honestly to "no key —
these checks stay session-fulfilled" when none is present.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import paths
from .brain import Brain, load_brain
from .observations import record_observation
from .planner import build_plan
from .semrush import (
    SemrushClient, SemrushKeyMissing, UnitsLedger, load_key,
)


def _int(cell: str) -> int:
    try:
        return int(float(cell))
    except (ValueError, TypeError):
        return 0


# ─────────────────────── pure adapters: rows -> records ───────────────────────

def adapt_organic_footprint(rows: list[dict], *, brand_token: str = "fresh") -> dict:
    """domain_organic rows -> seo.organic_footprint records.
    Ph=phrase, Po=position. Non-branded = phrase without the brand token."""
    total = len(rows)
    nonbranded = sum(1 for r in rows if brand_token not in r.get("Ph", "").lower())
    page1 = sum(1 for r in rows if 0 < _int(r.get("Po", "0")) <= 10)
    return {
        "total_keywords": total,
        "nonbranded_keywords": nonbranded,
        "page1_keywords": page1,
    }


def adapt_authority_gap(our_rows: list[dict], competitor_ascores: list[int]) -> dict:
    """backlinks_overview rows (ours) + competitor ascores -> authority_gap.
    ascore=Authority Score, domains_num=referring domains."""
    our = our_rows[0] if our_rows else {}
    ascores = sorted(competitor_ascores)
    if ascores:
        mid = len(ascores) // 2
        median = (ascores[mid] if len(ascores) % 2
                  else (ascores[mid - 1] + ascores[mid]) // 2)
    else:
        median = 0
    return {
        "our_authority_score": _int(our.get("ascore", "0")),
        "competitor_median_as": median,
        "our_referring_domains": _int(our.get("domains_num", "0")),
    }


def adapt_market_demand(near_me_rows: list[dict]) -> dict:
    """phrase_this rows for the 'near me' head term -> market.demand.
    Nq=search volume, Td=trend (semicolon-packed monthly array)."""
    volume = 0
    trend = "unknown"
    for r in near_me_rows:
        if "near me" in r.get("Ph", "").lower():
            volume = _int(r.get("Nq", "0"))
            trend = r.get("Td", "unknown") or "unknown"
            break
    return {
        "near_me_volume": volume,
        "clusters_checked": len(near_me_rows),
        "trend_direction": trend,
    }


def adapt_related_topics(rows: list[dict], *, min_volume: int = 1) -> dict:
    """phrase_related/phrase_questions rows -> topics.related_clusters."""
    with_volume = sum(1 for r in rows if _int(r.get("Nq", "0")) >= min_volume)
    return {
        "candidates_found": len(rows),
        "candidates_with_volume": with_volume,
    }


# ─────────────────────────── orchestrator ───────────────────────────

@dataclass
class SyncResult:
    fetched: list[str]        # check_ids observed via API
    skipped_no_key: list[str]  # API-backed checks left for the session path
    errors: dict[str, str]    # check_id -> error message


def sync_due(config: dict, *, brain: Brain | None = None,
             observations_dir: Path | None = None) -> SyncResult:
    """Fetch every API-backed DUE check via the Semrush REST API and record
    observations. Without a key, records nothing and reports the checks that
    stay on the session path — no faked data (GATE-4)."""
    brain = brain or load_brain()
    env_file = Path(config["creds_env"])
    try:
        load_key(env_file)
    except (SemrushKeyMissing, OSError):
        # No key: identify what WOULD have been headless, honestly.
        plan = build_plan(brain, has_semrush_key=False, observations_dir=observations_dir)
        from .semrush import which_checks_are_api_backed
        api_backed = set(which_checks_are_api_backed())
        skipped = [pc.check_id for pc in plan.due if pc.check_id in api_backed]
        return SyncResult(fetched=[], skipped_no_key=skipped, errors={})

    cap = int(config.get("semrush", {}).get("units_cap", 500))
    database = config.get("semrush", {}).get("database", "us")
    client = SemrushClient(env_file, UnitsLedger(cap_units=cap))
    domain = brain.state["site"]["domain"]

    plan = build_plan(brain, has_semrush_key=True, observations_dir=observations_dir)
    due_api = [pc for pc in plan.due if pc.fulfillment == "engine_api"]

    fetched: list[str] = []
    errors: dict[str, str] = {}

    def _observe(check_id: str, records: dict, source: str) -> None:
        record_observation(brain, check_id, records, fulfillment="engine_api",
                           source=source, directory=observations_dir)
        fetched.append(check_id)

    for pc in due_api:
        try:
            if pc.check_id == "seo.organic_footprint":
                rows = client.fetch("domain_organic", domain=domain, database=database,
                                    display_limit=100)
                _observe(pc.check_id, adapt_organic_footprint(rows),
                         "semrush:domain_organic")
            elif pc.check_id == "competitor.authority_gap":
                ours = client.fetch("backlinks_overview", target=domain,
                                    target_type="root_domain")
                comp_scores = []
                for comp in brain.state.get("competitor_set", []):
                    crows = client.fetch("backlinks_overview", target=comp["domain"],
                                         target_type="root_domain")
                    if crows:
                        comp_scores.append(_int(crows[0].get("ascore", "0")))
                _observe(pc.check_id, adapt_authority_gap(ours, comp_scores),
                         "semrush:backlinks_overview")
            elif pc.check_id == "market.demand":
                rows = []
                for term in brain.state.get("head_terms", []):
                    if "near me" in term:
                        rows += client.fetch("phrase_this", phrase=term, database=database)
                _observe(pc.check_id, adapt_market_demand(rows), "semrush:phrase_this")
            elif pc.check_id == "topics.related_clusters":
                rows = []
                for term in ["car detailing", "auto detailing", "mobile detailing"]:
                    rows += client.fetch("phrase_related", phrase=term, database=database,
                                         display_limit=50)
                _observe(pc.check_id, adapt_related_topics(rows), "semrush:phrase_related")
            # seo.positions / seo.site_health are Projects-API — not yet wired;
            # they stay on the session path and are not attempted here.
        except Exception as err:  # noqa: BLE001 - one bad check must not abort the rest
            errors[pc.check_id] = str(err)

    return SyncResult(fetched=fetched, skipped_no_key=[], errors=errors)
