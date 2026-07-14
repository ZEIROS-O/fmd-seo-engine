# FMD Entity & Citation Audit — 2026-07-14

> **⚠ PARTIALLY SUPERSEDED by `baseline-2026-07-14.md`.** Two conclusions here are WRONG once
> Lou's own console data is in evidence:
> - §6 "build one interior-detailing page per suburb" — **those nine pages already exist**, and
>   Google is refusing to index 14 of the site's 20 URLs. Do not add pages.
> - The "#1 for east-side queries" reading — FMD is #1 for *"east side"* only because **no one
>   else uses that phrase and no one searches it** (GSC: real queries are "…near me" and
>   "car detailing mayfield"). It is a zero-volume #1.
>
> Review count corrected: **13 Google reviews** (not ~11, and it's Google, not Yelp).
> `drivefreshdetail.com` confirmed as **Lou's own legacy domain**. GBP **is** claimed & verified.
> The sections below on the review gap, name collisions, listicle targets, and paid-PR competitors
> remain valid.

**Method:** free web-search/fetch evidence + the committed DataForSEO GBP snapshot
(`evidence/slice-v1/ev-gbp_snapshot-*.json`). No paid API calls were spent on this audit.
**Provenance labels:** `[SERP]` = observed in live web search, `[GBP]` = DataForSEO business
listings, `[SNIPPET]` = search-result summary text (needs owner confirmation), `[INFERRED]`.

---

## Headline finding — the earlier "zero AI citations" reading was misleading

The Phase-3 LLM-Mentions baseline came back empty, which I reported as "FMD has zero AI
citations." That is **wrong as stated**. Live search shows AI answer summaries citing FMD
**accurately and in detail** — pricing ($209 Full / $279 Ultimate), the Door-Open Guarantee,
the 47-point reset, the text-3-photos flow, and the suburb list. `[SERP]`

The real pattern is sharper and more useful:

| Query shape | FMD visibility |
|---|---|
| East-side / suburb ("detailing Beachwood Solon east side") | **#1 organic result, cited in the AI summary** `[SERP]` |
| City-level ("best mobile car detailing Cleveland") | **Absent** — page one is ATF, It's A Wash, Zayas, Detail Dash, Panda Hub, Yelp, national aggregators `[SERP]` |

**FMD already owns the east-side suburb niche and is invisible at city level.** That is the
single most decisive strategic fact found so far.

---

## 1. Entity presence (what exists today)

| Surface | State |
|---|---|
| freshmobiledetail.com | Live, ranks #1 for east-side queries `[SERP]` |
| Yelp | Listing exists (`yelp.com/biz/fresh-mobile-detailing-cleveland-2`), "Updated October 2025" `[SERP]` |
| Chamber of Commerce directory | Listing exists (Cleveland OH 44124) `[SERP]` |
| Yahoo Local | Listing exists `[SERP]` |
| Google Business Profile | **Did not surface** in a DataForSEO listings search by title near the service area `[GBP]` |
| Reviews | **5.0★ from 11 reviewers** `[SNIPPET]` — needs owner confirmation of which surface |

## 2. The review gap is the dominant weakness

| Business | Reviews | Rating |
|---|---|---|
| **Fresh Mobile Detailing** | **~11** `[SNIPPET]` | 5.0 |
| All Things Fresh (ATF) | 195 | 4.8 `[GBP]` |
| Zayas Mobile Detailing | "250+ 5-star" `[SERP]` | — |
| Unnamed competitor PR | "360+ five-star" `[SERP]` | — |

Review count and **velocity** are primary local-ranking inputs. At ~11 reviews FMD is an order
of magnitude behind the city-level field — which explains the city-level invisibility better
than any content gap does. It also keeps FMD below its own `claim_gates.review_count_public_claim`
threshold (unlock at 30), so review counts cannot even be cited in copy yet.

**This is the highest-leverage action available and costs $0 in API spend.**

## 3. Name-collision risk (confirmed, and worse than assumed)

- **"All Things Fresh Mobile Car Detailing"** (ATF Detail, `allthingsfreshcardetailing.com`,
  FB `@allthingsfreshdetail`) contains the string *Fresh Mobile … Detailing* and markets itself
  as the "#1 choice" in Cleveland. It holds two GBP listings and 195 reviews. `[GBP]` `[SERP]`
- Searching the exact brand `"Fresh Mobile Detailing"` surfaces **ATF alongside FMD**. `[SERP]`
- A `trustindex.io` reviews page exists for **`drivefreshdetail.com`** — a different domain
  under a near-identical name. Unclear whether this is an abandoned FMD domain or a third party;
  **owner confirmation required.** `[SERP]`

Consequence: brand-name search leaks equity to a larger competitor. Entity disambiguation
(consistent NAP, distinct branding signals, GBP claim/optimization) matters more here than for a
typical local business.

## 4. Competitors are buying authority, not earning it

A competitor is running syndicated **paid press releases** ("Industry-Leading Mobile Car
Detailing in Cleveland Announces 360+ Five-Star Customer Reviews" across openpr,
financialcontent, and newswire mirrors). `[SERP]` This corroborates the ZEIROS note that
*rankings pay measured authority proxies, not merit*. It is **not** a recommended play
(ZEIROS guardrails: no paid press releases / link schemes), but it explains the city-level SERP.

## 5. Listicle-inclusion targets (the highest-leverage citation surfaces)

| Target | Type | FMD listed? | Path in |
|---|---|---|---|
| `theclevelandbucketlist.com/blog/recommended-car-detailers` | Editorial listicle, 16 detailers | **No** | Community-sourced — "We asked on Instagram, you answered!" → get customers/community to name Fresh; or contact the site owner directly `[SERP]` |
| Yelp — "TOP 10 BEST Mobile Car Detailing in Cleveland" | Directory ranking | Listing exists, not top-10 | Reviews + completeness drive Yelp rank |
| Yelp — "BEST 10 AUTO DETAILING near Solon 44139" | Directory ranking (suburb) | Unknown | **Best odds — suburb-level, where FMD is already strong** |
| `pandahub.com/car-detailing/cleveland-oh` | Aggregator | No | Aggregator onboarding |
| `nationaldetailpros.com/ohio/cleveland` | Aggregator | No | Aggregator onboarding |

Competitors already on the Bucket List include Nathan's Mobile Car Detailing, Rhino Mobile
Detailing, and Detail Delivery — i.e. inclusion is achievable for a business of FMD's size.

## 6. SERP page-type evidence (money-page selection — determined free)

The plan requires building *the page type the SERP already rewards*. For suburb queries the
answer is unambiguous — competitors rank **dedicated service+suburb pages**: `[SERP]`

- `nathansdetailing.com/solon-car-detail/`
- `ceramicprocle.com/car-detailing/solon/`
- `galaxyautospa.co/solon`
- `esotericdetail.com/car-detail-near-me-beachwood-ohio/`
- `infinitiofbeachwood.com/precision-detailing-beachwood`

**Verified money-page type: one interior-detailing page per suburb.** FMD currently ranks #1 for
east-side queries on the strength of the homepage alone — with no suburb pages at all. That is
the clearest content gap on the board, and it needed **no paid API call** to establish.

Candidate suburb pages, ordered by the primary cluster in `business-facts.yaml`
(`Solon, Beachwood, Orange, Pepper Pike`) — one page each, non-cannibalizing by geography,
and each must carry genuinely distinct local content (not a geo-token swap, which the corpus
checker blocks).

---

## Recommended action order (revised by this evidence)

1. **Reviews.** Drive 11 → 30+ (unlocks the claim gate *and* attacks the actual ranking
   deficit). Ask at the peak-value moment — right after the finished car is handed back.
   Cost: $0.
2. **GBP.** Confirm the profile is claimed, categories correct, and it surfaces on a
   name/near-me search. It currently does not appear in a listings search by title. Cost: $0.
3. **Listicle inclusion**, starting with the **suburb-level** Yelp/Solon surfaces and the
   Cleveland Bucket List (community/Instagram route). Cost: $0.
4. **Entity disambiguation** vs. All Things Fresh; resolve the `drivefreshdetail.com` question.
5. **Only then content** — and target **suburb money pages** (Beachwood / Solon / Pepper Pike /
   Shaker Heights interior detailing), not "Cleveland car detailing," which is a bloodbath FMD
   cannot currently win and is not the niche it already owns.

## Open questions for Lou

- Is `drivefreshdetail.com` yours (old domain) or a third party?
- Is the GBP claimed and verified? Which categories are set?
- Is the ~11-review figure Google or Yelp?
