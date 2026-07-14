"""Run lock with stale-lock recovery, plus resume-point helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .receipts import now_iso


class LockHeld(RuntimeError):
    pass


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False
    return True


class RunLock:
    def __init__(self, lock_file: Path):
        self.lock_file = lock_file
        self.stale_recovered = False

    def acquire(self, run_id: str) -> None:
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        if self.lock_file.exists():
            try:
                held = json.loads(self.lock_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                held = {}
            pid = held.get("pid")
            if isinstance(pid, int) and pid != os.getpid() and _pid_alive(pid):
                raise LockHeld(f"Run lock held by live pid {pid} (run {held.get('run_id')})")
            self.stale_recovered = True
        self.lock_file.write_text(
            json.dumps({"pid": os.getpid(), "run_id": run_id, "acquired_at": now_iso()}),
            encoding="utf-8",
        )

    def release(self) -> None:
        try:
            self.lock_file.unlink()
        except FileNotFoundError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.release()
        return False
