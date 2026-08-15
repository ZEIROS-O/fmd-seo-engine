"""Verified site-action planning and PagePackage branch publication."""

from __future__ import annotations

import subprocess
import difflib
import hashlib
import json
from datetime import date
from pathlib import Path

from . import paths
from .brain import load_brain
from .contracts import load_package, load_patch_package
from .corpus import corpus_checks
from .export import content_destination, export_package, render_content_json, write_manifest
from .facts import FactError, load_snapshot, verify_binding
from .live_site import parse_live_posts
from .receipts import now_iso
from .report import append_intervention
from .site import sync_worktree
from .verify import checks_pass, deterministic_checks


class ActError(RuntimeError):
    pass


def validate_current_fact_binding(package, facts_file: Path) -> tuple[str, str, str]:
    """Reject a package whose captured fact slice is stale or no longer current."""
    captured = package.fact_snapshot or {}
    facts_used = captured.get("facts_used")
    source_hash = captured.get("source_hash")
    if not isinstance(facts_used, dict) or not facts_used or not source_hash:
        return "package_fact_binding", "BLOCK", "package has no complete fact snapshot"
    try:
        current = load_snapshot(facts_file, list(facts_used))
    except (FactError, OSError, KeyError, ValueError) as err:
        return "package_fact_binding", "BLOCK", str(err)
    if not verify_binding(current):
        return "package_fact_binding", "BLOCK", "canonical facts binding changed during verification"
    if current.source_hash != source_hash or current.facts_used != facts_used:
        return "package_fact_binding", "BLOCK", "package facts differ from current canonical facts"
    return "package_fact_binding", "PASS", f"current source hash {source_hash[:12]}"


