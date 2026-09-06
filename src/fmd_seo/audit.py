"""Independent, read-only integrity audit for committed engine artifacts."""

from __future__ import annotations

import ast
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from .brain import ExpressionError, evaluate
from .provenance import file_sha256, parse_file, resolve_source

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _recompute_local(_root: Path, _data: dict, source: Path) -> dict[str, Any]:
    from .local_finder import aggregate
    return aggregate(_jsonl(source))


def _recompute_grid(root: Path, _data: dict, source: Path) -> dict[str, Any]:
    from .geogrid import aggregate_map_pack
    manifest = root / "state" / "geogrid-task-manifest.json"
    task_count = len(json.loads(manifest.read_text(encoding="utf-8")).get("tasks") or []) \
        if manifest.exists() else None
    return aggregate_map_pack(_jsonl(source), fmd_aliases=[], tasks_posted=task_count)


def _recompute_positions(root: Path, _data: dict, source: Path) -> dict[str, Any]:
    from .serp_bulk import position_records
    manifest = root / "state" / "serp-bulk-task-manifest.json"
    expected = len(json.loads(manifest.read_text(encoding="utf-8")).get("tasks") or []) \
        if manifest.exists() else None
    return position_records(_jsonl(source), expected_keywords=expected)


def _recompute_competitors(root: Path, _data: dict, source: Path) -> dict[str, Any]:
    from .serp_bulk import competitor_records
    config = _load_yaml(root / "config" / "engine.yaml", {}) or {}
    candidates = sorted((root / "evidence").glob("serp-bulk-*/results*.jsonl"))
    previous_rows: list[dict[str, Any]] = []
    if source in candidates:
        index = candidates.index(source)
        if index:
            previous_rows = _jsonl(candidates[index - 1])
    return competitor_records(
        _jsonl(source),
        head_terms=list((config.get("serp_bulk") or {}).get("head_terms") or []),
        previous_rows=previous_rows,
    )


RECOMPUTE = {
    "seo.local_visibility": _recompute_local,
    "seo.map_pack": _recompute_grid,
    "seo.positions": _recompute_positions,
    "competitor.serp_movement": _recompute_competitors,
}


@dataclass(frozen=True)
class AuditFinding:
    severity: str
    code: str
    detail: str
    check_id: str = ""
    path: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "detail": self.detail,
            "check_id": self.check_id,
            "path": self.path,
        }


