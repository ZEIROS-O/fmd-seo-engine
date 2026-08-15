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
from .gate_manager import update_gate1_state
from .observations import record_observation
from .planner import build_plan
from .semrush import SemrushKeyMissing, load_key


def _has_semrush_key(config: dict) -> bool:
    try:
        load_key(Path(config["creds_env"]))
        return True
    except (SemrushKeyMissing, KeyError, OSError):
        return False


def _has_gsc(config: dict) -> bool:
    """GSC is 'available' when a service-account key file exists. Import-ability of
    the google libs is checked at fetch time; presence of the key is what flips the
    planner label off 'human'."""
    gsc_cfg = config.get("gsc") or {}
    key_path = gsc_cfg.get("key_path")
    return bool(key_path and Path(key_path).exists())


def _has_ga4(config: dict) -> bool:
    """GA4 is headless only with both a property and an existing key file."""
    ga4_cfg = config.get("ga4") or {}
    key_path = ga4_cfg.get("key_path")
    return bool(
        ga4_cfg.get("property_id")
        and key_path
        and Path(key_path).is_file()
    )


def cmd_beat(config: dict) -> tuple[dict, int]:
    """What is due right now, ordered, with fulfillment paths."""
    brain = load_brain()
    has_key = _has_semrush_key(config)
    plan = build_plan(
        brain,
        has_semrush_key=has_key,
        has_gsc=_has_gsc(config),
        has_ga4=_has_ga4(config),
    )
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
    quarantine_root = paths.ENGINE_ROOT / "brain" / "quarantine"
    quarantine_depth = len(list(quarantine_root.glob("*/*.json"))) if quarantine_root.exists() else 0
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
            "quarantine_depth": quarantine_depth,
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
    gate_update = None
    if check_id == "seo.indexation":
        observed_at = json.loads(path.read_text(encoding="utf-8"))["observed_at"]
        gate_update = update_gate1_state(
            brain.state_path,
            brain.gate_rule("GATE-1"),
            records,
            observed_at,
        )
    # Immediately assess the just-recorded check so the caller sees consequences.
    from .assess import assess_check
    _, findings = assess_check(brain, check_id)
    return {
        "command": "observe",
        "recorded": str(path.relative_to(paths.ENGINE_ROOT)),
        "check_id": check_id,
        "fulfillment": fulfillment,
        "gate_update": gate_update,
        "findings": [
            {"severity": f.severity, "finding": f.finding, "action": f.action}
            for f in findings
        ],
    }, 0


def cmd_sync(
    config: dict,
    observations_dir: Path | None = None,
    *,
    sources: set[str] | None = None,
) -> tuple[dict, int]:
    """Run selected sources independently so one credential cannot suppress another."""
    from .sync import SyncResult, sync_due

    selected = sources or {"semrush", "ga4", "gbp", "site"}
    unsupported = selected - {"semrush", "ga4", "gbp", "site"}
    if unsupported:
        return {"command": "sync", "error": f"unsupported sources: {sorted(unsupported)}"}, 4
    brain = load_brain()
    result = (
        sync_due(config, brain=brain, observations_dir=observations_dir)
        if "semrush" in selected
        else SyncResult(fetched=[], skipped_no_key=[], errors={})
    )
    from .gbp import sync_if_due
    fetched = list(result.fetched)
    errors = dict(result.errors)
    gbp_result = {"status": "not_selected"}
    if "gbp" in selected:
        try:
            gbp_result = sync_if_due(config, brain, observations_dir=observations_dir)
            if gbp_result["status"] == "fetched":
                fetched.append("gbp.performance")
        except Exception as err:  # noqa: BLE001 - provider failure becomes sync health
            gbp_result = {"status": "failed", "error": str(err)}
            errors["gbp.performance"] = str(err)
    from .site_facts import sync_public_facts
    site_facts_result = {"status": "not_selected"}
    if "site" in selected:
        try:
            site_facts_result = sync_public_facts(
                config, brain, observations_dir=observations_dir,
            )
            if site_facts_result["status"] == "fetched":
                fetched.append("site.facts_drift")
        except Exception as err:  # noqa: BLE001 - surfaced through sync.health
            site_facts_result = {"status": "failed", "error": str(err)}
            errors["site.facts_drift"] = str(err)
    from .ga4 import sync_if_due as sync_ga4_if_due
    ga4_result = {"status": "not_selected"}
    if "ga4" in selected:
        try:
            ga4_result = sync_ga4_if_due(
                config, brain, observations_dir=observations_dir,
            )
            if ga4_result["status"] == "fetched":
                fetched.append("analytics.traffic")
        except Exception as err:  # noqa: BLE001 - surfaced through sync.health
            ga4_result = {"status": "failed", "error": str(err)}
            errors["analytics.traffic"] = str(err)
    attempted = len(fetched) + len(errors)
    if attempted:
        record_observation(
            brain,
            "sync.health",
            {
                "checks_attempted": attempted,
                "checks_succeeded": len(fetched),
                "checks_failed": len(errors),
            },
            fulfillment="engine",
            source="agent:headless-sync",
            note="; ".join(f"{key}: {value}" for key, value in errors.items()),
            directory=observations_dir,
        )
    payload = {
        "command": "sync",
        "sources": sorted(selected),
        "fetched": fetched,
        "skipped_no_key": result.skipped_no_key,
        "errors": errors,
        "gbp": gbp_result,
        "site_facts": site_facts_result,
        "ga4": ga4_result,
        "note": ("no SEMRUSH_API_KEY present — these API-backed checks stay on the "
                 "session (MCP) path" if result.skipped_no_key else
                 f"fetched {len(fetched)} check(s) headlessly"),
    }
    if errors and fetched:
        return payload, 3
    if errors:
        return payload, 4
    return payload, 0


