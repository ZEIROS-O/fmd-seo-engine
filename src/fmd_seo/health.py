"""Persistent cross-run health counters for systemic provider failures."""

from __future__ import annotations

import json
from pathlib import Path


def _load(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": 1, "systemic_failures": {}}
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("systemic_failures"), dict):
        raise ValueError(f"invalid health state: {path}")
    return data


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def record_systemic_failure(path: Path, provider: str) -> int:
    data = _load(path)
    failures = data["systemic_failures"]
    count = int(failures.get(provider, 0)) + 1
    failures[provider] = count
    _write(path, data)
    return count


def clear_systemic_failures(path: Path, provider: str) -> None:
    data = _load(path)
    if data["systemic_failures"].get(provider, 0) == 0:
        return
    data["systemic_failures"][provider] = 0
    _write(path, data)
