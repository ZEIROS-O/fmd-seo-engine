import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from fmd_seo.contracts import PatchPackage


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _direction_facts(source_last_updated: str) -> str:
    return f"""\
schema_version: 1
source_last_updated: "{source_last_updated}"
identity: {{name: Fresh Mobile Detailing, phone: "(216) 359-1034"}}
service_area: {{base: Beachwood, radius_miles: 30, places: [Beachwood]}}
hours: {{days: [Monday], opens: "08:00", closes: "18:00"}}
services: {{duration_hours: {{min: 1.5, max: 4}}, offered: [The Interior Reset, The Deep Interior Reset], exterior_add_on: exterior hand wash, not_offered: [PPF]}}
fleet_discount: {{available: true, applies_to: [fleet]}}
pricing:
  one_time: {{full_interior: {{price: 209, duration_hours: 2}}, ultimate_interior: {{price: 289, duration_hours: 3}}}}
  membership_per_visit: {{monthly: 149, bi_monthly: 169, quarterly: 189}}
  neighbor_discount: 25
guarantee: {{name: Fresh Finish Guarantee, summary: "We make missed work right", public_statement: "We return and correct it", remedy_window_hours: 24}}
claim_gates: {{review_count_public_claim: {{allowed: false}}}}
equipment: {{steamer: {{owned: false}}, ozone_machine: {{owned: false}}}}
"""


def _commit_site_facts(repo, facts_file, *, committed_at: str, mutate_payload=None, llms=None):
    from fmd_seo.site_facts import _render_llms, _render_typescript, public_fact_payload

    payload = public_fact_payload(facts_file)
    if mutate_payload is not None:
        mutate_payload(payload)
    ts = repo / "src/lib/business-facts.ts"
    llms_path = repo / "public/llms.txt"
    ts.parent.mkdir(parents=True, exist_ok=True)
    llms_path.parent.mkdir(parents=True, exist_ok=True)
    ts.write_text(_render_typescript(payload), encoding="utf-8")
    llms_path.write_text(llms if llms is not None else _render_llms(payload), encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "src/lib/business-facts.ts", "public/llms.txt"],
        check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "site facts"],
        check=True,
        capture_output=True,
        env={**os.environ, "GIT_AUTHOR_DATE": committed_at, "GIT_COMMITTER_DATE": committed_at},
    )


def _route_evidence(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "ev-route-inventory-fixture.json").write_text(
        json.dumps({
            "evidence_id": "ev-route-inventory-fixture",
            "kind": "route_inventory",
            "routes": [],
        })
        + "\n",
        encoding="utf-8",
    )
    return directory


SITEMAP_SCRIPT_STUB = (
    'const excludedRoutes = new Set(["/booking-confirmed"]);\n'
    "export function generate() {}\n"
)


def _commit_sitemap_script(repo, text=SITEMAP_SCRIPT_STUB):
    path = repo / "scripts/generate-sitemap.mjs"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", "scripts/generate-sitemap.mjs"], check=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "sitemap generator"],
        check=True, capture_output=True,
    )
    return path


def _script_patch(repo, *, before, after, base=None, fact_hash="facts-current"):
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return PatchPackage.create(
        generator="sitemap",
        created_at="2026-08-12T12:00:00+00:00",
        site_base_commit=base or head,
        fact_snapshot_hash=fact_hash,
        evidence_refs=["ev-route-inventory-fixture"],
        modifications=[{
            "operation": "modify",
            "path": "scripts/generate-sitemap.mjs",
            "before_sha256": _sha(before),
            "after_sha256": _sha(after),
            "replacement_content": after,
        }],
    )


def _patch(repo, *, before, after, base=None, fact_hash="facts-current"):
    """A sitemap package aimed at the XML artifact — forbidden after 3.1."""
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return PatchPackage.create(
        generator="sitemap",
        created_at="2026-08-12T12:00:00+00:00",
        site_base_commit=base or head,
        fact_snapshot_hash=fact_hash,
        evidence_refs=["ev-route-inventory-fixture"],
        modifications=[{
            "operation": "modify",
            "path": "public/sitemap.xml",
            "before_sha256": _sha(before),
            "after_sha256": _sha(after),
            "replacement_content": after,
        }],
    )


