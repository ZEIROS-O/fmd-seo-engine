# Standing Thesis — what the engine believes and why

Loaded by every loop run. This is the engine's *judgment layer*: it decides
what work is worth doing at all. Checks measure; the thesis decides.

Revise only with measured evidence, and record the measurement that forced the
revision. Prose that contradicts `brain/state.yaml` is wrong by definition —
state wins.

---

## T1. Entity trust is step zero. Rankings pay authority, not merit.

**Measured basis (2026-07-14):** GSC reports **4 URLs indexed, 18 not** — 14 of
them "Discovered – currently not indexed." The nine `/areas` suburb pages are
already written, and are *not* lazy geo-swaps: each carries its own
`introHeading`, `intro`, `neighborhoods`, and reviews. The craft is present.

Google has discovered these pages and is **declining to spend crawl budget**
indexing them. At this scale that is the classic low-authority, low-corroboration
signal for a young entity — not a content-quality gap.

**Therefore: writing more pages right now is actively counterproductive.** It adds
to a pile of 14 pages Google already refuses to index. This is why `GATE-1` exists.

## T2. Structured data is SSR in raw HTML. The remaining gap is narrow.

**Superseded reading (2026-07-14):** Semrush Site Audit and an earlier raw-HTML
capture showed Schema.org on **0** pages. That snapshot became stale when the
site changed; it was not evidence that schema required JavaScript or a headless
browser.

**Corrected reading:** the TanStack Start site renders server-side, and schema is
present directly in raw HTML. A plain `curl` fetch finds **32 ld+json blocks
across 16/20 pages**, with `LocalBusiness`, `Service`, and `AggregateRating` all
present. The homepage, money pages, and every suburb page carry it.

**What this means:** the single highest-leverage fix identified at baseline **has
largely been executed.** T2 is no longer the open bottleneck. The residual schema
work is narrow, not foundational:

1. **4 pages still have no schema:** `/chat`, `/fresh-pro`, `/areas` (hub), `/blog`
   (hub). The two hubs and `/fresh-pro` are worth `LocalBusiness`/`Service`.
2. **Blog posts carry `FAQPage` but not `BlogPosting`** — add `BlogPosting` when
   GATE-1 opens and posts matter for indexation.
3. **`schema.validate` must confirm the `AggregateRating` is fact-bound** and not a
   reused-review artifact across suburbs (see T-caveat / known_issues).

Schema remains the direct machine-readable lever on T1 — but as a *maintain-and-
validate* job now, not a *build* job.

## T3. Eight of nine suburb pages target zero search volume.

**Measured basis (2026-07-14, DataForSEO Google Ads volumes, Cleveland metro, $0.09):**
"car detailing beachwood", "mobile detailing solon" et al. return **0** — not "low",
zero. Only `/areas/chagrin-falls` shows any volume at all (10/mo).

Real demand sits in the **"near me" cluster (2,350/mo)** and in
`service + suburb` shapes like "car detailing mayfield" (observed in GSC).

**Corollary:** more suburb pages cannot work even after T1 resolves. The suburb
page is the wrong unit. Volume lives in "near me" + service language.

## T4. The site never says the words people type.

GSC + GBP query data: head terms are **"car detailing"**, **"auto detailing"**,
**"mobile detailing"** — usually with **"near me"** or a suburb.

The site's own language is **"Mobile Interior Detailing."** It contains neither
**"car"** nor **"auto"**. This is a free, uncapped fix that requires no authority.

## T5. FMD owns the east-side suburb niche and is invisible at city level.

- East-side / suburb queries → **#1 organic, cited in the AI summary**.
- City-level ("best mobile car detailing Cleveland") → **absent**; page one is ATF,
  It's A Wash, Zayas, Detail Dash, Panda Hub, Yelp, aggregators.

**Caveat that matters:** the "#1 for east side" reading is a **zero-volume #1** — FMD
ranks first for *"east side"* only because nobody else uses the phrase and nobody
searches it. Do not read it as strength. Treat T5 as a statement about where the
gap is, not a win to defend.

## T6. AI answers already cite FMD accurately.

The Phase-3 LLM-Mentions baseline came back empty and was reported as "zero AI
citations." **That was wrong as stated.** Live search shows AI summaries citing FMD
in detail — pricing ($209 Full / $279 Ultimate), the Door-Open Guarantee, the
47-point reset, the text-3-photos flow, the suburb list.

