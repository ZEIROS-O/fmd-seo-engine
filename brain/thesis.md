# Standing Thesis — what the engine believes and why

Loaded by every loop run. This is the engine's *judgment layer*: it decides
what work is worth doing at all. Checks measure; the thesis decides.

Revise only with measured evidence, and record the measurement that forced the
revision. Prose that contradicts `brain/state.yaml` is wrong by definition —
state wins.

---

## T1. Entity trust is step zero. Rankings pay authority, not merit.

**Original basis (2026-07-14):** GSC reported **4 URLs indexed, 18 not** — 14 of
them "Discovered – currently not indexed." The nine `/areas` suburb pages are
already written, and are *not* lazy geo-swaps: each carries its own
`introHeading`, `intro`, `neighborhoods`, and reviews. The craft is present.

**Remeasured 2026-08-11** (`fmd-seo gsc-sync`, URL Inspection over all 24 sitemap
URLs — the first fresh reading in 28 days):

| | 2026-07-14 | 2026-08-11 |
|---|---|---|
| indexed | 4 | **11** |
| not indexed | 18 | **13** |
| discovered – not indexed | 14 | 10 |

**Indexation is recovering, and T1's core claim survives in a narrower form.**

Three things this forces:

1. **GATE-1 is now half-met.** The rule is `not_indexed < 8` **and**
   `indexed >= 10`. The second condition is satisfied (11). The first is not (13).
   The gate stays CLOSED with `consecutive_clean_readings: 0` — but it is one
   condition away, not two, and the direction of travel is toward opening.
2. **The real backlog is 10, not 18.** Three of the 13 not-indexed URLs are legal
   boilerplate — `/privacy-policy`, `/terms-of-service`,
   `/cancellation-refund-policy` — with no search value and no business being in a
   sitemap. Removing them is free, does not open the gate, and stops the engine
   from counting doc-required pages as an indexation failure.
3. **"Unknown to Google" is a different diagnosis, and the engine cannot see it.**
   Three URLs return *"URL is unknown to Google"* — Google does not know they
   exist, despite the sitemap. That is a **discovery** failure. "Discovered –
   currently not indexed" is a **crawl-budget/authority** decision. They call for
   opposite fixes, and `gsc.classify_coverage` collapses both into `not_indexed`,
   so `seo.indexation` cannot express the distinction. T1's whole argument rests on
   the second mechanism; the engine should stop asserting it for URLs exhibiting
   the first.

**Both money pages are now indexed** (`/interior-detailing`, `/mobile-detailing`),
as is `/chat` — which retires the `chat-orphaned` known issue.

**Therefore: writing more pages is still counterproductive**, but the reason is
thinner than it was. It is now a 10-page backlog, not 14, and the gate is one
condition from opening. T1 should be re-examined on the next clean reading rather
than treated as settled.

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

## T5. Local visibility is a tight ring around the profile anchor, not a niche.

**Measured 2026-08-03 (DataForSEO Local Finder, Places tab, depth 20, mobile, $0.076):**

| Location | Result |
|---|---|
| Mayfield Heights | "mobile detailing mayfield heights" **rank 2**, "car detailing mayfield heights" **rank 3** — both in the 3-slot pack. "mobile detailing near me" rank 11. |
| Beachwood (~4mi) | "mobile detailing beachwood" **rank 6** — Places tab only, not the pack. Everything else absent. |
| Solon (~10mi) | Absent on all six queries. |

4 of 18 query/location pairs. **Visibility decays with distance from the anchor and
is gone by ~10 miles.** That is standard service-area-business behaviour: Google
ranks an SAB in a ring around its registered address, and the ring's *radius* is
set by prominence — reviews and citations — not by pages or domain authority.

**Two corrections this measurement forced:**

1. The earlier "#1 for east-side suburb queries" reading was a zero-volume #1 on a
   phrase nobody searches. Superseded: the real reading is rank 2–3 at the anchor,
   6 one suburb out, absent two suburbs out.
2. **A 3-slot probe cannot measure this.** The 5x5 geogrid run the same night
   reported `points_present: 0` across 181 samples — for a business holding rank 2
   in its own strongest suburb. The pack has three slots; rank 4–20 reads as
   absence. It also never tested the `mobile detailing <suburb>` shape and never
   sampled Mayfield Heights, so it missed the stronghold entirely. Local
   visibility is measured at depth (`seo.local_visibility`), never pack-only.

**The binding gap is "near me."** That cluster is ~2,350/mo (T3). The
2026-08-03 Local Finder run found FMD in it once, at rank 11, at the anchor.