def cmd_tick(config: dict, observations_dir: Path | None = None) -> tuple[dict, int]:
    """Record credential-free daily watchdog observations."""
    from .freshness import record_daily_engine_checks
    engine_checks = record_daily_engine_checks(config, load_brain(), observations_dir)
    return {
        "command": "tick",
        "engine_checks": engine_checks,
        "note": "credential-free freshness watchdog recorded",
    }, 0


def _sitemap_urls(sitemap_url: str) -> list[str]:
    """Fetch and parse a sitemap's <loc> URLs. Uses a Googlebot UA — the live
    site bot-protects the default urllib UA (403)."""
    import re
    import urllib.request
    req = urllib.request.Request(
        sitemap_url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; "
                               "+http://www.google.com/bot.html)"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        xml = resp.read().decode(errors="ignore")
    return re.findall(r"<loc>([^<]+)</loc>", xml)


def cmd_gsc_sync(
    config: dict,
    *,
    observations_dir: Path | None = None,
    evidence_dir: Path | None = None,
) -> tuple[dict, int]:
    """Run independent GSC inspection and finalized query/page instruments."""
    from .gsc import (
        GscConfig,
        GscUnavailable,
        fetch_indexation,
        fetch_query_footprint,
    )
    from .query_footprint import write_top_rows_artifact

    brain = load_brain()
    gsc_cfg = config.get("gsc") or {}
    key_path = Path(gsc_cfg.get("key_path", ""))
    if not gsc_cfg or not key_path or not key_path.exists():
        return {
            "command": "gsc-sync",
            "fetched": False,
            "note": ("no GSC service-account key present — indexation and query "
                     "footprint remain unobserved"),
        }, 0
    cfg = GscConfig(key_path=key_path, site_url=gsc_cfg["site_url"])
    try:
        urls = _sitemap_urls(gsc_cfg["sitemap_url"])
    except Exception as err:  # noqa: BLE001
        return {"command": "gsc-sync", "fetched": False, "error": str(err)}, 4

    fetched: list[str] = []
    errors: dict[str, str] = {}
    recorded: dict[str, str] = {}
    gate_update = None
    findings_payload: list[dict] = []
    try:
        indexation = fetch_indexation(cfg, urls)
        path = record_observation(
            brain, "seo.indexation", indexation, fulfillment="engine_api",
            source="google_search_console:url_inspection",
            note="headless index-coverage tally",
            directory=observations_dir,
        )
        observed_at = json.loads(path.read_text(encoding="utf-8"))["observed_at"]
        gate_update = update_gate1_state(
            brain.state_path,
            brain.gate_rule("GATE-1"),
            indexation,
            observed_at,
        )
        from .assess import assess_check
        _, findings = assess_check(
            brain, "seo.indexation", directory=observations_dir,
        )
        findings_payload = [
            {"severity": finding.severity, "finding": finding.finding}
            for finding in findings
        ]
        fetched.append("seo.indexation")
        recorded["seo.indexation"] = str(path)
    except Exception as err:  # noqa: BLE001 - one GSC instrument must not suppress the other
        errors["seo.indexation"] = str(err)

    try:
        artifact, footprint = fetch_query_footprint(
            cfg, pages_in_sitemap=len(urls),
        )
        artifact_path = write_top_rows_artifact(
            artifact,
            directory=evidence_dir or (paths.EVIDENCE_DIR / "gsc-query-footprint"),
        )
        try:
            artifact_source = str(artifact_path.relative_to(paths.ENGINE_ROOT))
        except ValueError:
            artifact_source = str(artifact_path)
        path = record_observation(
            brain, "seo.query_footprint", footprint, fulfillment="engine_api",
            source=artifact_source,
            note="GSC Search Analytics finalized 28-day query/page top_rows; not exhaustive",
            directory=observations_dir,
        )
        fetched.append("seo.query_footprint")
        recorded["seo.query_footprint"] = str(path)
        recorded["gsc_query_footprint_evidence"] = str(artifact_path)
    except Exception as err:  # noqa: BLE001 - one GSC instrument must not suppress the other
        errors["seo.query_footprint"] = str(err)

    code = 0 if not errors else (3 if fetched else 4)
    return {
        "command": "gsc-sync",
        "fetched": fetched,
        "errors": errors,
        "urls_inspected": len(urls),
        "recorded": recorded,
        "gate_update": gate_update,
        "findings": findings_payload,
    }, code


def cmd_brief(config: dict) -> tuple[dict, int]:
    """The full operator briefing: gates, what's due, standing findings,
    priority order. One call answers 'what do I do now and why'."""
    brain = load_brain()
    has_key = _has_semrush_key(config)
    plan = build_plan(
        brain,
        has_semrush_key=has_key,
        has_gsc=_has_gsc(config),
        has_ga4=_has_ga4(config),
    )
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
