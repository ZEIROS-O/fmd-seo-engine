# SEO Engine Hardening — S0/S1/S2 Design

**Date:** 2026-08-11
**Source doctrine:** `/mnt/c/Users/lucas/Downloads/AI_Search_SEO_Master_Operating_System_2026.md`
**Status:** design, awaiting review

---

## Why this exists

Lou asked to harden the engine's mechanics against the AI Search + SEO Master
Operating System (2026) doc. Auditing the engine against that doc surfaced six
gaps. Auditing the engine against *itself* surfaced something more urgent: the
autonomous loop has never run.

```
gh api repos/ZEIROS-O/fmd-seo-engine/actions/secrets → {"total_count":0}
daily optimizer: 10 runs, 10 failures, 0 successes
git log --author=github-actions → 0 commits
PYTHONPATH=src python3 -m fmd_seo beat → 17 of 17 checks due
```

Every observation in `brain/observations/` came from a local session. The
headless path is unproven. That governs the sequencing below: the doc's own
failure mode #1 is building production capacity faster than the system can
absorb it, and adding checks to a registry that is 100% overdue is that failure
one level up.

### What the doc validates

The doc does not overturn the thesis. §22 (weak domain) puts technical + entity
foundation before content, and §25.1 names "content volume before authority" as
failure mode #1 — that is GATE-1, near verbatim. The doc's contribution is
naming what the brain is *missing*, not what it has wrong.

### Full gap map (S1–S6)

| ID | Gap | Doc refs | This spec |
|---|---|---|---|
| S0 | Loop never runs; priority order drifted | §15, §24, §25.2 | **in scope** |
| S1 | Priorities #1 and #2 have no check | §10.1–10.8 | **in scope** |
| S2 | GSC opportunity loop absent | §16.2–.6, §17, §23.1–.4 | **in scope** |
| S3 | AEO records too coarse to express the 2026-08-06 finding | §17 | deferred |
| S4 | Link intent + borrowed authority: zero coverage | §11, §12, §10.14 | deferred |
| S5 | Publish-time verifier gaps; no opportunity gate | §5, §6, §7.7–.8, §26 | deferred |
| S6 | No conversion measurement (`ga4-no-key-event`) | §10.20, §25.10 | deferred |

---

## S0 — Make the loop run

**Acceptance: one green scheduled or dispatched run that lands at least one new
observation and a `github-actions[bot]` state commit.** A passing test suite does
not close S0.

### S0.1 — Eliminate the priority-order drift class