**Sharpened 2026-08-11 by GSC Search Analytics (28d, 2026-07-12..08-08):**

| query | avg position | impressions | clicks |
|---|---|---|---|
| mobile car detailing near me | **1.0** | 1 | 0 |
| mobile detailing near me | **2.6** | 8 | 1 |
| car detailing near me | 10.7 | 3 | 1 |
| detailing near me | 19.7 | 3 | 0 |
| mobile detail near me | 32.0 | 1 | 0 |

**This does not contradict the rank-11 reading — the two measure different
questions.** DataForSEO measures a coordinate *the engine picks*. GSC averages over
the searchers *Google actually served*, who skew heavily toward people near the
business. Both are true simultaneously.

**What it changes is the diagnosis.** FMD ranks 1–2.6 for near-me searches among
the people Google serves it to, and Google serves it to **almost nobody**: 16
impressions in 28 days against a cluster measured at ~2,350/mo.

**So the near-me gap is an impression-volume problem, not a ranking problem.** That
is the same ring mechanism this thesis already argues, stated more precisely — and
it matters because "appears once at rank 11" invites ranking work, while the true
constraint is radius. Prominence widens the radius; nothing about the ranking needs
fixing where the ring already reaches.

**Vocabulary decides the marginal ring.** At the anchor both "mobile" and "car"
phrasings rank (2 and 3) — proximity dominates. One suburb out, "mobile" ranks 6
and "car" is absent. So T4's copy fix is not cosmetic: it is what converts the
ring's outer band from absent to present.

## T6. AI answers cite FMD accurately — and now send traffic. The slot is conditional, and reviews are what upgrade it.

The Phase-3 LLM-Mentions baseline came back empty and was reported as "zero AI
citations." **That was wrong as stated.** Live search shows AI summaries citing FMD
in detail — pricing ($209 Full / $279 Ultimate), the Door-Open Guarantee, the
47-point reset, the text-3-photos flow, the suburb list.

**Therefore AEO is a defend-and-extend job, not a cold start.** The risk is
*drift* — an AI answer citing stale prices or the wrong entity — which is why
`aeo.answer_accuracy` runs weekly and treats a wrong fact as high severity.

**Extended 2026-08-06** (`evidence/aeo-chatgpt-citation-2026-08-06/`). Lou captured a
live ChatGPT answer to *"best place to get mobile detailing around beachwood ohio"*
plus the same-day GA4 snapshot. Three things came out of it, and only the first is
the good news:

**1. The channel now delivers traffic, not just visibility.** GA4 recorded **2
sessions from `chatgpt.com`** on 2026-08-06, one of them a new user whose *first*
source was the AI assistant. That is the first AI-sourced arrival in the analytics
record. Accuracy held: ChatGPT cited **6 FMD facts, 0 wrong** — $209 sedan interior,
$279 deeper reset, the guarantee, the photo-based quote flow, interior focus,
Beachwood coverage.

**2. But FMD's slot is *conditional*, not default.** The answer ranks three picks —
Mavics (4.8★, **72 reviews**), Lucente (4.9★, **129**), Refresh (5.0★, **65**) — and
places FMD *after* them, unranked, in a use-case paragraph: *"If your interior is the
main concern…"*, closing with *"go Fresh if the inside is trashed."* FMD is the
contingency, never the first call.

**3. The mechanism is the same one T5 and T7 already identified.** ChatGPT cited a
star rating and review count for **all three** ranked competitors and **none** for
FMD, which carries 16. The floor for a ranked AI slot in this answer was 65 reviews;
the floor for a local pack slot on 2026-08-03 was 37. **Two independent surfaces are
applying the same corroboration gate.**

**Therefore: review velocity is not a local-SEO lever that also helps AEO — it is one
lever gating both surfaces.** This is the strongest corroboration the thesis has for
priority #1, and it arrived from a direction that had nothing to do with the local
ring.

Two corollaries:

- **The interior wedge is worth defending.** ChatGPT correctly identified the
  specialization and matched it to a use case. T4's breadth language
  ("car detailing" / "auto detailing" / "near me") should be added *alongside* the
  interior positioning, not in place of it — the wedge is what earns the slot; breadth
  is what widens which queries reach it.
- **GATE-3 is now a revenue control.** Published prices are being read verbatim into
  answers that route booking traffic. A stale price does not just mislead — it
  propagates into the acquisition path.

