"""Deterministic existing-page PatchPackage generators."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from .contracts import PatchPackage


LEGAL_SITEMAP_PATHS = frozenset({
    "/privacy-policy", "/terms-of-service", "/cancellation-refund-policy",
})


def _head(worktree: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree), "rev-parse", "HEAD"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or "cannot resolve site HEAD")
    return result.stdout.strip()


SITEMAP_SCRIPT = "scripts/generate-sitemap.mjs"
# The generator's own exclusion set, which is the only durable authority over
# what the sitemap contains. `public/sitemap.xml` is regenerated on prebuild.
_EXCLUDED_ROUTES_DECLARATION = re.compile(
    r"const excludedRoutes = new Set\(\[(?P<members>.*?)\]\);",
    re.DOTALL,
)
_PRETTIER_PRINT_WIDTH = 100


def _render_excluded_routes(routes: list[str]) -> str:
    """Emit the exclusion set the way the site's prettier config would.

    A patch that lands correct code in a shape `prettier --check` rejects still
    fails the site's own gates, so the formatting is part of correctness.
    """
    quoted = ", ".join('"{}"'.format(route) for route in routes)
    inline = f"const excludedRoutes = new Set([{quoted}]);"
    if len(inline) <= _PRETTIER_PRINT_WIDTH:
        return inline
    members = "".join(f'  "{route}",\n' for route in routes)
    return f"const excludedRoutes = new Set([\n{members}]);"


def _exclude_legal_routes(script: str) -> str | None:
    """Add the legal routes to the generator's exclusion set, or None if absent."""
    match = _EXCLUDED_ROUTES_DECLARATION.search(script)
    if not match:
        return None
    existing = re.findall(r'"([^"]*)"', match.group("members"))
    routes = sorted(set(existing) | set(LEGAL_SITEMAP_PATHS))
    return script[: match.start()] + _render_excluded_routes(routes) + script[match.end():]


def _last_commit_date(worktree: Path, relative: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree), "log", "-1", "--format=%cs", "--", relative],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"git log failed for {relative}")
    committed = result.stdout.strip()
    if not committed:
        raise ValueError(f"git log returned no commit date for {relative}")
    return committed


def _direction_blocker(
    target: str,
    reason: str,
    *,
    canonical_date: str | None,
    site_commit_date: str | None,
    divergent_keys: list[str],
) -> dict:
    return {
        "target": target,
        "reason": reason,
        "canonical_date": canonical_date,
        "site_commit_date": site_commit_date,
        "divergent_keys": divergent_keys,
    }


def _parse_direction_date(value: object) -> date:
    return date.fromisoformat(str(value))


def _read_site_fact_payload(path: Path) -> dict:
    content = path.read_text(encoding="utf-8")
    match = re.search(
        r"BUSINESS_FACTS_PAYLOAD\s*=\s*(\{.*\})\s+as const;",
        content,
        re.DOTALL,
    )
    if match is None:
        raise ValueError("BUSINESS_FACTS_PAYLOAD is absent")
    payload = json.loads(match.group(1))
    if not isinstance(payload, dict) or not isinstance(payload.get("facts"), dict):
        raise ValueError("BUSINESS_FACTS_PAYLOAD.facts is not an object")
    return payload


def _dotted_differences(expected: object, observed: object, prefix: str = "") -> list[str]:
    if isinstance(expected, dict) and isinstance(observed, dict):
        differences: list[str] = []
        for key in sorted(set(expected) | set(observed)):
            child = f"{prefix}.{key}" if prefix else str(key)
            if key not in expected or key not in observed:
                differences.append(child)
            else:
                differences.extend(_dotted_differences(expected[key], observed[key], child))
        return differences
    return [] if expected == observed else [prefix]


