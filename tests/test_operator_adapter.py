import pytest

from fmd_seo.operator_adapter import (
    VERIFIER_FILES, OperatorAdapter, OperatorMutated, OperatorUnavailable, snapshot,
)


def test_snapshot_captures_head_and_status(git_repo):
    snap = snapshot(git_repo)
    assert len(snap.head_sha) == 40
    (git_repo / "file.txt").write_text("changed\n")
    assert snapshot(git_repo).status_hash != snap.status_hash


def test_adapter_passes_when_repo_untouched(git_repo):
    for rel in VERIFIER_FILES:
        target = git_repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {rel}\n")
    with OperatorAdapter(git_repo) as adapter:
        context = adapter.verifier_context()
    assert set(context) == set(VERIFIER_FILES)


def test_adapter_fails_hard_on_mutation(git_repo):
    with pytest.raises(OperatorMutated):
        with OperatorAdapter(git_repo):
            (git_repo / "file.txt").write_text("mutated during adapter use\n")


def test_missing_verifier_context_is_unavailable_not_degraded(git_repo):
    with pytest.raises(OperatorUnavailable):
        with OperatorAdapter(git_repo) as adapter:
            adapter.verifier_context()


def test_missing_repo_is_unavailable(tmp_path):
    with pytest.raises(OperatorUnavailable):
        with OperatorAdapter(tmp_path / "nowhere"):
            pass
