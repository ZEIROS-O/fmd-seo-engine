import subprocess

from fmd_seo.contracts import PagePackage
from fmd_seo.export import export_package


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