def _facts_are_behind_the_site(
    worktree: Path, facts_file: Path, replacements: dict[str, str],
) -> list[dict]:
    """Name every target the facts authority is older than.

    `business-facts.yaml` is treated as authoritative, so a stale copy of it
    generates a patch that reverts newer published copy. `facts.freshness`
    cannot catch this -- it only measures reviewed_at + review_after_days, and a
    file that was reviewed but never updated passes it while sitting behind the
    site.
    """
    changed: list[str] = []
    blockers: list[dict] = []
    for relative, rendered in sorted(replacements.items()):
        path = worktree / relative
        if not path.is_file():
            blockers.append(_direction_blocker(
                relative,
                "site_target_unreadable",
                canonical_date=None,
                site_commit_date=None,
                divergent_keys=["payload.unreadable"],
            ))
            continue
        try:
            current = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            blockers.append(_direction_blocker(
                relative,
                "site_target_unreadable",
                canonical_date=None,
                site_commit_date=None,
                divergent_keys=["payload.unreadable"],
            ))
            continue
        if current == rendered:
            continue
        changed.append(relative)

    if blockers:
        return blockers
    if not changed:
        return []

    try:
        data = yaml.safe_load(facts_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError, ValueError):
        return [
            _direction_blocker(
                relative,
                "canonical_payload_unreadable",
                canonical_date=None,
                site_commit_date=None,
                divergent_keys=["payload.unreadable"],
            )
            for relative in changed
        ]
    authority_value = (
        (data or {}).get("source_last_updated") if isinstance(data, dict) else None
    )
    authority_text = (
        str(authority_value)
        if authority_value is not None and authority_value != ""
        else None
    )
    authority_date = None
    authority_reason = None
    if authority_text is None:
        authority_reason = "canonical_date_missing"
    else:
        try:
            authority_date = _parse_direction_date(authority_text)
        except ValueError:
            authority_reason = "canonical_date_invalid"

    from .site_facts import public_fact_payload

    try:
        canonical_payload = public_fact_payload(facts_file)
        site_payload = _read_site_fact_payload(worktree / "src/lib/business-facts.ts")
        fact_differences = _dotted_differences(
            canonical_payload["facts"], site_payload["facts"],
        )
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return [
            _direction_blocker(
                relative,
                "site_payload_unreadable",
                canonical_date=authority_text,
                site_commit_date=None,
                divergent_keys=["payload.unreadable"],
            )
            for relative in changed
        ]

    for relative in changed:
        divergent_keys = (
            fact_differences
            if fact_differences
            else (["template.public_llms"] if relative == "public/llms.txt" else [])
        )
        try:
            committed_text = _last_commit_date(worktree, relative)
        except (OSError, subprocess.SubprocessError, ValueError):
            blockers.append(_direction_blocker(
                relative,
                "site_commit_date_unavailable",
                canonical_date=authority_text,
                site_commit_date=None,
                divergent_keys=divergent_keys,
            ))
            continue
        try:
            committed_date = _parse_direction_date(committed_text)
        except ValueError:
            blockers.append(_direction_blocker(
                relative,
                "site_commit_date_invalid",
                canonical_date=authority_text,
                site_commit_date=committed_text,
                divergent_keys=divergent_keys,
            ))
            continue
        if authority_reason is not None:
            blockers.append(_direction_blocker(
                relative,
                authority_reason,
                canonical_date=authority_text,
                site_commit_date=committed_text,
                divergent_keys=divergent_keys,
            ))
            continue
        if committed_date > authority_date:
            blockers.append(_direction_blocker(
                relative,
                "site_newer_than_canonical",
                canonical_date=authority_text,
                site_commit_date=committed_text,
                divergent_keys=divergent_keys,
            ))
    return blockers


def _canonical_fact_replacements(facts_file: Path) -> dict[str, str]:
    from .site_facts import _render_llms, _render_typescript, public_fact_payload

    payload = public_fact_payload(facts_file)
    return {
        "src/lib/business-facts.ts": _render_typescript(payload),
        "public/llms.txt": _render_llms(payload),
    }


