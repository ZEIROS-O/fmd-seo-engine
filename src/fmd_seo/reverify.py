"""Reconcile historical exports against current origin/main and live HTML."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Callable

from .htmlcheck import check_page
from .receipts import now_iso
from .report import append_intervention
from .site import sync_worktree


def _run_git(worktree: Path, *args: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["git", "-C", str(worktree), *args],
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def reverify_manifests(
    exports_dir: Path,
    worktree: Path,
    *,
    sync: bool = True,
    git_runner: Callable[..., tuple[int, str, str]] = _run_git,
    page_checker: Callable[..., dict] = check_page,
) -> dict:
    synced_sha = sync_worktree(worktree) if sync else None
    checks: list[dict[str, str]] = []
    reconciled: list[dict[str, str]] = []
    # Only active manifests live directly in exports/. Historical manifests
    # move under exports/archive/ with a supersede record and are never
    # re-verified against the current site.
    manifests = sorted(exports_dir.glob("*-export.json"))
    archived = sorted((exports_dir / "archive").glob("*-export.json"))
    if not manifests:
        checks.append({
            "name": "exports", "verdict": "PASS", "detail": "no export manifests",
        })
    for path in manifests:
        first_check = len(checks)
        data = json.loads(path.read_text(encoding="utf-8"))
        package_id = data["package_id"]
        commit = data["destination_commit"]
        code, _stdout, stderr = git_runner(
            worktree, "merge-base", "--is-ancestor", commit, "origin/main",
        )
        checks.append({
            "name": f"{package_id}:ancestor",
            "verdict": "PASS" if code == 0 else "BLOCK",
            "detail": (
                f"{commit} is on origin/main" if code == 0
                else f"{commit} not on origin/main: {stderr or 'not an ancestor'}"
            ),
        })
        for relative in data.get("generated_files") or []:
            exists = (worktree / relative).exists()
            checks.append({
                "name": f"{package_id}:file:{relative}",
                "verdict": "PASS" if exists else "BLOCK",
                "detail": "present" if exists else "missing from current worktree",
            })
        expected = data.get("expected") or {}
        if not expected:
            checks.append({
                "name": f"{package_id}:manifest_contract",
                "verdict": "BLOCK",
                "detail": "manifest predates exact live-page expectations",
            })
        live = page_checker(data["canonical_url"], expected=expected)
        for name, (verdict, detail) in live.items():
            checks.append({
                "name": f"{package_id}:live:{name}",
                "verdict": verdict,
                "detail": detail,
            })
        if all(check["verdict"] != "BLOCK" for check in checks[first_check:]):
            reconciled.append({"package_id": package_id, "sha": commit})
    blocked = [check["name"] for check in checks if check["verdict"] == "BLOCK"]
    return {
        "command": "reverify",
        "status": "BLOCK" if blocked else "DONE",
        "synced_sha": synced_sha,
        "manifests": len(manifests),
        "archived_manifests": len(archived),
        "checks": checks,
        "blockers": blocked,
        "reconciled": reconciled,
    }


def record_reconciled_interventions(
    result: dict,
    worktree: Path,
    interventions_path: Path,
    *,
    git_runner: Callable[..., tuple[int, str, str]] = _run_git,
) -> list[str]:
    """Append merge-proven interventions once, using the commit timestamp."""
    existing: set[str] = set()
    if interventions_path.exists():
        for line in interventions_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                event = json.loads(line)
                if event.get("merged_at") and event.get("sha"):
                    existing.add(event["sha"])
    recorded: list[str] = []
    for item in result.get("reconciled") or []:
        sha = item["sha"]
        if sha in existing:
            continue
        code, first_parent, stderr = git_runner(
            worktree, "rev-list", "--first-parent", "origin/main",
        )
        if code != 0:
            raise RuntimeError(f"cannot inspect origin/main first-parent history: {stderr}")
        if sha in first_parent.splitlines():
            merge_sha = sha
        else:
            code, ancestry, stderr = git_runner(
                worktree, "rev-list", "--ancestry-path", "--reverse", f"{sha}..origin/main",
            )
            if code != 0 or not ancestry:
                raise RuntimeError(
                    f"cannot prove merge descendant for {sha}: {stderr or 'empty ancestry path'}"
                )
            merge_sha = ancestry.splitlines()[0]
        code, merged_at, stderr = git_runner(
            worktree, "show", "-s", "--format=%cI", merge_sha,
        )
        if code != 0 or not merged_at:
            raise RuntimeError(
                f"cannot timestamp reconciled export {sha}: {stderr or 'empty git show'}"
            )
        append_intervention(interventions_path, {
            "occurred_at": now_iso(),
            "merged_at": merged_at,
            "change": f"merged PagePackage {item['package_id']}",
            "thesis_priority": "GATE-1 open topic queue",
            "sha": sha,
            "merge_sha": merge_sha,
        })
        recorded.append(sha)
        existing.add(sha)
    return recorded
