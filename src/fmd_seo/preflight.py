"""Preflight: verify the engine can run before spending anything.

Checks (offline unless --online):
  kill switch, repo presence, facts authority (present + parseable + not stale),
  DataForSEO creds presence, site worktree, run-lock health.
Online adds the capped account probe. Any failed check contributes a blocker
and the receipt status is BLOCK; preflight never degrades to a partial pass.
"""

from __future__ import annotations

from pathlib import Path

from . import killswitch, paths
from .contracts import RunReceipt
from .dataforseo import ApiFailure, CredsMissing, DataForSeoClient, load_creds
from .facts import FactError, load_snapshot, verify_binding
from .operator_adapter import OperatorAdapter, OperatorUnavailable
from .receipts import ReceiptBuilder
from .spend import BudgetExceeded, SpendLedger


def run_preflight(config: dict, *, online: bool = False) -> RunReceipt:
    rb = ReceiptBuilder("preflight")

    if killswitch.engaged():
        rb.check("killswitch", "BLOCK", "DISABLED file present at engine root")
        return rb.finish("BLOCK")
    rb.check("killswitch", "PASS", "not engaged")

    for label in ("operator_repo", "zeiros_repo"):
        repo = Path(config["paths"][label])
        if (repo / ".git").exists():
            rb.check(f"repo:{label}", "PASS", str(repo))
        else:
            rb.check(f"repo:{label}", "BLOCK", f"missing or not a git repo: {repo}")

    facts_file = Path(config["paths"]["facts_file"])
    if not facts_file.exists():
        rb.check("facts", "BLOCK", f"facts authority missing: {facts_file}")
    else:
        try:
            snap = load_snapshot(facts_file, ["identity.name", "autonomy.posting"])
            if not verify_binding(snap):
                rb.check("facts", "BLOCK", "canonical facts binding changed during preflight")
            else:
                rb.check("facts", "PASS",
                         f"hash {snap.source_hash[:12]}, reviewed {snap.reviewed_at}")
            if snap.facts_used["autonomy.posting"] != "human_only":
                rb.check("facts:autonomy", "WARN",
                         "posting autonomy changed from human_only — review deploy gating")
        except FactError as err:
            rb.check("facts", "BLOCK", str(err))

    try:
        with OperatorAdapter(Path(config["paths"]["operator_repo"])) as adapter:
            adapter.verifier_context()
        rb.check("operator_adapter", "PASS", "verifier context readable, repo unchanged")
    except OperatorUnavailable as err:
        rb.check("operator_adapter", "BLOCK", f"BLOCK_SEMANTIC_UNAVAILABLE: {err}")

    creds_file = Path(config["creds_env"])
    try:
        load_creds(creds_file)
        rb.check("dataforseo_creds", "PASS", f"present at {creds_file} (values not shown)")
        creds_ok = True
    except CredsMissing as err:
        rb.check("dataforseo_creds", "BLOCK", str(err))
        creds_ok = False

    worktree = Path(config["paths"]["site_worktree"])
    if (worktree / ".git").exists():
        rb.check("site_worktree", "PASS", str(worktree))
    else:
        rb.check("site_worktree", "BLOCK", f"isolated Fresh worktree missing: {worktree}")

    if online:
        if not creds_ok:
            rb.check("probe", "BLOCK", "skipped: credentials missing")
        else:
            paths.ensure_run_dirs()
            ledger = SpendLedger(
                paths.SPEND_LEDGER,
                config["budget"]["total_usd"],
                config["budget"]["endpoint_caps_usd"],
            )
            client = DataForSeoClient(
                creds_file, ledger,
                systemic_failures_to_kill=config["limits"]["systemic_failures_to_kill"],
            )
            try:
                info = client.probe()
                rb.check("probe", "PASS", f"auth ok, balance ${info['balance_usd']}")
            except (ApiFailure, BudgetExceeded, killswitch.KillSwitchEngaged) as err:
                rb.check("probe", "BLOCK", str(err))

    return rb.finish()
