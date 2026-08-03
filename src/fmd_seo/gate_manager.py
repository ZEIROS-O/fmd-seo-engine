"""Machine-managed GATE-1 transition logic with comment-preserving YAML edits."""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import yaml


def _replace_line(section: str, key: str, value: str) -> str:
    pattern = rf"(?m)^    {re.escape(key)}:.*$"
    replacement = f"    {key}: {value}"
    if re.search(pattern, section):
        return re.sub(pattern, replacement, section, count=1)
    anchor = r"(?m)^(    consecutive_clean_readings:.*)$"
    return re.sub(anchor, rf"\1\n{replacement}", section, count=1)


def update_gate1_state(
    state_file: Path,
    rule: dict,
    records: dict,
    observed_at: str,
) -> dict:
    text = state_file.read_text(encoding="utf-8")
    state = yaml.safe_load(text)
    gate = dict(state["gates"]["GATE-1"])
    current = datetime.fromisoformat(observed_at)
    last_raw = gate.get("last_counted_at")
    last = datetime.fromisoformat(str(last_raw)) if last_raw else None
    minimum_gap = timedelta(days=int(rule["minimum_days_between_readings"]))
    clean = (
        int(records["not_indexed"]) < int(rule["not_indexed_max_exclusive"])
        and int(records["indexed"]) >= int(rule["indexed_min"])
    )

    if clean and last is not None and current - last < minimum_gap:
        return gate

    if clean:
        count = int(gate.get("consecutive_clean_readings", 0)) + 1
        required = int(rule["consecutive_clean_required"])
        gate["state"] = "OPEN" if count >= required else "CLOSED"
        gate["reason"] = (
            f"clean indexation reading {count}/{required}; "
            + ("publish gate opened" if count >= required else "awaiting next weekly reading")
        )
        gate["consecutive_clean_readings"] = count
    else:
        gate["state"] = "CLOSED"
        gate["reason"] = (
            f"indexation dirty: indexed={records['indexed']}, "
            f"not_indexed={records['not_indexed']}"
        )
        gate["consecutive_clean_readings"] = 0
    gate["last_counted_at"] = observed_at

    marker = re.search(r"(?m)^  GATE-1:\s*$", text)
    if marker is None:
        raise ValueError("state file has no GATE-1 section")
    start = marker.start()
    next_gate = re.search(r"(?m)^  [A-Za-z0-9_-]+:\s*$", text[marker.end():])
    end = marker.end() + next_gate.start() if next_gate else len(text)
    section = text[start:end]
    section = _replace_line(section, "state", gate["state"])
    section = _replace_line(section, "reason", json.dumps(gate["reason"]))
    section = _replace_line(
        section,
        "consecutive_clean_readings",
        str(gate["consecutive_clean_readings"]),
    )
    section = _replace_line(section, "last_counted_at", json.dumps(observed_at))
    state_file.write_text(text[:start] + section + text[end:], encoding="utf-8")
    return gate
