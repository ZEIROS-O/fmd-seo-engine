"""fmd-seo CLI.

Phase 1 implements `preflight` fully. The remaining surfaces exist and emit
honest BLOCK receipts (NOT_IMPLEMENTED) so callers and tests can rely on the
receipt contract from day one. There is deliberately no `publish` command:
business-facts.yaml defines posting as human_only, so V1 only ever emits a
disabled deploy intent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import killswitch, paths
from .preflight import run_preflight
from .receipts import ReceiptBuilder, write_receipt
from .runstate import LockHeld, RunLock

EXIT = {"DONE": 0, "NO_OP": 0, "PARTIAL": 3, "BLOCK": 4}


def _not_implemented(command: str, detail: str):
    rb = ReceiptBuilder(command)
    rb.check("implemented", "BLOCK", f"NOT_IMPLEMENTED: {detail}")
    return rb.finish("BLOCK")


def _emit(receipt, receipts_dir: Path) -> int:
    path = write_receipt(receipt, receipts_dir)
    print(json.dumps(receipt.to_dict(), indent=2))
    print(f"receipt: {path}", file=sys.stderr)
    return EXIT[receipt.status]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="fmd-seo")
    parser.add_argument("--config", type=Path, default=None, help="engine config yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("preflight", help="verify the engine can run")
    p.add_argument("--online", action="store_true", help="include capped DataForSEO probe")

    p = sub.add_parser("intelligence", help="SEO intelligence operations")
    isub = p.add_subparsers(dest="intel_command", required=True)
    pf = isub.add_parser("fetch")
    pf.add_argument("--query-set", required=True)
    pf.add_argument("--budget-usd", type=float, required=True)

    p = sub.add_parser("page", help="page package operations")
    psub = p.add_subparsers(dest="page_command", required=True)
    pb = psub.add_parser("build")
    pb.add_argument("--intent-key", required=True)
    pb.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("verify", help="verify a page package")
    p.add_argument("package", type=Path)

    p = sub.add_parser("export", help="export a package to the site worktree")
    p.add_argument("package", type=Path)
    p.add_argument("--site-worktree", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")

    p = sub.add_parser("run", help="coordinated end-to-end run")
    p.add_argument("--limit", type=int, default=1)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--offline", action="store_true")
    mode.add_argument("--online", action="store_true")

    sub.add_parser("reverify", help="re-run verification over existing packages")

    args = parser.parse_args(argv)
    config = paths.load_config(args.config)
    receipts_dir = paths.RECEIPTS_DIR

    if args.command == "preflight":
        # Preflight reports the kill switch as a blocker instead of refusing to run.
        return _emit(run_preflight(config, online=args.online), receipts_dir)

    try:
        killswitch.assert_not_engaged()
    except killswitch.KillSwitchEngaged as err:
        rb = ReceiptBuilder(args.command)
        rb.check("killswitch", "BLOCK", str(err))
        return _emit(rb.finish("BLOCK"), receipts_dir)

    paths.ensure_run_dirs()
    lock = RunLock(paths.LOCK_FILE)
    rb_probe = ReceiptBuilder(args.command)  # for run_id only
    try:
        lock.acquire(rb_probe.run_id)
    except LockHeld as err:
        rb = ReceiptBuilder(args.command)
        rb.check("run_lock", "BLOCK", str(err))
        return _emit(rb.finish("BLOCK"), receipts_dir)

    with lock:
        detail = {
            "intelligence": "Phase 4 delivers DataForSEO fetchers",
            "page": "Phase 3 delivers the vertical-slice builder",
            "verify": "Phase 3 delivers deterministic + semantic verification",
            "export": "Phase 2/3 deliver the site-worktree exporter",
            "run": "Phase 5 delivers the coordinator",
            "reverify": "Phase 5 delivers reverify",
        }[args.command]
        return _emit(_not_implemented(args.command, detail), receipts_dir)


if __name__ == "__main__":
    raise SystemExit(main())
