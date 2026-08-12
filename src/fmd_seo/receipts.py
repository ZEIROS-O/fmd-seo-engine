"""RunReceipt writing/loading. Every command run — success or failure — ends
with a receipt under receipts/."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from . import paths
from .contracts import RunReceipt, canonical_json, from_dict


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id(command: str) -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-{command}-{os.getpid()}"


def write_receipt(receipt: RunReceipt, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{receipt.run_id}.json"
    path.write_text(canonical_json(receipt.to_dict()), encoding="utf-8")
    return path


def load_receipt(path: Path) -> RunReceipt:
    return from_dict("RunReceipt", json.loads(path.read_text(encoding="utf-8")))


def latest_receipt(directory: Path, command: str | None = None) -> RunReceipt | None:
    if not directory.exists():
        return None
    candidates = sorted(directory.glob("*.json"))
    for path in reversed(candidates):
        receipt = load_receipt(path)
        if command is None or receipt.command == command:
            return receipt
    return None


class ReceiptBuilder:
    """Collects checks/blockers during a run and emits a final RunReceipt."""

    def __init__(self, command: str, *, ledger_file: Path | None = None,
                 baseline_file: Path | None = None):
        self.command = command
        self.run_id = new_run_id(command)
        self.started_at = now_iso()
        self._t0 = time.monotonic()
        self.checks: list[dict[str, str]] = []
        self.blockers: list[str] = []
        self._ledger_file = ledger_file or paths.SPEND_LEDGER
        self._ledger_start = self._ledger_total()
        self.spend_usd = 0.0
        self.attempts = 1
        self.resume_point: str | None = None
        self.commit_hashes: dict[str, str] = self._baseline_hashes(
            baseline_file or (paths.BASELINES_DIR / "repo-baselines.json")
        )

    def _ledger_total(self) -> float:
        if not self._ledger_file.exists():
            return 0.0
        entries = json.loads(self._ledger_file.read_text(encoding="utf-8"))
        return sum(float(e["reserved_usd"] if e.get("actual_usd") is None else e["actual_usd"])
                   for e in entries)

    @staticmethod
    def _baseline_hashes(path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return {label: str(record["head_sha"])
                for label, record in (data.get("repos") or {}).items()
                if record.get("head_sha")}

    def check(self, name: str, verdict: str, detail: str = "") -> None:
        self.checks.append({"name": name, "verdict": verdict, "detail": detail})
        if verdict == "BLOCK":
            self.blockers.append(f"{name}: {detail}" if detail else name)

    def finish(self, status: str | None = None) -> RunReceipt:
        if status is None:
            status = "BLOCK" if self.blockers else "DONE"
        ledger_delta = max(self._ledger_total() - self._ledger_start, 0.0)
        return RunReceipt(
            run_id=self.run_id,
            status=status,
            started_at=self.started_at,
            ended_at=now_iso(),
            command=self.command,
            attempts=self.attempts,
            checks=self.checks,
            spend_usd=round(max(self.spend_usd, ledger_delta), 4),
            blockers=self.blockers,
            resume_point=self.resume_point,
            commit_hashes=self.commit_hashes,
        )
