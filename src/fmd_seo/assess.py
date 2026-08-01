"""Assess: evaluate thresholds against the latest observations and report gate
state. This is the engine deciding what its measurements *mean* — the judgment
the loop consults instead of Lou.

A finding fires when a threshold expression is true against a check's latest
observation. Findings are ranked most-severe first. Gates are read from
brain/state.yaml (machine-owned) and cross-checked against live observations so
a stale gate declaration cannot silently diverge from measured reality.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .brain import SEVERITY_ORDER, Brain, evaluate
from .observations import Observation, latest_observation


@dataclass(frozen=True)
class Finding:
    check_id: str
    domain: str
    severity: str
    finding: str
    action: str
    observed_at: str
    fulfillment: str
    expr: str

    @property
    def rank(self) -> int:
        return SEVERITY_ORDER.index(self.severity)


@dataclass(frozen=True)
class GateReport:
    gate_id: str
    name: str
    declared_state: str
    reason: str
    drift: str | None  # non-None if the declared state disagrees with observations


def assess_check(brain: Brain, check_id: str, directory: Path | None = None
                 ) -> tuple[Observation | None, list[Finding]]:
    check = brain.check(check_id)
    obs = latest_observation(check_id, directory)
    if obs is None:
        return None, []
    findings: list[Finding] = []
    for threshold in check.thresholds:
        if evaluate(
            threshold.expr,
            {**brain.expression_constants, **obs.records},
        ):
            findings.append(Finding(
                check_id=check.id,
                domain=check.domain,
                severity=threshold.severity,
                finding=threshold.finding,
                action=threshold.action,
                observed_at=obs.observed_at,
                fulfillment=obs.fulfillment,
                expr=threshold.expr,
            ))
    return obs, findings


def assess_all(brain: Brain, directory: Path | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for check in brain.checks:
        try:
            _, check_findings = assess_check(brain, check.id, directory)
            findings.extend(check_findings)
        except Exception as err:  # noqa: BLE001 - one broken check must not erase the rest
            try:
                obs = latest_observation(check.id, directory)
            except Exception:  # noqa: BLE001 - malformed storage is the failure being surfaced
                obs = None
            findings.append(Finding(
                check_id=check.id,
                domain=check.domain,
                severity="critical",
                finding=(f"Threshold evaluation failed for {check.id}: "
                         f"{type(err).__name__}: {err}"),
                action="Repair the malformed observation or threshold; other checks remain active.",
                observed_at=obs.observed_at if obs else "unknown",
                fulfillment=obs.fulfillment if obs else "engine",
                expr="<assessment>",
            ))
    findings.sort(key=lambda f: (-f.rank, f.domain, f.check_id))
    return findings


# ─────────────────────────── gate drift ───────────────────────────
#
# The gate state in state.yaml is the machine's declaration. Live observations
# can contradict it (e.g. indexation recovered but nobody re-declared the gate).
# We detect that drift rather than trusting the declaration blindly.

def _indexation_says(brain: Brain, directory: Path | None) -> str | None:
    obs = latest_observation("seo.indexation", directory)
    if obs is None:
        return None
    not_indexed = obs.records.get("not_indexed")
    indexed = obs.records.get("indexed")
    if not_indexed is None or indexed is None:
        return None
    rule = brain.gate_rule("GATE-1")
    if (
        not_indexed < rule["not_indexed_max_exclusive"]
        and indexed >= rule["indexed_min"]
    ):
        return "OPEN"
    return "CLOSED"


def assess_gates(brain: Brain, directory: Path | None = None) -> list[GateReport]:
    reports: list[GateReport] = []
    for gate_id, gate in brain.gates.items():
        drift = None
        if gate_id == "GATE-1":
            rule = brain.gate_rule(gate_id)
            required = int(rule["consecutive_clean_required"])
            observed = _indexation_says(brain, directory)
            declared = "OPEN" if gate["state"] == "OPEN" else "CLOSED"
            if observed is not None and observed != declared:
                consecutive = gate.get("consecutive_clean_readings", 0)
                if observed == "OPEN" and consecutive < required:
                    drift = ("indexation now meets the open condition; needs "
                             f"{required - consecutive} more consecutive clean weekly "
                             "reading(s) before GATE-1 opens")
                else:
                    drift = (f"declared {declared} but live indexation implies "
                             f"{observed} — re-declare after review")
        reports.append(GateReport(
            gate_id=gate_id,
            name=gate.get("name", gate_id),
            declared_state=gate["state"],
            reason=gate.get("reason", ""),
            drift=drift,
        ))
    return reports
