"""The brain: check registry, standing state, gates, and a restricted evaluator.

The engine cannot call MCP tools — those live only inside a Claude Code session.
So the engine does not fetch. It *decides*: what is due, what to check, what the
thresholds are, and what the result means. The agent session is the hands.

Threshold expressions are evaluated by a restricted AST walker: comparisons and
boolean ops over observation fields only. No calls, no attributes, no
subscripts, no imports, no builtins. `eval` is never used on brain input.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from . import paths

BRAIN_DIR = paths.ENGINE_ROOT / "brain"
CHECKS_FILE = BRAIN_DIR / "checks.yaml"
STATE_FILE = BRAIN_DIR / "state.yaml"
GATES_FILE = BRAIN_DIR / "gates.yaml"
THESIS_FILE = BRAIN_DIR / "thesis.md"

# per_draft is event-driven, never time-scheduled.
CADENCE_DAYS: dict[str, int | None] = {
    "daily": 1,
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "per_draft": None,
}

# A time-scheduled check becomes DUE at one complete cadence. That is what the
# operator work order and the planner act on.
DUE_CADENCE_MULTIPLIER = 1

# It becomes OVERDUE one complete cadence plus one day of grace. The two are
# deliberately not the same instant: the producer runs on a daily cron, so a
# daily check is always ~24h old at the moment the watchdog asks. With zero
# slack every on-schedule daily check reads as neglected, permanently, and
# engine.freshness fires a standing critical finding that means nothing. One day
# is the smallest grace that absorbs the cron's own period, and it can never
# hide a fully missed cycle — at two cadences a check is overdue for any cadence
# in the registry.
OVERDUE_CADENCE_MULTIPLIER = 1
OVERDUE_GRACE_DAYS = 1


def overdue_after(cadence_days: int) -> timedelta:
    """The age at which a time-scheduled check counts as neglected.

    The single definition. Both freshness surfaces call it, so the same evidence
    cannot be overdue in one and current in the other.
    """
    return timedelta(
        days=OVERDUE_CADENCE_MULTIPLIER * cadence_days + OVERDUE_GRACE_DAYS
    )

SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"]

# Methods the engine itself can never execute — they need the agent session.
AGENT_METHODS = {"mcp", "agent", "console", "http"}
EXECUTION_MODES = {"scheduled", "session", "console"}
INSTRUMENT_STATUSES = {"active", "retired"}

# Bare literals allowed in threshold expressions so YAML authors can write
# `has_localbusiness == false` instead of Python's `False`.
LITERALS = {"true": True, "false": False, "none": None}


class BrainError(ValueError):
    pass


class ExpressionError(BrainError):
    pass


# ─────────────────────── restricted evaluator ───────────────────────

_ALLOWED_NODES = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or, ast.UnaryOp, ast.Not,
    ast.Compare, ast.Name, ast.Load, ast.Constant,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.BinOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.List, ast.Tuple,
)


def _eval_node(node: ast.AST, scope: dict[str, Any]) -> Any:
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, scope)
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in LITERALS:
            return LITERALS[node.id]
        if node.id not in scope:
            raise ExpressionError(f"unknown field: {node.id}")
        return scope[node.id]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [_eval_node(e, scope) for e in node.elts]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return not _eval_node(node.operand, scope)
    if isinstance(node, ast.BoolOp):
        values = (_eval_node(v, scope) for v in node.values)
        if isinstance(node.op, ast.And):
            return all(values)
        return any(values)
    if isinstance(node, ast.BinOp):
        left, right = _eval_node(node.left, scope), _eval_node(node.right, scope)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if isinstance(node.op, ast.Div):
            if right == 0:
                raise ExpressionError("division by zero")
            return left / right
    if isinstance(node, ast.Compare):
        left = _eval_node(node.left, scope)
        for op, comparator in zip(node.ops, node.comparators):
            right = _eval_node(comparator, scope)
            if isinstance(op, ast.Eq):
                ok = left == right
            elif isinstance(op, ast.NotEq):
                ok = left != right
            elif isinstance(op, ast.Lt):
                ok = left < right
            elif isinstance(op, ast.LtE):
                ok = left <= right
            elif isinstance(op, ast.Gt):
                ok = left > right
            elif isinstance(op, ast.GtE):
                ok = left >= right
            elif isinstance(op, ast.In):
                ok = left in right
            elif isinstance(op, ast.NotIn):
                ok = left not in right
            else:
                raise ExpressionError(f"unsupported comparison: {type(op).__name__}")
            if not ok:
                return False
            left = right
        return True
    raise ExpressionError(f"unsupported expression node: {type(node).__name__}")


def evaluate(expr: str, scope: dict[str, Any]) -> bool:
    """Evaluate a threshold expression against observation records.

    Raises ExpressionError on anything outside the allowlist or on a missing
    field. Missing fields must raise, not default to False — a threshold that
    silently never fires is worse than a crash.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as err:
        raise ExpressionError(f"invalid expression {expr!r}: {err}") from err
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ExpressionError(
                f"disallowed construct {type(node).__name__} in {expr!r}"
            )
    return bool(_eval_node(tree, scope))


