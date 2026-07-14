"""RunReceipt writing/loading. Every command run — success or failure — ends
with a receipt under receipts/."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

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

    def __init__(self, command: str):
        self.command = command
        self.run_id = new_run_id(command)
        self.started_at = now_iso()
        self._t0 = time.monotonic()
        self.checks: list[dict[str, str]] = []
        self.blockers: list[str] = []
        self.spend_usd = 0.0
        self.attempts = 1
        self.resume_point: str | None = None
        self.commit_hashes: dict[str, str] = {}

    def check(self, name: str, verdict: str, detail: str = "") -> None:
        self.checks.append({"name": name, "verdict": verdict, "detail": detail})
        if verdict == "BLOCK":
            self.blockers.append(f"{name}: {detail}" if detail else name)

    def finish(self, status: str | None = None) -> RunReceipt:
        if status is None:
            status = "BLOCK" if self.blockers else "DONE"
        return RunReceipt(
            run_id=self.run_id,
            status=status,
            started_at=self.started_at,
            ended_at=now_iso(),
            command=self.command,
            attempts=self.attempts,
            checks=self.checks,
            spend_usd=round(self.spend_usd, 4),
            blockers=self.blockers,
            resume_point=self.resume_point,
            commit_hashes=self.commit_hashes,
        )
