"""Kill switch: a DISABLED file at the engine root halts all commands.

Engage manually with `touch ~/fmd-seo-engine/DISABLED` or programmatically on
systemic failures (e.g. repeated auth/transport errors).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from . import paths


class KillSwitchEngaged(RuntimeError):
    pass


def _kill_file(root: Path | None = None) -> Path:
    return (root / "DISABLED") if root else paths.KILL_FILE


def engaged(root: Path | None = None) -> bool:
    return _kill_file(root).exists()


def engage(reason: str, root: Path | None = None) -> None:
    stamp = datetime.now(timezone.utc).isoformat()
    _kill_file(root).write_text(f"{stamp} {reason}\n", encoding="utf-8")


def assert_not_engaged(root: Path | None = None) -> None:
    kf = _kill_file(root)
    if kf.exists():
        raise KillSwitchEngaged(f"Kill switch engaged: {kf.read_text(encoding='utf-8').strip()}")
