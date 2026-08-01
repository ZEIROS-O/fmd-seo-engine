"""Safe synchronization primitives for the isolated Fresh site worktree."""

from __future__ import annotations

import subprocess
from pathlib import Path


class SiteSyncError(RuntimeError):
    pass


def _git(worktree: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree), *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise SiteSyncError(f"git {' '.join(args)} failed: {detail[-500:]}")
    return result.stdout.strip()


def sync_worktree(worktree: Path) -> str:
    """Fetch and align an isolated, clean worktree to ``origin/main``.

    Dirty input fails before reset so operator work is never erased. Once clean,
    origin/main is authoritative and the isolated branch is reset to it.
    """
    if not (worktree / ".git").exists():
        raise SiteSyncError(f"not a git worktree: {worktree}")
    dirty = _git(worktree, "status", "--porcelain")
    if dirty:
        raise SiteSyncError(f"site worktree is dirty before sync: {dirty[:300]}")
    _git(worktree, "fetch", "origin")
    ancestry = subprocess.run(
        ["git", "-C", str(worktree), "merge-base", "--is-ancestor", "HEAD", "origin/main"],
        capture_output=True,
        text=True,
    )
    if ancestry.returncode != 0:
        raise SiteSyncError(
            "site HEAD is not an ancestor of origin/main; refusing to discard "
            "a clean local or divergent commit"
        )
    _git(worktree, "reset", "--hard", "origin/main")
    dirty_after = _git(worktree, "status", "--porcelain")
    if dirty_after:
        raise SiteSyncError(f"site worktree dirty after sync: {dirty_after[:300]}")
    return _git(worktree, "rev-parse", "HEAD")
