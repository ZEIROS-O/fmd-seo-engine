"""Observation store: the engine's memory of what has been measured and when.

An observation is one recorded run of one check: its records (the measured
fields) plus provenance (source, retrieval time, fulfillment path). Observations
are committed evidence — they are how `assess` evaluates gates and how `beat`
knows what is due. Raw API payloads stay in ignored `.run/`; the normalized
observation is committed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import paths
from .brain import Brain, Check

OBSERVATIONS_DIR = paths.ENGINE_ROOT / "brain" / "observations"

# How a check's data was obtained — provenance that survives into the receipt.
FULFILLMENT = {"engine_api", "mcp", "agent", "console", "engine"}


@dataclass(frozen=True)
class Observation:
    check_id: str
    observed_at: str        # ISO-8601, UTC
    fulfillment: str        # one of FULFILLMENT — HOW it was obtained
    records: dict[str, Any]  # measured fields, keyed by check.record_names
    source: str             # evidence file, API endpoint, console name, etc.
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _validate(check: Check, records: dict[str, Any], fulfillment: str) -> None:
    if fulfillment not in FULFILLMENT:
        raise ValueError(f"unknown fulfillment: {fulfillment}")
    expected = set(check.record_names)
    got = set(records)
    missing = expected - got
    if missing:
        raise ValueError(
            f"observation for {check.id} missing recorded field(s): {sorted(missing)}"
        )
    extra = got - expected
    if extra:
        raise ValueError(
            f"observation for {check.id} has undeclared field(s): {sorted(extra)}"
        )
    # Type-coerce per the check's declared record types; reject the uncoercible
    # rather than let a string sneak into a numeric threshold.
    for record in check.records:
        name, kind = record["name"], record["type"]
        value = records[name]
        if kind == "bool" and not isinstance(value, bool):
            raise ValueError(f"{check.id}.{name} must be bool, got {value!r}")
        if kind == "int" and (isinstance(value, bool) or not isinstance(value, int)):
            raise ValueError(f"{check.id}.{name} must be int, got {value!r}")
        if kind == "float" and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            raise ValueError(f"{check.id}.{name} must be float, got {value!r}")
        if kind == "str" and not isinstance(value, str):
            raise ValueError(f"{check.id}.{name} must be str, got {value!r}")


def record_observation(brain: Brain, check_id: str, records: dict[str, Any],
                       fulfillment: str, source: str, note: str = "",
                       observed_at: str | None = None,
                       directory: Path | None = None) -> Path:
    check = brain.check(check_id)
    _validate(check, records, fulfillment)
    stamp = observed_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    obs = Observation(
        check_id=check_id,
        observed_at=stamp,
        fulfillment=fulfillment,
        records=records,
        source=source,
        note=note,
    )
    out_dir = (directory or OBSERVATIONS_DIR) / check_id
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = stamp.replace(":", "").replace("-", "") + ".json"
    path = out_dir / fname
    path.write_text(json.dumps(obs.to_dict(), indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")
    return path


def load_observations(check_id: str, directory: Path | None = None) -> list[Observation]:
    out_dir = (directory or OBSERVATIONS_DIR) / check_id
    if not out_dir.exists():
        return []
    obs = []
    for path in sorted(out_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        obs.append(Observation(**data))
    return sorted(obs, key=lambda o: o.observed_at)


def latest_observation(check_id: str, directory: Path | None = None) -> Observation | None:
    obs = load_observations(check_id, directory)
    return obs[-1] if obs else None


def last_seen_map(brain: Brain, directory: Path | None = None) -> dict[str, str]:
    """check_id -> latest observed_at, for every check that has one."""
    result: dict[str, str] = {}
    for check in brain.checks:
        obs = latest_observation(check.id, directory)
        if obs is not None:
            result[check.id] = obs.observed_at
    return result