**Therefore AEO is a defend-and-extend job, not a cold start.** The risk is
*drift* — an AI answer citing stale prices or the wrong entity — which is why
`aeo.answer_accuracy` runs weekly and treats a wrong fact as high severity.

## T7. Authority gap is real and is the binding constraint.

Authority Score **2** vs competitors 7–16 (Refresh 7, cledetailing 7, Detail Dash 8,
Diamond Finish 9, Nathan's 11, Ceramic Pro CLE 16, Inside Out 16). Organic footprint:
**4 keywords, all branded, none on page 1**, 9 clicks / 28d.

Backlinks 211 / 106 referring domains — higher raw counts than Refresh, yet AS 2.
That combination means the links are low-quality or non-corroborating. **Chasing
link volume is not the move; chasing local corroboration is.**

## T8. Entity contamination: 'Drive Fresh' bleed.

`drivefreshdetail.com` is **Lou's own legacy domain**, and "Drive Fresh" naming
contaminates social + directory listings. Split identity across citations directly
suppresses entity resolution — it is a T1 problem wearing a different hat, and it
is fixable for free.

---

# Gates — hard, machine-enforced

Gates are evaluated by `fmd-seo assess` and block work regardless of what any check
"suggests." A gate is not advice. The loop cannot route around one.

## GATE-1 — PUBLISH GATE (currently **CLOSED**)

**Rule:** no new blog post or money page may be authored while indexation is failing.

**Closes when:** `seo.indexation.not_indexed >= 8`
**Opens when:** `not_indexed < 8` **and** `indexed >= 10` on two consecutive
weekly readings.

**Basis:** T1. Publishing into a 14-page unindexed backlog converts effort into
crawl-budget dilution.

**What the loop does instead while CLOSED:** route all content capacity to
`GATE-1-BYPASS` work — schema, entity corroboration, internal linking, and copy
language (T2 / T4 / T8). These raise indexation without adding URLs.

> This gate is the single most important line in the brain. Its whole job is to stop
> a content engine from doing the thing content engines want to do.

## GATE-2 — SUBURB-PAGE GATE (**CLOSED**, indefinitely)

**Rule:** no new `/areas/<suburb>` page, ever, on current evidence.
**Opens when:** a suburb clears **≥ 30/mo** measured volume for a
`car|auto|mobile detailing <suburb>` query.
**Basis:** T3. Zero volume is not a ranking problem; it is an absent market.

## GATE-3 — FACT GATE (always armed)

**Rule:** every price, service, area, contact detail, guarantee, equipment claim,
and review claim in any generated artifact must bind to the current
`business-facts.yaml` snapshot hash. Unbound or stale → **BLOCK**, never a
degraded pass.
**Basis:** CONTRACT.md authority boundaries. T6 makes this sharper: AI answers
repeat our published facts, so a wrong fact propagates into answer engines.

## GATE-4 — NO-INVENTION GATE (always armed)

**Rule:** never manufacture search volume, rankings, traffic, review counts,
competitor facts, or customer/vehicle imagery. Estimates and proxies must be
labeled as such, with source and retrieval time.
**Basis:** CONTRACT.md; ZEIROS OS-6A-003 public-claim perimeter.

---

## Priority order while GATE-1 is CLOSED

The loop works this list top-down. Each item is free or near-free and none adds a URL.

1. **Entity decontamination** (T8) — collapse 'Drive Fresh' → 'Fresh Mobile
   Detailing' across social + directories; consistent NAP. Now the top lever:
   schema (the former #1) is largely done.
2. **Copy language** (T4) — introduce "car detailing" / "auto detailing" /
   "near me" into existing page copy. No new URLs.
3. **Internal linking** (T1) — the unindexed pages are link-starved; crawl
   priority follows internal links.
4. **Review velocity** (T7) — local corroboration is what AS 2 actually lacks.
5. **Schema finish + validate** (T2) — the 4 unschema'd pages + `BlogPosting` on
   posts, and confirm `AggregateRating` is fact-bound (not reused across suburbs).
   Maintenance now, not the bottleneck.
6. **Only then** reassess GATE-1.
