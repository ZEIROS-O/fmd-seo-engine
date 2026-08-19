"""Fail-closed validation and application of immutable PatchPackages."""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from .contracts import PatchPackage, canonical_json, sha256_text


GENERATOR_PATHS = {
    "canonical": frozenset(),
    # public/sitemap.xml is a build artifact. No generator produces it; the
    # deterministic sitemap patch rewrites the generator script only.
    "sitemap": frozenset({"scripts/generate-sitemap.mjs"}),
    "schema": frozenset({"src/lib/business-facts.ts", "public/llms.txt"}),
    "internal-links": frozenset(),
    "copy": frozenset(),
}


def _git(repo: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, (result.stdout.strip() or result.stderr.strip())


def _urls(text: str) -> set[str]:
    return set(re.findall(r"<loc>\s*([^<]+?)\s*</loc>", text, flags=re.IGNORECASE))


# --- route inventory -------------------------------------------------------
# The site uses file-based routing, so `public/sitemap.xml` is downstream of the
# route inventory rather than being it. These mirror the discovery rules in the
# site's own scripts/generate-sitemap.mjs; if that script's rules change, the
# site_repo fixture's end-to-end test is what catches the divergence.

ROUTE_DIR = "src/routes"
SITEMAP_SCRIPT = "scripts/generate-sitemap.mjs"
CITY_PAGE = "src/components/CityPage.tsx"
LEGACY_BLOG_ROUTE = "src/routes/blog.$slug.tsx"
BLOG_CONTENT_DIR = "content/blog"
_SLUG = re.compile(r'\n\s+slug:\s+"([^"]+)"')
_EXCLUDED_ROUTES = re.compile(r"const excludedRoutes = new Set\(\[(.*?)\]\);", re.DOTALL)


def _route_from_filename(name: str, siblings: set[str]) -> str | None:
    if (
        not name.endswith(".tsx")
        or name.startswith("api.")
        or name.startswith("[")
        or name == "__root.tsx"
        or "$" in name
    ):
        return None
    stem = name[: -len(".tsx")]
    if not stem.endswith(".index") and f"{stem}.index.tsx" in siblings:
        return None
    route = stem
    if route.endswith(".index"):
        route = route[: -len(".index")]
    route = route.replace(".", "/")
    return "/" if route == "index" else f"/{route}"


def route_inventory(worktree: Path, overrides: dict[str, str] | None = None) -> set[str]:
    """Every URL path the site's sitemap generator would emit.

    ``overrides`` supplies post-patch content for specific paths, so the same
    function computes the before and after inventories. Sources the site does
    not have contribute nothing rather than failing -- a modify-only patch can
    only change files that already exist, so an absent source cannot hide an
    addition.
    """
    supplied = overrides or {}

    def read(relative: str) -> str | None:
        if relative in supplied:
            return supplied[relative]
        path = worktree / relative
        return path.read_text(encoding="utf-8") if path.is_file() else None

    excluded: set[str] = set()
    script = read(SITEMAP_SCRIPT)
    if script is not None:
        declaration = _EXCLUDED_ROUTES.search(script)
        if declaration:
            excluded = set(re.findall(r'"([^"]*)"', declaration.group(1)))

    routes: set[str] = set()
    route_dir = worktree / ROUTE_DIR
    if route_dir.is_dir():
        siblings = {entry.name for entry in route_dir.iterdir() if entry.is_file()}
        for name in sorted(siblings):
            route = _route_from_filename(name, siblings)
            if route is not None and route not in excluded:
                routes.add(route)

    city = read(CITY_PAGE)
    if city is not None:
        routes.update(f"/areas/{slug}" for slug in _SLUG.findall(city))

    legacy_blog = read(LEGACY_BLOG_ROUTE)
    if legacy_blog is not None:
        routes.update(f"/blog/{slug}" for slug in _SLUG.findall(legacy_blog))

    content_dir = worktree / BLOG_CONTENT_DIR
    if content_dir.is_dir():
        import json
        for entry in sorted(content_dir.glob("*.json")):
            relative = f"{BLOG_CONTENT_DIR}/{entry.name}"
            raw = read(relative)
            if raw is None:
                continue
            try:
                slug = json.loads(raw).get("slug")
            except json.JSONDecodeError:
                continue
            if slug:
                routes.add(f"/blog/{slug}")
    return routes


def _route_inventory_body(worktree: Path, head: str) -> dict:
    return {
        "routes": sorted(route_inventory(worktree)),
        "site_base_commit": head,
    }


def _validate_v2_route_inventory(
    record: dict, evidence_id: str, worktree: Path, head: str,
) -> str | None:
    """Bind a v2 sitemap evidence_ref to the live inventory, not to file existence."""
    if record.get("kind") != "route_inventory":
        return f"{evidence_id} is not route_inventory evidence"
    expected = _route_inventory_body(worktree, head)
    digest = sha256_text(canonical_json(expected))
    if record.get("source_sha256") != digest:
        return (
            f"{evidence_id} source_sha256 does not match the live route inventory"
        )
    if not evidence_id.endswith(digest[:12]):
        return f"{evidence_id} does not bind digest {digest[:12]}"
    if record.get("site_base_commit") != head:
        return f"{evidence_id} site_base_commit does not match {head}"
    if record.get("routes") != expected["routes"]:
        return f"{evidence_id} routes do not match the live inventory"
    return None


def _validate_v2_fact_snapshot(
    record: dict, evidence_id: str, current_fact_hash: str,
) -> str | None:
    """Bind a v2 schema evidence_ref to the live facts file hash."""
    if record.get("kind") != "fact_snapshot":
        return f"{evidence_id} is not fact_snapshot evidence"
    digest = record.get("source_sha256") or record.get("source_hash")
    if digest != current_fact_hash:
        return f"{evidence_id} does not bind current facts"
    if not evidence_id.endswith(current_fact_hash[:12]):
        return f"{evidence_id} does not bind digest {current_fact_hash[:12]}"
    return None


def validate_patch_package(
    worktree: Path,
    package: PatchPackage,
    *,
    current_fact_hash: str,
    facts_file: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict:
    if not (worktree / ".git").exists():
        return {"status": "BLOCK", "blockers": [f"not a site checkout: {worktree}"]}
    code, head = _git(worktree, "rev-parse", "HEAD")
    if code or head != package.site_base_commit:
        return {
            "status": "BLOCK",
            "blockers": [
                f"site base changed: package {package.site_base_commit}, current {head or 'unknown'}"
            ],
        }
    if package.fact_snapshot_hash != current_fact_hash:
        return {
            "status": "BLOCK",
            "blockers": [
                "fact snapshot changed: PatchPackage must be regenerated against current facts"
            ],
        }

    evidence_blockers: list[str] = []
    if package.schema_version >= 2 and not package.evidence_refs:
        if package.generator == "sitemap":
            evidence_blockers.append(
                "v2 sitemap packages require a hash-bound route-inventory evidence record"
            )
        elif package.generator == "schema":
            evidence_blockers.append(
                "v2 schema packages require a hash-bound fact-snapshot evidence record"
            )
    for evidence_ref in package.evidence_refs:
        if evidence_ref == "agent:sitemap-route-inventory":
            if package.schema_version >= 2:
                evidence_blockers.append(
                    "v2 sitemap packages require a hash-bound route-inventory "
                    "evidence record, not agent:sitemap-route-inventory"
                )
            elif package.generator != "sitemap":
                evidence_blockers.append(
                    "route-inventory evidence is valid only for the sitemap generator"
                )
            continue
        if evidence_ref.startswith("canonical-facts:"):
            if package.schema_version >= 2:
                evidence_blockers.append(
                    "v2 schema packages require a hash-bound fact-snapshot "
                    "evidence record, not canonical-facts:<hash>"
                )
                continue
            bound_hash = evidence_ref.partition(":")[2]
            if package.generator != "schema" or bound_hash != current_fact_hash:
                evidence_blockers.append(
                    f"canonical fact evidence does not bind current facts: {evidence_ref}"
                )
            continue
        if evidence_dir is None:
            evidence_blockers.append(f"evidence directory required to resolve {evidence_ref}")
            continue
        from .verify import _resolve_verified_evidence
        record, detail = _resolve_verified_evidence(evidence_ref, evidence_dir)
        if record is None:
            evidence_blockers.append(detail)
            continue
        if package.schema_version >= 2 and package.generator == "sitemap":
            mismatch = _validate_v2_route_inventory(
                record, evidence_ref, worktree, head,
            )
            if mismatch:
                evidence_blockers.append(mismatch)
        if package.schema_version >= 2 and package.generator == "schema":
            mismatch = _validate_v2_fact_snapshot(
                record, evidence_ref, current_fact_hash,
            )
            if mismatch:
                evidence_blockers.append(mismatch)
    if evidence_blockers:
        return {"status": "BLOCK", "blockers": evidence_blockers}

    permitted = GENERATOR_PATHS[package.generator]
    rejected = [
        f"generator {package.generator} cannot modify {item['path']}"
        for item in package.modifications
        if item["path"] not in permitted
    ]
    if rejected:
        return {"status": "BLOCK", "blockers": rejected}

    expected_replacements: dict[str, str] | None = None
    if package.generator == "schema":
        if facts_file is None or not facts_file.is_file():
            return {
                "status": "BLOCK",
                "blockers": ["canonical facts file is required for schema validation"],
            }
        from .patch_generators import _canonical_fact_replacements
        expected_replacements = _canonical_fact_replacements(facts_file)
    elif package.generator == "sitemap":
        script_path = worktree / SITEMAP_SCRIPT
        if not script_path.is_file():
            return {
                "status": "BLOCK",
                "blockers": [f"tracked {SITEMAP_SCRIPT} is missing"],
            }
        from .patch_generators import _exclude_legal_routes
        expected_script = _exclude_legal_routes(
            script_path.read_text(encoding="utf-8")
        )
        if expected_script is None:
            return {
                "status": "BLOCK",
                "blockers": [
                    f"cannot locate the excludedRoutes declaration in {SITEMAP_SCRIPT}"
                ],
            }
        expected_replacements = {SITEMAP_SCRIPT: expected_script}

    before_urls: set[str] = set()
    after_urls: set[str] = set()
    overrides: dict[str, str] = {}
    for modification in package.modifications:
        relative = modification["path"]
        if expected_replacements is not None and (
            expected_replacements.get(relative) != modification["replacement_content"]
        ):
            return {
                "status": "BLOCK",
                "blockers": [
                    f"{relative} replacement does not match canonical generator output"
                ],
            }
        code, _ = _git(worktree, "ls-files", "--error-unmatch", "--", relative)
        if code:
            return {
                "status": "BLOCK",
                "blockers": [f"PatchPackage path is not tracked: {relative}"],
            }
        path = worktree / relative
        if not path.is_file():
            return {"status": "BLOCK", "blockers": [f"tracked path missing: {relative}"]}
        existing = path.read_text(encoding="utf-8")
        digest = hashlib.sha256(existing.encode("utf-8")).hexdigest()
        if digest != modification["before_sha256"]:
            return {
                "status": "BLOCK",
                "blockers": [f"tracked file changed since package creation: {relative}"],
            }
        overrides[relative] = modification["replacement_content"]
        if relative.endswith("sitemap.xml"):
            before_urls.update(_urls(existing))
            after_urls.update(_urls(modification["replacement_content"]))

    additions = sorted(after_urls - before_urls)
    if additions:
        return {
            "status": "BLOCK",
            "blockers": [f"URL addition is forbidden in PatchPackage: {additions}"],
        }

    # A sitemap-only diff misses every route the site mints elsewhere: a `slug:`
    # in CityPage.tsx or the generator script itself both create live URLs
    # without touching a file named sitemap.xml. Removal stays permitted --
    # retiring a URL is an intended capability.
    before_routes = route_inventory(worktree)
    after_routes = route_inventory(worktree, overrides)
    new_routes = sorted(after_routes - before_routes)
    if new_routes:
        return {
            "status": "BLOCK",
            "blockers": [f"route addition is forbidden in PatchPackage: {new_routes}"],
        }
    return {
        "status": "DONE",
        "checks": {
            "base_sha": head,
            "fact_snapshot_hash": current_fact_hash,
            "url_additions": 0,
            "route_additions": 0,
            "route_removals": len(before_routes - after_routes),
            "tracked_paths": len(package.modifications),
        },
    }


def apply_patch_package(
    worktree: Path,
    package: PatchPackage,
    *,
    current_fact_hash: str,
    facts_file: Path | None = None,
    evidence_dir: Path | None = None,
) -> dict:
    validation = validate_patch_package(
        worktree, package, current_fact_hash=current_fact_hash,
        facts_file=facts_file, evidence_dir=evidence_dir,
    )
    if validation["status"] != "DONE":
        return validation
    modified: list[str] = []
    for modification in package.modifications:
        relative = modification["path"]
        (worktree / relative).write_text(
            modification["replacement_content"], encoding="utf-8"
        )
        modified.append(relative)
    return {"status": "DONE", "modified_paths": modified}