def _run(repo: Path, *args: str) -> str:
    result = subprocess.run(
        [*args],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise ActError(f"{' '.join(args)} failed: {detail[-600:]}")
    return result.stdout.strip()


def _status(repo: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=repo,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise ActError(f"git status --porcelain failed: {result.stderr.strip()[-600:]}")
    return result.stdout


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _bypass_actions(worktree: Path) -> list[dict[str, str]]:
    city = _read(worktree / "src/components/CityPage.tsx").lower()
    chrome = _read(worktree / "src/components/SiteChrome.tsx")
    blog = _read(worktree / "src/routes/blog.$slug.tsx")
    areas = _read(worktree / "src/routes/areas.index.tsx")
    chat = _read(worktree / "src/routes/chat.tsx")
    pro = _read(worktree / "src/routes/fresh-pro.tsx")
    llms = _read(worktree / "public/llms.txt")
    return [
        {
            "action": "entity_decontamination",
            "target": "EZlocal, HotFrog, Cylex correction drafts",
            "state": (
                "DRAFT_READY_HUMAN_SUBMISSION"
                if (paths.ENGINE_ROOT / "drafts/entity-corrections/listing-corrections.json").exists()
                else "NEEDS_DRAFT"
            ),
        },
        {
            "action": "copy_language",
            "target": "src/components/CityPage.tsx",
            "state": "READY" if ("car detailing" in city or "auto detailing" in city) else "NEEDS_CHANGE",
        },
        {
            "action": "internal_linking",
            "target": "src/components/SiteChrome.tsx",
            "state": "READY" if 'href: "/chat"' in chrome else "NEEDS_CHANGE",
        },
        {
            "action": "schema_finish",
            "target": "areas, blog, chat, and fresh-pro routes",
            "state": "READY" if all(
                token in text
                for token, text in (
                    ('"CollectionPage"', areas),
                    ('"BlogPosting"', blog),
                    ('"WebPage"', chat),
                    ('"Service"', pro),
                )
            ) else "NEEDS_CHANGE",
        },
        {
            "action": "llms_refresh",
            "target": "public/llms.txt",
            "state": "READY" if all(route in llms for route in ("/areas", "/blog", "/chat")) else "NEEDS_CHANGE",
        },
    ]


def dry_run_plan(worktree: Path, package_path: Path | None = None,
                 facts_file: Path | None = None) -> dict:
    """Return the exact current diff and action queue using read-only git calls."""
    if not worktree.exists():
        return {
            "command": "act",
            "dry_run": True,
            "status": "BLOCK",
            "blockers": ["site worktree missing; run `fmd-seo site-init`"],
        }
    if not (worktree / ".git").exists():
        return {
            "command": "act",
            "dry_run": True,
            "status": "BLOCK",
            "blockers": [f"configured site path is not a git checkout: {worktree}"],
        }
    head = _run(worktree, "git", "rev-parse", "HEAD")
    status = _status(worktree)
    changed = [line[3:] for line in status.splitlines() if len(line) > 3]
    payload: dict = {
        "command": "act",
        "dry_run": True,
        "status": "DONE",
        "git": {
            "head": head,
            "changed_files": changed,
            "diff_stat": _run(worktree, "git", "diff", "--stat", "HEAD"),
        },
        "gate1_bypass_actions": _bypass_actions(worktree),
        "next_write_steps": [
            "sync worktree to origin/main",
            "apply fact-bound change",
            "run deterministic and corpus checks",
            "run production build and raw-HTML checks",
            "push a dated seo-engine branch and open a draft PR",
        ],
    }
    if package_path is not None:
        raw = json.loads(package_path.read_text(encoding="utf-8"))
        if "modifications" in raw:
            from .patch_action import validate_patch_package
            package = load_patch_package(package_path)
            if facts_file is None or not facts_file.is_file():
                payload["patch"] = {
                    "package_id": package.package_id,
                    "status": "BLOCK",
                    "blockers": ["canonical facts file is required for PatchPackage validation"],
                }
                return payload
            validation = validate_patch_package(
                worktree,
                package,
                current_fact_hash=hashlib.sha256(facts_file.read_bytes()).hexdigest(),
                facts_file=facts_file,
                evidence_dir=paths.EVIDENCE_DIR,
            )
            payload["patch"] = {
                "package_id": package.package_id,
                **validation,
                "modified_paths": [item["path"] for item in package.modifications],
            }
            return payload
        package = load_package(package_path)
        target = content_destination(worktree, package.content["slug"])
        rendered = json.dumps(render_content_json(package), indent=2, ensure_ascii=False) + "\n"
        existing = _read(target)
        payload["package"] = {
            "package_id": package.package_id,
            "target": str(target),
            "would_create": not target.exists(),
            "planned_diff": "".join(difflib.unified_diff(
                existing.splitlines(keepends=True),
                rendered.splitlines(keepends=True),
                fromfile=str(target) if target.exists() else "/dev/null",
                tofile=str(target),
            )),
        }
    return payload


def publish_patch_package(config: dict, package_path: Path) -> dict:
    """Apply a PatchPackage, verify the site build, and open a draft PR only."""
    package = load_patch_package(package_path)
    worktree = Path(config["paths"]["site_worktree"])
    facts_file = Path(config["paths"]["facts_file"])
    from .patch_action import validate_patch_package
    preflight = validate_patch_package(
        worktree,
        package,
        current_fact_hash=hashlib.sha256(facts_file.read_bytes()).hexdigest(),
        facts_file=facts_file,
        evidence_dir=paths.EVIDENCE_DIR,
    )
    if preflight["status"] != "DONE":
        return {"command": "act", **preflight}
    base_sha = sync_worktree(worktree)
    if base_sha != package.site_base_commit:
        return {
            "command": "act", "status": "BLOCK",
            "blockers": ["site base changed; regenerate the PatchPackage"],
        }
    branch = f"seo-engine/{date.today().isoformat()}-patch-{package.generator}"
    _run(worktree, "git", "switch", "-C", branch, base_sha)
    try:
        from .patch_action import apply_patch_package
        applied = apply_patch_package(
            worktree,
            package,
            current_fact_hash=hashlib.sha256(facts_file.read_bytes()).hexdigest(),
            facts_file=facts_file,
            evidence_dir=paths.EVIDENCE_DIR,
        )
        if applied["status"] != "DONE":
            return {"command": "act", "branch": branch, **applied}
        # Build then test, both before anything is staged. A build that
        # succeeds while the site's own checks fail is exactly the state a
        # draft PR must never reach -- and nothing is committed either way.
        for step, command in (
            ("patch_build", "build"),
            ("patch_tests", "test:seo-scripts"),
        ):
            try:
                _run(worktree, "bun", "run", command)
            except ActError as err:
                return {
                    "command": "act", "status": "BLOCK", "branch": branch,
                    "checks": [{"name": step, "verdict": "BLOCK", "detail": str(err)}],
                    "blockers": [str(err)],
                }
        paths_to_commit = [item["path"] for item in package.modifications]
        _run(worktree, "git", "add", "--", *paths_to_commit)
        _run(
            worktree, "git", "commit", "-m",
            f"SEO: apply {package.generator} patch ({package.package_id})",
        )
        branch_sha = _run(worktree, "git", "rev-parse", "HEAD")
        try:
            _run(worktree, "git", "push", "-u", "origin", branch)
            pr_url = _run(
                worktree, "gh", "pr", "create", "--draft", "--base", "main",
                "--head", branch, "--title", f"SEO: {package.generator} patch",
                "--body", (
                    f"Generated from immutable PatchPackage `{package.package_id}`.\n\n"
                    "Modify-only, base/fact/hash guarded. Human merge and deployment required."
                ),
            )
        except ActError as err:
            return {
                "command": "act", "status": "BLOCK", "branch": branch,
                "commit_hashes": {"site": branch_sha}, "blockers": [str(err)],
            }
        return {
            "command": "act", "status": "DONE", "branch": branch,
            "pr_url": pr_url, "commit_hashes": {"site": branch_sha},
            "checks": [
                {"name": "patch_build", "verdict": "PASS", "detail": "bun run build"},
                {"name": "patch_tests", "verdict": "PASS",
                 "detail": "bun run test:seo-scripts"},
            ],
        }
    finally:
        # `git switch` carries uncommitted changes across, so a rejected patch
        # would survive as a dirty worktree -- and `sync_worktree` refuses to
        # run against one, wedging every later action behind a manual reset.
        # The tree was verified clean before the patch was applied, so the only
        # thing this discards is what this call itself wrote.
        _run(worktree, "git", "reset", "--hard", "HEAD")
        _run(worktree, "git", "switch", "--detach", base_sha)


def publish_package(config: dict, package_path: Path) -> dict:
    """Publish one verified package to a dated branch and open a draft PR."""
    brain = load_brain()
    if brain.gate_state("GATE-1") != "OPEN":
        return {
            "command": "act",
            "status": "BLOCK",
            "blockers": ["GATE-1 is CLOSED; supporting-page publication is disabled"],
        }

    package = load_package(package_path)
    worktree = Path(config["paths"]["site_worktree"])
    try:
        content_destination(worktree, package.content["slug"])
    except ValueError as err:
        return {"command": "act", "status": "BLOCK", "blockers": [str(err)]}
    binding = validate_current_fact_binding(package, Path(config["paths"]["facts_file"]))
    if binding[1] == "BLOCK":
        return {
            "command": "act",
            "status": "BLOCK",
            "checks": [{"name": binding[0], "verdict": binding[1], "detail": binding[2]}],
            "blockers": [binding[2]],
        }
    base_sha = sync_worktree(worktree)
    slug = package.content["slug"]
    branch = f"seo-engine/{date.today().isoformat()}-{slug}"
    _run(worktree, "git", "switch", "-C", branch, "origin/main")
    try:
        checks = [binding]
        checks.extend(deterministic_checks(
            package,
            site_public_dir=worktree / "public",
            known_routes={
                "/", "/areas", "/blog", "/chat", "/fleet", "/boat",
                "/fresh-pro", "/interior-detailing", "/mobile-detailing", "/#booking",
            },
        ))
        places = package.fact_snapshot.get("facts_used", {}).get("service_area.places", [])
        checks.extend(corpus_checks(
            package.content,
            worktree / "content" / "blog",
            places,
            live_posts=parse_live_posts(worktree),
        ))
        if not checks_pass(checks):
            return {
                "command": "act",
                "status": "BLOCK",
                "branch": branch,
                "checks": [
                    {"name": name, "verdict": verdict, "detail": detail}
                    for name, verdict, detail in checks
                ],
                "blockers": [name for name, verdict, _detail in checks if verdict == "BLOCK"],
            }

        export_checks, manifest = export_package(package, worktree)
        checks.extend(export_checks)
        if manifest is None or not checks_pass(checks):
            return {
                "command": "act",
                "status": "BLOCK",
                "branch": branch,
                "checks": [
                    {"name": name, "verdict": verdict, "detail": detail}
                    for name, verdict, detail in checks
                ],
                "blockers": [name for name, verdict, _detail in checks if verdict == "BLOCK"],
            }

        manifest_path = write_manifest(manifest, paths.EVIDENCE_DIR / "exports")
        branch_sha = _run(worktree, "git", "rev-parse", "HEAD")
        try:
            _run(worktree, "git", "push", "-u", "origin", branch)
            pr_url = _run(
                worktree,
                "gh", "pr", "create", "--draft", "--base", "main", "--head", branch,
                "--title", f"SEO: {package.content['title']}",
                "--body", (
                    f"Generated from immutable package `{package.package_id}`.\n\n"
                    "Deterministic, corpus, production-build, and raw-HTML checks passed."
                ),
            )
        except ActError as err:
            checks.append(("external_publish", "BLOCK", str(err)))
            return {
                "command": "act",
                "status": "BLOCK",
                "branch": branch,
                "manifest": str(manifest_path.relative_to(paths.ENGINE_ROOT)),
                "commit_hashes": {"site": branch_sha},
                "checks": [
                    {"name": name, "verdict": verdict, "detail": detail}
                    for name, verdict, detail in checks
                ],
                "blockers": [str(err)],
            }
        append_intervention(paths.EVIDENCE_DIR / "interventions.jsonl", {
            "occurred_at": now_iso(),
            "change": f"published PagePackage {package.package_id}: {package.content['title']}",
            "thesis_priority": "GATE-1 open topic queue",
            "sha": branch_sha,
            "branch": branch,
            "pr_url": pr_url,
            "merged_at": None,
        })
        notify = paths.ENGINE_ROOT / "bin" / "notify-run"
        if notify.exists():
            subprocess.run(
                ["bash", str(notify), "FMD-SEO act", "0", f"draft PR {pr_url}"],
                cwd=paths.ENGINE_ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
        return {
            "command": "act",
            "status": "DONE",
            "branch": branch,
            "pr_url": pr_url,
            "manifest": str(manifest_path.relative_to(paths.ENGINE_ROOT)),
            "commit_hashes": {"site": branch_sha},
            "checks": [
                {"name": name, "verdict": verdict, "detail": detail}
                for name, verdict, detail in checks
            ],
        }
    finally:
        _run(worktree, "git", "switch", "--detach", base_sha)
