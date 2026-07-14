# Real Keyword Research — 2026-07-14

**Source:** DataForSEO → Google Ads Search Volume (the same data behind Keyword Planner, but exact
numbers instead of Planner's "100–1K" ranges). 260 keywords, one request, **$0.09**.
Location: Cleveland, Ohio metro. Raw evidence: `evidence/keywords/`.

---

## 🔴 The finding: eight of the nine `/areas` pages target **zero** search volume

| Existing page | "car detailing X" | "auto detailing X" | "mobile detailing X" | **Total** |
|---|---|---|---|---|
| /areas/beachwood | 0 | 0 | 0 | **0** |
| /areas/solon | 0 | 0 | 0 | **0** |
| /areas/pepper-pike | 0 | 0 | 0 | **0** |
| /areas/mayfield-heights | 0 | 0 | 0 | **0** |
| /areas/moreland-hills | 0 | 0 | 0 | **0** |
| /areas/shaker-heights | 0 | 0 | 0 | **0** |
| /areas/university-heights | 0 | 0 | 0 | **0** |
| /areas/highland-heights | 0 | 0 | 0 | **0** |
| /areas/chagrin-falls | 10 | 0 | 0 | 10 |

**Nobody searches "car detailing beachwood." Nobody searches "mobile detailing solon."**
Not "low volume" — **zero**.

### Where the demand actually is

| Cluster | Monthly searches |
|---|---|
| **"near me" cluster** | **2,350** |
| Cleveland metro terms | 1,840 |
| **Every suburb detailing term combined** | **140** |

The suburb pages chase **140 searches/month across all nine towns**. "Near me" alone is **2,350** —
roughly **17× more demand**, and *none of it is won by a landing page*.

> **"Near me" is answered by the map pack — i.e. by the Google Business Profile: proximity,
> reviews, categories, and citations.** Not by content.
>
> This is the same conclusion as the indexing analysis, but now with a price tag: **reviews and GBP
> aren't "step zero" as a technicality — they are the only lever on 2,350 monthly searches.** It
> also gives Google a plain reason to decline indexing those nine pages: there is no query demand
> for them to serve.

---

## The keyword table that should drive the rewrite

| Keyword | Vol | Comp | CPC | Note |
|---|---|---|---|---|
| car detailing | **3,600** | MED | $3.69 | head term, metro-wide |
| **car detailing near me** | **1,300** | HIGH | $2.71 | **the money query — map pack** |
| auto detailing | 480 | LOW | $1.98 | low competition |
| car detailing cleveland | 390 | HIGH | $3.19 | *(auto/mobile/plain "detailing cleveland" all 390 — one cluster)* |
| auto detailing near me | 320 | HIGH | $1.44 | |
| **interior car detailing near me** | **320** | HIGH | $1.44 | **Fresh's perfect-fit query** |
| car interior cleaning | 210 | HIGH | $2.52 | |
| **mobile car detailing** | 170 | MED | **$5.41** | **highest CPC = highest commercial intent** |
| mobile auto detailing | 170 | MED | $5.41 | |
| mobile detailing near me | 140 | HIGH | $3.87 | |
| mobile car detailing near me | 110 | HIGH | $4.33 | |
| mobile car detailing cleveland | 110 | MED | $4.10 | |
| interior car detailing | 90 | HIGH | $2.47 | |
| car carpet cleaning | 90 | HIGH | $0.57 | |
| car detailing prices | 30 | MED | $1.21 | *(the live blog already owns this intent)* |

**`mobile car detailing` carries a $5.41 CPC** — advertisers pay more for it than for any other term
here. That is the market pricing Fresh's exact service as the highest-intent traffic on the board.

### ⚠️ Trap: "car wash [suburb]" has volume, but it is the wrong buyer

`car wash solon` (170), `car wash mayfield heights` (70), `car wash euclid` (50),
`car wash willoughby` (50), `car wash beachwood` (30)… **Do not chase these.** Someone searching
"car wash" wants a $15 exterior wash, not a $209 interior reset. Wrong intent, wrong customer,
guaranteed bounce. The volume is a mirage.

---

## What this means

1. **Stop investing in suburb pages.** They target zero. Keep the nine that exist (they cost
   nothing, carry internal links, and support local relevance) but expect no traffic and **build no
   more**. Consider consolidating them into `/areas` if they stay unindexed.
2. **The GBP *is* the SEO strategy.** 2,350 "near me" searches/month are decided by proximity +
   reviews + categories + citation consistency. Every hour spent on reviews and NAP beats every hour
   spent on content, by an order of magnitude.
3. **`/interior-detailing` should be the site's most important page** — it targets
   *interior car detailing near me* (320) + *interior car detailing* (90) + *car interior cleaning*
   (210) ≈ **620/month of perfectly-matched, differentiated demand.** Today it is nearly orphaned,
   linked only from pages Google won't index. **This is the single biggest on-site miss.**
4. **The homepage should target the metro cluster**, not a geography nobody types:
   *car detailing cleveland* / *mobile car detailing cleveland* / *car detailing near me*.
5. **The site's vocabulary is wrong.** It says "Mobile Interior Detailing" — the words with demand
   are **car detailing** (3,600) and **auto detailing** (480). It uses neither "car" nor "auto".

## Revised metadata (volume-grounded)

| Page | Now | Proposed | Targets |
|---|---|---|---|
| **Home** | `Mobile Interior Detailing — Cleveland's East Side \| Fresh` | `Mobile Car Detailing in Cleveland \| Interior-First \| Fresh` | car detailing cleveland (390), mobile car detailing cleveland (110) |
| **/interior-detailing** | — | `Interior Car Detailing Near You — Cleveland \| Fresh` | interior car detailing near me (320), car interior cleaning (210) |
| **/mobile-detailing** | — | `Mobile Car Detailing — We Come To Your Driveway \| Fresh` | mobile car detailing (170, $5.41 CPC) |
| **/areas/{city}** | `Mobile Interior Detailing in {city}, OH` | *leave as-is* — zero volume, not worth the edit |

---

## Answering "do I need Google Keyword Planner?"

**No.** Planner throttles volume to vague ranges ("100–1K") unless you're actively spending on ads.
This request returned **exact volumes, competition, and CPC for 260 keywords for $0.09** — and the
endpoint charges **the same for 1 keyword or 1,000**, so the marginal cost of going broader is zero.
Always batch to the limit.

**Balance: $0.7886 remaining.**
