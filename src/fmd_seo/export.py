"""Export a verified PagePackage to the isolated site worktree, prove it
through the production build + raw-HTML checks, and emit an ExportManifest.

The site's JSON is generated output; the package stays authoritative.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from .contracts import ExportManifest, PagePackage, canonical_json
from .htmlcheck import check_slash_variants
from .receipts import now_iso
from .spike import _wait_port

RENDER_KEYS = [
    "slug", "title", "description", "canonical", "robots", "date_published",
    "hero_image", "blocks", "internal_links", "cta", "jsonld",
]
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def content_destination(worktree: Path, slug: str) -> Path:
    """Return a contained content path for a strictly portable URL slug."""
    if not isinstance(slug, str) or len(slug) > 80 or not SLUG_RE.fullmatch(slug):
        raise ValueError(f"unsafe content slug: {slug!r}")
    content_root = (worktree / "content" / "blog").resolve()
    destination = (content_root / f"{slug}.json").resolve()
    if destination.parent != content_root:
        raise ValueError(f"content destination escapes blog root: {destination}")
    return destination


def _changed_paths(worktree: Path) -> tuple[list[Path], str]:
    status = subprocess.run(
        ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        return [], status.stderr.strip()
    paths: list[Path] = []
    for line in status.stdout.splitlines():
        relative = line[3:]
        if " -> " in relative:
            relative = relative.split(" -> ", 1)[1]
        candidate = (worktree / relative).resolve()
        try:
            candidate.relative_to(worktree.resolve())
        except ValueError:
            return [], f"changed path escapes worktree: {relative}"
        paths.append(candidate)
    return paths, ""


def render_content_json(package: PagePackage) -> dict:
    """Project the package onto the site's content schema (render-only keys —
    claims/provenance metadata stay in the engine)."""
    return {k: package.content[k] for k in RENDER_KEYS if k in package.content}


def expected_page_contract(package: PagePackage) -> dict[str, str]:
    jsonld = package.content.get("jsonld") or {}
    return {
        "canonical": package.content["canonical"],
        "schema_type": str(jsonld.get("@type", "BlogPosting")),
        "headline": str(jsonld.get("headline", package.content.get("title", ""))),
        "date_published": str(jsonld.get("datePublished", package.content.get("date_published", ""))),
    }


def export_package(package: PagePackage, worktree: Path, *, port: int = 4176,
                   dry_run: bool = False) -> tuple[list[tuple[str, str, str]], ExportManifest | None]:
    checks: list[tuple[str, str, str]] = []
    slug = package.content["slug"]
    try:
        dest = content_destination(worktree, slug)
    except ValueError as err:
        checks.append(("content_slug", "BLOCK", str(err)))
        return checks, None

    if dry_run:
        checks.append(("export_plan", "PASS", f"would write {dest}"))
        return checks, None

    status = subprocess.run(["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all"],
                            capture_output=True, text=True)
    if status.returncode != 0:
        checks.append(("worktree_clean", "BLOCK",
                       f"git status failed: {status.stderr.strip()[-300:]}"))
        return checks, None
    if status.stdout.strip():
        checks.append(("worktree_clean", "BLOCK", f"dirty worktree: {status.stdout.strip()[:200]}"))
        return checks, None
    rev_parse = subprocess.run(["git", "-C", str(worktree), "rev-parse", "HEAD"],
                               capture_output=True, text=True)
    if rev_parse.returncode != 0:
        checks.append(("worktree_clean", "BLOCK",
                       f"git rev-parse failed: {rev_parse.stderr.strip()[-300:]}"))
        return checks, None
    rollback_base = rev_parse.stdout.strip()
    checks.append(("worktree_clean", "PASS", f"rollback base {rollback_base[:10]}"))

    relative_dest = str(dest.relative_to(worktree))
    def rollback() -> None:
        reset = subprocess.run(
            ["git", "-C", str(worktree), "reset", "--hard", rollback_base],
            capture_output=True,
            text=True,
        )
        if reset.returncode != 0:
            checks.append(("rollback", "BLOCK", f"git reset failed: {reset.stderr[-300:]}"))
            return
        changed, error = _changed_paths(worktree)
        if error:
            checks.append(("rollback", "BLOCK", error))
            return
        for changed_path in changed:
            if changed_path.is_file() or changed_path.is_symlink():
                changed_path.unlink()
        clean = subprocess.run(
            ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all"],
            capture_output=True,
            text=True,
        )
        if clean.returncode != 0 or clean.stdout.strip():
            detail = clean.stderr[-300:] if clean.returncode else clean.stdout.strip()[:300]
            checks.append(("rollback", "BLOCK", f"worktree not clean after rollback: {detail}"))
        else:
            checks.append(("rollback", "PASS", f"restored {rollback_base[:10]}"))

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(render_content_json(package), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    checks.append(("write_content", "PASS", str(dest.relative_to(worktree))))

    build = subprocess.run(["bun", "run", "build"], cwd=worktree,
                           capture_output=True, text=True, timeout=900)
    if build.returncode != 0:
        checks.append(("production_build", "BLOCK", build.stderr[-500:]))
        rollback()
        return checks, None
    checks.append(("production_build", "PASS", "bun run build exit 0"))

    try:
        server = subprocess.Popen(
            ["bun", "run", "preview", "--", "--port", str(port)],
            cwd=worktree,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
    except OSError as err:
        checks.append(("preview_server", "BLOCK", str(err)))
        rollback()
        return checks, None
    try:
        if not _wait_port(port):
            checks.append(("preview_server", "BLOCK", "never opened port"))
            rollback()
            return checks, None
        results = check_slash_variants(
            f"http://127.0.0.1:{port}",
            f"blog/{slug}",
            expected=expected_page_contract(package),
        )
        for name, (verdict, detail) in results.items():
            checks.append((f"html:{name}", verdict, detail))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    if any(v == "BLOCK" for _, v, _ in checks):
        rollback()
        return checks, None

    generated_paths, status_error = _changed_paths(worktree)
    if status_error or not generated_paths:
        checks.append((
            "generated_artifacts",
            "BLOCK",
            status_error or "build produced no committable content artifacts",
        ))
        rollback()
        return checks, None
    generated_files = [str(path.relative_to(worktree.resolve())) for path in generated_paths]
    if relative_dest not in generated_files:
        checks.append(("generated_artifacts", "BLOCK", f"missing generated content {relative_dest}"))
        rollback()
        return checks, None
    checks.append(("generated_artifacts", "PASS", ", ".join(generated_files)))

    add = subprocess.run(
        ["git", "-C", str(worktree), "add", "--", *generated_files],
        capture_output=True,
        text=True,
    )
    if add.returncode != 0:
        checks.append(("site_commit", "BLOCK", f"git add failed: {add.stderr[-300:]}"))
        rollback()
        return checks, None
    commit = subprocess.run(
        ["git", "-C", str(worktree), "commit", "-q", "-m",
         f"Add verified blog content: {slug} (package {package.package_id})\n\n"
         "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"],
        capture_output=True, text=True)
    if commit.returncode != 0:
        checks.append(("site_commit", "BLOCK", commit.stderr[-300:]))
        rollback()
        return checks, None
    destination_rev = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
    )
    if destination_rev.returncode != 0:
        checks.append(("site_commit", "BLOCK",
                       f"git rev-parse failed: {destination_rev.stderr[-300:]}"))
        rollback()
        return checks, None
    dest_sha = destination_rev.stdout.strip()
    checks.append(("site_commit", "PASS", dest_sha[:10]))

    remaining, status_error = _changed_paths(worktree)
    if status_error or remaining:
        detail = status_error or ", ".join(str(path.relative_to(worktree)) for path in remaining)
        checks.append(("postcommit_clean", "BLOCK", detail))
        rollback()
        return checks, None
    checks.append(("postcommit_clean", "PASS", "worktree clean after generated commit"))

    manifest = ExportManifest(
        package_id=package.package_id,
        package_hash=package.content_hash(),
        generated_files=generated_files,
        canonical_url=package.content["canonical"],
        destination_commit=dest_sha,
        rollback_base=rollback_base,
        exported_at=now_iso(),
        expected=expected_page_contract(package),
    )
    return checks, manifest


def write_manifest(manifest: ExportManifest, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{manifest.package_id}-export.json"
    path.write_text(canonical_json(manifest.to_dict()), encoding="utf-8")
    return path


def deploy_intent(package: PagePackage, directory: Path) -> Path:
    """V1 emits a DISABLED deploy intent: posting is human_only in facts."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{package.package_id}-deploy-intent.json"
    path.write_text(canonical_json({
        "package_id": package.package_id,
        "action": "publish",
        "driver": "disabled",
        "reason": "business-facts autonomy.posting = human_only; Lou publishes manually",
        "created_at": now_iso(),
    }), encoding="utf-8")
    return path