**Two things this evidence does NOT establish**, and the engine must not treat as
measured: (a) **no conversion measurement exists.** GA4's "Key events" card reads
"No data available"; Lou's report that online-booking leads are arriving from ChatGPT
is credible and is why this was captured, but it stays labelled *owner-reported* under
GATE-4 until a booking key event exists. (b) The capture was an **ad-hoc query**, not
the standing 5-query `aeo_query_set`, so it is **not** a weekly `aeo.answer_accuracy`
reading and was deliberately not recorded as one — a 1-query universe would destroy
comparability. That check remains due.

**It does not open GATE-1.** AI traffic is a reason to do prominence work faster, not
a reason to publish into an 18-page unindexed backlog.

## T7. Authority Score is a symptom, not the constraint. Prominence is.

Authority Score **2** vs competitors 7–16 (Refresh 7, cledetailing 7, Detail Dash 8,
Diamond Finish 9, Nathan's 11, Ceramic Pro CLE 16, Inside Out 16).

**The "4 keywords, all branded, none on page 1" figure is retired (2026-08-11).**
It came from Semrush's third-party database. GSC — Google's own record of what it
served — reports for the same kind of window (28d, 2026-07-12..08-08):

- **56 queries**, of which **41 are non-branded** (96 impressions, 2 clicks)
- **4 queries at position ≤ 3**; **11 in positions 4–20** carrying 87 impressions
- 213 impressions, 4 clicks total
- **5 pages** have ever received an impression, of 24 in the sitemap

So the claim "zero organic discovery by strangers" was **wrong as stated** — a
Semrush coverage artifact for a domain too small for its index, not a measurement.
Strangers do find this site. The honest reading is that they find it in very small
numbers: 96 non-branded impressions in 28 days.

**This does not weaken T7's conclusion; it relocates the evidence.** The constraint
was never keyword count — `seo.organic_footprint`'s `nonbranded_keywords == 0`
threshold was measuring the wrong instrument. Prominence is still the binding gap,
now visible as 5 pages of 24 ever being served and 87 impressions sitting in
striking distance unconverted.

**Revised 2026-08-03.** Two things forced this:

1. **Owner disclosure: the 211 backlinks / 106 referring domains are fake.** That
   fully explains AS 2 without AS being a constraint on anything. The prior
   inference ("low-quality or non-corroborating") was right about the mechanism.
   Do not spend effort on disavow — Google discounts spam links on its own. The one
   free action worth taking is checking GSC for a manual action; a penalty would
   change the picture, and its absence closes the question.
2. **Semrush Authority Score is not a Google ranking factor.** It is a third-party
   proxy for organic domain strength. The queries that carry FMD's demand are
   "near me" and `service + suburb`, where the map pack sits above organic and is
   ranked on proximity, prominence, and relevance. AS barely touches that surface.

**The measured constraint is prominence, expressed as ring radius (T5).** Every
business holding a pack slot in the 2026-08-03 sample carried 37–1600 reviews;
FMD carries 16. Proshine (18) and Brushwood (26) rank in Solon where FMD does not
— they are simply closer, which is exactly the point: reviews are what buy reach
past the businesses nearest the searcher.

**Therefore:** reviews and citation consistency, not link volume and not domain
authority. Treat AS as a diagnostic readout, never as a target.

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

Reordered 2026-08-03 on the T5 ring measurement. Review velocity moves to the top:
it is the only lever that widens the ring, and the ring is what gates every query
at every location.

1. **Review velocity** (T5/T7) — 16 → 40+. Pack holders in the measured sample
   carry 37–1600. This widens the radius, which is the binding constraint; it also
   compounds into AI answers (T6), which already cite FMD.
2. **GBP configuration audit** (T5) — confirm the anchor address, service-area
   settings, primary category, and verification state. The ring centres on
   Mayfield Heights while `business-facts.yaml` calls the base
   "Beachwood / Mayfield Heights". Free, and it explains the ring's shape.
3. **Entity decontamination** (T8) — collapse 'Drive Fresh' → 'Fresh Mobile
   Detailing' across social + directories; consistent NAP. Feeds prominence
   directly, so it now serves the same goal as #1.
4. **Copy language** (T4) — introduce "car detailing" / "auto detailing" /
   "near me" into existing copy. No new URLs. Measured effect: at the anchor both
   phrasings rank, one suburb out only "mobile" does — this is what converts the
   ring's outer band.
5. **Internal linking** (T1) — the unindexed pages are link-starved; crawl
   priority follows internal links.
6. **Schema finish + validate** (T2) — the 4 unschema'd pages + `BlogPosting` on
   posts, and confirm `AggregateRating` is fact-bound (not reused across suburbs).
   Maintenance now, not the bottleneck.
7. **Only then** reassess GATE-1.
