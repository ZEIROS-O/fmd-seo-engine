# Master SEO loop operator runbook

## Daily scheduled run

1. Honor committed `DISABLED` and `state/source-switches.yaml`.
2. Validate DataForSEO, Semrush, Google service account, canonical facts, and
   site token independently. A required missing capability leaves the run red.
3. Run credential-free watchdogs, then each enabled provider independently.
   GSC URL Inspection and query/page footprint run before site checkout.
4. Assess, audit, plan actions, and persist committed state
   and receipts, then send measured Telegram fields. Persistence precedes the
   final red/green conclusion.
5. A green step is not release proof. Inspect observation files, spend ledger,
   receipt, workflow URL, and checks still due.

## Recovery

- Missing site checkout is a structured `BLOCK`; run `fmd-seo site-init` and
  inspect `state/site-worktree.json`.
- Provider failure affects only its source. Disable a source explicitly in the
  committed switch file if intentionally paused; never manufacture an observation.
- A failed persistence rebase pushes `state-recovery/<run-id>`; reconcile that
  branch before the next run so spend and provider health are not lost.
- Retire a bad instrument in `brain/instruments.yaml`, preserve its artifacts,
  replace the active check, and document the rationale. Do not rewrite history.

## Paid work

Run the dry-run/plan surface first. It must show exact calls, projected spend,
endpoint cap, and remaining lifetime budget. No cap is raised by the engine.
AEO scheduling stays off until Lou approves the measured canary's recurring cost.

## Site action

PatchPackage can modify existing tracked files only. `act` checks the site base,
facts hash, before hash, URL inventory, build/tests, and raw HTML; it may push and
open a draft PR, but never merge or deploy. Lou reviews/merges/deploys, then live
raw headers/HTML must match the package receipt.

## Weekly review

Review GSC near-winners, review velocity/floor, AEO accuracy/share/citations,
SERP consensus, CI heartbeat, war-room blockers/scores, draft authority queues,
and the seasonal calendar. Every strategic priority must resolve to a generator,
console task, draft queue, or explicit blocker and owner.
