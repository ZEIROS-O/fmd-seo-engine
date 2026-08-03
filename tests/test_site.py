import subprocess
from pathlib import Path

import pytest

from fmd_seo.site import SiteSyncError, reset_worktree, sync_worktree


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def test_sync_worktree_fetches_and_resets_to_origin_main(tmp_path: Path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-b", "main")
    _git(seed, "config", "user.email", "test@test.local")
    _git(seed, "config", "user.name", "test")
    (seed / "site.txt").write_text("one\n", encoding="utf-8")
    _git(seed, "add", "site.txt")
    _git(seed, "commit", "-m", "one")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-u", "origin", "main")
    worktree = tmp_path / "worktree"
    subprocess.run(
        ["git", "clone", "--branch", "main", str(remote), str(worktree)],
        check=True,
        capture_output=True,
    )
    (seed / "site.txt").write_text("two\n", encoding="utf-8")
    _git(seed, "add", "site.txt")
    _git(seed, "commit", "-m", "two")
    _git(seed, "push")

    sha = sync_worktree(worktree)

    assert sha == _git(seed, "rev-parse", "HEAD")
    assert (worktree / "site.txt").read_text() == "two\n"
    assert _git(worktree, "status", "--porcelain") == ""


def test_sync_worktree_blocks_dirty_state_before_fetch(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@test.local")
    _git(repo, "config", "user.name", "test")
    (repo / "site.txt").write_text("one\n", encoding="utf-8")
    _git(repo, "add", "site.txt")
    _git(repo, "commit", "-m", "one")
    (repo / "site.txt").write_text("dirty\n", encoding="utf-8")

    with pytest.raises(SiteSyncError, match="dirty"):
        sync_worktree(repo)


def test_sync_worktree_preserves_clean_unpushed_commit(tmp_path: Path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@test.local")
    _git(repo, "config", "user.name", "test")
    (repo / "site.txt").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "site.txt")
    _git(repo, "commit", "-m", "base")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")
    (repo / "site.txt").write_text("local commit\n", encoding="utf-8")
    _git(repo, "add", "site.txt")
    _git(repo, "commit", "-m", "local only")
    local_sha = _git(repo, "rev-parse", "HEAD")

    with pytest.raises(SiteSyncError, match="not an ancestor"):
        sync_worktree(repo)

    assert _git(repo, "rev-parse", "HEAD") == local_sha
    assert (repo / "site.txt").read_text(encoding="utf-8") == "local commit\n"

    report = reset_worktree(repo)
    assert report["ahead"] == 1
    assert report["needs_reset"] is True
    assert _git(repo, "rev-parse", "HEAD") == local_sha

    # An uncommitted edit is destroyed outright by --force, so the receipt has
    # to name it; `dirty` describes the worktree after the reset, which is empty.
    (repo / "scratch.txt").write_text("operator work in progress\n", encoding="utf-8")

    reset = reset_worktree(repo, force=True)
    assert reset["status"] == "DONE"
    assert reset["needs_reset"] is False
    assert _git(repo, "branch", "--show-current") == ""
    assert _git(repo, "rev-parse", "main") == local_sha
    assert (repo / "site.txt").read_text(encoding="utf-8") == "base\n"
    assert reset["dirty"] == []
    assert any("scratch.txt" in entry for entry in reset["discarded"])
    assert not (repo / "scratch.txt").exists()
