import json

from fmd_seo.reverify import record_reconciled_interventions, reverify_manifests


def test_reverify_blocks_export_commit_not_on_origin_and_missing_file(tmp_path):
    exports = tmp_path / "exports"
    exports.mkdir()
    (exports / "one-export.json").write_text(json.dumps({
        "schema_version": 1,
        "package_id": "pp-one",
        "package_hash": "hash",
        "generated_files": ["content/blog/one.json"],
        "canonical_url": "https://example.test/blog/one",
        "destination_commit": "deadbeef",
        "rollback_base": "base",
        "exported_at": "2026-08-01T00:00:00+00:00",
        "expected": {"canonical": "https://example.test/blog/one"},
    }), encoding="utf-8")
    worktree = tmp_path / "site"
    worktree.mkdir()

    result = reverify_manifests(
        exports,
        worktree,
        sync=False,
        git_runner=lambda *_args: (1, "", "not ancestor"),
        page_checker=lambda _url, **_kwargs: {"fetch": ("BLOCK", "404")},
    )

    assert result["status"] == "BLOCK"
    verdicts = {check["name"]: check["verdict"] for check in result["checks"]}
    assert verdicts["pp-one:ancestor"] == "BLOCK"
    assert verdicts["pp-one:file:content/blog/one.json"] == "BLOCK"
    assert verdicts["pp-one:live:fetch"] == "BLOCK"


def test_reverify_skips_archived_manifests(tmp_path):
    exports = tmp_path / "exports"
    archive = exports / "archive"
    archive.mkdir(parents=True)
    (archive / "old-export.json").write_text("{}", encoding="utf-8")
    worktree = tmp_path / "site"
    worktree.mkdir()

    result = reverify_manifests(exports, worktree, sync=False)

    assert result["status"] == "DONE"
    assert result["manifests"] == 0
    assert result["archived_manifests"] == 1


def test_reverify_records_proven_merge_once(tmp_path):
    exports = tmp_path / "exports"
    exports.mkdir()
    worktree = tmp_path / "site"
    (worktree / "content/blog").mkdir(parents=True)
    (worktree / "content/blog/one.json").write_text("{}", encoding="utf-8")
    (exports / "one-export.json").write_text(json.dumps({
        "schema_version": 1,
        "package_id": "pp-one",
        "package_hash": "hash",
        "generated_files": ["content/blog/one.json"],
        "canonical_url": "https://example.test/blog/one",
        "destination_commit": "abc123",
        "rollback_base": "base",
        "exported_at": "2026-08-01T00:00:00+00:00",
        "expected": {"canonical": "https://example.test/blog/one"},
    }), encoding="utf-8")
    result = reverify_manifests(
        exports,
        worktree,
        sync=False,
        git_runner=lambda *_args: (0, "", ""),
        page_checker=lambda _url, **_kwargs: {"fetch": ("PASS", "200")},
    )
    interventions = tmp_path / "interventions.jsonl"

    first = record_reconciled_interventions(
        result,
        worktree,
        interventions,
        git_runner=lambda _worktree, *args: (
            (0, "abc123", "") if args[:2] == ("rev-list", "--first-parent")
            else (0, "2026-08-03T12:00:00+00:00", "")
        ),
    )
    second = record_reconciled_interventions(
        result,
        worktree,
        interventions,
        git_runner=lambda _worktree, *args: (
            (0, "abc123", "") if args[:2] == ("rev-list", "--first-parent")
            else (0, "2026-08-03T12:00:00+00:00", "")
        ),
    )

    assert result["reconciled"] == [{"package_id": "pp-one", "sha": "abc123"}]
    assert first == ["abc123"] and second == []
    assert len(interventions.read_text(encoding="utf-8").splitlines()) == 1