# ─────────────────────────── contracts ───────────────────────────

@dataclass(frozen=True)
class Threshold:
    expr: str
    severity: str
    finding: str
    action: str

    def __post_init__(self) -> None:
        if self.severity not in SEVERITY_ORDER:
            raise BrainError(f"unknown severity: {self.severity}")


@dataclass(frozen=True)
class Check:
    id: str
    domain: str
    title: str
    cadence: str
    cost: str
    method_kind: str
    method_run: str
    records: list[dict[str, str]]
    thresholds: list[Threshold]
    why: str
    execution_mode: str = "session"
    thesis_refs: list[str] = field(default_factory=list)
    instrument_ref: str = ""

    @property
    def cadence_days(self) -> int | None:
        return CADENCE_DAYS[self.cadence]

    @property
    def record_names(self) -> list[str]:
        return [r["name"] for r in self.records]


@dataclass
class Brain:
    checks: list[Check]
    state: dict[str, Any]
    gate_rules: dict[str, dict[str, Any]] = field(default_factory=dict)
    expression_constants: dict[str, Any] = field(default_factory=dict)
    # Ordered work-order entries from brain/priorities.yaml. The single copy —
    # a caller filters by live gate state instead of re-deriving from prose.
    priorities: list[dict[str, Any]] = field(default_factory=list)
    instruments: dict[str, dict[str, Any]] = field(default_factory=dict)
    thesis_path: Path = THESIS_FILE
    state_path: Path = STATE_FILE
    _by_id: dict[str, Check] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._by_id = {c.id: c for c in self.checks}

    def check(self, check_id: str) -> Check:
        if check_id not in self._by_id:
            raise BrainError(f"unknown check: {check_id}")
        return self._by_id[check_id]

    @property
    def gates(self) -> dict[str, Any]:
        return self.state.get("gates", {})

    def gate_state(self, gate_id: str) -> str:
        gate = self.gates.get(gate_id)
        if not gate:
            raise BrainError(f"unknown gate: {gate_id}")
        return gate["state"]

    def gate_rule(self, gate_id: str) -> dict[str, Any]:
        if gate_id not in self.gate_rules:
            raise BrainError(f"unknown gate rule: {gate_id}")
        return dict(self.gate_rules[gate_id])


