# Repository review against the Master Search Visibility Operating System

**Date:** 2026-08-12
**Reference:** `SEO Master Doc.md` (2,451 lines, 2026-08-12 revision)
**Subject:** `~/fmd-seo-engine` @ `258f9ef` — 8,164 LOC, 47 modules, 23 checks, 248 tests

---

## Verdict

This repo is the strongest implementation of the Master Doc's *hardest* ideas that
I have seen — the ones almost everyone skips. §VII's "hard pass/fail verification
rules the model cannot rationalize its way around" is GATE-3/GATE-4. §XX's
"automation success messages are not verification" is the receipt-and-provenance
layer. §XVIII's context/memory layer is `brain/`. The thesis file does something
the Master Doc only gestures at: it records *retractions* with the measurement
that forced them (T7's Semrush artifact, T5's geogrid artifact). That is a
search-learning machine's most important organ and it is already built.

And it is not running.

Of 23 registered checks, **7 have never been observed**. Of the 16 that have,
**12 hold exactly one observation**, most dated 2026-07-14. The newest reading in
the entire system is 29 days old except for one manual `gsc-sync` on 2026-08-11.
`fmd-seo brief` reports **17 checks due right now**. The daily CI job has failed
**every scheduled run since it was created** — six consecutive failures visible in
`gh run list`, zero `github-actions` commits in the log, each run dying in 21–29
seconds. `fmd-seo act --dry-run` errors locally with `FileNotFoundError:
.worktrees/fresh-site-v3`.

The Master Doc's visibility model is multiplicative:

> Eligibility × Intent Fit × Entity Trust × Answer Quality × Information Gain ×
> Authority × Distribution × **Iteration Speed**
>
> "If any major term approaches zero, the campaign gets crippled."

Iteration speed is currently the zero term. Every other proposal in this review is
downstream of fixing that, and I have sequenced accordingly: **S0 restarts the
heartbeat, S1 closes the analysis gaps, S2 gives the engine hands, S3 extends
coverage.** Do not build S1 before S0 — a better analysis layer over a dead
measurement layer produces more confident staleness.

---

## 1. The dead loop, precisely

```
check                        cadence     obs  latest
schema.presence              daily         2  2026-07-15
schema.validate              weekly        1  2026-08-01
seo.indexation               weekly        2  2026-08-11
seo.organic_footprint        weekly        1  2026-07-14
seo.positions                weekly        1  2026-07-19
seo.map_pack                 weekly        1  2026-07-19
seo.local_visibility         weekly        0  — NEVER OBSERVED —
gbp.performance              weekly        0  — NEVER OBSERVED —
analytics.traffic            weekly        0  — NEVER OBSERVED —
seo.site_health              weekly        1  2026-07-14
seo.internal_links           weekly        0  — NEVER OBSERVED —
aeo.answer_accuracy          weekly        1  2026-07-14
aeo.share_of_voice           monthly       1  2026-07-19
aeo.entity_consistency       monthly       1  2026-07-21
competitor.authority_gap     weekly        1  2026-07-14
competitor.serp_movement     weekly        0  — NEVER OBSERVED —
market.demand                monthly       1  2026-07-14
facts.freshness              daily         1  2026-08-01
sync.health                  daily         0  — NEVER OBSERVED —
site.facts_drift             daily         0  — NEVER OBSERVED —
engine.freshness             daily         1  2026-08-03
topics.related_clusters      monthly       1  2026-07-14
blog.cannibalization         per_draft     0  — NEVER OBSERVED —
```

A check with one observation is a baseline, not a time series. The engine cannot
detect a trend, a regression, or a gate transition on a single point — which means
GATE-1's "two consecutive clean weekly readings" rule has never had the data to
evaluate itself. `engine.freshness` correctly fires **critical** on this, and has
been firing since 2026-08-03. The watchdog worked. Nothing acted on it.

### Why CI fails — two independent defects

**Defect A — the site worktree checkout dies.** Step `Checkout site worktree`
exits 128 against `ZEIROS-O/fresh-mobile-detailing`. `SITE_REPO_TOKEN` is missing
or lacks access. This has no `continue-on-error`, so it hard-fails the job before
`facts-check` runs.

**Defect B — the credential gate fails silently and the run renders green.**
`Validate required provider credentials` carries `continue-on-error: true`. GitHub
therefore shows the step with a ✓ (that is its *conclusion*), while
`steps.providers.outcome` is `failure`. Every downstream fetch step is guarded by
`steps.providers.outcome == 'success'`, so `sync`, `gsc-sync`, `serp-bulk`, and
`geogrid` **all skip** — visible as `-` in the run view. The Telegram notification
then reports `sync:skipped gsc:skipped`, which reads like "nothing was due."

