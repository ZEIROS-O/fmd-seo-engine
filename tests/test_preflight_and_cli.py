import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from fmd_seo.preflight import run_preflight
from fmd_seo.cli import _emit_loop
from fmd_seo.receipts import ReceiptBuilder

ENGINE_ROOT = Path(__file__).resolve().parents[1]


def _config(tmp_path, facts_file, git_repo, *, creds=False, worktree=False):
    creds_file = tmp_path / "dataforseo.env"
    if creds:
        creds_file.write_text("DATAFORSEO_LOGIN=x\nDATAFORSEO_PASSWORD=y\n")
    wt = tmp_path / "site-worktree"
    if worktree:
        (wt / ".git").mkdir(parents=True)
    return {
        "schema_version": 1,
        "budget": {"total_usd": 10.0, "endpoint_caps_usd": {"probe": 0.05}},
        "paths": {
            "facts_file": str(facts_file),
            "fresh_repo": str(git_repo),
            "operator_repo": str(git_repo),
            "zeiros_repo": str(git_repo),
            "site_worktree": str(wt),
        },
        "creds_env": str(creds_file),
        "limits": {"systemic_failures_to_kill": 2},
    }


def _add_verifier_context(git_repo):
    from fmd_seo.operator_adapter import VERIFIER_FILES
    for rel in VERIFIER_FILES:
        target = git_repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"# {rel}\n")


def test_preflight_blocks_on_missing_creds_and_worktree(tmp_path, facts_file, git_repo):
    _add_verifier_context(git_repo)
    receipt = run_preflight(_config(tmp_path, facts_file, git_repo))
    assert receipt.status == "BLOCK"
    joined = " ".join(receipt.blockers)
    assert "dataforseo_creds" in joined and "site_worktree" in joined
    # facts + operator adapter still pass — blockers are precise, not global
    verdicts = {c["name"]: c["verdict"] for c in receipt.checks}
    assert verdicts["facts"] == "PASS"
    assert verdicts["operator_adapter"] == "PASS"


def test_preflight_done_when_all_present(tmp_path, facts_file, git_repo):
    _add_verifier_context(git_repo)
    receipt = run_preflight(_config(tmp_path, facts_file, git_repo, creds=True, worktree=True))
    assert receipt.status == "DONE"
    assert receipt.blockers == []


def test_preflight_online_without_creds_blocks_probe(tmp_path, facts_file, git_repo):
    _add_verifier_context(git_repo)
    receipt = run_preflight(_config(tmp_path, facts_file, git_repo), online=True)
    verdicts = {c["name"]: c["verdict"] for c in receipt.checks}
    assert verdicts["probe"] == "BLOCK"


def test_preflight_does_not_require_removed_fresh_repo_path(
    tmp_path, facts_file, git_repo,
):
    _add_verifier_context(git_repo)
    config = _config(
        tmp_path, facts_file, git_repo, creds=True, worktree=True,
    )
    del config["paths"]["fresh_repo"]

    receipt = run_preflight(config)

    assert receipt.status == "DONE"
    assert all(check["name"] != "repo:fresh_repo" for check in receipt.checks)


def _run_cli(tmp_path, config, *args):
    cfg_file = tmp_path / "engine.yaml"
    cfg_file.write_text(yaml.safe_dump(config))
    env_root = tmp_path / "engine-root"
    env_root.mkdir(exist_ok=True)
    shutil.copytree(ENGINE_ROOT / "brain", env_root / "brain", dirs_exist_ok=True)
    result = subprocess.run(
        ["python3", "-m", "fmd_seo", "--config", str(cfg_file), *args],
        capture_output=True, text=True, timeout=60,
        env={"PYTHONPATH": str(ENGINE_ROOT / "src"), "FMD_SEO_ROOT": str(env_root), "PATH": "/usr/bin:/bin"},
    )
    return result, env_root


def test_cli_loop_surface_emits_receipt(tmp_path, facts_file, git_repo):
    result, root = _run_cli(
        tmp_path,
        _config(tmp_path, facts_file, git_repo),
        "beat",
    )
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["command"] == "beat"
    receipt_files = list((root / "receipts").glob("*.json"))
    assert len(receipt_files) == 1
    receipt = json.loads(receipt_files[0].read_text())
    assert receipt["command"] == "beat"
    assert receipt["status"] == "DONE"


def test_loop_receipt_preserves_structured_checks_blockers_and_commit(tmp_path):
    code = _emit_loop(
        ReceiptBuilder("act"),
        {
            "command": "act",
            "branch": "seo-engine/2026-08-01-test",
            "checks": [{"name": "external_publish", "verdict": "BLOCK", "detail": "auth failed"}],
            "blockers": ["auth failed"],
            "commit_hashes": {"site": "abc123"},
        },
        4,
        tmp_path,
    )

    receipt = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert code == 4
    assert receipt["checks"][0]["name"] == "external_publish"
    assert any("auth failed" in blocker for blocker in receipt["blockers"])
    assert receipt["commit_hashes"] == {"site": "abc123"}
    assert receipt["resume_point"] == "site branch seo-engine/2026-08-01-test"