def _build_package(
    generator: str,
    *,
    worktree: Path,
    facts_file: Path,
    replacements: dict[str, str],
    evidence_refs: list[str],
) -> dict:
    digest = lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest()
    modifications = []
    for relative, after in replacements.items():
        path = worktree / relative
        if not path.is_file():
            return {"status": "BLOCK", "blockers": [f"tracked source is missing: {relative}"]}
        before = path.read_text(encoding="utf-8")
        if before == after:
            continue
        modifications.append({
            "operation": "modify",
            "path": relative,
            "before_sha256": digest(before),
            "after_sha256": digest(after),
            "replacement_content": after,
        })
    if not modifications:
        return {"status": "NO_OP", "note": f"{generator} source already matches its authority"}
    package = PatchPackage.create(
        generator=generator,
        created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        site_base_commit=_head(worktree),
        fact_snapshot_hash=hashlib.sha256(facts_file.read_bytes()).hexdigest(),
        evidence_refs=evidence_refs,
        modifications=modifications,
    )
    return {"status": "DONE", "package": package.to_dict()}


def write_route_inventory_evidence(worktree: Path, directory: Path) -> str:
    """Persist the current route inventory as a hash-bound evidence record.

    v1 sitemap packages cited the nominal string agent:sitemap-route-inventory,
    which validate_patch_package accepted on generator name alone. v2 binds the
    inventory itself so a package cannot claim a route set it did not measure.
    """
    from .contracts import canonical_json, sha256_text
    from .patch_action import route_inventory

    body = {
        "routes": sorted(route_inventory(worktree)),
        "site_base_commit": _head(worktree),
    }
    digest = sha256_text(canonical_json(body))
    evidence_id = f"ev-route-inventory-{digest[:12]}"
    payload = {
        "evidence_id": evidence_id,
        "kind": "route_inventory",
        "source_sha256": digest,
        **body,
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{evidence_id}.json"
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != payload:
            raise ValueError(f"immutable evidence id collision: {evidence_id}")
        return evidence_id
    path.write_text(rendered, encoding="utf-8")
    return evidence_id


def generate_patch_preview(
    generator: str,
    *,
    worktree: Path,
    facts_file: Path,
    evidence_dir: Path | None = None,
) -> dict:
    if not (worktree / ".git").exists():
        return {"status": "BLOCK", "blockers": ["site worktree is unavailable"]}
    if not facts_file.is_file():
        return {"status": "BLOCK", "blockers": ["canonical facts file is unavailable"]}
    if generator == "schema":
        fact_hash = hashlib.sha256(facts_file.read_bytes()).hexdigest()
        try:
            replacements = _canonical_fact_replacements(facts_file)
        except (OSError, UnicodeError, yaml.YAMLError, KeyError, TypeError, ValueError):
            return {
                "status": "BLOCK",
                "blockers": [
                    _direction_blocker(
                        target,
                        "canonical_payload_unreadable",
                        canonical_date=None,
                        site_commit_date=None,
                        divergent_keys=["payload.unreadable"],
                    )
                    for target in ("src/lib/business-facts.ts", "public/llms.txt")
                ],
            }
        stale = _facts_are_behind_the_site(worktree, facts_file, replacements)
        if stale:
            return {"status": "BLOCK", "blockers": stale}
        return _build_package(
            "schema",
            worktree=worktree,
            facts_file=facts_file,
            replacements=replacements,
            evidence_refs=[f"canonical-facts:{fact_hash}"],
        )
    if generator != "sitemap":
        messages = {
            "canonical": "canonical source pattern needs a verified hosting target before generation",
            "internal-links": "internal-link generator requires a current orphan evidence artifact",
            "copy": "copy generator requires GSC, SERP consensus, and review-language evidence",
        }
        return {"status": "BLOCK", "blockers": [messages[generator]]}

    script_path = worktree / SITEMAP_SCRIPT
    if not script_path.is_file():
        return {"status": "BLOCK", "blockers": [f"tracked {SITEMAP_SCRIPT} is missing"]}
    after = _exclude_legal_routes(script_path.read_text(encoding="utf-8"))
    if after is None:
        return {
            "status": "BLOCK",
            "blockers": [
                f"cannot locate the excludedRoutes declaration in {SITEMAP_SCRIPT}; "
                "the site's route-exclusion authority has moved"
            ],
        }
    store = evidence_dir if evidence_dir is not None else facts_file.parent / "evidence"
    evidence_id = write_route_inventory_evidence(worktree, store)
    return _build_package(
        "sitemap",
        worktree=worktree,
        facts_file=facts_file,
        replacements={SITEMAP_SCRIPT: after},
        evidence_refs=[evidence_id],
    )
