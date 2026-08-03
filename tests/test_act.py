import subprocess

from fmd_seo import paths as engine_paths
from fmd_seo.act import ActError, dry_run_plan, publish_package, validate_current_fact_binding
from fmd_seo.contracts import ExportManifest, PagePackage, write_package
from fmd_seo.facts import load_snapshot


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_act_dry_run_reports_diff_without_touching_git(git_repo):
    tracked = git_repo / "site.txt"
    tracked.write_text("changed\n", encoding="utf-8")
    (git_repo / "new.txt").write_text("new\n", encoding="utf-8")
    before_head = _git(git_repo, "rev-parse", "HEAD")
    before_status = _git(git_repo, "status", "--porcelain")

    result = dry_run_plan(git_repo)

    assert result["command"] == "act"
    assert result["dry_run"] is True
    assert result["git"]["head"] == before_head.strip()
    assert "site.txt" in result["git"]["changed_files"]
    assert "new.txt" in result["git"]["changed_files"]
    assert _git(git_repo, "rev-parse", "HEAD") == before_head
    assert _git(git_repo, "status", "--porcelain") == before_status


def _bound_package(facts_file):
    snapshot = load_snapshot(facts_file, ["identity.phone"])
    return PagePackage.create(
        intent_key="test", tier="supporting-post", created_at="2026-08-01T00:00:00+00:00",
        fact_snapshot=snapshot.to_dict(), evidence_refs=[],
        content={
            "slug": "test-post", "title": "Test post",
            "canonical": "https://freshmobiledetail.com/blog/test-post/", "blocks": [],
        },
        internal_links=[], assets=[],
    )


def test_package_fact_binding_rejects_changed_canonical_facts(facts_file):
    package = _bound_package(facts_file)
    assert validate_current_fact_binding(package, facts_file)[1] == "PASS"

    facts_file.write_text(
        facts_file.read_text(encoding="utf-8").replace("(216) 359-1034", "(216) 000-0000"),
        encoding="utf-8",
    )

    verdict = validate_current_fact_binding(package, facts_file)
    assert verdict[1] == "BLOCK"
    assert "differ" in verdict[2]


def test_act_package_dry_run_shows_planned_patch_without_writing(git_repo, facts_file, tmp_path):
    package_path = write_package(_bound_package(facts_file), tmp_path / "packages")

    result = dry_run_plan(git_repo, package_path)

    assert result["package"]["would_create"] is True
    assert '"slug": "test-post"' in result["package"]["planned_diff"]
    assert not (git_repo / "content/blog/test-post.json").exists()


def test_publish_returns_resumable_block_when_push_fails(
    git_repo, facts_file, tmp_path, monkeypatch,
):
    package_path = write_package(_bound_package(facts_file), tmp_path / "packages")

    class OpenBrain:
        @staticmethod
        def gate_state(_gate):
            return "OPEN"

    manifest = ExportManifest(
        package_id=_bound_package(facts_file).package_id,
        package_hash="hash",
        generated_files=["content/blog/test-post.json", "public/sitemap.xml"],
        canonical_url="https://freshmobiledetail.com/blog/test-post/",
        destination_commit="abc123",
        rollback_base="base",
        exported_at="2026-08-01T00:00:00+00:00",
    )
    monkeypatch.setattr("fmd_seo.act.load_brain", lambda: OpenBrain())
    monkeypatch.setattr("fmd_seo.act.sync_worktree", lambda _worktree: "base")
    monkeypatch.setattr("fmd_seo.act.deterministic_checks", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("fmd_seo.act.corpus_checks", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("fmd_seo.act.parse_live_posts", lambda *_args, **_kwargs: [])
    monkeypatch.setattr("fmd_seo.act.export_package", lambda *_args, **_kwargs: ([], manifest))
    monkeypatch.setattr(
        "fmd_seo.act.write_manifest",
        lambda *_args, **_kwargs: engine_paths.EVIDENCE_DIR / "exports/test.json",
    )

    calls = []

    def fake_run(_repo, *args):
        calls.append(args)
        if args[:2] == ("git", "push"):
            raise ActError("git push failed: auth denied")
        if args[:3] == ("git", "rev-parse", "HEAD"):
            return "abc123"
        return ""

    monkeypatch.setattr("fmd_seo.act._run", fake_run)

    result = publish_package({
        "paths": {"site_worktree": str(git_repo), "facts_file": str(facts_file)},
    }, package_path)

    assert result["status"] == "BLOCK"
    assert result["commit_hashes"] == {"site": "abc123"}
    assert result["manifest"].endswith("exports/test.json")
    assert "auth denied" in result["blockers"][0]
    assert ("git", "switch", "--detach", "base") in calls