def test_cli_observe_machine_updates_gate1_state(tmp_path, facts_file, git_repo):
    records = {
        "indexed": 20,
        "not_indexed": 2,
        "discovered_not_indexed": 0,
        "crawled_not_indexed": 0,
        "inspected_ok": 22,
    }

    result, root = _run_cli(
        tmp_path,
        _config(tmp_path, facts_file, git_repo),
        "observe",
        "seo.indexation",
        "--records",
        json.dumps(records),
        "--fulfillment",
        "console",
        "--source",
        "test",
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["gate_update"]["consecutive_clean_readings"] == 1
    state = yaml.safe_load((root / "brain" / "state.yaml").read_text())
    assert state["gates"]["GATE-1"]["consecutive_clean_readings"] == 1


def test_cli_sync_respects_live_run_lock(tmp_path, facts_file, git_repo):
    config = _config(tmp_path, facts_file, git_repo)
    cfg_file = tmp_path / "engine.yaml"
    cfg_file.write_text(yaml.safe_dump(config))
    env_root = tmp_path / "engine-root"
    shutil.copytree(ENGINE_ROOT / "brain", env_root / "brain", dirs_exist_ok=True)
    lock_file = env_root / ".run" / "lock"
    lock_file.parent.mkdir(parents=True)
    lock_file.write_text(json.dumps({"pid": os.getpid(), "run_id": "other"}))

    result = subprocess.run(
        ["python3", "-m", "fmd_seo", "--config", str(cfg_file), "sync"],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PYTHONPATH": str(ENGINE_ROOT / "src"),
            "FMD_SEO_ROOT": str(env_root),
            "PATH": "/usr/bin:/bin",
        },
    )

    assert result.returncode == 4
    assert lock_file.exists()
    assert json.loads(lock_file.read_text())["run_id"] == "other"
    receipt = json.loads(next((env_root / "receipts").glob("*.json")).read_text())
    assert receipt["status"] == "BLOCK"


def test_cli_assess_internal_error_is_exit_five(tmp_path, facts_file, git_repo):
    config = _config(tmp_path, facts_file, git_repo)
    cfg_file = tmp_path / "engine.yaml"
    cfg_file.write_text(yaml.safe_dump(config))
    env_root = tmp_path / "engine-root"
    shutil.copytree(ENGINE_ROOT / "brain", env_root / "brain", dirs_exist_ok=True)
    (env_root / "brain" / "checks.yaml").write_text("checks: [unterminated\n")

    result = subprocess.run(
        ["python3", "-m", "fmd_seo", "--config", str(cfg_file), "assess"],
        capture_output=True,
        text=True,
        timeout=60,
        env={
            "PYTHONPATH": str(ENGINE_ROOT / "src"),
            "FMD_SEO_ROOT": str(env_root),
            "PATH": "/usr/bin:/bin",
        },
    )

    assert result.returncode == 5
    payload = json.loads(result.stdout)
    assert "error" in payload
    receipt = json.loads(next((env_root / "receipts").glob("*.json")).read_text())
    assert receipt["status"] == "BLOCK"


def test_cli_preflight_emits_receipt(tmp_path, facts_file, git_repo):
    _add_verifier_context(git_repo)
    result, root = _run_cli(tmp_path, _config(tmp_path, facts_file, git_repo), "preflight")
    assert result.returncode == 4  # BLOCK: no creds/worktree in this config
    receipt = json.loads(result.stdout)
    assert receipt["command"] == "preflight" and receipt["status"] == "BLOCK"
    assert list((root / "receipts").glob("*.json"))


def test_cli_reverify_is_wired_and_blocks_on_invalid_worktree(tmp_path, facts_file, git_repo):
    _add_verifier_context(git_repo)
    config = _config(tmp_path, facts_file, git_repo, creds=True, worktree=True)
    result, root = _run_cli(tmp_path, config, "reverify")
    assert result.returncode == 4
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "BLOCK"
    assert "not a git worktree" in receipt["error"] or "git status --porcelain failed" in receipt["error"]
    assert "NOT_IMPLEMENTED" not in result.stdout
    assert not (root / ".run" / "lock").exists()  # lock released


def test_cli_respects_kill_switch(tmp_path, facts_file, git_repo):
    _add_verifier_context(git_repo)
    config = _config(tmp_path, facts_file, git_repo, creds=True, worktree=True)
    cfg_file = tmp_path / "engine.yaml"
    cfg_file.write_text(yaml.safe_dump(config))
    env_root = tmp_path / "engine-root"
    env_root.mkdir(exist_ok=True)
    (env_root / "DISABLED").write_text("halt\n")
    result = subprocess.run(
        ["python3", "-m", "fmd_seo", "--config", str(cfg_file), "reverify"],
        capture_output=True, text=True, timeout=60,
        env={"PYTHONPATH": str(ENGINE_ROOT / "src"), "FMD_SEO_ROOT": str(env_root), "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 4
    receipt = json.loads(result.stdout)
    assert any("Kill switch" in b for b in receipt["blockers"])
