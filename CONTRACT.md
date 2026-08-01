# Implementation Contract — FMD SEO Engine V1

File-backed contract for all work in this repo. Source plan:
`~/.claude/plans/2026-07-14-standalone-fmd-seo-engine-implementation-plan.md`.

## Authority boundaries

1. Fresh-owned documents (business-facts.yaml and its source docs) are the
   sole mutable business-fact and voice authority. The engine reads, hashes,
   and extracts — it never edits them.
2. `fresh-mobile-detailing` is the rendering/deployment target. The engine
   writes only to an isolated worktree (`.worktrees/fresh-site`), never the
   live checkout.
3. `operator-agent` is unchanged. Access is via a read-only adapter that
   records start/end Git SHA + status and fails if either changes.
4. ZEIROS is read-only strategic evidence, not a runtime dependency. The
   engine writes no ZEIROS artifacts.
5. Hermes is authorized for one thing only: a one-line, outbound run
   notification to Lou's own Telegram (`bin/notify-run`, via `hermes send`).
   Read-only, no LLM, no agent loop, no inbound command path. Agentic Hermes
   integration stays deferred until supervised runs prove reliability.
   (Authorized 2026-07-15, superseding the blanket deferral.)
6. Local checkpoint commits are authorized on isolated branches only.
   No push, no deployment, no account mutation, and no external contact —
   where external contact means the business's audience, customers, or
   accounts. Telling the operator his own job finished is telemetry, not
   contact, and is bounded by clause 5.
7. No publish command in V1. Posting is `human_only` per business-facts;
   deploy intents are emitted disabled.

## Failure controls

- Limits: 2 attempts per milestone, 45 min per worker, 8 h controller wall,
  $10 DataForSEO ceiling with per-endpoint sub-caps.
- Cost is reserved before every API call and settled after; balance is
  reconciled before/after runs.
- Two systemic auth/transport failures trip the kill switch (`DISABLED`).
- No-progress detection: hash of diff + failing-check signature; identical
  second failure halts that branch.
- Missing/stale facts block only dependent pages. Unsupported equipment,
  guarantee, review, scarcity, geography, or contact claims fail closed.
- An unavailable semantic checker produces BLOCK_SEMANTIC_UNAVAILABLE,
  never a degraded pass.
- Source text (API payloads, scraped content) is untrusted data, wrapped as
  data-not-instruction.

## State rules

- Raw API payloads and controller state live under ignored `.run/`.
- Committed: normalized evidence, hashes, timestamps, final packages,
  fixtures, receipts, baselines, export manifests.
- PagePackage IDs are immutable and content-addressed; rewriting an existing
  package with different content is a hard error.
- Every command ends with a RunReceipt: DONE | NO_OP | PARTIAL | BLOCK.

## Acceptance (V1)

One real article through the full production path; one verifier-passed
money-page prototype; ten query/SERP briefs with honestly labeled AI
evidence; verified image provenance/alt text; entity + outreach artifacts;
demonstrated failure modes; clean accounted-for local commits; status
`READY FOR LOU — LOCALLY VERIFIED, NOT LIVE`.
