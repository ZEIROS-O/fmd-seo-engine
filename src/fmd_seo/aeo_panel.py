"""Frozen AEO v1 panel and cost-gated request planning."""

from __future__ import annotations


AEO_PANEL_V1 = (
    "best mobile car detailing Cleveland",
    "mobile car detailing near me Cleveland",
    "interior car detailing Beachwood Ohio",
    "mobile detailing cost Cleveland",
    "mobile auto detailing Solon Ohio",
    "best interior detailing Cleveland",
    "best mobile detailing in Beachwood",
    "best mobile detailing in Mayfield Heights",
    "best mobile detailing in Pepper Pike",
    "best mobile detailing in Lyndhurst",
    "best mobile detailing in Orange",
    "best mobile detailing in University Heights",
    "best mobile detailing in Highland Heights",
    "mobile detailing for family SUVs Cleveland",
    "mobile detailing for kid messes Cleveland",
    "mobile detailing for pet hair Cleveland",
    "mobile detailing for road salt stains Cleveland",
    "mobile detailing for odors Cleveland",
    "mobile detailing for car-seat areas Cleveland",
    "mobile detailing at apartment complexes Cleveland",
    "mobile detailing Beachwood pricing",
    "Cleveland interior detailing pricing",
    "mobile detailing upfront pricing Cleveland",
    "mobile detailing best reviews Cleveland",
    "minimal-upsell mobile detailing Cleveland",
)

ENGINES = ("chatgpt", "perplexity")
RUNS_PER_QUERY = 2


def build_plan(*, canary: bool, unit_cost_usd: float, endpoint_cap_usd: float) -> dict:
    queries = AEO_PANEL_V1[:5] if canary else AEO_PANEL_V1
    responses = len(queries) * len(ENGINES) * RUNS_PER_QUERY
    projected = responses * unit_cost_usd
    full_weekly = len(AEO_PANEL_V1) * len(ENGINES) * RUNS_PER_QUERY * unit_cost_usd
    return {
        "panel_version": 1,
        "mode": "canary" if canary else "full",
        "queries": list(queries),
        "engines": list(ENGINES),
        "runs_per_query": RUNS_PER_QUERY,
        "responses": responses,
        "unit_cost_usd": unit_cost_usd,
        "projected_cost_usd": projected,
        "projected_full_weekly_cost_usd": full_weekly,
        "projected_full_monthly_cost_usd": full_weekly * 52 / 12,
        "endpoint_cap_usd": endpoint_cap_usd,
        "within_cap": projected <= endpoint_cap_usd,
        "scheduling_enabled": False,
        "approval_required": True,
    }
