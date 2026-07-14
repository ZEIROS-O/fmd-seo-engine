"""Command handlers for the autonomous-loop surface: beat, assess, observe,
brief. These are the commands a session or a cron job calls to let the engine
drive. Each returns (payload_dict, exit_code); the CLI prints the payload.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import paths
from .assess import assess_all, assess_gates
from .brain import BrainError, load_brain
from .observations import record_observation
from .planner import build_plan
from .semrush import SemrushKeyMissing, load_key


def _has_semrush_key(config: dict) -> bool:
    try:
        load_key(Path(config["creds_env"]))
        return True
    except (SemrushKeyMissing, KeyError, OSError):
        return False


def cmd_beat(config: dict) -> tuple[dict, int]:
    """What is due right now, ordered, with fulfillment paths."""
    brain = load_brain()
    has_key = _has_semrush_key(config)
    plan = build_plan(brain, has_semrush_key=has_key)
    payload = {
        "command": "beat",
        "generated_at": plan.generated_at,
        "semrush_api_key_present": has_key,
        "gates": plan.gate_summary,
        "priority_order": plan.priority_order,
        "due_counts": plan.counts,
        "due": [
            {
                "check_id": pc.check_id,
                "domain": pc.domain,
                "title": pc.title,
                "cadence": pc.cadence,
                "reason": pc.reason,
                "fulfillment": pc.fulfillment,
                "api_reports": pc.api_reports,
                "run": pc.run,
            }
            for pc in plan.due
        ],
    }
    return payload, 0


def cmd_assess(config: dict) -> tuple[dict, int]:
    """Evaluate thresholds against the latest observations; report gate drift."""
    brain = load_brain()
    findings = assess_all(brain)
    gates = assess_gates(brain)
    has_critical = any(f.severity == "critical" for f in findings)
    has_drift = any(g.drift for g in gates)
    payload = {
        "command": "assess",
        "gates": [
            {"gate": g.gate_id, "name": g.name, "state": g.declared_state,
             "reason": g.reason, "drift": g.drift}
            for g in gates
        ],
        "findings": [
            {"check_id": f.check_id, "domain": f.domain, "severity": f.severity,
             "finding": f.finding, "action": f.action, "observed_at": f.observed_at,
             "fulfillment": f.fulfillment}
            for f in findings
        ],
        "summary": {
            "total_findings": len(findings),
            "critical": sum(1 for f in findings if f.severity == "critical"),
            "high": sum(1 for f in findings if f.severity == "high"),
            "gate_drift": has_drift,
        },
    }
    # Exit 4 (BLOCK-equivalent) when a critical finding or gate drift exists, so a
    # cron wrapper can react without parsing JSON.
    return payload, (4 if (has_critical or has_drift) else 0)


def cmd_observe(config: dict, check_id: str, records_json: str, *,
                fulfillment: str, source: str, note: str = "") -> tuple[dict, int]:
    """Record one measured observation. records_json is a JSON object of the
    check's declared fields. Validation is strict — wrong/missing fields fail."""
    brain = load_brain()
    try:
        records = json.loads(records_json)
    except json.JSONDecodeError as err:
        return {"command": "observe", "error": f"invalid --records JSON: {err}"}, 4
    if not isinstance(records, dict):
        return {"command": "observe", "error": "--records must be a JSON object"}, 4
    try:
        path = record_observation(brain, check_id, records, fulfillment=fulfillment,
                                  source=source, note=note)
    except (BrainError, ValueError) as err:
        return {"command": "observe", "error": str(err)}, 4
    # Immediately assess the just-recorded check so the caller sees consequences.
    from .assess import assess_check
    _, findings = assess_check(brain, check_id)
    return {
        "command": "observe",
        "recorded": str(path.relative_to(paths.ENGINE_ROOT)),
        "check_id": check_id,
        "fulfillment": fulfillment,
        "findings": [
            {"severity": f.severity, "finding": f.finding, "action": f.action}
            for f in findings
        ],
    }, 0


def cmd_sync(config: dict) -> tuple[dict, int]:
    """Headless Semrush fetch of API-backed due checks. No key -> honest no-op
    that names the checks still needing a session."""
    from .sync import sync_due
    brain = load_brain()
    result = sync_due(config, brain=brain)
    payload = {
        "command": "sync",
        "fetched": result.fetched,
        "skipped_no_key": result.skipped_no_key,
        "errors": result.errors,
        "note": ("no SEMRUSH_API_KEY present — these API-backed checks stay on the "
                 "session (MCP) path" if result.skipped_no_key else
                 f"fetched {len(result.fetched)} check(s) headlessly"),
    }
    return payload, (4 if result.errors else 0)


def cmd_brief(config: dict) -> tuple[dict, int]:
    """The full operator briefing: gates, what's due, standing findings,
    priority order. One call answers 'what do I do now and why'."""
    brain = load_brain()
    has_key = _has_semrush_key(config)
    plan = build_plan(brain, has_semrush_key=has_key)
    findings = assess_all(brain)
    gates = assess_gates(brain)
    payload = {
        "command": "brief",
        "generated_at": plan.generated_at,
        "semrush_api_key_present": has_key,
        "gates": [
            {"gate": g.gate_id, "state": g.declared_state, "reason": g.reason,
             "drift": g.drift}
            for g in gates
        ],
        "priority_order": plan.priority_order,
        "standing_findings": [
            {"check_id": f.check_id, "severity": f.severity, "finding": f.finding,
             "action": f.action}
            for f in findings if f.severity in ("critical", "high")
        ],
        "due_now": [
            {"check_id": pc.check_id, "fulfillment": pc.fulfillment,
             "reason": pc.reason, "title": pc.title}
            for pc in plan.due
        ],
        "due_counts": plan.counts,
    }
    return payload, 0
