"""Export a verified PagePackage to the isolated site worktree, prove it
through the production build + raw-HTML checks, and emit an ExportManifest.

The site's JSON is generated output; the package stays authoritative.
"""

from __future__ import annotations

import json
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


def render_content_json(package: PagePackage) -> dict:
    """Project the package onto the site's content schema (render-only keys —
    claims/provenance metadata stay in the engine)."""
    return {k: package.content[k] for k in RENDER_KEYS if k in package.content}


def export_package(package: PagePackage, worktree: Path, *, port: int = 4176,
                   dry_run: bool = False) -> tuple[list[tuple[str, str, str]], ExportManifest | None]:
    checks: list[tuple[str, str, str]] = []
    slug = package.content["slug"]
    dest = worktree / "content" / "blog" / f"{slug}.json"

    if dry_run:
        checks.append(("export_plan", "PASS", f"would write {dest}"))
        return checks, None

    status = subprocess.run(["git", "-C", str(worktree), "status", "--porcelain"],
                            capture_output=True, text=True)
    if status.stdout.strip():
        checks.append(("worktree_clean", "BLOCK", f"dirty worktree: {status.stdout.strip()[:200]}"))
        return checks, None
    rollback_base = subprocess.run(["git", "-C", str(worktree), "rev-parse", "HEAD"],
                                   capture_output=True, text=True).stdout.strip()
    checks.append(("worktree_clean", "PASS", f"rollback base {rollback_base[:10]}"))

    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(render_content_json(package), indent=2, ensure_ascii=False) + "\n",
                    encoding="utf-8")
    checks.append(("write_content", "PASS", str(dest.relative_to(worktree))))

    build = subprocess.run(["bun", "run", "build"], cwd=worktree,
                           capture_output=True, text=True, timeout=900)
    if build.returncode != 0:
        checks.append(("production_build", "BLOCK", build.stderr[-500:]))
        return checks, None
    checks.append(("production_build", "PASS", "bun run build exit 0"))

    server = subprocess.Popen(["bun", "run", "preview", "--", "--port", str(port), "--strictPort"],
                              cwd=worktree, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        if not _wait_port(port):
            checks.append(("preview_server", "BLOCK", "never opened port"))
            return checks, None
        results = check_slash_variants(f"http://127.0.0.1:{port}", f"blog/{slug}")
        for name, (verdict, detail) in results.items():
            checks.append((f"html:{name}", verdict, detail))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    if any(v == "BLOCK" for _, v, _ in checks):
        return checks, None

    subprocess.run(["git", "-C", str(worktree), "add", str(dest)], check=True)
    commit = subprocess.run(
        ["git", "-C", str(worktree), "commit", "-q", "-m",
         f"Add verified blog content: {slug} (package {package.package_id})\n\n"
         "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"],
        capture_output=True, text=True)
    if commit.returncode != 0:
        checks.append(("site_commit", "BLOCK", commit.stderr[-300:]))
        return checks, None
    dest_sha = subprocess.run(["git", "-C", str(worktree), "rev-parse", "HEAD"],
                              capture_output=True, text=True).stdout.strip()
    checks.append(("site_commit", "PASS", dest_sha[:10]))

    manifest = ExportManifest(
        package_id=package.package_id,
        package_hash=package.content_hash(),
        generated_files=[str(dest.relative_to(worktree))],
        canonical_url=package.content["canonical"],
        destination_commit=dest_sha,
        rollback_base=rollback_base,
        exported_at=now_iso(),
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
