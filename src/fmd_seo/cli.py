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

EXIT = {"DONE": 0, "NO_OP": 0, "PARTIAL": 3, "BLOCK": 4, "ERROR": 5}


def _not_implemented(command: str, detail: str):
    rb = ReceiptBuilder(command)
    rb.check("implemented", "BLOCK", f"NOT_IMPLEMENTED: {detail}")
    return rb.finish("BLOCK")


def _emit(receipt, receipts_dir: Path) -> int:
    path = write_receipt(receipt, receipts_dir)
    print(json.dumps(receipt.to_dict(), indent=2))
    print(f"receipt: {path}", file=sys.stderr)
    return EXIT[receipt.status]


def _emit_loop(rb: ReceiptBuilder, payload: dict, code: int, receipts_dir: Path) -> int:
    if code == EXIT["PARTIAL"]:
        status, verdict = "PARTIAL", "WARN"
    elif code == EXIT["ERROR"]:
        status, verdict = "ERROR", "BLOCK"
    elif code == EXIT["BLOCK"]:
        status, verdict = "BLOCK", "BLOCK"
    elif (
        (payload.get("command") == "sync" and payload.get("skipped_no_key")
         and not payload.get("fetched"))
        or (payload.get("command") == "gsc-sync" and payload.get("fetched") is False)
    ):
        status, verdict = "NO_OP", "WARN"
    else:
        status, verdict = "DONE", "PASS"
    for item in payload.get("checks") or []:
        if isinstance(item, dict):
            name = str(item.get("name", "check"))
            check_verdict = str(item.get("verdict", "WARN"))
            check_detail = str(item.get("detail", ""))
        else:
            name, check_verdict, check_detail = (str(value) for value in item)
        rb.check(name, check_verdict, check_detail)
    for blocker in payload.get("blockers") or []:
        blocker_text = str(blocker)
        if blocker_text not in rb.blockers:
            rb.blockers.append(blocker_text)
    commit_hashes = payload.get("commit_hashes") or {}
    if isinstance(commit_hashes, dict):
        rb.commit_hashes.update({str(key): str(value) for key, value in commit_hashes.items()})
    if payload.get("branch"):
        rb.resume_point = f"site branch {payload['branch']}"
    detail = payload.get("error") or payload.get("stderr") or f"exit {code}"
    rb.check("command_result", verdict, str(detail))
    receipt = rb.finish(status)
    path = write_receipt(receipt, receipts_dir)
    print(json.dumps(payload, indent=2))
    print(f"receipt: {path}", file=sys.stderr)
    return code


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

    p = sub.add_parser("act", help="plan or publish a verified site change")
    p.add_argument("--package", type=Path, default=None, help="immutable PagePackage to publish")
    p.add_argument("--dry-run", action="store_true", help="print planned diff without touching git")

    p = sub.add_parser("report", help="read-only outcome deltas from observation history")
    p.add_argument("--since", required=True, help="ISO date or timestamp")

    p = sub.add_parser("gbp-draft", help="generate fact-bound GBP and review-request drafts")
    p.add_argument("--output", type=Path, default=None, help="draft directory")

    p = sub.add_parser("spike", help="Phase 2 rendering spike against the site worktree")
    p.add_argument("--port", type=int, default=4173)
    p.add_argument("--skip-build", action="store_true")

    # ── Autonomous-loop surface: the engine as decision brain ──
    sub.add_parser("beat", help="what checks are due now, ordered, with fulfillment paths")
    sub.add_parser("assess", help="evaluate thresholds against latest observations; report gate drift")
    sub.add_parser("brief", help="full operator briefing: gates + due + standing findings + priority")
    sub.add_parser("sync", help="headless Semrush fetch of API-backed due checks (cron path)")
    sub.add_parser("tick", help="record credential-free engine freshness checks")
    sub.add_parser("gsc-sync", help="headless index-coverage fetch via the GSC URL Inspection API")

    p = sub.add_parser("site-reset", help="report or repair the isolated site worktree")
    p.add_argument("--force", action="store_true", help="hard-sync the worktree to origin/main")

    p = sub.add_parser("facts-check", help="compare canonical facts with the generated site payload")
    p.add_argument("--generated", type=Path, default=None, help="business-facts.ts path")

    p = sub.add_parser("serp-bulk", help="capped resumable position-tracking queue")
    serp_mode = p.add_mutually_exclusive_group(required=True)
    serp_mode.add_argument("--dry-run", action="store_true", help="estimate only; post zero tasks")
    serp_mode.add_argument("--post", action="store_true", help="post missing tasks to the standard queue")
    serp_mode.add_argument("--collect", action="store_true", help="collect posted tasks and record results")

    p = sub.add_parser("geogrid", help="capped resumable map-pack grid queue")
    grid_mode = p.add_mutually_exclusive_group(required=True)
    grid_mode.add_argument("--dry-run", action="store_true", help="estimate only; post zero tasks")
    grid_mode.add_argument("--post", action="store_true", help="post missing grid tasks")
    grid_mode.add_argument("--collect", action="store_true", help="collect grid tasks and record map-pack results")

    p = sub.add_parser("observe", help="record one measured check observation")
    p.add_argument("check_id")
    p.add_argument("--records", required=True, help="JSON object of the check's declared fields")
    p.add_argument("--fulfillment", required=True,
                   choices=["engine_api", "mcp", "agent", "console", "engine"],
                   help="how the data was obtained")
    p.add_argument("--source", required=True, help="evidence file, API endpoint, or console name")
    p.add_argument("--note", default="", help="optional provenance note")

    args = parser.parse_args(argv)
    config = paths.load_config(args.config)
    receipts_dir = paths.RECEIPTS_DIR

    if args.command == "preflight":
        # Preflight reports the kill switch as a blocker instead of refusing to run.
        return _emit(run_preflight(config, online=args.online), receipts_dir)

    if args.command == "act" and args.dry_run:
        from .act import dry_run_plan
        rb = ReceiptBuilder(args.command)
        try:
            payload = dry_run_plan(
                Path(config["paths"]["site_worktree"]), args.package,
            )
            code = 0
        except Exception as err:  # noqa: BLE001 - malformed package/repo is a hard error
            payload = {"command": "act", "error": f"{type(err).__name__}: {err}"}
            code = EXIT["ERROR"]
        return _emit_loop(rb, payload, code, receipts_dir)

    if args.command == "report":
        from .report import build_report
        rb = ReceiptBuilder(args.command)
        try:
            payload = build_report(
                args.since,
                observations_dir=paths.ENGINE_ROOT / "brain" / "observations",
                interventions_path=paths.EVIDENCE_DIR / "interventions.jsonl",
            )
            code = 0
        except Exception as err:  # noqa: BLE001 - malformed history must fail loudly
            payload = {"command": "report", "error": f"{type(err).__name__}: {err}"}
            code = EXIT["ERROR"]
        return _emit_loop(rb, payload, code, receipts_dir)

    if args.command == "site-reset":
        # Destructive: --force discards uncommitted worktree edits. It must obey
        # the kill switch and hold the run lock, or it can reset the worktree out
        # from under an `act` that is mid-publish.
        from .site import reset_worktree
        rb = ReceiptBuilder(args.command)
        lock = None
        lock_acquired = False
        try:
            if args.force:
                killswitch.assert_not_engaged()
                paths.ensure_run_dirs()
                lock = RunLock(paths.LOCK_FILE)
                lock.acquire(rb.run_id)
                lock_acquired = True
            payload = reset_worktree(
                Path(config["paths"]["site_worktree"]), force=args.force,
            )
            code = 0
        except (LockHeld, killswitch.KillSwitchEngaged) as err:
            payload = {"command": args.command, "error": str(err)}
            code = EXIT["BLOCK"]
        except Exception as err:  # noqa: BLE001 - git failures are execution errors
            payload = {"command": args.command, "error": f"{type(err).__name__}: {err}"}
            code = EXIT["ERROR"]
        finally:
            if lock is not None and lock_acquired:
                lock.release()
        return _emit_loop(rb, payload, code, receipts_dir)

    if args.command == "facts-check":
        from .site_facts import verify_generated_fact_hash
        rb = ReceiptBuilder(args.command)
        generated = args.generated or (
            Path(config["paths"]["site_worktree"]) / "src/lib/business-facts.ts"
        )
        try:
            payload = verify_generated_fact_hash(
                Path(config["paths"]["facts_file"]), generated,
            )
            code = 0
        except Exception as err:  # noqa: BLE001 - drift must fail loudly in CI
            payload = {"command": args.command, "error": f"{type(err).__name__}: {err}"}
            code = EXIT["ERROR"]
        return _emit_loop(rb, payload, code, receipts_dir)

    if args.command == "serp-bulk":
        from . import serp_bulk
        rb = ReceiptBuilder(args.command)
        lock = None
        lock_acquired = False
        try:
            if args.dry_run:
                payload = serp_bulk.dry_run(config)
                code = 0 if payload["within_cap"] else EXIT["BLOCK"]
            else:
                killswitch.assert_not_engaged()
                paths.ensure_run_dirs()
                lock = RunLock(paths.LOCK_FILE)
                lock.acquire(rb.run_id)
                lock_acquired = True
                if args.post:
                    payload = serp_bulk.post_tasks(config)
                    code = 0
                else:
                    payload, rows = serp_bulk.collect_tasks(config)
                    if payload["pending"]:
                        code = EXIT["PARTIAL"]
                    else:
                        from .brain import load_brain
                        from .observations import record_observation
                        brain = load_brain()
                        path = record_observation(
                            brain,
                            "seo.positions",
                            payload["records"],
                            fulfillment="engine_api",
                            source=payload["results"],
                            note="DataForSEO standard queue, coordinate-anchored mobile depth 20",
                        )
                        payload["recorded"] = str(path.relative_to(paths.ENGINE_ROOT))
                        competitor_path = record_observation(
                            brain,
                            "competitor.serp_movement",
                            payload["competitor_records"],
                            fulfillment="engine_api",
                            source=payload["results"],
                            note="same coordinate-anchored mobile SERP dataset as seo.positions",
                        )
                        payload["competitor_recorded"] = str(
                            competitor_path.relative_to(paths.ENGINE_ROOT)
                        )
                        code = 0
        except (LockHeld, killswitch.KillSwitchEngaged) as err:
            payload, code = {"command": args.command, "error": str(err)}, EXIT["BLOCK"]
        except Exception as err:  # noqa: BLE001 - receipt distinguishes internal failure
            payload, code = {
                "command": args.command,
                "error": f"{type(err).__name__}: {err}",
            }, EXIT["ERROR"]
        finally:
            if lock is not None and lock_acquired:
                lock.release()
        return _emit_loop(rb, payload, code, receipts_dir)

    if args.command == "geogrid":
        from . import geogrid
        rb = ReceiptBuilder(args.command)
        lock = None
        lock_acquired = False
        try:
            if args.dry_run:
                payload = geogrid.dry_run(config)
                code = 0 if payload["within_cap"] else EXIT["BLOCK"]
            else:
                killswitch.assert_not_engaged()
                paths.ensure_run_dirs()
                lock = RunLock(paths.LOCK_FILE)
                lock.acquire(rb.run_id)
                lock_acquired = True
                if args.post:
                    payload = geogrid.post_tasks(config)
                    code = 0
                else:
                    payload, _rows = geogrid.collect_tasks(config)
                    if payload["pending"]:
                        code = EXIT["PARTIAL"]
                    else:
                        from .brain import load_brain
                        from .observations import record_observation
                        brain = load_brain()
                        path = record_observation(
                            brain,
                            "seo.map_pack",
                            payload["records"],
                            fulfillment="engine_api",
                            source=payload["results"],
                            note="5x5 service-area mobile geogrid",
                        )
                        payload["recorded"] = str(path.relative_to(paths.ENGINE_ROOT))
                        code = 0
        except (LockHeld, killswitch.KillSwitchEngaged) as err:
            payload, code = {"command": args.command, "error": str(err)}, EXIT["BLOCK"]
        except Exception as err:  # noqa: BLE001
            payload, code = {
                "command": args.command,
                "error": f"{type(err).__name__}: {err}",
            }, EXIT["ERROR"]
        finally:
            if lock is not None and lock_acquired:
                lock.release()
        return _emit_loop(rb, payload, code, receipts_dir)

    # Read-only loop commands remain available under the kill switch so an
    # operator can inspect why the engine stopped. Observation-writing and
    # provider-sync commands are locked and respect DISABLED.
    if args.command in ("beat", "assess", "brief", "observe", "sync", "tick", "gsc-sync"):
        from . import loop_cli
        rb = ReceiptBuilder(args.command)
        mutating = args.command in ("observe", "sync", "tick", "gsc-sync")
        lock = None
        lock_acquired = False
        try:
            if mutating:
                killswitch.assert_not_engaged()
                paths.ensure_run_dirs()
                lock = RunLock(paths.LOCK_FILE)
                lock.acquire(rb.run_id)
                lock_acquired = True
            if args.command == "beat":
                payload, code = loop_cli.cmd_beat(config)
            elif args.command == "assess":
                payload, code = loop_cli.cmd_assess(config)
            elif args.command == "brief":
                payload, code = loop_cli.cmd_brief(config)
            elif args.command == "sync":
                payload, code = loop_cli.cmd_sync(config)
            elif args.command == "tick":
                payload, code = loop_cli.cmd_tick(config)
            elif args.command == "gsc-sync":
                payload, code = loop_cli.cmd_gsc_sync(config)
            else:
                payload, code = loop_cli.cmd_observe(
                    config, args.check_id, args.records,
                    fulfillment=args.fulfillment, source=args.source, note=args.note)
        except (LockHeld, killswitch.KillSwitchEngaged) as err:
            payload, code = {"command": args.command, "error": str(err)}, EXIT["BLOCK"]
        except Exception as err:  # noqa: BLE001 - internal failure is distinct from findings
            payload, code = {
                "command": args.command,
                "error": f"{type(err).__name__}: {err}",
            }, EXIT["ERROR"]
        finally:
            if lock is not None and lock_acquired:
                lock.release()
        return _emit_loop(rb, payload, code, receipts_dir)

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
        if args.command == "reverify":
            from .reverify import reverify_manifests
            from .site import SiteSyncError
            rb = ReceiptBuilder(args.command)
            try:
                payload = reverify_manifests(
                    paths.EVIDENCE_DIR / "exports",
                    Path(config["paths"]["site_worktree"]),
                )
                code = EXIT["BLOCK"] if payload["status"] == "BLOCK" else 0
                if code == 0:
                    from .reverify import record_reconciled_interventions
                    payload["interventions_recorded"] = record_reconciled_interventions(
                        payload,
                        Path(config["paths"]["site_worktree"]),
                        paths.EVIDENCE_DIR / "interventions.jsonl",
                    )
            except SiteSyncError as err:
                payload = {"command": "reverify", "status": "BLOCK", "error": str(err)}
                code = EXIT["BLOCK"]
            except Exception as err:  # noqa: BLE001 - malformed evidence is internal failure
                payload = {
                    "command": "reverify",
                    "status": "ERROR",
                    "error": f"{type(err).__name__}: {err}",
                }
                code = EXIT["ERROR"]
            return _emit_loop(rb, payload, code, receipts_dir)
        if args.command == "act":
            from .act import publish_package
            rb = ReceiptBuilder(args.command)
            if args.package is None:
                payload = {
                    "command": "act",
                    "status": "BLOCK",
                    "error": "--package is required unless --dry-run is used",
                }
                return _emit_loop(rb, payload, EXIT["BLOCK"], receipts_dir)
            try:
                payload = publish_package(config, args.package)
                code = 0 if payload["status"] == "DONE" else EXIT["BLOCK"]
            except Exception as err:  # noqa: BLE001
                payload = {"command": "act", "error": f"{type(err).__name__}: {err}"}
                code = EXIT["ERROR"]
            return _emit_loop(rb, payload, code, receipts_dir)
        if args.command == "gbp-draft":
            from .gbp import draft_gbp_assets
            rb = ReceiptBuilder(args.command)
            try:
                output = args.output or (paths.ENGINE_ROOT / "drafts" / "gbp")
                payload = draft_gbp_assets(
                    Path(config["paths"]["facts_file"]), output,
                )
                code = 0 if payload["status"] == "DONE" else EXIT["BLOCK"]
            except Exception as err:  # noqa: BLE001
                payload = {"command": "gbp-draft", "error": f"{type(err).__name__}: {err}"}
                code = EXIT["ERROR"]
            return _emit_loop(rb, payload, code, receipts_dir)
        if args.command == "spike":
            from .spike import run_spike, write_memo
            worktree = Path(config["paths"]["site_worktree"])
            receipt = run_spike(worktree, port=args.port, skip_build=args.skip_build)
            write_memo(receipt, paths.EVIDENCE_DIR / "m1-rendering-decision.md")
            return _emit(receipt, receipts_dir)
        detail = {
            "intelligence": "Phase 4 delivers DataForSEO fetchers",
            "page": "Phase 3 delivers the vertical-slice builder",
            "verify": "Phase 3 delivers deterministic + semantic verification",
            "export": "Phase 2/3 deliver the site-worktree exporter",
            "run": "Phase 5 delivers the coordinator",
        }[args.command]
        return _emit(_not_implemented(args.command, detail), receipts_dir)


if __name__ == "__main__":
    raise SystemExit(main())