def _parse_check(raw: dict, expression_constants: set[str] | None = None,
                 *, registry_version: int = 1) -> Check:
    required = {"id", "domain", "title", "cadence", "cost", "method", "records",
                "thresholds", "why"}
    missing = required - raw.keys()
    if missing:
        raise BrainError(f"check {raw.get('id', '?')} missing keys: {sorted(missing)}")
    if raw["cadence"] not in CADENCE_DAYS:
        raise BrainError(f"check {raw['id']}: unknown cadence {raw['cadence']}")
    execution_mode = raw.get("execution_mode", "session")
    if execution_mode not in EXECUTION_MODES:
        raise BrainError(
            f"check {raw['id']}: unknown execution_mode {execution_mode}"
        )
    if registry_version >= 2:
        missing_metadata = {
            "execution_mode", "thesis_refs", "instrument_ref",
        } - raw.keys()
        if missing_metadata:
            raise BrainError(
                f"check {raw['id']} missing metadata: {sorted(missing_metadata)}"
            )
    for record in raw["records"]:
        if set(record) - {"name", "type", "nullable"}:
            raise BrainError(
                f"check {raw['id']}: unknown record declaration keys for "
                f"{record.get('name', '?')}"
            )
        if record.get("nullable", False) not in {True, False}:
            raise BrainError(
                f"check {raw['id']}.{record.get('name', '?')}: nullable must be boolean"
            )

    thresholds = [Threshold(**t) for t in raw["thresholds"]]
    check = Check(
        id=raw["id"],
        domain=raw["domain"],
        title=raw["title"],
        cadence=raw["cadence"],
        cost=raw["cost"],
        method_kind=raw["method"]["kind"],
        method_run=raw["method"]["run"].strip(),
        records=raw["records"],
        thresholds=thresholds,
        why=raw["why"].strip(),
        execution_mode=execution_mode,
        thesis_refs=list(raw.get("thesis_refs") or []),
        instrument_ref=str(raw.get("instrument_ref") or ""),
    )

    # A threshold referencing a field the check never records can never fire.
    # Catch it at load time, not silently at assess time.
    names = set(check.record_names)
    for threshold in thresholds:
        try:
            tree = ast.parse(threshold.expr, mode="eval")
        except SyntaxError as err:
            raise BrainError(f"check {check.id}: bad expr {threshold.expr!r}: {err}") from err
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        unknown = used - names - set(LITERALS) - (expression_constants or set())
        if unknown:
            raise BrainError(
                f"check {check.id}: threshold {threshold.expr!r} references "
                f"unrecorded field(s) {sorted(unknown)}; recorded: {sorted(names)}"
            )
        nullable_used = {
            record["name"] for record in check.records
            if record.get("nullable") and record["name"] in used
        }
        if nullable_used:
            boolean_guards = {
                record["name"] for record in check.records
                if record["type"] == "bool" and record["name"] in used
            }
            if not boolean_guards:
                raise BrainError(
                    f"check {check.id}: threshold {threshold.expr!r} uses nullable "
                    f"field(s) {sorted(nullable_used)} without a boolean measurability guard"
                )
    return check


def _load_instruments(path: Path) -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if raw.get("schema_version") != 1:
        raise BrainError(f"unsupported instruments schema: {path}")
    instruments: dict[str, dict[str, Any]] = {}
    for entry in raw.get("instruments") or []:
        missing = {"id", "status", "purpose", "source"} - entry.keys()
        if missing:
            raise BrainError(
                f"instrument {entry.get('id', '?')} missing keys: {sorted(missing)}"
            )
        instrument_id = str(entry["id"])
        if instrument_id in instruments:
            raise BrainError(f"duplicate instrument id: {instrument_id}")
        if entry["status"] not in INSTRUMENT_STATUSES:
            raise BrainError(
                f"instrument {instrument_id}: unknown status {entry['status']}"
            )
        if entry["status"] == "retired":
            missing_retirement = {"retired_at", "rationale"} - entry.keys()
            if missing_retirement:
                raise BrainError(
                    f"retired instrument {instrument_id} missing keys: "
                    f"{sorted(missing_retirement)}"
                )
        instruments[instrument_id] = dict(entry)
    return instruments


def _parse_priorities(path: Path) -> list[dict[str, Any]]:
    """Load the ordered work order. Malformed entries fail closed at load time.

    An entry the planner cannot attribute to a gate state would silently vanish
    from `beat`'s output, which is exactly the drift this file exists to end.
    """
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    version = raw.get("schema_version")
    if version not in {1, 2}:
        raise BrainError(f"unsupported priorities schema: {path}")

    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw.get("priorities") or []):
        missing = {"id", "gate", "label"} - entry.keys()
        if missing:
            raise BrainError(f"priority #{index + 1} missing keys: {sorted(missing)}")
        if not isinstance(entry["gate"], dict) or not entry["gate"]:
            raise BrainError(f"priority {entry['id']}: gate must be a non-empty mapping")
        if entry["id"] in seen:
            raise BrainError(f"duplicate priority id: {entry['id']}")
        seen.add(entry["id"])
        action = entry.get("action")
        if version >= 2:
            if not isinstance(action, dict) or not {"type", "target", "owner"} <= action.keys():
                raise BrainError(
                    f"priority {entry['id']}: v2 requires action type, target, and owner"
                )
        entries.append({
            "id": entry["id"],
            "gate": dict(entry["gate"]),
            "thesis_refs": list(entry.get("thesis_refs") or []),
            "label": " ".join(str(entry["label"]).split()),
            "action": dict(action or {}),
        })
    if not entries:
        raise BrainError(f"no priorities defined: {path}")
    return entries