def _load_yaml(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    return default if value is None else value


def _parse_stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _observation_files(root: Path) -> list[Path]:
    directory = root / "brain" / "observations"
    return sorted(directory.glob("*/*.json")) if directory.exists() else []


def _grandfathered(root: Path) -> set[str]:
    data = json.loads((root / "evals" / "grandfathered.json").read_text(encoding="utf-8")) \
        if (root / "evals" / "grandfathered.json").exists() else {}
    values = data.get("observations", data if isinstance(data, list) else [])
    return {str(value) for value in values}


def _record_invariants(root: Path) -> dict[str, list[dict[str, str]]]:
    merged: dict[str, list[dict[str, str]]] = {}
    for path in sorted((root / "evals" / "invariants").glob("*.yaml")):
        for check_id, rules in (_load_yaml(path, {}) or {}).items():
            merged.setdefault(check_id, []).extend(rules or [])
    return merged


def _declared_record_fields(root: Path) -> dict[str, set[str]]:
    checks = (_load_yaml(root / "brain" / "checks.yaml", {}) or {}).get("checks", [])
    return {
        str(check.get("id")): {str(record["name"]) for record in check.get("records") or []}
        for check in checks
    }


def _audit_observations(root: Path, now: datetime) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    grandfathered = _grandfathered(root)
    invariants = _record_invariants(root)
    declared_fields = _declared_record_fields(root)
    for path in _observation_files(root):
        rel = str(path.relative_to(root))
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            observed_at = _parse_stamp(str(data["observed_at"]))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as err:
            findings.append(AuditFinding("critical", "invalid_observation", str(err), path=rel))
            continue
        check_id = str(data.get("check_id", ""))
        if observed_at > now:
            findings.append(AuditFinding("high", "future_observation", "observed_at is in the future", check_id, rel))
        if observed_at.utcoffset() != timedelta(0):
            findings.append(AuditFinding("high", "non_utc_timestamp", "observed_at must be normalized UTC", check_id, rel))
        records = data.get("records", {})
        expected_fields = declared_fields.get(check_id)
        if expected_fields is not None and set(records) != expected_fields:
            stored_fields = set(records)
            schema_version = int(data.get("schema_version", 1))
            if schema_version == 1 and stored_fields < expected_fields:
                findings.append(AuditFinding(
                    "info", "legacy_record_schema",
                    f"historical v1 stored {sorted(records)}; current declaration adds "
                    f"{sorted(expected_fields - stored_fields)}",
                    check_id, rel,
                ))
            else:
                findings.append(AuditFinding(
                    "info" if rel in grandfathered else "critical", "record_schema_mismatch",
                    f"stored {sorted(records)} != declared {sorted(expected_fields)}",
                    check_id, rel,
                ))
        for rule in invariants.get(check_id, []):
            try:
                passed = evaluate(str(rule["expr"]), records)
            except (ExpressionError, KeyError, TypeError) as err:
                findings.append(AuditFinding("critical", "record_invariant", f"{rule.get('expr')}: {err}", check_id, rel))
                continue
            if not passed:
                findings.append(AuditFinding(str(rule.get("severity", "critical")), "record_invariant", str(rule["expr"]), check_id, rel))

        source = str(data.get("source", ""))
        resolved = resolve_source(source, root)
        declared_kind = str(data.get("source_kind", ""))
        if resolved.kind == "file":
            assert resolved.path is not None
            recorded_hash = str(data.get("source_sha256", ""))
            if not recorded_hash:
                severity = "info" if rel in grandfathered else "critical"
                findings.append(AuditFinding(severity, "missing_source_hash", source, check_id, rel))
            if not resolved.path.exists():
                findings.append(AuditFinding("critical", "source_missing", source, check_id, rel))
            else:
                try:
                    parse_file(resolved.path)
                except (OSError, UnicodeError, ValueError, json.JSONDecodeError, yaml.YAMLError) as err:
                    findings.append(AuditFinding("critical", "source_unparseable", f"{source}: {err}", check_id, rel))
                else:
                    if recorded_hash and recorded_hash != file_sha256(resolved.path):
                        findings.append(AuditFinding("critical", "source_hash_mismatch", source, check_id, rel))
                    if observed_at < datetime.fromtimestamp(resolved.path.stat().st_mtime, timezone.utc):
                        severity = "info" if rel in grandfathered and not recorded_hash else "critical"
                        findings.append(AuditFinding(severity, "source_newer_than_observation", source, check_id, rel))
                    if resolved.path.suffix == ".json":
                        source_data = json.loads(resolved.path.read_text(encoding="utf-8"))
                        captured_at = source_data.get("captured_at") if isinstance(source_data, dict) else None
                        if captured_at and _parse_stamp(str(captured_at)) > observed_at:
                            findings.append(AuditFinding("critical", "evidence_newer_than_observation", source, check_id, rel))
                if resolved.path.exists() and resolved.path.suffix == ".jsonl" and check_id in RECOMPUTE:
                    try:
                        recomputed = RECOMPUTE[check_id](root, data, resolved.path)
                    except (OSError, ValueError, KeyError, json.JSONDecodeError) as err:
                        findings.append(AuditFinding("critical", "recompute_failed", str(err), check_id, rel))
                    else:
                        compare_fields = expected_fields or set(records)
                        mismatches = {
                            key: (records.get(key), recomputed.get(key))
                            for key in compare_fields
                            if key not in records or key not in recomputed
                            or records[key] != recomputed[key]
                        }
                        if mismatches:
                            findings.append(AuditFinding(
                                "critical", "recompute_mismatch",
                                json.dumps(mismatches, sort_keys=True), check_id, rel,
                            ))
        elif resolved.kind == "unknown":
            severity = "info" if rel in grandfathered and not declared_kind else "high"
            findings.append(AuditFinding(severity, "invalid_source_handle", source, check_id, rel))
        elif declared_kind and declared_kind != resolved.kind:
            findings.append(AuditFinding("high", "source_kind_mismatch", f"declared {declared_kind}, resolved {resolved.kind}", check_id, rel))
    return findings


def _audit_denominators(root: Path) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    manifest_path = root / "state" / "geogrid-task-manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        task_count = len(manifest.get("tasks") or [])
        posted_at = _parse_stamp(str(manifest["posted_at"])) if manifest.get("posted_at") else None
        for path in _observation_files(root):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("check_id") != "seo.map_pack":
                continue
            observed_at = _parse_stamp(str(data.get("observed_at")))
            if posted_at is not None and observed_at < posted_at:
                continue
            sampled = int((data.get("records") or {}).get("points_sampled", 0))
            if sampled != task_count:
                findings.append(AuditFinding(
                    "critical", "manifest_denominator_mismatch",
                    f"points_sampled {sampled} != manifest tasks {task_count}",
                    "seo.map_pack", str(path.relative_to(root)),
                ))
            if manifest.get("completed_at") is None and task_count:
                findings.append(AuditFinding(
                    "critical", "partial_observation",
                    "incomplete geogrid manifest produced an observation",
                    "seo.map_pack", str(path.relative_to(root)),
                ))
    return findings


def _audit_counter_metrics(root: Path) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    pairs = {
        "seo.local_visibility": ("pairs_tested", "pairs_ranked"),
        "seo.map_pack": ("points_sampled", "points_present"),
        "seo.positions": ("keywords_tracked", "top10_count"),
    }
    for check_id, (denominator, quality) in pairs.items():
        series: list[dict[str, Any]] = []
        directory = root / "brain" / "observations" / check_id
        for path in sorted(directory.glob("*.json")) if directory.exists() else []:
            series.append(json.loads(path.read_text(encoding="utf-8")))
        series.sort(key=lambda item: str(item.get("observed_at", "")))
        for previous, current in zip(series, series[1:]):
            before, after = previous.get("records") or {}, current.get("records") or {}
            if denominator not in before or denominator not in after or quality not in before or quality not in after:
                continue
            prior_denominator = float(before[denominator])
            if (prior_denominator > 0
                    and float(after[denominator]) < prior_denominator * 0.9
                    and float(after[quality]) > float(before[quality])):
                findings.append(AuditFinding(
                    "high", "shrinking_denominator",
                    f"{quality} improved while {denominator} shrank by more than 10%",
                    check_id,
                ))
    return findings


def _audit_injectability(root: Path) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    source_dir = root / "src" / "fmd_seo"
    committed_names = {"EVIDENCE_DIR", "PACKAGES_DIR", "STATE_DIR", "OBSERVATIONS_DIR"}
    write_methods = {"write_text", "write_bytes", "open", "touch"}
    for path in sorted(source_dir.glob("*.py")) if source_dir.exists() else []:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError as err:
            findings.append(AuditFinding("critical", "invalid_python", str(err), path=str(path.relative_to(root))))
            continue
        for function in (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))):
            attrs = {node.attr for node in ast.walk(function) if isinstance(node, ast.Attribute)}
            writes = any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                         and node.func.attr in write_methods for node in ast.walk(function))
            if attrs & committed_names and writes:
                parameters = {arg.arg for arg in (*function.args.args, *function.args.kwonlyargs)}
                if not any(name.endswith(("_dir", "_directory")) or name == "directory"
                           for name in parameters):
                    findings.append(AuditFinding(
                        "critical", "uninjectable_write",
                        f"{function.name} hardcodes a committed destination",
                        path=str(path.relative_to(root)),
                    ))
    return findings


