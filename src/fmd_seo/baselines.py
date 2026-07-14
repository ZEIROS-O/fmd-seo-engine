"""Baseline SHAs/status for the repos the engine touches or reads, and drift
detection against the recorded baseline."""

from __future__ import annotations

import json
from pathlib import Path

from .operator_adapter import snapshot
from .receipts import now_iso

REPO_LABELS = ("fresh_repo", "operator_repo", "zeiros_repo")
BASELINE_FILE = "repo-baselines.json"


def record(config: dict, baselines_dir: Path) -> Path:
    baselines_dir.mkdir(parents=True, exist_ok=True)
    entry = {"captured_at": now_iso(), "repos": {}}
    for label in REPO_LABELS:
        repo = Path(config["paths"][label])
        snap = snapshot(repo)
        entry["repos"][label] = {
            "path": str(repo),
            "head_sha": snap.head_sha,
            "status_hash": snap.status_hash,
        }
    path = baselines_dir / BASELINE_FILE
    path.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    return path


def check_drift(baselines_dir: Path) -> dict[str, str]:
    """Return {label: description} for repos that drifted from baseline.
    Empty dict = no drift. Missing baseline raises FileNotFoundError."""
    path = baselines_dir / BASELINE_FILE
    baseline = json.loads(path.read_text(encoding="utf-8"))
    drift: dict[str, str] = {}
    for label, rec in baseline["repos"].items():
        snap = snapshot(Path(rec["path"]))
        parts = []
        if snap.head_sha != rec["head_sha"]:
            parts.append(f"HEAD {rec['head_sha'][:10]} -> {snap.head_sha[:10]}")
        if snap.status_hash != rec["status_hash"]:
            parts.append("working-tree status changed")
        if parts:
            drift[label] = "; ".join(parts)
    return drift
