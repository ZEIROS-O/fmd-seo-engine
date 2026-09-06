import json
import re
import subprocess

import pytest

from fmd_seo.act import dry_run_plan
from fmd_seo.brain import load_brain


def test_capability_check_names_all_missing_inputs_without_values():
    from fmd_seo.credentials import check_capability

    result = check_capability(
        "dataforseo",
        environ={"DATAFORSEO_LOGIN": "present", "DATAFORSEO_PASSWORD": ""},
    )

    assert result == {
        "capability": "dataforseo",
        "status": "BLOCK",
        "missing": ["DATAFORSEO_PASSWORD"],
    }
    assert "present" not in json.dumps(result)


def test_capability_checks_are_independent():
    from fmd_seo.credentials import check_capabilities

    results = check_capabilities(
        ["dataforseo", "semrush", "gsc", "facts", "site"],
        environ={
            "DATAFORSEO_LOGIN": "login",
            "DATAFORSEO_PASSWORD": "password",
            "SEMRUSH_API_KEY": "",
            "GSC_SERVICE_ACCOUNT_JSON": "{}",
            "BUSINESS_FACTS_YAML": "facts: true",
            "SITE_REPO_TOKEN": "",
        },
    )

    by_name = {item["capability"]: item for item in results}
    assert by_name["dataforseo"]["status"] == "DONE"
    assert by_name["gsc"]["status"] == "DONE"
    assert by_name["facts"]["status"] == "DONE"
    assert by_name["semrush"]["missing"] == ["SEMRUSH_API_KEY"]
    assert by_name["site"]["missing"] == ["SITE_REPO_TOKEN"]


def test_local_capability_checks_use_configured_files_without_secret_copies(tmp_path):
    from fmd_seo.credentials import check_capabilities

    creds = tmp_path / "providers.env"
    creds.write_text(
        "DATAFORSEO_LOGIN=local-login\n"
        "DATAFORSEO_PASSWORD=local-password\n"
        "SEMRUSH_API_KEY=local-key\n",
        encoding="utf-8",
    )
    google = tmp_path / "google.json"
    google.write_text('{"type":"service_account"}\n', encoding="utf-8")
    facts = tmp_path / "business-facts.yaml"
    facts.write_text("schema_version: 1\n", encoding="utf-8")
    site = tmp_path / "site"
    (site / ".git").mkdir(parents=True)
    config = {
        "creds_env": str(creds),
        "gsc": {"key_path": str(google)},
        "paths": {
            "facts_file": str(facts),
            "site_worktree": str(site),
        },
    }

    results = check_capabilities(config=config, environ={})

    assert [item["status"] for item in results] == ["DONE"] * 5
    assert all(item["missing"] == [] for item in results)


def test_local_capability_checks_name_missing_paths_without_secret_values(tmp_path):
    from fmd_seo.credentials import check_capabilities

    results = check_capabilities(
        config={
            "creds_env": str(tmp_path / "missing.env"),
            "gsc": {"key_path": str(tmp_path / "missing-google.json")},
            "paths": {
                "facts_file": str(tmp_path / "missing-facts.yaml"),
                "site_worktree": str(tmp_path / "missing-site"),
            },
        },
        environ={},
    )

    by_name = {item["capability"]: item for item in results}
    assert by_name["dataforseo"]["missing"] == ["DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD"]
    assert by_name["semrush"]["missing"] == ["SEMRUSH_API_KEY"]
    assert by_name["gsc"]["missing"] == ["gsc.key_path"]
    assert by_name["facts"]["missing"] == ["paths.facts_file"]
    assert by_name["site"]["missing"] == ["paths.site_worktree"]


def test_missing_site_worktree_returns_structured_block(tmp_path):
    result = dry_run_plan(tmp_path / "missing-site")

    assert result["status"] == "BLOCK"
    assert result["blockers"] == ["site worktree missing; run `fmd-seo site-init`"]


def test_site_init_creates_detached_checkout_and_records_exact_base(git_repo, tmp_path):
    from fmd_seo.site import initialize_site_worktree

    target = tmp_path / "fresh-site-v3"
    state_path = tmp_path / "site-worktree.json"
    expected = subprocess.run(
        ["git", "-C", str(git_repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = initialize_site_worktree(
        target,
        repository=str(git_repo),
        base_ref=expected,
        state_path=state_path,
    )

    assert result["status"] == "DONE"
    assert result["base_sha"] == expected
    assert result["detached"] is True
    assert json.loads(state_path.read_text(encoding="utf-8"))["base_sha"] == expected
    status = subprocess.run(
        ["git", "-C", str(target), "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    )
    assert status.stdout == ""


def test_site_init_rewrites_a_missing_receipt_for_an_existing_checkout(git_repo, tmp_path):
    """A receipt that only the clone path can write can never be regenerated.

    Deleting a hand-authored receipt and re-running `site-init` has to actually
    produce a code-authored one, or the hand-authored version is permanent.
    """
    from fmd_seo.site import initialize_site_worktree

    target = tmp_path / "fresh-site-v3"
    state_path = tmp_path / "site-worktree.json"
    first = initialize_site_worktree(
        target, repository=str(git_repo), base_ref="origin/main", state_path=state_path,
    )
    assert first["status"] == "DONE"
    original = json.loads(state_path.read_text(encoding="utf-8"))
    state_path.unlink()

    again = initialize_site_worktree(
        target, repository=str(git_repo), base_ref="origin/main", state_path=state_path,
    )

    assert again["status"] == "NO_OP"
    rewritten = json.loads(state_path.read_text(encoding="utf-8"))
    assert rewritten["base_sha"] == original["base_sha"]
    assert rewritten["base_ref"] == "origin/main"
    assert set(rewritten) == set(original)


def test_tracked_site_worktree_receipt_matches_what_the_code_emits(git_repo, tmp_path):
    """The committed receipt must be code-authored, not hand-authored.

    A hand-written receipt can carry keys the engine never reads and put a SHA
    where a ref belongs -- and because `initialize_site_worktree` short-circuits
    on an existing file, the lie is never corrected by running the command.
    """
    from fmd_seo import paths
    from fmd_seo.site import initialize_site_worktree

    tracked_path = paths.ENGINE_ROOT / "state" / "site-worktree.json"
    if not tracked_path.exists():
        pytest.skip("site worktree receipt not initialized in this checkout")
    tracked = json.loads(tracked_path.read_text(encoding="utf-8"))

    initialize_site_worktree(
        tmp_path / "reference-site",
        repository=str(git_repo),
        base_ref="origin/main",
        state_path=tmp_path / "reference.json",
    )
    reference = json.loads((tmp_path / "reference.json").read_text(encoding="utf-8"))

    assert set(tracked) == set(reference)
    # base_ref names the ref the checkout tracks; base_sha holds the commit.
    # Storing a SHA in base_ref erases which ref the pin was taken from.
    assert not re.fullmatch(r"[0-9a-f]{40}", str(tracked["base_ref"]))