def _miles_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 3958.8
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    value = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(value))


def _audit_geometry(root: Path) -> list[AuditFinding]:
    invariant_path = root / "evals" / "invariants" / "geometry.yaml"
    config_path = root / "config" / "engine.yaml"
    if not invariant_path.exists() or not config_path.exists():
        return []
    frozen = (_load_yaml(invariant_path, {}) or {}).get("geogrid") or {}
    configured = (_load_yaml(config_path, {}) or {}).get("geogrid") or {}
    expected_radius = float(frozen.get("sampling_radius_miles", 0))
    actual_radius = float(configured.get("radius_miles", 0))
    findings: list[AuditFinding] = []
    if expected_radius != actual_radius:
        findings.append(AuditFinding(
            "critical", "geometry_invariant",
            f"geogrid radius {actual_radius:g} != frozen {expected_radius:g}",
        ))
        return findings
    from .geogrid import build_grid
    center_lat, center_lon = map(float, configured.get("center") or (0, 0))
    size = int(configured.get("size", 5))
    points = build_grid(center_lat, center_lon, radius_miles=actual_radius, size=size)
    if frozen.get("service_radius_source"):
        facts_path = Path(str(((_load_yaml(config_path, {}) or {}).get("paths") or {}).get("facts_file", "")))
        if not facts_path.exists():
            findings.append(AuditFinding(
                "critical", "geometry_invariant", "service ring facts source is unavailable",
            ))
        else:
            facts = _load_yaml(facts_path, {}) or {}
            service_radius = float((facts.get("service_area") or {}).get("radius_miles", 0))
            outside = [
                point for point in points
                if _miles_between(center_lat, center_lon, point.latitude, point.longitude)
                > service_radius + 0.01
            ]
            if outside:
                findings.append(AuditFinding(
                    "critical", "geometry_invariant",
                    f"{len(outside)} generated point(s) fall outside the {service_radius:g}mi service ring",
                ))
    maximum_gap = actual_radius * math.sqrt(2) / (size - 1)
    for stronghold in frozen.get("strongholds") or []:
        latitude, longitude = float(stronghold["latitude"]), float(stronghold["longitude"])
        nearest = min(_miles_between(point.latitude, point.longitude, latitude, longitude)
                      for point in points)
        if nearest > maximum_gap:
            findings.append(AuditFinding(
                "critical", "geometry_invariant",
                f"stronghold {stronghold['name']} is {nearest:.2f}mi from nearest sample",
            ))
    return findings


