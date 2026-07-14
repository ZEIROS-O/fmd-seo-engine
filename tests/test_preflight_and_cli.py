import json
import subprocess
from pathlib import Path

import pytest
import yaml

from fmd_seo.preflight import run_preflight

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


def _run_cli(tmp_path, config, *args):
    cfg_file = tmp_path / "engine.yaml"
    cfg_file.write_text(yaml.safe_dump(config))
    env_root = tmp_path / "engine-root"
    env_root.mkdir(exist_ok=True)
    result = subprocess.run(
        ["python3", "-m", "fmd_seo", "--config", str(cfg_file), *args],
        capture_output=True, text=True, timeout=60,
        env={"PYTHONPATH": str(ENGINE_ROOT / "src"), "FMD_SEO_ROOT": str(env_root), "PATH": "/usr/bin:/bin"},
    )
    return result, env_root


def test_cli_preflight_emits_receipt(tmp_path, facts_file, git_repo):
    _add_verifier_context(git_repo)
    result, root = _run_cli(tmp_path, _config(tmp_path, facts_file, git_repo), "preflight")
    assert result.returncode == 4  # BLOCK: no creds/worktree in this config
    receipt = json.loads(result.stdout)
    assert receipt["command"] == "preflight" and receipt["status"] == "BLOCK"
    assert list((root / "receipts").glob("*.json"))


def test_cli_stub_commands_block_honestly(tmp_path, facts_file, git_repo):
    _add_verifier_context(git_repo)
    config = _config(tmp_path, facts_file, git_repo, creds=True, worktree=True)
    result, root = _run_cli(tmp_path, config, "reverify")
    assert result.returncode == 4
    receipt = json.loads(result.stdout)
    assert receipt["status"] == "BLOCK"
    assert any("NOT_IMPLEMENTED" in b for b in receipt["blockers"])
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
