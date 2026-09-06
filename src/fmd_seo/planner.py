"""Planner: the engine's answer to "what should I do right now?"

`beat` turns the brain + observation history + gate state into an ordered work
plan a caller can execute without Lou deciding anything. Each due check is
labeled with its fulfillment path:

  engine_api  — a configured provider can fetch it headlessly. Needs credentials.
  session     — needs an interactive Claude Code session (MCP or model judgment).
  human       — a console only Lou can open (GSC/GA4/GBP). The true residue.

The plan also carries the gate-respecting priority order, read from
`brain/priorities.yaml` for the live gate state, so a caller never has to
re-derive that publishing is closed while indexation fails. The planner holds
no copy of that order: a second copy is what drifted from the thesis for the
eight days after the 2026-08-03 reorder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .brain import Brain, Check, due_checks, priority_order
from .observations import last_seen_map
from .semrush import which_checks_are_api_backed

# method.kind -> default fulfillment when no API path exists.
KIND_FULFILLMENT = {
    "http": "session",     # free live fetch; a session (or a future engine http path) does it
    "mcp": "session",      # Semrush MCP — session only, unless API-backed (see below)
    "agent": "session",    # model judgment + web search
    "console": "human",    # GSC/GA4/GBP — only Lou can open these
    "engine": "engine",    # pure local computation, no external anything
}


@dataclass(frozen=True)
class PlannedCheck:
    check_id: str
    domain: str
    title: str
    cadence: str
    reason: str            # why it is due
    fulfillment: str       # engine_api | session | human | engine
    api_reports: list[str]  # provider operation names when engine_api, else []
    run: str               # the check's run instructions
    why: str


@dataclass(frozen=True)
class Plan:
    generated_at: str
    gate_summary: list[dict]
    priority_order: list[str]
    due: list[PlannedCheck]

    @property
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for pc in self.due:
            out[pc.fulfillment] = out.get(pc.fulfillment, 0) + 1
        return out


def _fulfillment_for(check: Check, has_semrush_key: bool, has_gsc: bool,
                     has_ga4: bool,
                     api_backed: dict[str, list[str]]) -> tuple[str, list[str]]:
    reports = api_backed.get(check.id, [])
    if check.method_kind == "mcp" and reports and has_semrush_key:
        return "engine_api", reports
    # GSC provides two independent headless instruments: per-URL inspection
    # and finalized Search Analytics rows. The footprint reads two dimension
    # sets, and both are declared — a query-only pull alone cannot report page
    # coverage, and a query/page pull alone cannot report a query total.
    if check.id == "seo.indexation" and has_gsc:
        return "engine_api", ["gsc:urlInspection"]
    if check.id == "seo.query_footprint" and has_gsc:
        return "engine_api", [
            "gsc:searchAnalytics.query",
            "gsc:searchAnalytics.queryPage",
        ]
    if check.id == "analytics.traffic" and has_ga4:
        return "engine_api", ["ga4:runReport"]
    return KIND_FULFILLMENT.get(check.method_kind, "session"), []


def build_plan(brain: Brain, *, has_semrush_key: bool, has_gsc: bool = False,
               has_ga4: bool = False,
               observations_dir: Path | None = None,
               now: datetime | None = None) -> Plan:
    last_seen = last_seen_map(brain, observations_dir)
    due = due_checks(brain, last_seen, now=now)
    api_backed = which_checks_are_api_backed()

    planned: list[PlannedCheck] = []
    for check, reason in due:
        fulfillment, reports = _fulfillment_for(
            check, has_semrush_key, has_gsc, has_ga4, api_backed,
        )
        planned.append(PlannedCheck(
            check_id=check.id,
            domain=check.domain,
            title=check.title,
            cadence=check.cadence,
            reason=reason,
            fulfillment=fulfillment,
            api_reports=reports,
            run=check.method_run,
            why=check.why,
        ))

    priority = priority_order(brain)

    gate_summary = [
        {"gate": gid, "state": g.get("state"), "reason": g.get("reason", "")}
        for gid, g in brain.gates.items()
    ]

    from .brain import CADENCE_DAYS  # local import to avoid cycle at module load
    order = {"human": 0, "engine_api": 1, "session": 2, "engine": 3}
    planned.sort(key=lambda pc: (order.get(pc.fulfillment, 9),
                                 CADENCE_DAYS.get(pc.cadence) or 999, pc.check_id))

    stamp = (now or datetime.utcnow()).isoformat(timespec="seconds")
    return Plan(generated_at=stamp, gate_summary=gate_summary,
                priority_order=priority, due=planned)