def _contract_budget(root: Path) -> list[AuditFinding]:
    contract = root / "CONTRACT.md"
    config = root / "config" / "engine.yaml"
    if not contract.exists() or not config.exists():
        return [AuditFinding("critical", "budget_inputs_missing", "CONTRACT.md or config/engine.yaml is missing")]
    match = re.search(r"\$(\d+(?:\.\d+)?)\s+DataForSEO ceiling", contract.read_text(encoding="utf-8"), re.I)
    if not match:
        return [AuditFinding("high", "contract_budget_unparseable", "could not find DataForSEO ceiling")]
    configured = float((_load_yaml(config, {}) or {}).get("budget", {}).get("total_usd", 0))
    declared = float(match.group(1))
    if declared != configured:
        return [AuditFinding("critical", "contract_config_budget_drift", f"CONTRACT ${declared:g} != config ${configured:g}")]
    return []


def _audit_receipts_and_spend(root: Path, now: datetime) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    spend_path = root / "state" / "spend.json"
    entries = json.loads(spend_path.read_text(encoding="utf-8")) if spend_path.exists() else []
    receipts: list[dict[str, Any]] = []
    for path in sorted((root / "receipts").glob("*.json")):
        try:
            receipts.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as err:
            findings.append(AuditFinding("critical", "invalid_receipt", f"{path.name}: {err}"))
    baseline_path = root / "state" / "spend-reconciliation-baseline.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else None
    baseline_at = _parse_stamp(str(baseline["captured_at"])) if baseline else None
    baseline_index = -1
    if baseline:
        boundary_id = str(baseline.get("last_reservation_id", ""))
        matches = [index for index, entry in enumerate(entries) if str(entry.get("id")) == boundary_id]
        if len(matches) != 1:
            findings.append(AuditFinding("critical", "invalid_spend_baseline",
                                         f"boundary reservation {boundary_id!r} is not unique"))
        else:
            baseline_index = matches[0]
    receipt_windows: list[tuple[datetime, datetime]] = []
    for receipt in receipts:
        try:
            window = (_parse_stamp(receipt["started_at"]), _parse_stamp(receipt["ended_at"]))
            if baseline_at is None or window[1] > baseline_at:
                receipt_windows.append(window)
        except (KeyError, ValueError):
            findings.append(AuditFinding("critical", "invalid_receipt_window", str(receipt.get("run_id", "unknown"))))
    ids: set[str] = set()
    ledger_total = 0.0
    auditable_total = 0.0
    auditable_entries: list[dict[str, Any]] = []
    endpoint_totals: dict[str, float] = {}
    for index, entry in enumerate(entries):
        entry_id = str(entry.get("id", ""))
        if entry_id in ids:
            findings.append(AuditFinding("critical", "duplicate_reservation_id", entry_id))
        ids.add(entry_id)
        ts = _parse_stamp(str(entry["ts"]))
        actual = entry.get("actual_usd")
        amount = float(entry["reserved_usd"] if actual is None else actual)
        ledger_total += amount
        endpoint = str(entry.get("endpoint", ""))
        endpoint_totals[endpoint] = endpoint_totals.get(endpoint, 0.0) + amount
        if baseline and index <= baseline_index:
            if baseline_at is not None and ts > baseline_at:
                findings.append(AuditFinding("critical", "invalid_spend_baseline",
                                             f"boundary includes later entry {entry_id}"))
            continue
        auditable_total += amount
        auditable_entries.append(entry)
        if not any(start <= ts <= end for start, end in receipt_windows):
            findings.append(AuditFinding("high", "orphan_spend", entry_id))
        if actual is None and now - ts > timedelta(hours=24):
            findings.append(AuditFinding("high", "stale_reservation", entry_id))
    if baseline:
        declared = float(baseline.get("ledger_total_usd", -1))
        prefix_entries = entries[:baseline_index + 1] if baseline_index >= 0 else []
        prefix_total = sum(float(e["reserved_usd"] if e.get("actual_usd") is None else e["actual_usd"])
                           for e in prefix_entries)
        if round(declared, 6) != round(prefix_total, 6):
            findings.append(AuditFinding("critical", "invalid_spend_baseline",
                                         f"baseline ${declared:.6f} != ledger prefix ${prefix_total:.6f}"))
        historical_receipts = sum(float(receipt.get("spend_usd", 0.0)) for receipt in receipts
                                  if _parse_stamp(receipt["ended_at"]) <= baseline_at)
        declared_receipts = float(baseline.get("receipt_total_usd", -1))
        if round(historical_receipts, 6) != round(declared_receipts, 6):
            findings.append(AuditFinding("critical", "invalid_spend_baseline",
                                         f"receipt baseline ${declared_receipts:.6f} != history ${historical_receipts:.6f}"))
        declared_endpoints = {str(key): float(value) for key, value in
                              (baseline.get("endpoint_totals_usd") or {}).items()}
        prefix_endpoints: dict[str, float] = {}
        for entry in prefix_entries:
            endpoint = str(entry.get("endpoint", ""))
            amount = float(entry["reserved_usd"] if entry.get("actual_usd") is None else entry["actual_usd"])
            prefix_endpoints[endpoint] = prefix_endpoints.get(endpoint, 0.0) + amount
        if {key: round(value, 6) for key, value in declared_endpoints.items()} != {
            key: round(value, 6) for key, value in prefix_endpoints.items()
        }:
            findings.append(AuditFinding("critical", "invalid_spend_baseline",
                                         "endpoint baseline does not match ledger prefix"))
    receipt_total = sum(float(receipt.get("spend_usd", 0.0)) for receipt in receipts
                        if baseline_at is None or _parse_stamp(receipt["ended_at"]) > baseline_at)
    comparison_total = auditable_total if baseline else ledger_total
    if round(receipt_total, 4) != round(comparison_total, 4):
        findings.append(AuditFinding("critical", "receipt_spend_mismatch", f"receipts ${receipt_total:.4f} != ledger ${comparison_total:.4f}"))
    config = _load_yaml(root / "config" / "engine.yaml", {}) or {}
    budget = config.get("budget", {})
    total_cap = float(budget.get("total_usd", 0.0))
    if ledger_total > total_cap:
        findings.append(AuditFinding("critical", "total_budget_exceeded", f"${ledger_total:.4f} > ${total_cap:.4f}"))
    for endpoint, cap in (budget.get("endpoint_caps_usd", {}) or {}).items():
        exception = float(((baseline or {}).get("endpoint_cap_exceptions_usd") or {}).get(endpoint, 0.0))
        endpoint_total = endpoint_totals.get(endpoint, 0.0) - exception
        if exception > float(((baseline or {}).get("endpoint_totals_usd") or {}).get(endpoint, 0.0)):
            findings.append(AuditFinding("critical", "invalid_spend_baseline",
                                         f"{endpoint} cap exception exceeds historical spend"))
        if endpoint_total > float(cap):
            findings.append(AuditFinding("critical", "endpoint_budget_exceeded", f"{endpoint}: ${endpoint_total:.4f} > ${float(cap):.4f}"))
    return findings


