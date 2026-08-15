# Implementation Contract — FMD SEO Engine V1/V2 artifacts

File-backed contract for all work in this repo. Source plan:
`~/.claude/plans/2026-07-14-standalone-fmd-seo-engine-implementation-plan.md`.

## Authority boundaries

1. Fresh-owned documents (business-facts.yaml and its source docs) are the
   sole mutable business-fact and voice authority. The engine reads, hashes,
   and extracts — it never edits them.
   The configured local `business-facts.yaml` is the one canonical copy. CI,
   scheduler configuration, secrets, and generated site files must never carry
   a second mutable copy; generated projections remain hash-bound derivatives.
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
6. Local checkpoint commits are authorized on isolated branches only. The
   scheduler runs only from its dedicated linked worktree on
   `automation/fmd-seo-state`, starts clean, stages the exact machine-owned
   paths produced by that run, and never pulls or pushes. No push, no
   deployment, no account mutation, and no external contact —
   where external contact means the business's audience, customers, or
   accounts. Telling the operator his own job finished is telemetry, not
   contact, and is bounded by clause 5.
7. No publish command in V1. Posting is `human_only` per business-facts;
   deploy intents are emitted disabled.
8. PatchPackage may bypass GATE-1 only because it permits `modify` operations
   on existing tracked files and rejects URL additions. GATE-3, GATE-4, human
   merge, deployment, and post-deploy verification still apply.
9. `act` may push an isolated branch and open a draft PR. It cannot merge,
   deploy, mutate a console, edit a third-party entity, contact a customer, or
   publish a post.

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

- Raw API payloads, locks, and per-run scratch state live under ignored `.run/`.
- Spend, provider-health counters, and resumable task manifests live under
  committed `state/` so cloud runs cannot silently reset their safety state.
- Committed: normalized evidence, hashes, timestamps, final packages,
  fixtures, receipts, baselines, export manifests.
- PagePackage IDs are immutable and content-addressed; rewriting an existing
  package with different content is a hard error.
- Artifact versions are independent: Observation v2, PagePackage v2, and
  PatchPackage v1. Historical v1 artifacts remain readable and immutable; new
  PagePackages must be v2 and declare evidence-backed information gain.
- Observation v2 accepts `null` only for a declared nullable field. A threshold
  using it must also use a declared boolean measurability guard.
- `brain/instruments.yaml` is the instrument authority. Active checks cannot
  cite retired instruments; retirement preserves the evidence, date, and reason.
- PatchPackages record exact site base, fact hash, evidence refs, tracked path,
  before/after hashes, and replacement content. Stale inputs or a new URL block.
- Every command ends with a RunReceipt: DONE | NO_OP | PARTIAL | BLOCK | ERROR.
- **Any function that writes committed evidence or observations must take the
  output directory as a parameter, and every test must pass a temp path.** A
  module that defaults straight to `paths.EVIDENCE_DIR` can be invoked by its
  own test suite and overwrite a real measurement with fixture output. See
  `docs/incidents/2026-08-03-fixture-overwrote-evidence.md`.

## Acceptance (V1)

One real article through the full production path; one verifier-passed
money-page prototype; ten query/SERP briefs with honestly labeled AI
evidence; verified image provenance/alt text; entity + outreach artifacts;
demonstrated failure modes; clean accounted-for local commits; status
`READY FOR LOU — LOCALLY VERIFIED, NOT LIVE`.

## Authority and ethical perimeter

Answer-engine citation sources are measured separately from generic backlink
authority. Citation and local-corroboration queues are research/draft surfaces
only: no cold outreach, automated submission, purchased links, fabricated
endorsements, invented listings, or fake corroboration. Review-floor values
must be verified against listing evidence; an answer-engine assertion is never
promoted to a business fact.