This is the exact failure mode the Master Doc names in §VIII:

> **Automation success messages are not verification.**

The engine enforces that principle rigorously against *SEO data* and not at all
against *itself*.

**Fixes (S0):**

1. Set `SITE_REPO_TOKEN`, or make the site-worktree checkout conditional and let
   `facts-check` degrade to a declared `BLOCK` instead of a job crash.
2. Drop `continue-on-error` from the credential gate, or invert it: fail the job
   immediately with a named missing-secret list.
3. Add a `ci.heartbeat` check to `checks.yaml`: records `runs_succeeded_7d`,
   `checks_refreshed_7d`. Threshold `checks_refreshed_7d == 0 → critical`. The
   engine should be able to observe its own liveness with the same instrument it
   uses on everything else.
4. Make the Telegram line report *refreshed observation count*, not step outcomes.
   "sync:success" is theater; "4 observations recorded, 13 checks still stale" is
   measurement.
5. Repair or remove `.worktrees/fresh-site-v3` so `act` runs locally.

---

## 2. What is already better than the Master Doc — do not rebuild

| Master Doc principle | Repo implementation | Assessment |
|---|---|---|
| §VII hard verifier the model can't rationalize around | GATE-3 fact binding by snapshot hash | Stronger than the doc |
| §XXV "don't let an AI agent self-certify" | GATE-4 no-invention; honest-`blocked` over estimates | Stronger |
| §XVIII context/memory layer | `brain/` + external `business-facts.yaml` with `claim_gates` | Matches |
| §XXV "assuming automation completed because it said done" | RunReceipts, `audit`, content-addressed packages | Stronger |
| Law 11 "automate loops, not content volume" | GATE-1 publish gate | **Much** stronger — this is the best line in the repo |
| Law 12 measure outcomes not theater | `report --since`, intervention ledger | Right shape, no outcome data yet (§7) |
| §XVII indexation before content | T1 + `seo.indexation` machine-managing GATE-1 | Matches |
| §XXVI "treat source claims as hypotheses" | Thesis retraction record (T5, T7) | Stronger |

Two specific things to protect from any future refactor: **GATE-1** and the rule
that a check whose threshold references an undeclared field is rejected at load
time. The second is a small invariant doing enormous work — it makes a silently
never-firing threshold impossible.

---

## 3. Gap map — Master Doc loops vs. engine coverage

| Doc loop (§XIX) | Engine coverage | Verdict |
|---|---|---|
| L1 Search opportunity discovery | `topics.related_clusters`, `market.demand` | Partial — discovery, no scoring |
| **L2 Existing-page optimization** | **none** | **Absent — highest-value gap (§4)** |
| L3 Content production | PagePackage + `verify` + `act` | Built, gated shut, path broken |
| **L4 Backlink engine** | `competitor.authority_gap` (measurement only) | **Absent as a loop (§9)** |
| L5 AI visibility | `aeo.answer_accuracy`, `aeo.share_of_voice` | Present but schema-limited (§7) |
| L6 News/freshness | none | Correctly out of scope (§12) |
| L7 Technical/indexability | `seo.indexation`, `internal_links`, `site_health` | Strongest area |
| L8 GBP/local | `local_visibility`, `map_pack`, `gbp.performance` | Best-designed, never run |

Eight gaps follow, ordered by expected value.

---

## 4. G1 — Near-winner mining is absent, and the data is already sitting in the repo