def _audit_coverage(root: Path) -> list[AuditFinding]:
    checks = (_load_yaml(root / "brain" / "checks.yaml", {}) or {}).get("checks", [])
    observed_ids = set()
    for path in _observation_files(root):
        try:
            observed_ids.add(json.loads(path.read_text(encoding="utf-8")).get("check_id"))
        except json.JSONDecodeError:
            continue
    findings: list[AuditFinding] = []
    for check in checks:
        check_id = str(check.get("id", ""))
        if check_id == "gbp.performance" and not check.get("thresholds"):
            findings.append(AuditFinding("high", "unwired_check", "gbp.performance has no thresholds", check_id))
        if check_id == "engine.freshness" and check_id not in observed_ids:
            findings.append(AuditFinding("high", "missing_engine_freshness", "engine.freshness has never been observed", check_id))
    return findings


def audit_repository(root: Path, now: datetime | None = None) -> list[AuditFinding]:
    """Audit only committed data under *root*; this function never writes."""
    current = now or datetime.now(timezone.utc)
    findings = _audit_observations(root, current)
    findings.extend(_audit_denominators(root))
    findings.extend(_audit_counter_metrics(root))
    findings.extend(_audit_injectability(root))
    findings.extend(_audit_geometry(root))
    findings.extend(_contract_budget(root))
    findings.extend(_audit_receipts_and_spend(root, current))
    findings.extend(_audit_coverage(root))
    return sorted(findings, key=lambda finding: (-SEVERITY_RANK[finding.severity], finding.code, finding.path))


def audit_payload(root: Path) -> tuple[dict[str, Any], int]:
    findings = audit_repository(root)
    highest = max((SEVERITY_RANK[finding.severity] for finding in findings), default=0)
    code = 4 if highest >= SEVERITY_RANK["critical"] else 3 if highest >= SEVERITY_RANK["high"] else 0
    return {"command": "audit", "findings": [finding.to_dict() for finding in findings]}, code
