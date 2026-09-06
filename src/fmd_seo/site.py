"""Safe synchronization primitives for the isolated Fresh site worktree."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


class SiteSyncError(RuntimeError):
    pass


def _write_site_receipt(
    state_path: Path, *, repository: str, base_ref: str, base_sha: str, worktree: Path,
) -> None:
    """Write the site-worktree receipt, or verify an existing one still agrees.

    The receipt is the record of which commit every patch package is based on.
    It is emitted here and nowhere else so its shape cannot drift from the code
    that reads it -- a hand-authored receipt is indistinguishable from a real
    one to every downstream consumer.
    """
    payload = {
        "repository": repository,
        "base_ref": base_ref,
        "base_sha": base_sha,
        "worktree": str(worktree),
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        existing = json.loads(state_path.read_text(encoding="utf-8"))
        if existing.get("base_sha") != base_sha:
            raise SiteSyncError(
                f"site worktree receipt already records a different base: {state_path}"
            )
        return
    state_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def initialize_site_worktree(
    worktree: Path,
    *,
    repository: str,
    base_ref: str,
    state_path: Path,
) -> dict:
    """Create a clean detached site checkout pinned to an exact base SHA.

    A clone is used rather than mutating another checkout's git-common-dir. It
    remains isolated from the user's dirty primary site checkout.
    """
    if worktree.exists():
        if not (worktree / ".git").exists():
            return {
                "status": "BLOCK",
                "blockers": [f"target exists but is not a git checkout: {worktree}"],
            }
        dirty = _git(worktree, "status", "--porcelain")
        if dirty:
            return {
                "status": "BLOCK",
                "blockers": [f"existing site checkout is dirty: {dirty[:300]}"],
            }
        base_sha = _git(worktree, "rev-parse", "HEAD")
        try:
            _write_site_receipt(
                state_path, repository=repository, base_ref=base_ref,
                base_sha=base_sha, worktree=worktree,
            )
        except Exception as err:  # noqa: BLE001 - structured failure, never a raw traceback
            return {"status": "BLOCK", "blockers": [str(err)]}
        return {
            "status": "NO_OP",
            "worktree": str(worktree),
            "base_sha": base_sha,
            "detached": not bool(_git(worktree, "branch", "--show-current")),
            "state": str(state_path),
        }

    worktree.parent.mkdir(parents=True, exist_ok=True)
    clone = subprocess.run(
        ["git", "clone", "--no-checkout", "--", repository, str(worktree)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if clone.returncode != 0:
        detail = clone.stderr.strip() or clone.stdout.strip()
        return {
            "status": "BLOCK",
            "blockers": [f"site clone failed: {detail[-500:]}"],
        }
    try:
        base_sha = _git(worktree, "rev-parse", base_ref)
        _git(worktree, "checkout", "--detach", base_sha)
        if _git(worktree, "status", "--porcelain"):
            raise SiteSyncError("new site checkout is unexpectedly dirty")
        _write_site_receipt(
            state_path, repository=repository, base_ref=base_ref,
            base_sha=base_sha, worktree=worktree,
        )
        return {
            "status": "DONE",
            "worktree": str(worktree),
            "base_sha": base_sha,
            "detached": True,
            "state": str(state_path),
        }
    except Exception as err:  # noqa: BLE001 - structured failure, never raw FileNotFound
        return {"status": "BLOCK", "blockers": [str(err)]}


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