def test_patch_validation_fails_closed_on_stale_base_file_and_fact(git_repo, tmp_path):
    from fmd_seo.patch_action import validate_patch_package
    from fmd_seo.patch_generators import _exclude_legal_routes

    evidence = _route_evidence(tmp_path / "evidence")
    before = SITEMAP_SCRIPT_STUB
    after = _exclude_legal_routes(before)
    assert after is not None and after != before
    script = _commit_sitemap_script(git_repo, before)

    assert validate_patch_package(
        git_repo, _script_patch(git_repo, before=before, after=after),
        current_fact_hash="facts-current", evidence_dir=evidence,
    )["status"] == "DONE"

    stale_base = _script_patch(
        git_repo, before=before, after=after, base="a" * 40,
    )
    assert "base" in validate_patch_package(
        git_repo, stale_base, current_fact_hash="facts-current",
        evidence_dir=evidence,
    )["blockers"][0]

    stale_fact = _script_patch(
        git_repo, before=before, after=after, fact_hash="old-facts",
    )
    assert "fact" in validate_patch_package(
        git_repo, stale_fact, current_fact_hash="facts-current",
        evidence_dir=evidence,
    )["blockers"][0]

    # Already-applied: expected bytes match, so the before-hash is what fires.
    script.write_text(after, encoding="utf-8")
    assert "changed" in validate_patch_package(
        git_repo, _script_patch(git_repo, before=before, after=after),
        current_fact_hash="facts-current", evidence_dir=evidence,
    )["blockers"][0]


