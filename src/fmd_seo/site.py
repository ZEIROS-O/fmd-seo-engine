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
        raise SiteSyncError(
            f"site worktree is dirty before sync: {dirty[:300]} "
            "(inspect with `fmd-seo site-reset`; discard with `--force`)"
        )
    _git(worktree, "fetch", "origin")
    ancestry = subprocess.run(
        ["git", "-C", str(worktree), "merge-base", "--is-ancestor", "HEAD", "origin/main"],
        capture_output=True,
        text=True,
    )
    if ancestry.returncode != 0:
        raise SiteSyncError(
            "site HEAD is not an ancestor of origin/main; refusing to discard "
            "a clean local or divergent commit "
            "(inspect with `fmd-seo site-reset`; discard with `--force`)"
        )
    _git(worktree, "reset", "--hard", "origin/main")
    dirty_after = _git(worktree, "status", "--porcelain")
    if dirty_after:
        raise SiteSyncError(f"site worktree dirty after sync: {dirty_after[:300]}")
    return _git(worktree, "rev-parse", "HEAD")


def reset_worktree(worktree: Path, *, force: bool = False) -> dict:
    """Report divergence, or explicitly hard-sync the isolated site to origin/main.

    Destructive cleanup is available only behind ``force``. The branch ref is
    not deleted, so divergent commits remain recoverable after detaching HEAD --
    but commits made while already detached survive only in the reflog, and
    uncommitted edits are destroyed outright. The receipt records exactly which
    paths were discarded under ``discarded``.
    """
    if not (worktree / ".git").exists():
        raise SiteSyncError(f"not a git worktree: {worktree}")
    _git(worktree, "fetch", "origin")
    branch = _git(worktree, "branch", "--show-current") or "(detached)"
    head = _git(worktree, "rev-parse", "HEAD")
    origin = _git(worktree, "rev-parse", "origin/main")
    counts = _git(worktree, "rev-list", "--left-right", "--count", "HEAD...origin/main")
    ahead, behind = (int(value) for value in counts.split())
    dirty = _git(worktree, "status", "--porcelain", "--untracked-files=all")
    report = {
        "command": "site-reset",
        "status": "NO_OP",
        "worktree": str(worktree),
        "branch": branch,
        "head": head,
        "origin_main": origin,
        "ahead": ahead,
        "behind": behind,
        "dirty": dirty.splitlines(),
        "needs_reset": bool(dirty or head != origin),
        "forced": force,
    }
    if not force:
        return report
    # Clean the attached branch without moving its ref, then detach at the
    # authoritative remote commit. Divergent commits remain recoverable by the
    # branch name even though the isolated worktree is now unwedged.
    _git(worktree, "reset", "--hard", "HEAD")
    _git(worktree, "clean", "-fd")
    _git(worktree, "switch", "--detach", "origin/main")
    remaining = _git(worktree, "status", "--porcelain", "--untracked-files=all")
    if remaining:
        raise SiteSyncError(f"site worktree dirty after forced reset: {remaining[:300]}")
    report.update({
        "status": "DONE",
        "head": _git(worktree, "rev-parse", "HEAD"),
        "branch": "(detached)",
        "ahead": 0,
        "behind": 0,
        # `dirty` describes the worktree now; `discarded` is the forensic record
        # of what the reset destroyed, which is otherwise unrecoverable.
        "dirty": [],
        "discarded": dirty.splitlines(),
        "needs_reset": False,
    })
    return report