def priority_order(brain: Brain) -> list[str]:
    """The labels that apply under every gate's current state, in file order."""
    return [entry["label"] for entry in brain.priorities
            if all(brain.gate_state(gate_id) == state
                   for gate_id, state in entry["gate"].items())]


def load_brain(brain_dir: Path | None = None) -> Brain:
    directory = brain_dir or BRAIN_DIR
    checks_file = directory / "checks.yaml"
    state_file = directory / "state.yaml"
    gates_file = directory / "gates.yaml"
    priorities_file = directory / "priorities.yaml"
    for path in (checks_file, state_file, gates_file, priorities_file):
        if not path.exists():
            raise BrainError(f"brain file missing: {path}")

    raw_checks = yaml.safe_load(checks_file.read_text(encoding="utf-8"))
    checks_version = raw_checks.get("schema_version")
    if checks_version not in {1, 2}:
        raise BrainError(f"unsupported checks schema: {checks_file}")
    state = yaml.safe_load(state_file.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1:
        raise BrainError(f"unsupported state schema: {state_file}")

    raw_gates = yaml.safe_load(gates_file.read_text(encoding="utf-8"))
    if raw_gates.get("schema_version") != 1:
        raise BrainError(f"unsupported gates schema: {gates_file}")
    gate_rules = raw_gates.get("gates") or {}

    priorities = _parse_priorities(priorities_file)
    expression_constants: dict[str, Any] = {}
    gate1 = gate_rules.get("GATE-1", {})
    if gate1:
        expression_constants = {
            "gate1_indexed_min": gate1["indexed_min"],
            "gate1_not_indexed_max_exclusive": gate1["not_indexed_max_exclusive"],
        }
    instruments: dict[str, dict[str, Any]] = {}
    instruments_file = directory / "instruments.yaml"
    if checks_version >= 2:
        if not instruments_file.exists():
            raise BrainError(f"brain file missing: {instruments_file}")
        instruments = _load_instruments(instruments_file)
    elif instruments_file.exists():
        instruments = _load_instruments(instruments_file)
    checks = [
        _parse_check(
            c, set(expression_constants), registry_version=int(checks_version),
        )
        for c in raw_checks["checks"]
    ]
    for check in checks:
        if not check.instrument_ref:
            continue
        instrument = instruments.get(check.instrument_ref)
        if instrument is None:
            raise BrainError(
                f"check {check.id} references unknown instrument {check.instrument_ref}"
            )
        if instrument["status"] == "retired":
            raise BrainError(
                f"active check {check.id} references retired instrument "
                f"{check.instrument_ref}"
            )
    ids = [c.id for c in checks]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise BrainError(f"duplicate check ids: {sorted(duplicates)}")
    return Brain(
        checks=checks,
        state=state,
        gate_rules=gate_rules,
        expression_constants=expression_constants,
        priorities=priorities,
        instruments=instruments,
        thesis_path=directory / "thesis.md",
        state_path=state_file,
    )


def due_checks(brain: Brain, last_seen: dict[str, str], now: datetime | None = None
               ) -> list[tuple[Check, str]]:
    """Return (check, reason) for every check due now, most severe cadence first.

    A check with no prior observation is always due — the engine never assumes
    an unmeasured check is passing.
    """
    current = now or datetime.now(timezone.utc)
    due: list[tuple[Check, str]] = []
    for check in brain.checks:
        days = check.cadence_days
        if days is None:
            continue  # per_draft: event-driven only
        stamp = last_seen.get(check.id)
        if stamp is None:
            due.append((check, "never observed"))
            continue
        observed = datetime.fromisoformat(stamp)
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        age = current - observed
        if age >= timedelta(days=DUE_CADENCE_MULTIPLIER * days):
            due.append((check, f"last observed {age.days}d ago (cadence {check.cadence})"))
    due.sort(key=lambda pair: (CADENCE_DAYS[pair[0].cadence] or 999, pair[0].id))
    return due