`src/fmd_seo/planner.py:65` `GATE1_CLOSED_PRIORITY` is a hand-maintained copy of
the ordered list in `brain/thesis.md:255`. The thesis was reordered on 2026-08-03
(review velocity to #1, GBP configuration audit added at #2); the copy was not.
`beat` has been emitting the stale order since.

Do not repair the copy — remove it.

- New `brain/priorities.yaml`: ordered entries, each with `id`, `label`,
  `thesis_refs`, and the gate state it applies under (`GATE-1: CLOSED` / `OPEN`).
- `planner.build_plan` reads it; `GATE1_CLOSED_PRIORITY` and
  `GATE1_OPEN_PRIORITY` are deleted.
- `brain/thesis.md:255` keeps the *reasoning* and points at `brain/priorities.yaml`
  as the machine copy, matching how `state.yaml` already wins over prose.

Test: `beat`'s `priority_order` equals `brain/priorities.yaml` for the current
gate state, and a planner test asserts no ordering literal survives in the module.

### S0.2 — Credential materialization must fail on absent input

`.github/workflows/daily.yml` → `Materialize provider credentials` runs `printf`
with empty secret values and exits 0, writing empty credential files that read as
provisioned. This is doc §24 precisely: *"the most dangerous failures are not
crashes; they are plausible outputs that look finished."*

Assert each of `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`, `SEMRUSH_API_KEY`,
`GSC_SERVICE_ACCOUNT_JSON`, `BUSINESS_FACTS_YAML` is non-empty before writing.
Name the missing secret in the error. No `continue-on-error` on this step.

### S0.3 — Stop the green-wash

`Validate required provider credentials` carries `continue-on-error: true`, so the
run UI renders ✓ (conclusion) while `steps.providers.outcome` is `failure`. Every
fetch step (`sync`, `gsc-sync`, `serp-bulk`, `geogrid`) is gated on that outcome,
so all four skip. The net effect is a run that fetched nothing displaying as a
column of checkmarks.

Keep the attempt-all-then-fail pattern — it is correct, and it is what lets the
Telegram notification carry true outcomes. Change only the final gate: replace the
sequence of `test` calls (which aborts at the first failure, hiding the rest) with
a printed table of every stage's outcome followed by a non-zero exit. A reader
must be able to see which stages failed from the summary alone.

### S0.4 — Restore the checks a worktree failure currently deletes

- `Verify canonical facts` gains `always()`. It depends on the facts secret, not
  the site worktree, but today an unrelated worktree failure skips it — the GATE-3
  fact check silently vanishes.
- `Checkout site worktree` gains `continue-on-error: true`. It currently exits 128
  (empty `SITE_REPO_TOKEN`) and takes the run with it. No daily step writes to the
  site — `act` runs `--dry-run` — so the worktree is not required for the loop to
  produce observations.

### S0.5 — Unfork the source of truth

The workflow expects `BUSINESS_FACTS_YAML` as a secret. That is a second copy of
the OneDrive canonical file, and it will drift from it silently while GATE-3 binds
generated artifacts to its hash. T6 makes this expensive rather than untidy:
published prices are read verbatim into ChatGPT answers that route booking
traffic, so a stale fact propagates into the acquisition path.

- New committed `brain/facts-fingerprint.json`: `{sha256, reviewed_at,
  recorded_at, recorded_from}`.
- New `fmd-seo facts-fingerprint` command, local-only, records the fingerprint
  from the real OneDrive file. It never writes the facts file (CONTRACT §1).
- `facts-check` and `preflight` compare the loaded facts file's hash against the
  fingerprint. Mismatch → BLOCK, with "canonical facts changed since fingerprint;
  re-record from a local session." Never a degraded pass.

This converts silent divergence into a loud stop without moving authority into the
repo.

### S0.6 — Reconcile the working tree before proving CI

74 uncommitted files, including modified `src/fmd_seo/*.py` and `daily.yml`. CI
runs `origin/main`, which has none of them. Proving the loop against current
`main` proves a different engine than the one in the working tree.

The tree must be reconciled — committed, stashed, or explicitly discarded — before
S0.8. Which of those applies is Lou's call, not the plan's; the plan surfaces the
diff and asks. It must not commit 74 files on his behalf.

### S0.7 — Secrets runbook

`docs/runbooks/ci-secrets.md`: one `gh secret set` invocation per secret, each with
its value source (`~/.dataforseo.env`, `~/.gsc-service-account.json`, the OneDrive
`business-facts.yaml`, a freshly minted `SITE_REPO_TOKEN`, Telegram bot/chat).
Lou runs it. No credential value is read, echoed, or transmitted by the engine or
by Claude during this step.

The nine referenced secrets: `DATAFORSEO_LOGIN`, `DATAFORSEO_PASSWORD`,
`SEMRUSH_API_KEY`, `GSC_SERVICE_ACCOUNT_JSON`, `BUSINESS_FACTS_YAML`,
`SITE_REPO_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

### S0.8 — Prove it

Dispatch the workflow. Confirm: providers validate, `sync` and `gsc-sync` land
observations, the bot commits state, and `seo.indexation` carries a reading newer
than 2026-07-14. Record the result — a real `seo.indexation` reading may move
GATE-1's counters, which is a thesis-level event and must be surfaced, not
absorbed.

---

## Sequencing

S0 is a **blocking milestone**. S1 and S2 add seven observation streams whose only
value is that the loop fetches them on cadence; building them against an unproven
headless path repeats the failure this spec exists to fix. The implementation plan
must not start S1 or S2 work until S0.8 has produced a `github-actions[bot]` state
commit.

S1 and S2 are independent of each other and may proceed in either order once S0
closes.

---

## S1 — Measure priorities #1 and #2

The thesis names review velocity #1 and GBP configuration audit #2. Neither has a
check. `baseline.reviews.google_reviews: 16` came from a Local Finder side-effect,
not a tracked stream. The engine cannot tell whether its own top lever is moving.

**The fetcher already exists.** `evidence.py:190` `fetch_gbp` calls
`/v3/business_data/business_listings/search/live` and returns `title`, `category`,
`phone`, `address`, `rating`, `reviews` (votes_count), `url` at $0.03/call. It is
wired to nothing. This endpoint queries by title + coordinate — it needs neither
`gbp.location_id` (empty in config) nor the OAuth `business.manage` scope, so S1
does not block on Lou's GBP API setup.

### `gbp.reviews` — weekly, engine

Records: `review_count`, `rating`, `reviews_30d`, `reviews_60d`, `reviews_90d`.

Velocity is derived from the engine's own weekly `review_count` series, not a
reviews-endpoint pull — zero extra cost, and it needs no new endpoint. Until three
readings exist the velocity fields record `null`, which `assess` must treat as
"not yet measurable", never as zero (GATE-4).

Thresholds — these instrument the corroboration gate the thesis found on two
independent surfaces:

| expr | severity | basis |
|---|---|---|
| `review_count < 37` | high | measured local-pack floor, 2026-08-03 |
| `review_count < 65` | medium | measured AEO ranked-slot floor, 2026-08-06 |
| `reviews_30d == 0` | high | priority #1 is not moving |

This promotes the `aeo-review-floor` known issue from prose to a live threshold.

### `gbp.configuration` — monthly, engine

Records: `primary_category`, `categories_count`, `attributes_count`,
`services_listed`, `description_present`, `photos_count`, `photo_recency_days`,
`verified`, `service_area_configured`. Doc §10.1, §10.2, §10.6, §10.7, §10.8.

`business_listings/search/live` supplies title, category, phone, address. The
remaining fields need `business_data/google/my_business_info/live`. **The
implementation plan must verify that endpoint's response shape before committing
to these field names**; any field the endpoint cannot supply is dropped from
`records` rather than recorded as absent — a check must not encode a value it
cannot measure.

Closes `gbp-anchor-unconfirmed`, which determines the ring's centre and radius and
is priority #2 with no measurement today.

### `competitor.local_prominence` — monthly, engine

Records: `competitors_measured`, `median_review_count`, `pack_floor_reviews`,
`our_review_gap`. Same endpoint across `state.yaml → competitor_set` plus observed
pack holders. Doc §10.1, §10.3.

Makes the review floor **derived from measurement** rather than asserted from two
snapshots — so the review target in priority #1 stops being a remembered number.

### Budget

At the code's rate (`evidence.py:22`, `business_data: 0.03`): weekly FMD ≈
$0.13/mo; monthly 8-domain competitor sweep ≈ $0.24/mo. Total ≈ $0.37/mo.

Raise `config/engine.yaml → budget.endpoint_caps_usd.business_data` from `0.10` to
`0.50`. The $10 total ceiling is untouched.

Note a pre-existing inconsistency to correct while here: the engine.yaml comment
reads "~7 local-listing pulls" at a $0.10 cap, implying ~$0.014/call, while
`evidence.py:22` reserves $0.03. The code's rate is what the ledger enforces; the
comment is wrong.

---

## S2 — The GSC opportunity loop

`gsc.py` already holds a working service and the correct scope —
`webmasters.readonly` covers `searchanalytics.query`. Only URL Inspection is used
today. Adding Search Analytics unlocks doc §16.2–.6, §17 and §23.1–.4: the entire
established-domain reallocation playbook, on free data already authenticated,
where every resulting action edits an existing page. Zero new URLs, fully
GATE-1-compatible — this is the largest untapped GATE-1-BYPASS lever in the doc.

New `gsc.fetch_search_analytics(cfg, *, days, dimensions)` following the existing
fail-closed convention: `GscUnavailable` on any auth or API problem, never a
degraded reading.

| Check | Cadence | Records | Doc |
|---|---|---|---|
| `seo.striking_distance` | weekly | `queries_total`, `queries_pos_4_20`, `queries_pos_5_15`, `best_opportunity_position`, `impressions_in_band` | §16.5, §23.1 |
| `seo.ctr_gap` | weekly | `pages_measured`, `high_impression_low_ctr_count`, `worst_ctr_impressions` | §16.4, §23.2 |
| `seo.query_decay` | weekly | `pages_measured`, `pages_losing_impressions`, `largest_drop_pct` | §16.2, §23.3 |
| `seo.cannibalization` | weekly | `queries_with_multiple_pages`, `worst_query_page_count` | §16.3, §23.4 |

`seo.query_decay` compares the trailing 28 days against the preceding 28 and
records `null` for the delta fields until two windows exist.

`seo.cannibalization` measures the live corpus and complements — does not replace —
the existing `blog.cannibalization`, which is `per_draft`.

### Expect near-zero, and record it honestly

FMD has 4 ranked keywords, all branded, none on page 1, 9 clicks/28d. These checks
will most likely return values at or near zero.

**That is a finding, not a failure.** A measured "0 striking-distance queries
across N impressions" corroborates T7 and belongs in the observation record.
Thresholds are written so emptiness reads as signal rather than error, and each
check's `why` field says so explicitly, so a future reader does not mistake an
honest zero for a broken fetcher.

---

## Doctrine changes

**CONTRACT.md — State rules.** Add: *No check enters `brain/checks.yaml` without an
engine-side fetcher. The `session` and `human` fulfillment paths are grandfathered
for existing checks and are not options for new ones.* This is the single rule
that would have prevented the current staleness — the streams that went cold are
the ones nothing could fetch without a human.

**CONTRACT.md — Failure controls.** Add: *A CI step that provisions credentials or
writes state must fail on absent input. `continue-on-error` may defer a failure to
a later aggregation step; it must never convert a failure into a pass.*

**brain/thesis.md:255.** Reduce the priority list to reasoning plus a pointer to
`brain/priorities.yaml`.

**brain/checks.yaml header.** Document that `method.kind` values `http`, `mcp`,
`agent`, and `console` are grandfathered; new checks use `engine`.

---

## Out of scope, named for later cycles

- **S3 — AEO placement modeling.** `aeo.answer_accuracy` records
  citing/not-citing. The 2026-08-06 ChatGPT capture already broke that schema: FMD
  was cited with 6 facts and 0 wrong, and still lost — placed as an unranked
  conditional pick, with review counts cited for all three ranked competitors and
  none for FMD. Doc §17 wants recommendation order, competitors appearing, cited
  domains, source overlap. The check cannot express the finding the evidence
  already produced.
- **S4 — Link intent and borrowed authority.** Doc §11 orders opportunities by
  existing link intent; §10.14 gives the local flavor (news, chambers,
  associations, sponsorships); §12 covers borrowed-authority distribution. T7 says
  "not link volume," which is right — but this is local corroboration, which is
  what T7 names as the binding gap.
- **S5 — Verifier hardening and GATE-5.** Doc §7.8 and §26 add intent
  classification, answer-first block, heading structure, meta length, canonical,
  declared information-gain element, internal-link range, statistic traceability,
  and a §7.7 slop scan. Plus an opportunity gate: nothing stops the engine, the day
  GATE-1 opens, from publishing a page that fails §6's consensus + information-gain
  test.
- **S6 — Conversion wiring.** `ga4-no-key-event` is a standing known issue with no
  check. In state.yaml's own words, without a booking key event the AEO channel
  "cannot be optimised, only observed." Doc §25.10.

---

## Risks

- **S0.8 may move GATE-1.** The first real `seo.indexation` reading in 28 days
  could change the gate's counters in either direction. That is a thesis-level
  event; it must be surfaced explicitly, not absorbed into a routine run.
- **`my_business_info` response shape is unverified.** S1's `gbp.configuration`
  field list is provisional until the plan confirms it. Fields the endpoint cannot
  supply get dropped, not defaulted.
- **S2 may measure nothing for months.** Accepted, and handled by writing the
  thresholds so zero is a signal. The cost is four weekly checks against a free
  API.
- **New checks raise `engine.freshness` exposure.** Seven new streams mean seven
  more that can go overdue and trip the watchdog critical. Mitigated by the
  headless-first rule — every check added here has an engine fetcher — but the
  rule only holds if S0.8 actually passes.
