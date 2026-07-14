# NAP / Citation Sweep — "Drive Fresh" contamination
**2026-07-14 · found via free web search · no API spend**

Lou confirms `drivefreshdetail.com` is his **old** domain (live site is `freshmobiledetail.com`
only). The old identity is still propagating — and it is doing measurable damage.

## The headline problem: AI answers are citing the dead domain as the website

Search summaries currently state, verbatim: *"Fresh Mobile Detailing operates at
**drivefreshdetail.com**"* and *"**Website: drivefreshdetail.com**"*. The answer engines have
learned the wrong homepage. Every citation of the dead domain is a corroborating trace pointing
away from the live site — which is precisely the entity signal Google weighs before deciding
whether to index the 14 pages it is currently ignoring.

## NAP is inconsistent across three different cities

| Source | Address as published |
|---|---|
| **Google Business Profile (canonical)** | 6605 Kingswood Dr, **Mayfield Heights**, OH **44124** |
| Search summaries / Chamber of Commerce | 6605 Kingswood Dr, **Cleveland**, OH 44124 |
| **MapQuest** | **Beachwood**, OH **44122** ← wrong city *and* wrong ZIP |

Pick **one** canonical NAP (the GBP one) and force every surface to match it, character for
character.

---

## Fix list — highest impact first

### 1. Social handles still carry the old brand (highest authority signals)

| Surface | State | Action |
|---|---|---|
| **Instagram `@drivefreshdetail`** | Profile *name* is "Fresh Mobile Detailing", **handle is the old brand** | At minimum change the **website field** to `freshmobiledetail.com`. Consider renaming the handle to `@freshmobiledetail` (IG allows it; old @-mentions break, but the entity signal is worth more). |
| **Facebook `/drivefreshdetail`** | Same — name right, **URL slug is the old brand** | Update the **website field** + page username. |

These two are the loudest third-party signals about who Fresh *is*. They should not say
"drivefresh".

### 2. Directory records to correct (website + NAP + services)

| Surface | URL | What's wrong |
|---|---|---|
| **MapQuest** | mapquest.com → "Fresh Mobile Detailing, Beachwood, OH 44122" | **Wrong city + ZIP.** Also lists **exterior washes, waxing, paint correction** — services Fresh does **not** offer (interior-first; no steamer/ozone per `business-facts.yaml`). Claim the listing and fix. |
| **Trustindex.io** | `trustindex.io/reviews/www.drivefreshdetail.com` | Indexed under the **dead domain**. Request correction/removal. |
| **Yelp** | `yelp.com/biz/fresh-mobile-detailing-cleveland-2` | Last updated Oct 2025 — stale. Verify website + NAP + hours; refresh. |
| **Chamber of Commerce** | `chamberofcommerce.com/.../2026065916-fresh-mobile-detailing` | City listed as "Cleveland"; verify website field isn't the old domain. |
| **Yahoo Local** | `local.yahoo.com/info-233772813-fresh-mobile-detailing-cleveland` | Verify website + NAP. |

### 3. Stale facts propagating everywhere

- Review count cached as **"5.0 from 11 reviewers"** — actual is **13**. Will self-correct as
  citations refresh.
- Several surfaces still describe the **service area as "Cleveland's east side"** — see the
  baseline doc: that phrase should be retired in favour of named suburbs.

---

## Name collisions — now **four** competing "Fresh" entities

| # | Entity | Surface |
|---|---|---|
| 1 | **All Things Fresh Mobile Car Detailing** (ATF) | `allthingsfreshcardetailing.com`, 195 reviews, 2 GBP listings, markets as "#1 in Cleveland" |
| 2 | **Refresh Mobile Detailing** | `refreshmobiledetailingcle.com`, FB `/RefreshDetailingLLC`, `refresh-mobile-detailing.wheree.com` — **also Mayfield Heights** |
| 3 | **Fresh Start Mobile Detailing LLC** | Square booking page |
| 4 | **Drive Fresh** *(Fresh's own ghost)* | `drivefreshdetail.com`, `@drivefreshdetail` on IG + FB |

Fresh's brand-name SERP is shared with three competitors **and its own dead identity**. Cleaning up
#4 is the only one fully within Lou's control — and it is the one actively confusing the answer
engines today.

---

## Why this is the unlock (not more content)

Google has **discovered 14 pages and declined to index them**. For a young entity that is a trust
signal, not a content signal. Contradicting citations — a dead website, three different cities, a
service list that doesn't match reality — are exactly the traces that keep an entity below the
threshold where Google spends crawl budget. **Fix the traces, then ask for indexing.**

## What I can and cannot do here

- ✅ **Found** every contaminated surface above (free, no API spend).
- ❌ **Cannot fix them autonomously** — each requires a logged-in claim/edit, and
  `business-facts.yaml` sets `customer_contact: human_only` / `posting: human_only`. These are
  Lou-executed, and the list above is the worklist.
- ⏭ Next free step available on request: a full sweep of the remaining aggregator tier (Bing
  Places, Apple Maps, Nextdoor, Angi, Thumbtack, BBB, Foursquare, local .com directories) for
  additional stale "Drive Fresh" records.
