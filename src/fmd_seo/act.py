"""Verified site-action planning and PagePackage branch publication."""

from __future__ import annotations

import subprocess
import difflib
import json
from datetime import date
from pathlib import Path

from . import paths
from .brain import load_brain
from .contracts import load_package
from .corpus import corpus_checks
from .export import content_destination, export_package, render_content_json, write_manifest
from .facts import FactError, load_snapshot
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


def dry_run_plan(worktree: Path, package_path: Path | None = None) -> dict:
    """Return the exact current diff and action queue using read-only git calls."""
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
        _run(worktree, "git", "switch", "--detach", base_sha)
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
