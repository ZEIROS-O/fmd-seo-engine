import subprocess

from fmd_seo.contracts import PagePackage
from fmd_seo.export import content_destination, export_package
from fmd_seo.verify import checks_pass


def _package() -> PagePackage:
    return PagePackage.create(
        intent_key="test-post",
        tier="supporting-post",
        created_at="2026-08-01T00:00:00+00:00",
        fact_snapshot={"source_hash": "test"},
        evidence_refs=["evidence/test.json"],
        content={
            "slug": "test-post",
            "title": "Test post",
            "canonical": "https://freshmobiledetail.com/blog/test-post/",
            "blocks": [],
        },
        internal_links=[],
        assets=[],
    )


def test_export_blocks_when_git_status_fails(tmp_path):
    worktree = tmp_path / "not-a-repository"
    worktree.mkdir()

    checks, manifest = export_package(_package(), worktree)

    assert manifest is None
    assert any(name == "worktree_clean" and verdict == "BLOCK" for name, verdict, _ in checks)
    assert not (worktree / "content" / "blog" / "test-post.json").exists()


def test_content_destination_rejects_path_or_branch_injection(tmp_path):
    for slug in ("../escape", "Mixed-Case", "safe;git-push", "two--dashes"):
        try:
            content_destination(tmp_path, slug)
        except ValueError:
            pass
        else:
            raise AssertionError(f"accepted unsafe slug {slug!r}")


def test_export_build_failure_rolls_back_to_clean_worktree(git_repo, monkeypatch):
    real_run = subprocess.run

    def fake_run(args, *pargs, **kwargs):
        if args[:3] == ["bun", "run", "build"]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="build failed")
        return real_run(args, *pargs, **kwargs)

    monkeypatch.setattr("fmd_seo.export.subprocess.run", fake_run)

    checks, manifest = export_package(_package(), git_repo)

    assert manifest is None
    assert any(name == "production_build" and verdict == "BLOCK" for name, verdict, _ in checks)
    assert any(name == "rollback" and verdict == "PASS" for name, verdict, _ in checks)
    assert not (git_repo / "content" / "blog" / "test-post.json").exists()
    status = real_run(
        ["git", "-C", str(git_repo), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""


def test_export_commits_content_and_build_generated_sitemap_cleanly(git_repo, monkeypatch):
    sitemap = git_repo / "public/sitemap.xml"
    sitemap.parent.mkdir()
    sitemap.write_text("<urlset></urlset>\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(git_repo), "add", "public/sitemap.xml"], check=True)
    subprocess.run(["git", "-C", str(git_repo), "commit", "-m", "add sitemap"], check=True)
    real_run = subprocess.run
    real_popen = subprocess.Popen

    def fake_run(args, *pargs, **kwargs):
        if args[:3] == ["bun", "run", "build"]:
            sitemap.write_text("<urlset><url>test-post</url></urlset>\n", encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, stdout="built", stderr="")
        return real_run(args, *pargs, **kwargs)

    class FakeServer:
        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

        def kill(self):
            pass

    monkeypatch.setattr("fmd_seo.export.subprocess.run", fake_run)
    monkeypatch.setattr(
        "fmd_seo.export.subprocess.Popen",
        lambda args, *pargs, **kwargs: (
            FakeServer() if args[:3] == ["bun", "run", "preview"]
            else real_popen(args, *pargs, **kwargs)
        ),
    )
    monkeypatch.setattr("fmd_seo.export._wait_port", lambda _port: True)
    monkeypatch.setattr(
        "fmd_seo.export.check_slash_variants",
        lambda *_args, **_kwargs: {"fetch": ("PASS", "200")},
    )

    checks, manifest = export_package(_package(), git_repo)

    assert manifest is not None
    assert set(manifest.generated_files) == {
        "content/blog/test-post.json", "public/sitemap.xml",
    }
    committed = real_run(
        ["git", "-C", str(git_repo), "show", "--name-only", "--format="],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    assert set(committed) == set(manifest.generated_files)
    assert real_run(
        ["git", "-C", str(git_repo), "status", "--porcelain", "--untracked-files=all"],
        check=True, capture_output=True, text=True,
    ).stdout == ""
    assert any(name == "postcommit_clean" and verdict == "PASS" for name, verdict, _ in checks)


def test_verification_aggregation_blocks_if_any_check_blocks():
    assert checks_pass([("a", "PASS", "ok"), ("b", "BLOCK", "bad")]) is False
    assert checks_pass([("a", "PASS", "ok")]) is True