def test_patch_apply_modifies_only_declared_tracked_paths(git_repo, tmp_path):
    from fmd_seo.patch_action import apply_patch_package
    from fmd_seo.patch_generators import _exclude_legal_routes

    evidence = _route_evidence(tmp_path / "evidence")
    before = SITEMAP_SCRIPT_STUB
    after = _exclude_legal_routes(before)
    assert after is not None
    script = _commit_sitemap_script(git_repo, before)

    result = apply_patch_package(
        git_repo,
        _script_patch(git_repo, before=before, after=after),
        current_fact_hash="facts-current",
        evidence_dir=evidence,
    )

    assert result == {
        "status": "DONE",
        "modified_paths": ["scripts/generate-sitemap.mjs"],
    }
    assert script.read_text(encoding="utf-8") == after
    assert subprocess.run(
        ["git", "-C", str(git_repo), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout == " M scripts/generate-sitemap.mjs\n"


def _site_patch(repo, *, path, before, after, generator="sitemap"):
    head = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return PatchPackage.create(
        generator=generator,
        created_at="2026-08-12T12:00:00+00:00",
        site_base_commit=head,
        fact_snapshot_hash="facts-current",
        evidence_refs=["ev-route-inventory-fixture"],
        modifications=[{
            "operation": "modify",
            "path": path,
            "before_sha256": _sha(before),
            "after_sha256": _sha(after),
            "replacement_content": after,
        }],
    )


def test_patch_validation_rejects_path_outside_generator_policy(git_repo, tmp_path):
    from fmd_seo.patch_action import validate_patch_package

    evidence = _route_evidence(tmp_path / "evidence")
    target = git_repo / "README.md"
    target.write_text("site readme\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "add", "README.md"], check=True)
    subprocess.run(
        ["git", "-C", str(git_repo), "commit", "-m", "readme"], check=True,
        capture_output=True,
    )
    before = target.read_text(encoding="utf-8")
    after = before + "scheduler-owned now\n"

    result = validate_patch_package(
        git_repo,
        _site_patch(git_repo, path="README.md", before=before, after=after),
        current_fact_hash="facts-current",
        evidence_dir=evidence,
    )

    assert result["status"] == "BLOCK"
    assert "generator sitemap cannot modify README.md" in result["blockers"]


def test_schema_patch_replacement_must_match_current_canonical_facts(
    git_repo, tmp_path,
):
    from fmd_seo.patch_action import validate_patch_package

    facts = tmp_path / "business-facts.yaml"
    facts.write_text(_direction_facts("2026-08-14"), encoding="utf-8")
    _commit_site_facts(
        git_repo, facts, committed_at="2026-08-14T12:00:00+00:00",
    )
    target = git_repo / "src/lib/business-facts.ts"
    before = target.read_text(encoding="utf-8")
    after = before.replace('"fullInterior": 209', '"fullInterior": 999')
    fact_hash = hashlib.sha256(facts.read_bytes()).hexdigest()
    package = PatchPackage.create(
        generator="schema",
        created_at="2026-08-14T12:00:00+00:00",
        site_base_commit=subprocess.run(
            ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip(),
        fact_snapshot_hash=fact_hash,
        evidence_refs=[f"canonical-facts:{fact_hash}"],
        modifications=[{
            "operation": "modify",
            "path": "src/lib/business-facts.ts",
            "before_sha256": _sha(before),
            "after_sha256": _sha(after),
            "replacement_content": after,
        }],
    )

    result = validate_patch_package(
        git_repo, package, current_fact_hash=fact_hash, facts_file=facts,
    )

    assert result["status"] == "BLOCK"
    assert "canonical generator output" in result["blockers"][0]


def _publish_fixture(site_repo, tmp_path, monkeypatch):
    """Wire publish_patch_package to the synthetic site with commands recorded."""
    import json

    from fmd_seo import act, patch_generators

    facts = tmp_path / "business-facts.yaml"
    facts.write_text("canonical facts\n", encoding="utf-8")
    generated = patch_generators.generate_patch_preview(
        "sitemap", worktree=site_repo, facts_file=facts,
    )
    assert generated["status"] == "DONE"
    monkeypatch.setattr(act.paths, "EVIDENCE_DIR", tmp_path / "evidence")
    package_path = tmp_path / "patch.json"
    package_path.write_text(json.dumps(generated["package"], indent=2), encoding="utf-8")

    head = subprocess.run(
        ["git", "-C", str(site_repo), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    monkeypatch.setattr(act, "sync_worktree", lambda _worktree: head)

    calls: list[tuple[str, ...]] = []
    real_run = act._run

    def fake_run(repo, *args):
        """Record every command; stub only what leaves the machine."""
        calls.append(args)
        if args[0] in {"bun", "gh"} or args[:2] == ("git", "push"):
            return "https://example.invalid/pr/1" if args[0] == "gh" else ""
        return real_run(repo, *args)

    monkeypatch.setattr(act, "_run", fake_run)
    config = {"paths": {"site_worktree": str(site_repo), "facts_file": str(facts)}}
    return config, package_path, calls


def test_act_rejects_v1_patch_packages_as_legacy(site_repo, tmp_path, monkeypatch):
    from fmd_seo import act
    from fmd_seo.contracts import PatchPackage

    config, package_path, _calls = _publish_fixture(site_repo, tmp_path, monkeypatch)
    data = json.loads(package_path.read_text(encoding="utf-8"))
    data["schema_version"] = 1
    data["package_id"] = PatchPackage.derive_id(
        generator=data["generator"],
        created_at=data["created_at"],
        site_base_commit=data["site_base_commit"],
        fact_snapshot_hash=data["fact_snapshot_hash"],
        evidence_refs=data["evidence_refs"],
        modifications=data["modifications"],
        schema_version=1,
    )
    package_path.write_text(json.dumps(data), encoding="utf-8")

    result = act.publish_patch_package(config, package_path)

    assert result["status"] == "BLOCK"
    assert "legacy" in result["blockers"][0]


def test_v2_sitemap_package_rejects_the_nominal_route_inventory_alias(git_repo, tmp_path):
    from fmd_seo.patch_action import validate_patch_package
    from fmd_seo.patch_generators import _exclude_legal_routes

    before = SITEMAP_SCRIPT_STUB
    after = _exclude_legal_routes(before)
    _commit_sitemap_script(git_repo, before)
    package = _script_patch(git_repo, before=before, after=after)
    # Force the v1 alias onto a v2 package.
    package = PatchPackage.create(
        generator="sitemap",
        created_at=package.created_at,
        site_base_commit=package.site_base_commit,
        fact_snapshot_hash=package.fact_snapshot_hash,
        evidence_refs=["agent:sitemap-route-inventory"],
        modifications=package.modifications,
    )

    result = validate_patch_package(
        git_repo, package, current_fact_hash="facts-current",
        evidence_dir=tmp_path / "evidence",
    )

    assert result["status"] == "BLOCK"
    assert "hash-bound" in result["blockers"][0]


def test_patch_publish_runs_the_sites_tests_after_building(site_repo, tmp_path, monkeypatch):
    from fmd_seo import act

    config, package_path, calls = _publish_fixture(site_repo, tmp_path, monkeypatch)

    result = act.publish_patch_package(config, package_path)

    assert result["status"] == "DONE", result
    bun = [args for args in calls if args[:2] == ("bun", "run")]
    assert bun == [("bun", "run", "build"), ("bun", "run", "test:seo-scripts")]
    # The tests have to run before anything is staged, or a failing build is
    # already committed by the time it is discovered.
    assert calls.index(("bun", "run", "test:seo-scripts")) < next(
        index for index, args in enumerate(calls) if args[:2] == ("git", "add")
    )
    assert {check["name"] for check in result["checks"]} == {"patch_build", "patch_tests"}


def test_patch_publish_rejects_policy_violation_before_git_mutation(
    site_repo, tmp_path, monkeypatch,
):
    import json

    from fmd_seo import act

    facts = tmp_path / "facts.yaml"
    facts.write_text("canonical facts\n", encoding="utf-8")
    fact_hash = hashlib.sha256(facts.read_bytes()).hexdigest()
    target = site_repo / "src/components/CityPage.tsx"
    before = target.read_text(encoding="utf-8")
    after = before + "// hand-authored escape\n"
    package = PatchPackage.create(
        generator="schema",
        created_at="2026-08-14T12:00:00+00:00",
        site_base_commit=subprocess.run(
            ["git", "-C", str(site_repo), "rev-parse", "HEAD"],
            check=True, capture_output=True, text=True,
        ).stdout.strip(),
        fact_snapshot_hash=fact_hash,
        evidence_refs=[f"canonical-facts:{fact_hash}"],
        modifications=[{
            "operation": "modify",
            "path": "src/components/CityPage.tsx",
            "before_sha256": _sha(before),
            "after_sha256": _sha(after),
            "replacement_content": after,
        }],
    )
    package_path = tmp_path / "patch.json"
    package_path.write_text(json.dumps(package.to_dict()), encoding="utf-8")
    calls = []

    def forbidden(*args):
        calls.append(args)
        raise AssertionError("Git mutation reached")

    monkeypatch.setattr(act, "sync_worktree", forbidden)
    monkeypatch.setattr(act, "_run", forbidden)

    result = act.publish_patch_package(
        {"paths": {"site_worktree": str(site_repo), "facts_file": str(facts)}},
        package_path,
    )

    assert result["status"] == "BLOCK"
    assert calls == []


def test_patch_publish_blocks_and_commits_nothing_when_site_tests_fail(
    site_repo, tmp_path, monkeypatch,
):
    from fmd_seo import act

    config, package_path, calls = _publish_fixture(site_repo, tmp_path, monkeypatch)
    stubbed = act._run

    def failing(repo, *args):
        if args == ("bun", "run", "test:seo-scripts"):
            calls.append(args)
            raise act.ActError("bun run test:seo-scripts failed: raw-html check regressed")
        return stubbed(repo, *args)

    monkeypatch.setattr(act, "_run", failing)

    result = act.publish_patch_package(config, package_path)

    assert result["status"] == "BLOCK"
    assert any("test:seo-scripts" in blocker for blocker in result["blockers"])
    assert any("raw-html check regressed" in blocker for blocker in result["blockers"])
    assert not any(args[:2] == ("git", "add") for args in calls)
    assert not any(args[:2] == ("git", "commit") for args in calls)
    # The worktree is left clean at the base commit, not mid-patch.
    assert subprocess.run(
        ["git", "-C", str(site_repo), "status", "--porcelain"],
        check=True, capture_output=True, text=True,
    ).stdout == ""


def test_route_inventory_agrees_with_the_sites_own_generator(site_repo, run_sitemap_generator):
    """The Python inventory is a mirror of a JavaScript source of truth.

    If the site's discovery rules drift, the mirror stops being a guard and
    starts being a rubber stamp, so the two are compared directly.
    """
    from urllib.parse import urlparse

    from fmd_seo.patch_action import route_inventory

    emitted = {urlparse(url).path or "/" for url in run_sitemap_generator(site_repo)}

    assert route_inventory(site_repo) == emitted


def test_patch_validation_blocks_a_route_added_outside_the_sitemap_file(site_repo, tmp_path):
    """The site uses file-based routing; the sitemap XML is downstream of it.

    A modify-only patch can still mint a brand new URL by adding a `slug:` to
    CityPage.tsx, which never touches a file named sitemap.xml.
    """
    from fmd_seo.patch_action import validate_patch_package

    evidence = _route_evidence(tmp_path / "evidence")
    city = site_repo / "src/components/CityPage.tsx"
    before = city.read_text(encoding="utf-8")
    after = before.replace(
        '    slug: "beachwood",\n',
        '    slug: "beachwood",\n  },\n  {\n    slug: "solon",\n',
    )
    assert after != before

    result = validate_patch_package(
        site_repo,
        _site_patch(site_repo, path="src/components/CityPage.tsx", before=before, after=after),
        current_fact_hash="facts-current",
        evidence_dir=evidence,
    )

    assert result["status"] == "BLOCK"
    assert result["blockers"] == [
        "generator sitemap cannot modify src/components/CityPage.tsx"
    ]


def test_patch_validation_permits_route_removal_via_the_sitemap_generator(site_repo, tmp_path):
    """Fix 5's own patch removes three URLs and must not be blocked."""
    from fmd_seo import patch_generators
    from fmd_seo.contracts import from_dict
    from fmd_seo.patch_action import validate_patch_package

    facts = tmp_path / "business-facts.yaml"
    facts.write_text("canonical facts\n", encoding="utf-8")
    generated = patch_generators.generate_patch_preview(
        "sitemap", worktree=site_repo, facts_file=facts,
    )
    assert generated["status"] == "DONE"

    result = validate_patch_package(
        site_repo,
        from_dict("PatchPackage", generated["package"]),
        current_fact_hash=_sha("canonical facts\n"),
        evidence_dir=tmp_path / "evidence",
    )

    assert result["status"] == "DONE"
    assert result["checks"]["route_additions"] == 0
    assert result["checks"]["route_removals"] == 3


def test_sitemap_package_tampered_replacement_blocks(site_repo, tmp_path):
    """Appending arbitrary JS to the sitemap generator replacement used to
    validate DONE. The replacement must match `_exclude_legal_routes` of the
    tracked script, exactly as a schema replacement must match the renderer.
    """
    from fmd_seo import patch_generators
    from fmd_seo.contracts import from_dict
    from fmd_seo.patch_action import validate_patch_package

    facts = tmp_path / "business-facts.yaml"
    facts.write_text("canonical facts\n", encoding="utf-8")
    generated = patch_generators.generate_patch_preview(
        "sitemap", worktree=site_repo, facts_file=facts,
    )
    assert generated["status"] == "DONE"
    honest = from_dict("PatchPackage", generated["package"])
    tampered_body = honest.modifications[0]["replacement_content"] + "\nconsole.log('tamper');\n"
    tampered = PatchPackage.create(
        generator=honest.generator,
        created_at=honest.created_at,
        site_base_commit=honest.site_base_commit,
        fact_snapshot_hash=honest.fact_snapshot_hash,
        evidence_refs=list(honest.evidence_refs),
        modifications=[{
            **honest.modifications[0],
            "replacement_content": tampered_body,
            "after_sha256": _sha(tampered_body),
        }],
    )

    result = validate_patch_package(
        site_repo,
        tampered,
        current_fact_hash=_sha("canonical facts\n"),
        facts_file=facts,
        evidence_dir=tmp_path / "evidence",
    )

    assert result["status"] == "BLOCK"
    assert "canonical generator output" in result["blockers"][0]


def test_sitemap_generator_cannot_modify_the_xml_artifact(git_repo, tmp_path):
    """public/sitemap.xml is a build artifact. No sitemap generator produces
    it, so permitting it was a widening beyond the stated policy.
    """
    from fmd_seo.patch_action import validate_patch_package

    evidence = _route_evidence(tmp_path / "evidence")
    sitemap = git_repo / "public/sitemap.xml"
    sitemap.parent.mkdir()
    before = "<urlset><url><loc>https://example.com/</loc></url></urlset>\n"
    sitemap.write_text(before, encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "add", "public/sitemap.xml"], check=True)
    subprocess.run(["git", "-C", str(git_repo), "commit", "-m", "sitemap"], check=True)

    result = validate_patch_package(
        git_repo,
        _patch(git_repo, before=before, after="<urlset></urlset>\n"),
        current_fact_hash="facts-current",
        evidence_dir=evidence,
    )

    assert result["status"] == "BLOCK"
    assert "cannot modify public/sitemap.xml" in result["blockers"][0]


def test_sitemap_generator_patches_the_script_that_survives_the_build(
    site_repo, tmp_path, run_sitemap_generator,
):
    """public/sitemap.xml is a build artifact, so patching it accomplishes nothing.

    `bun run build` runs the generator on prebuild, which overwrites whatever
    the patch wrote. Only the generator's own exclusion set is authoritative.
    """
    from fmd_seo import patch_generators

    facts = tmp_path / "business-facts.yaml"
    facts.write_text("canonical facts\n", encoding="utf-8")
    before_locs = run_sitemap_generator(site_repo)
    legal = {
        "https://freshmobiledetail.com/privacy-policy",
        "https://freshmobiledetail.com/terms-of-service",
        "https://freshmobiledetail.com/cancellation-refund-policy",
    }
    assert legal <= before_locs

    result = patch_generators.generate_patch_preview(
        "sitemap", worktree=site_repo, facts_file=facts,
    )

    assert result["status"] == "DONE"
    modifications = result["package"]["modifications"]
    assert [item["path"] for item in modifications] == ["scripts/generate-sitemap.mjs"]

    script = site_repo / "scripts/generate-sitemap.mjs"
    script.write_text(modifications[0]["replacement_content"], encoding="utf-8")
    after_locs = run_sitemap_generator(site_repo)

    assert after_locs == before_locs - legal
    assert result["package"]["schema_version"] == 2
    assert all(
        ref.startswith("ev-route-inventory-")
        for ref in result["package"]["evidence_refs"]
    )
    assert "agent:sitemap-route-inventory" not in result["package"]["evidence_refs"]
    # Deterministic: a second pass over the already-patched script has nothing
    # left to add, so a re-run cannot churn the file.
    assert patch_generators.generate_patch_preview(
        "sitemap", worktree=site_repo, facts_file=facts,
    )["status"] == "NO_OP"


def test_sitemap_generator_blocks_when_the_exclusion_set_cannot_be_located(site_repo, tmp_path):
    from fmd_seo import patch_generators

    facts = tmp_path / "business-facts.yaml"
    facts.write_text("canonical facts\n", encoding="utf-8")
    script = site_repo / "scripts/generate-sitemap.mjs"
    script.write_text(
        script.read_text(encoding="utf-8").replace("const excludedRoutes = new Set(", "const gone = ("),
        encoding="utf-8",
    )

    result = patch_generators.generate_patch_preview(
        "sitemap", worktree=site_repo, facts_file=facts,
    )

    # Silently emitting no patch would read as "nothing to exclude".
    assert result["status"] == "BLOCK"
    assert any("excludedRoutes" in blocker for blocker in result["blockers"])


def test_schema_generator_emits_fact_bound_replacements_for_drift(git_repo, tmp_path):
    from fmd_seo import patch_generators

    facts = tmp_path / "business-facts.yaml"
    # source_last_updated is required: the direction guard has no way to prove a
    # patch moves the site forward without it.
    facts.write_text(_direction_facts("2030-01-01"), encoding="utf-8")

    def change_nested_price(payload):
        payload["facts"]["pricing"]["ultimateInterior"] = 300

    _commit_site_facts(
        git_repo,
        facts,
        committed_at="2026-08-05T12:00:00+00:00",
        mutate_payload=change_nested_price,
    )

    result = patch_generators.generate_patch_preview(
        "schema", worktree=git_repo, facts_file=facts,
    )

    assert result["status"] == "DONE"
    assert result["package"]["generator"] == "schema"
    assert {item["path"] for item in result["package"]["modifications"]} == {
        "src/lib/business-facts.ts", "public/llms.txt",
    }
    assert result["package"]["evidence_refs"][0].startswith("canonical-facts:")


def test_warroom_score_is_deterministic_and_blockers_force_execution_to_zero():
    from fmd_seo.warroom import score_opportunity

    opportunity = {
        "id": "q1",
        "commercial": 80,
        "position": 7,
        "beatability": 60,
        "authority_gap": 100,
        "freshness": 50,
        "cost": 20,
        "risk": 10,
        "blockers": [],
    }
    scored = score_opportunity(opportunity)
    assert scored["components"]["traction"] == 100
    assert scored["score_raw"] == 78.5
    assert scored["score_executable"] == 78.5

    blocked = score_opportunity({**opportunity, "blockers": ["GATE-3 fact binding"]})
    assert blocked["score_raw"] == 78.5
    assert blocked["score_executable"] == 0


def test_manual_override_requires_expiration_and_cannot_override_blockers():
    from fmd_seo.warroom import WarroomError, score_opportunity

    base = {
        "id": "q1", "commercial": 50, "position": 12, "beatability": 50,
        "authority_gap": 0, "freshness": 50, "cost": 10, "risk": 10,
        "blockers": ["human approval"],
    }
    with pytest.raises(WarroomError, match="expiration"):
        score_opportunity({**base, "override": {"owner": "Lou", "reason": "priority", "timestamp": "2026-08-12"}})

    result = score_opportunity({
        **base,
        "override": {
            "owner": "Lou", "reason": "priority", "timestamp": "2026-08-12",
            "expiration": "2026-08-31", "score": 99,
        },
    }, now=datetime(2026, 8, 12, tzinfo=timezone.utc))
    assert result["score_raw"] == 99
    assert result["score_executable"] == 0


def test_expired_manual_override_stops_forcing_the_score_and_says_so():
    from fmd_seo.warroom import score_opportunity

    base = {
        "id": "q1", "commercial": 50, "position": 12, "beatability": 50,
        "authority_gap": 0, "freshness": 50, "cost": 10, "risk": 10,
    }
    override = {
        "owner": "Lou", "reason": "priority", "timestamp": "2026-08-12",
        "expiration": "2026-08-31", "score": 99,
    }
    raw = score_opportunity(base, now=datetime(2026, 8, 12, tzinfo=timezone.utc))["score_raw"]
    assert raw != 99

    live = score_opportunity(
        {**base, "override": override}, now=datetime(2026, 8, 30, tzinfo=timezone.utc),
    )
    assert live["score_raw"] == 99
    assert live["blockers"] == []

    expired = score_opportunity(
        {**base, "override": override}, now=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    # An expired override must fall back to the computed score, and the reader
    # of warroom.yaml has to be able to see that it lapsed.
    assert expired["score_raw"] == raw
    assert any("manual override expired" in b for b in expired["blockers"])
    assert "2026-08-31" in " ".join(expired["blockers"])
    # A lapsed override is a blocker like any other: nothing is executable.
    assert expired["score_executable"] == 0


def test_warroom_derives_authority_cost_risk_and_writes_refresh(tmp_path):
    import yaml

    from fmd_seo.warroom import score_opportunity, write_warroom

    scored = score_opportunity({
        "id": "q-derived",
        "commercial": 70,
        "position": 12,
        "serp_consensus": {"weakness_score": 55},
        "citation_sources": [
            {"frequency": 3, "supports": ["competitor-a", "competitor-b"]},
            {"frequency": 1, "supports": ["fmd"]},
        ],
        "seasonal_window_days": 20,
        "generator": "copy",
        "claim_class": "pricing",
        "blockers": ["GATE-3 fact binding"],
    })

    assert scored["components"]["beatability"] == 55
    assert scored["components"]["authority_gap"] == 100
    assert scored["components"]["freshness"] == 100
    assert scored["components"]["cost"] > 0
    assert scored["components"]["risk"] > 0
    assert scored["score_executable"] == 0

    output = tmp_path / "warroom.yaml"
    write_warroom([scored], output_path=output, generated_at="2026-08-12T12:00:00+00:00")
    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert data["score_version"] == 1
    assert data["opportunities"][0]["id"] == "q-derived"


def test_citation_queue_and_seasonal_calendar_remain_draft_only_under_gate1():
    from fmd_seo.queues import build_citation_queue, build_seasonal_calendar

    citations = build_citation_queue([
        {"domain": "local.example", "frequency": 4, "buyer_relevance": 5,
         "inclusion_feasibility": 3, "supports": ["competitor-a"]},
        {"domain": "national.example", "frequency": 10, "buyer_relevance": 1,
         "inclusion_feasibility": 1, "supports": ["competitor-b"]},
    ])
    assert citations[0]["domain"] == "local.example"
    assert citations[0]["priority"] == 60
    assert all(item["action_mode"] == "research_and_draft" for item in citations)

    calendar = build_seasonal_calendar(
        [{"month": 10, "query": "road salt stains", "page": "/interior-detailing", "score": 90}],
        gate1_state="CLOSED",
        owner="Lou",
        year=2026,
    )
    assert calendar[0]["action"] == "existing_page_or_gbp_draft"
    assert calendar[0]["new_url_allowed"] is False
    assert calendar[0]["gate_status"] == "GATE-1 CLOSED"


def test_schema_generator_blocks_when_the_site_is_newer_than_the_facts_authority(
    git_repo, tmp_path,
):
    """`business-facts.yaml` is only authoritative if it is actually current.

    A stale facts file plus an unconditional generator produces a patch that
    reverts published copy. `facts.freshness` cannot catch this: it measures
    reviewed_at + review_after_days, and a file reviewed but never updated
    passes it while its values sit behind the site.
    """
    from fmd_seo import patch_generators

    facts = tmp_path / "business-facts.yaml"
    facts.write_text(_direction_facts("2026-07-04"), encoding="utf-8")

    def change_nested_price(payload):
        payload["facts"]["pricing"]["ultimateInterior"] = 300

    _commit_site_facts(
        git_repo,
        facts,
        committed_at="2026-08-05T12:00:00+00:00",
        mutate_payload=change_nested_price,
    )

    result = patch_generators.generate_patch_preview(
        "schema", worktree=git_repo, facts_file=facts,
    )

    assert result["status"] == "BLOCK"
    blocker = next(
        item for item in result["blockers"]
        if item["target"] == "src/lib/business-facts.ts"
    )
    assert blocker == {
        "target": "src/lib/business-facts.ts",
        "reason": "site_newer_than_canonical",
        "canonical_date": "2026-07-04",
        "site_commit_date": "2026-08-05",
        "divergent_keys": ["pricing.ultimateInterior"],
    }

    # Once the authority is current again, generation proceeds normally.
    facts.write_text(_direction_facts("2026-08-06"), encoding="utf-8")
    assert patch_generators.generate_patch_preview(
        "schema", worktree=git_repo, facts_file=facts,
    )["status"] == "DONE"


def test_schema_direction_guard_reports_template_only_drift(git_repo, tmp_path):
    from fmd_seo import patch_generators

    facts = tmp_path / "business-facts.yaml"
    facts.write_text(_direction_facts("2026-07-04"), encoding="utf-8")
    _commit_site_facts(
        git_repo,
        facts,
        committed_at="2026-08-05T12:00:00+00:00",
        llms="newer hand-edited presentation\n",
    )

    result = patch_generators.generate_patch_preview(
        "schema", worktree=git_repo, facts_file=facts,
    )

    assert result["status"] == "BLOCK"
    assert result["blockers"] == [{
        "target": "public/llms.txt",
        "reason": "site_newer_than_canonical",
        "canonical_date": "2026-07-04",
        "site_commit_date": "2026-08-05",
        "divergent_keys": ["template.public_llms"],
    }]


@pytest.mark.parametrize("source_date", ["", "not-a-date", "2026-13-40"])
def test_schema_direction_guard_fails_closed_on_missing_or_invalid_canonical_date(
    git_repo, tmp_path, source_date,
):
    from fmd_seo import patch_generators

    facts = tmp_path / "business-facts.yaml"
    facts.write_text(_direction_facts("2026-08-06"), encoding="utf-8")
    _commit_site_facts(
        git_repo,
        facts,
        committed_at="2026-08-05T12:00:00+00:00",
        llms="drift\n",
    )
    facts.write_text(_direction_facts(source_date), encoding="utf-8")

    result = patch_generators.generate_patch_preview(
        "schema", worktree=git_repo, facts_file=facts,
    )

    assert result["status"] == "BLOCK"
    assert result["blockers"]
    assert all(blocker["target"] for blocker in result["blockers"])
    assert all(blocker["reason"] in {"canonical_date_missing", "canonical_date_invalid"}
               for blocker in result["blockers"])
    assert all("canonical_date" in blocker and "site_commit_date" in blocker
               and "divergent_keys" in blocker for blocker in result["blockers"])


def test_schema_direction_guard_fails_closed_on_git_log_failure(
    git_repo, tmp_path, monkeypatch,
):
    from fmd_seo import patch_generators

    facts = tmp_path / "business-facts.yaml"
    facts.write_text(_direction_facts("2026-08-06"), encoding="utf-8")
    _commit_site_facts(
        git_repo,
        facts,
        committed_at="2026-08-05T12:00:00+00:00",
        llms="drift\n",
    )
    monkeypatch.setattr(
        patch_generators,
        "_last_commit_date",
        lambda _worktree, _relative: (_ for _ in ()).throw(ValueError("git log failed")),
    )

    result = patch_generators.generate_patch_preview(
        "schema", worktree=git_repo, facts_file=facts,
    )

    assert result["status"] == "BLOCK"
    assert result["blockers"][0]["reason"] == "site_commit_date_unavailable"
    assert result["blockers"][0]["site_commit_date"] is None


def test_schema_direction_guard_fails_closed_on_unreadable_site_payload(git_repo, tmp_path):
    from fmd_seo import patch_generators

    facts = tmp_path / "business-facts.yaml"
    facts.write_text(_direction_facts("2026-08-06"), encoding="utf-8")
    _commit_site_facts(
        git_repo,
        facts,
        committed_at="2026-08-05T12:00:00+00:00",
    )
    ts = git_repo / "src/lib/business-facts.ts"
    ts.write_text("not a generated payload\n", encoding="utf-8")

    result = patch_generators.generate_patch_preview(
        "schema", worktree=git_repo, facts_file=facts,
    )

    assert result["status"] == "BLOCK"
    blocker = result["blockers"][0]
    assert blocker["target"] == "src/lib/business-facts.ts"
    assert blocker["reason"] == "site_payload_unreadable"
    assert blocker["divergent_keys"] == ["payload.unreadable"]


def test_schema_direction_guard_returns_structured_block_for_unreadable_canonical_payload(
    git_repo, tmp_path,
):
    from fmd_seo import patch_generators

    facts = tmp_path / "business-facts.yaml"
    facts.write_text(_direction_facts("2026-08-06"), encoding="utf-8")
    _commit_site_facts(
        git_repo,
        facts,
        committed_at="2026-08-05T12:00:00+00:00",
    )
    facts.write_text("schema_version: [\n", encoding="utf-8")

    result = patch_generators.generate_patch_preview(
        "schema", worktree=git_repo, facts_file=facts,
    )

    assert result["status"] == "BLOCK"
    assert {blocker["target"] for blocker in result["blockers"]} == {
        "src/lib/business-facts.ts", "public/llms.txt",
    }
    assert all(blocker["reason"] == "canonical_payload_unreadable"
               for blocker in result["blockers"])
    assert all(set(blocker) == {
        "target", "reason", "canonical_date", "site_commit_date", "divergent_keys",
    } for blocker in result["blockers"])