**The doc could not be more emphatic.** Law 8 ("fix near-winners before
manufacturing more URLs"), Arbitrage 1 (Existing-Traction), Phase 1 of the fastest
order of operations, Days 8–21 of the 90-day sprint, and the tactic matrix, where
"GSC position 4–20 optimization" scores **Fast / Very high leverage / Low effort /
Low risk** — the single best cell in the entire table.

**The engine has the data and has not wired it.** `brain/state.yaml` records, from
a hand-run GSC pull on 2026-08-11:

```yaml
queries_pos_4_20: 11
impressions_pos_4_20: 87        # of 213 total impressions
pages_with_impressions: 5       # of 24 in the sitemap
```

with its own admission attached:

> *"Not yet recorded as a check observation: no `seo.*` check declares these
> fields."*

So **41% of all impressions FMD receives sit in striking distance**, in a field no
threshold can read, refreshed by hand once. Meanwhile `seo.organic_footprint` —
which *does* run — fires a **high** finding (`nonbranded_keywords == 0`, "zero
organic discovery by strangers") off the Semrush figure that **T7 explicitly
retired as a third-party database artifact**. The thesis retired the instrument
and the check kept reading it. That false positive is in the standing findings
list today, twice.

### Proposal

**Retire `seo.organic_footprint`. Add `seo.query_footprint` (weekly, GSC Search
Analytics, headless — the credential already works).**

```yaml
- id: seo.query_footprint
  domain: seo
  title: GSC query footprint and near-winner inventory
  cadence: weekly
  cost: free
  method: {kind: engine, run: "gsc.searchanalytics query dimension, 28d window"}
  records:
    - {name: total_queries, type: int}
    - {name: nonbranded_queries, type: int}
    - {name: queries_pos_1_3, type: int}
    - {name: queries_pos_4_10, type: int}
    - {name: queries_pos_11_20, type: int}
    - {name: impressions_pos_4_20, type: int}
    - {name: ctr_leak_queries, type: int}      # impressions high, CTR < position-expected
    - {name: pages_with_impressions, type: int}
    - {name: pages_in_sitemap, type: int}
  thresholds:
    - expr: queries_pos_4_20 > 0
      severity: info
      finding: "Near-winner inventory available — the doc's fastest-ROI queue."
      action: "Work the 4–20 queue before any new URL. GATE-1-compatible."
    - expr: ctr_leak_queries > 0
      severity: medium
      finding: "Queries earning impressions at a CTR below their position band."
      action: "Title/meta work on the mapped page. No new URLs, no authority needed."
```

Store the per-query rows as evidence, not just the counts — that inventory is the
input to G3's scorer and to the copy work at priority #4.

**This also sharpens priority #4.** "Introduce car/auto/near-me into existing copy"
is currently untargeted. With this check it becomes: *these 11 queries, these 5
pages, this expected impression recovery.* Same work, aimed.

**Recommended priority-order change:** insert near-winner/CTR work at **#3**, above
entity decontamination. It is free, adds no URLs, is fully GATE-1-compatible, and
unlike reviews it does not depend on customer behavior — so it can run in parallel
with priority #1 rather than queueing behind it.

---

## 5. G2 — SERP consensus is collected and discarded

**Doc Law 2:** *"Reverse-engineer the result before creating the asset… the SERP is
the answer key."* §V specifies exactly what to extract: page type, H2/H3 structure,
entities, tables, depth, freshness, recurring subtopics. **Law 3** sets the target
mix at **80–90% consensus + 10–20% information gain**.

**Engine:** `serp-bulk` pulls depth-20 SERPs across 467 keywords and records
`top3_count / top10_count / top20_count`. The payloads land in ignored `.run/raw/`
and are thrown away. `competitor.serp_movement` records `fmd_page1_count` and
`new_entrants` — positional facts only.

So when GATE-1 opens, the content path has **no consensus model to hit**. The
verifier can check that a draft has *a* FAQ section; it cannot check that the draft
matches what the winning set actually does, because nothing ever read the winning
set. That is the Master Doc's "technically excellent wrong type of page" failure
waiting to happen, and it will happen at exactly the moment the gate opens and
everyone is eager.

### Proposal

**Add `serp.consensus` (per-query, engine, zero marginal cost — reuse the payloads
`serp-bulk` already buys).** For each head term, normalize the top 10 into a
committed `evidence/serp-consensus/<query>.json`:

```
page_type_distribution   # service | listicle | UGC | video | directory | map
result_surfaces_present  # AI Overview | map pack | PAA | video | Reddit | news
recurring_entities       # entities appearing in ≥ 50% of the winning set
recurring_sections       # H2/H3 patterns
depth_band               # p25/p50/p75 word count
freshness_band           # median last-modified age
weak_serp_score          # low-authority/outdated/thin winners present
```

Two payoffs, both available *while GATE-1 stays closed*:

1. **`weak_serp_score` is Arbitrage 2** (Weak-SERP) — it identifies queries where
   the winners are beatable *now*, independent of authority. That is a finding the
   engine currently cannot produce at all.
2. It converts the verifier from structural to **comparative**. A draft can be
   checked against consensus, and the required information-gain element becomes a
   named, blocking field rather than an aspiration.

Also add `information_gain` as a **required, non-empty, typed field** on
PagePackage — `data | tool | first_hand | original_media | comparison | benchmark`
— with the verifier blocking on absence. The Master Doc's §V.4 rule is *"define the
unique asset before writing"*; making it a schema requirement is how you enforce
that mechanically rather than by intention.

---

## 6. G3 — No opportunity scoring; the priority list is hand-ordered

**Doc §III** specifies a War Room table (17 fields per commercial query) and a
scoring function:

> 35% commercial intent + 25% existing traction + 20% SERP beatability +
> 10% distribution/authority leverage + 10% freshness/timing − execution cost/risk

**Engine:** `brain/priorities.yaml` is a static, hand-ordered list of 7 strategic
themes, last reordered 2026-08-03 by human judgment. It is a good list. It is not
derived from evidence and does not descend to the query level — there is no object
in the system representing "this specific query, its value, its status."

The inputs for the score already exist or will after G1/G2: commercial intent
(query shape), existing traction (`seo.query_footprint`), SERP beatability
(`serp.consensus.weak_serp_score`), volume (`market.demand`), local rank
(`seo.local_visibility`), AI presence (`aeo.*`).

### Proposal

**Add `brain/warroom.yaml` — one row per commercially important query**, machine-
maintained, human-overridable. Plus `fmd-seo score` emitting a ranked backlog.

Critical design constraint, and I want to be explicit about it: **the score ranks
*within* what the gates allow. It never overrides a gate.** The Master Doc has no
equivalent of GATE-1 and would happily score a content opportunity to the top of
the list while indexation is failing. Keep the engine's architecture: gates are
binary and prior; the score orders the survivors. Emit the score as
`score_gated: <n>` alongside `score_raw: <n>` so a gate-suppressed opportunity
stays visible without becoming actionable.

This also gives the thesis a promotion path: today a priority is promoted by Lou
rewriting prose. With a war room, `priorities.yaml` can carry *strategic themes*
while the scored backlog carries *specific work* — and the gap between them becomes
auditable.

---

## 7. G4 — The AEO schema cannot express its own most important finding

This is the sharpest structural defect in the repo, and it is worth stating
precisely.

The single most consequential discovery in the entire system is the **review floor**
— that ChatGPT's 2026-08-06 answer ranked three competitors carrying 72/129/65
reviews, cited a review count for every one of them, cited none for FMD (16), and
placed FMD as an unranked conditional pick. Cross-referenced against the local pack
floor of 37, that produced `known_issues.aeo-review-floor` and it is *why review
velocity is priority #1*.

`aeo.answer_accuracy` records exactly three fields:

```yaml
records:
  - {name: queries_run, type: int}
  - {name: queries_citing_fmd, type: int}
  - {name: wrong_facts, type: int}
```

**None of them can hold that finding.** It survives as prose in `state.yaml` and in
a one-off evidence folder. If that same signal appeared again next week, the check
would record `queries_run: 5, queries_citing_fmd: 1, wrong_facts: 0` — and the
discovery would be invisible. The system's best insight arrived *despite* its
instrument, not through it.

Compounding this, **doc §IX asks for things the schema has no room for**: a prompt
universe of 25–100 (engine: 5), repeated runs to measure frequency (engine: single
run), multiple engines (engine: one implied), citation *share* separate from
recommendation share, and per-engine source maps — the doc is emphatic that these
differ ("there is no universal GEO platform list"). And **§IX.3's Source Priority =
Citation Frequency × Buyer Relevance × Probability of Inclusion** requires recording
*which sources the answer cited*, which nothing does.

### Proposal

Restructure the AEO domain into three checks:

**`aeo.recommendation_share` (weekly)** — the standing query set × N runs × engines.
Records: `queries_run`, `runs_per_query`, `engines`, `fmd_mention_rate`,
`fmd_ranked_rate` (named as a ranked pick vs. a conditional aside — *the distinction
that mattered*), `fmd_mean_position_in_answer`, `competitors_named` (list with
mention counts and any review counts stated), `fmd_review_count_cited`.

**`aeo.citation_sources` (weekly)** — every URL/domain the answers cite. Records:
`sources_captured`, `distinct_domains`, `sources_citing_fmd`,
`sources_citing_competitors_only`, `top_sources` (frequency-ranked). This is the
input to Citation Arbitrage (§9) and it is currently 100% absent.

**`aeo.answer_accuracy` (weekly)** — keep as-is. Drift detection is a separate
question from share and should stay separately observable.

Mark competitor figures as **as-stated-by-engine, unverified** in the schema itself
(a `provenance: engine_asserted` field), so GATE-4 is enforced structurally rather
than by a note in a YAML comment — the state file already does this correctly by
hand, which proves the need.

**Expand the query set from 5 to ~25–40.** The doc's floor is 25. Five queries
cannot measure share of voice; `aeo.share_of_voice`'s current `1.9%` baseline is a
number with no meaningful denominator behind it. Keep the set *frozen* once
expanded — the doc's comparability warning is the right instinct, and the engine's
existing note about not polluting the standing set with ad-hoc queries shows it is
already understood.

---

## 8. G5 — Priority #1 has no measurement stream and no action path

Review velocity is the top priority, justified by two independent surfaces applying
the same corroboration gate. It is the correct call. And:

- **No check records review count on a cadence.** `seo.local_visibility` carries a
  `reviews` field incidentally, harvested from a Local Finder call — and that check
  has never been observed. The only review data in the system is `16 (2026-08-03)`
  and `13 (2026-07-14)` in `state.yaml`.
- **No competitor review velocity.** The doc (§XI.5) is explicit that *velocity*,
  not lifetime total, is the signal. FMD 13→16 in 20 days is ~4.5/mo; to reach 40
  by the pack floor takes ~5 months at that rate. That projection is the single most
  decision-relevant number in the business right now and nothing computes it.
- **No review sentiment mining** (§XI.6) — free voice-of-customer research that
  feeds directly into priority #4 (copy language), GBP copy, and the review-request
  drafts. Competitor reviews are public and free to read.
- **No funnel measurement.** `gbp-draft` emits a review-request draft. Nothing
  records requests sent → reviews landed.

### Proposal

**`local.review_velocity` (weekly, free — DataForSEO Local Finder already returns
`rating.votes_count` for every result in the panel, so competitor counts are a
by-product of a call the engine already makes).**

```yaml
records:
  - {name: fmd_reviews, type: int}
  - {name: fmd_rating, type: float}
  - {name: fmd_new_reviews_28d, type: int}
  - {name: competitor_median_reviews, type: int}
  - {name: pack_floor_reviews, type: int}     # min review count among pack holders
  - {name: months_to_floor_at_current_velocity, type: float}
thresholds:
  - expr: fmd_reviews < pack_floor_reviews
    severity: high
    finding: "Below the observed corroboration floor for a pack slot (T5/T7/T6)."
  - expr: fmd_new_reviews_28d == 0
    severity: critical
    finding: "Review velocity is zero — priority #1 is not moving."
    action: "The top-priority lever produced no movement this period. Escalate."
```

That last threshold is what turns a priority into an *accountable* priority. Right
now #1 could sit at zero movement for a quarter and no instrument would say so.

**`local.review_language` (monthly, free, agent)** — mine FMD's and competitors'
review text for the terms customers actually use, feeding the copy work. This is
the doc's §XI.6 and it costs nothing but a model pass.

---

## 9. G6 — Citation arbitrage: the thesis has a blind spot it inherited from being right

T7 concluded, correctly and with evidence, that **Authority Score is a symptom, not
the constraint**, and that link volume is not the lever. That conclusion is sound.
But it has quietly generalized into "authority work is out of scope," and the
Master Doc distinguishes two things the thesis now treats as one:

- **Link volume** — generic referring domains, disavow work, DR chasing. The
  thesis is right: irrelevant here. The doc agrees (§XXV: "treating DR as a
  business KPI").
- **Link *intent* and source entry** — §IV.5 Citation Arbitrage, §IV.6 Link-Intent
  Arbitrage, §XII's warmest-first ladder. This is a different mechanism, and for
  FMD it is *directly downstream of the finding that set priority #1*.

Here is the concrete case. ChatGPT's 2026-08-06 answer ranked three competitors and
cited sources to do it. **Those sources are the highest-value authority targets FMD
has** — not because of their DR, but because an answer engine that already sends
FMD traffic is demonstrably reading them. The doc's Source Priority formula exists
for exactly this. Nothing in the repo records which sources those were.

Similarly, §XI.11's *local* authority — chambers, local publications, suppliers,
associations, sponsorships — is the doc's own recommendation for a business in
FMD's position, and it feeds **prominence**, which is the thesis's own stated
binding constraint. The thesis argues prominence is the constraint and then lists
only reviews and NAP consistency as prominence levers. Local citations and local
press are prominence levers too.

### Proposal

**Do not build a generic backlink engine.** Build the two variants the evidence
supports:

**`authority.cited_sources` (monthly, agent)** — fed by `aeo.citation_sources`
(G4). For each frequently-cited source: is FMD present, is a competitor present,
is the source realistically enterable (local listicle vs. national publication),
what is the entry mechanism. Output: a ranked source-entry queue. Records:
`sources_ranked`, `sources_with_competitor_no_fmd`, `enterable_sources`.

**`authority.local_corroboration` (monthly, agent)** — the §XI.10/11 audit: which
local directories, chambers, associations, and suppliers list competitors and not
FMD. Records: `surfaces_audited`, `competitor_present_fmd_absent`, `nap_consistent`.
This merges naturally with `aeo.entity_consistency`, which already does the NAP
half.

Both are draft-and-queue only. **Outreach stays human** under CONTRACT.md clause 6
— and that is correct, not a limitation. The engine's job is to produce the
warmest-first queue with the evidence attached; the send is Lou's.

Then add a T-level thesis amendment making the distinction explicit, so the next
agent reading T7 does not conclude that authority work as a category is closed.

---

## 10. G7 — Outcome measurement: the doc's Law 12, unfixable from inside the repo

**Doc Law 12 and §XXIII** put revenue, leads, calls, and bookings above every
intermediate signal. The engine agrees in design — `analytics.traffic` declares
`key_events`, and its threshold fires **high** on `sessions > 0 and key_events == 0`.
That check has never run.

Three blockers are already documented in `known_issues` and all three are Lou-side:

| Blocker | Effect |
|---|---|
| `ga4-service-account-unauthorized` | Analytics APIs not enabled on the Cloud project; SA not granted on the GA4 property |
| `ga4-no-key-event` | No booking/lead conversion event configured — GA4 "Key events" reads *No data available* |
| `gbp.location_id: ""` | `gbp.performance` can never run — calls, direction requests, website clicks all unmeasurable |

The consequence is stated plainly in T6 and it is the most expensive gap in the
business: **the AEO channel is sending real traffic and its conversion cannot be
measured, so every revenue claim about it stays owner-reported under GATE-4.** The
channel can be observed but not optimized.

**This is the highest-value hour Lou can spend, and no amount of engine work
substitutes for it.** It is three console tasks: enable the Analytics Data + Admin
APIs on `local-lead-machine-498016`, grant the service account Viewer on GA4
property `541970582`, configure a booking key event, and retrieve the unobfuscated
GBP location ID. Everything downstream — attribution, `report --since` deltas, the
War Room's revenue-value column, the entire outcome half of §XXIII — is blocked on
it.

Secondary but worth noting: 100% bounce with 11s average engagement on both top
pages indicates engagement events are misconfigured, so even the traffic numbers
are partly untrustworthy.

---

## 11. G8 — The engine knows what to do and cannot do any of it

This is the gap that speaks most directly to the goal of *acting* on what it knows.

`brain/priorities.yaml` holds 7 priorities under GATE-1 CLOSED. **Six of the seven
have no machine action path whatsoever.** `act` handles exactly one thing: exporting
a **PagePackage** — a *new page* — and it requires GATE-1 to be open, which by
construction it is not. So the one action command in the repo is capable only of the
one action the gates forbid. It also currently crashes on a missing worktree.

Meanwhile `known_issues` contains a list of diagnosed, specified, GATE-1-compatible
fixes that the engine wrote itself and cannot execute:

| Known issue | Fix | Machine-generatable? |
|---|---|---|
| `www-302-not-301` | 301 the www host to apex | Yes — one config line in the site repo |
| `sitemap-carries-legal-boilerplate` | Drop 3 legal URLs from sitemap | Yes — deterministic patch |
| `coverage-state-collapses-unknown` | Add `unknown_to_google` to `classify_coverage` | Yes — engine-internal, ~10 lines |
| `geogrid-query-set-misses-stronghold` | Fix query set or retire the check | Yes — config edit |
| Priority #6 schema finish | JSON-LD for `/chat`, `/fresh-pro`, `/areas`, `/blog` + `BlogPosting` | Yes — generatable from `business-facts.yaml` |
| Priority #5 internal linking | Link plan for orphans | Yes — computable from the live crawl |
| Priority #4 copy language | Targeted copy patch (aimed by G1) | Yes — fact-bound diff |
| Priority #3 entity decontamination | Per-surface correction worklist | Partly — `drafts/entity-corrections/` precedent exists |
| Priority #2 GBP audit | Console inspection | No — Lou |
| Priority #1 review velocity | Customer behavior | No — Lou, engine supports |

**Seven of ten are machine-generatable and none has a path.**

### Proposal — the `PatchPackage`

Add a second package type alongside `PagePackage`. Where a PagePackage creates a
page, a **PatchPackage modifies existing site artifacts** and inherits every
guarantee the current package system already provides:

- Content-addressed and immutable, like PagePackage
- **GATE-3 fact-bound** — every touched price/phone/service/claim binds to the
  `business-facts.yaml` snapshot hash
- **GATE-4 clean** — patches only assert what evidence supports
- **GATE-1 compatible by construction** — a PatchPackage that adds a URL is a hard
  error. This is the key property: it lets the engine work productively for the
  entire duration of a closed publish gate.
- Verified, exported to the isolated worktree, pushed to a branch, opened as a
  **draft PR** — the exact path `act` already implements
- Human merge. No publish, no deploy, no account mutation. CONTRACT.md unchanged.

Then add generators, each mapping to a priority or known issue:

```
fmd-seo patch schema        # JSON-LD for the 4 unschema'd pages + BlogPosting
fmd-seo patch internal-links # link plan from the live crawl → nav/hub edits
fmd-seo patch copy          # near-winner-targeted copy, fact-bound (needs G1)
fmd-seo patch sitemap       # drop the legal boilerplate
fmd-seo patch canonical     # www 302 → 301
fmd-seo patch entity        # per-surface correction worklist (draft, no send)
```

This is the single highest-leverage architectural change in this review. It
converts the engine from a system that produces *findings Lou must implement* into
one that produces *reviewable diffs Lou merges* — which is what "act on what it
knows" actually means in a repo with a human-merge safety boundary. And it does so
without weakening a single gate: the safety model is preserved exactly, because a
draft PR is already the engine's authorized output shape.

---

## 12. What NOT to adopt from the Master Doc

A "well-rounded SEO master" that adopted all 30 sections would violate this
engine's own thesis. These are deliberate non-adoptions, and they should be
recorded in the thesis so a future agent does not "helpfully" add them:

| Doc section | Why not, for FMD |
|---|---|
| §VIII Programmatic SEO | Doc's own precondition is "scale a proven system." GATE-2 + T3 measured **zero** volume on 8 of 9 suburbs. Programmatic city pages here are the doorway pages the doc itself warns against (§XI.9, §XXV). |
| §XIV Newsjacking | Episodic by the doc's own admission. Mobile detailing has no news cycle. **Adopt the adjacent version instead:** seasonality. `market.demand` already notes detailing is seasonal and warns against averaging the trend array away — a seasonal demand calendar is the local analog of freshness arbitrage and is genuinely valuable. |
| §XV LinkedIn | The doc's own study found LinkedIn rarely cited by ChatGPT/Claude. FMD's measured AI channel is ChatGPT. B2C local service. Skip unless the fleet/commercial line grows. |
| §XII Tier-6 cold outreach | Doc ranks it last; T7 independently reached the same conclusion. |
| §V "scrape top 10–20" at scale | Budget-bounded. Reuse the `serp-bulk` payloads already purchased (G2) rather than adding spend. |
| §X founder personal brand | Real, but competes with priority #1 for the same scarce resource (Lou's time) at lower measured leverage. Revisit after reviews clear the floor. |

Also worth an explicit guard: the doc describes a fake-award/manufactured-
corroboration experiment (§II.5) and correctly condemns it. GATE-4 already forbids
it. Keep it that way — and note that the doc's own framing ("demonstrates a
weakness in machine pattern matching; not a durable or responsible strategy") is a
good line to preserve verbatim in the thesis.

---

## 13. Where the doc and the thesis conflict — adjudicated

**Suburb pages.** Doc §XI.9 "strongly favors service-city pages." Thesis GATE-2
forbids them. **Thesis wins** — it measured zero volume; the doc's own qualifier is
"only when there is enough real local differentiation to justify them." No conflict
once read fully.

**Opportunity scoring vs. gates.** Doc §III scores everything on one axis. Thesis
uses binary gates. **Thesis wins.** Adopt the score as a ranking *within* gate-
permitted work (G3), never as an override.

**"Fix near-winners first."** Doc Law 8 / Phase 1. Thesis priority order puts
reviews first and near-winner work nowhere. **Doc wins on the omission, thesis
wins on the ordering.** Reviews are correctly #1 — two surfaces, one gate, strong
evidence. But near-winner work is free, parallel, and non-competing for the same
resource. Insert at #3 (G1).

**Authority.** Doc §XII–XIII treat link acquisition as a core loop. T7 de-
prioritizes it. **Split the difference on the mechanism, not the volume** (G9):
link volume out, citation-source entry and local corroboration in.

**AI visibility depth.** Doc §IX wants 25–100 prompts, repeated, multi-engine.
Engine runs 5, once, one engine. **Doc wins outright** (G4). The engine's *caution*
about comparability is right; its *sample size* is not defensible.

---

## 14. Sequenced plan

### S0 — Restart the heartbeat (do nothing else first)

1. Fix CI defect A: `SITE_REPO_TOKEN`, or make the site checkout non-fatal.
2. Fix CI defect B: remove `continue-on-error` from the credential gate so a
   missing secret fails loudly instead of skipping every fetch under a green ✓.
3. Add `ci.heartbeat` check — the engine observes its own liveness.
4. Change the Telegram line to report refreshed-observation counts, not step
   outcomes.
5. Repair `.worktrees/fresh-site-v3` so `act` runs locally.
6. Backfill: run every due check once via the `fmd-seo-loop` session skill, so the
   17 stale streams have a current point.

**Exit criterion:** two consecutive daily runs that each refresh ≥ 1 observation,
and `engine.freshness` reporting `checks_overdue: 0`.

### S0.5 — Lou's console hour (parallel, unblocks S3)

Enable Analytics Data + Admin APIs on `local-lead-machine-498016`; grant the
service account on GA4 `541970582`; configure a booking key event; retrieve the
GBP location ID; fix the engagement-event misconfiguration.

### S1 — Close the analysis gaps

7. `seo.query_footprint` replacing `seo.organic_footprint` (G1) — **start here**,
   highest value per hour in the whole plan.
8. `local.review_velocity` + `local.review_language` (G5) — makes priority #1
   accountable.
9. AEO restructure: `aeo.recommendation_share` + `aeo.citation_sources`, query set
   5 → 25–40 (G4).
10. `serp.consensus` over the payloads already purchased (G2).
11. Reorder `priorities.yaml`: near-winner work to #3.

### S2 — Give the engine hands

12. `PatchPackage` type + verifier + `act` integration (G8).
13. Generators in dependency order: `patch canonical` and `patch sitemap` first
    (trivial, prove the path), then `patch schema`, `patch internal-links`,
    then `patch copy` once G1 supplies the targets.
14. Fix `gsc.classify_coverage` to record `unknown_to_google` — a discovery failure
    and a crawl-budget decision need opposite fixes and T1 rests on the second.

### S3 — Extend coverage

15. `brain/warroom.yaml` + `fmd-seo score` (G3).
16. `authority.cited_sources` + `authority.local_corroboration` (G6).
17. Seasonal demand calendar from `market.demand`'s trend array.
18. Thesis amendments: record the non-adoptions (§12) and the authority split (§9)
    so they survive the next agent.

---

## 15. Two smaller findings

**`seo.organic_footprint` fires on a retired instrument.** Covered in G1, but worth
isolating as a class of bug: **when the thesis retires a measurement, nothing
retires the check that reads it.** Consider adding a `thesis_refs` field to each
check (as `priorities.yaml` already has) plus an audit that flags a check whose
referenced thesis section has been revised since the check's last edit. That closes
the loop between the judgment layer and the measurement layer in the one direction
it is currently open.

**`schema.validate` has been standing critical since 2026-08-01** —
`fact_mismatches: 2`, reviewCount values 11 and 40 as unbound public claims while
the business-facts claim gate is false. That is a live GATE-3 breach on the
*published site*, it is 11 days old, and T6 says answer engines repeat published
facts verbatim. It is also cheap to fix. It should not be sitting in a findings
list; it should be S0 work alongside the CI repair.

---

## Closing

The Master Doc's final line is that the durable advantage is *"better evidence,
better prioritization, better authority, and faster verified iteration."*

This repo has built the first two to an unusually high standard — the evidence
discipline and the judgment layer are genuinely better than what the doc describes.
It has deliberately deferred the third for reasons that are sound but slightly
over-generalized. And it has not yet achieved the fourth at all: the iteration
exists as architecture and has not run.

The order that follows from that is: **make it run, then make it see the near-
winners, then give it hands.** Everything else is elaboration on a loop that is
currently stopped.
