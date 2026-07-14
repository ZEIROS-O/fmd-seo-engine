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
THESIS_FILE = BRAIN_DIR / "thesis.md"

# per_draft is event-driven, never time-scheduled.
CADENCE_DAYS: dict[str, int | None] = {
    "daily": 1,
    "weekly": 7,
    "biweekly": 14,
    "monthly": 30,
    "per_draft": None,
}

SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"]

# Methods the engine itself can never execute — they need the agent session.
AGENT_METHODS = {"mcp", "agent", "console", "http"}

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
    thesis_path: Path = THESIS_FILE
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


def _parse_check(raw: dict) -> Check:
    required = {"id", "domain", "title", "cadence", "cost", "method", "records",
                "thresholds", "why"}
    missing = required - raw.keys()
    if missing:
        raise BrainError(f"check {raw.get('id', '?')} missing keys: {sorted(missing)}")
    if raw["cadence"] not in CADENCE_DAYS:
        raise BrainError(f"check {raw['id']}: unknown cadence {raw['cadence']}")

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
        unknown = used - names - set(LITERALS)
        if unknown:
            raise BrainError(
                f"check {check.id}: threshold {threshold.expr!r} references "
                f"unrecorded field(s) {sorted(unknown)}; recorded: {sorted(names)}"
            )
    return check


def load_brain(brain_dir: Path | None = None) -> Brain:
    directory = brain_dir or BRAIN_DIR
    checks_file, state_file = directory / "checks.yaml", directory / "state.yaml"
    for path in (checks_file, state_file):
        if not path.exists():
            raise BrainError(f"brain file missing: {path}")

    raw_checks = yaml.safe_load(checks_file.read_text(encoding="utf-8"))
    if raw_checks.get("schema_version") != 1:
        raise BrainError(f"unsupported checks schema: {checks_file}")
    state = yaml.safe_load(state_file.read_text(encoding="utf-8"))
    if state.get("schema_version") != 1:
        raise BrainError(f"unsupported state schema: {state_file}")

    checks = [_parse_check(c) for c in raw_checks["checks"]]
    ids = [c.id for c in checks]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise BrainError(f"duplicate check ids: {sorted(duplicates)}")
    return Brain(checks=checks, state=state, thesis_path=directory / "thesis.md")


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
        if age >= timedelta(days=days):
            due.append((check, f"last observed {age.days}d ago (cadence {check.cadence})"))
    due.sort(key=lambda pair: (CADENCE_DAYS[pair[0].cadence] or 999, pair[0].id))
    return due
