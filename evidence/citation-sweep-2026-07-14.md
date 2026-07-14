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

## Name collisions — ranked by actual threat

| # | Entity | Threat | Detail |
|---|---|---|---|
| 1 | **Refresh Mobile Detailing** | **HIGH** | 1190 E Miner Rd, Mayfield Heights, OH **44124** — *the same city and ZIP as Fresh*. Owner Brayden. Phones (440) 589-8609 / (216) 331-8534. Present on **Nextdoor** (12 faves), Yelp (`refresh-detailing-mayfield-heights`), Facebook `/RefreshDetailingLLC`, `wheree.com`, own site. **Near-identical name, identical ZIP, and broader citation coverage than Fresh.** This is the real disambiguation problem. |
| 2 | **All Things Fresh** (ATF) | MED | `allthingsfreshcardetailing.com`, 195 reviews, 2 GBP listings, markets as "#1 in Cleveland". Owns the city-level brand-adjacent SERP. |
| 3 | **Drive Fresh** *(Fresh's own ghost)* | **HIGH — self-inflicted** | `drivefreshdetail.com`, `@drivefreshdetail` on IG + FB. The only one fully within Lou's control, and the one **actively teaching AI answers the wrong website**. |
| ~~4~~ | ~~Fresh Start Mobile Detailing~~ | **NONE — dismissed** | Columbus/London OH, 3.0★ with **2 reviews**. Not a competitor. Disregard. |

---

## ⚠ CORRECTION — the "citation void" claim was WRONG

I previously wrote that Fresh was absent from Nextdoor, BBB, Yelp and Bing. **That was a bad
inference: I concluded absence from a failed web search.** Gated/logged-in platforms like Nextdoor
are not fully visible to public search, so a null result there proves nothing. Lou confirms — and
his Nextdoor profile shows — the opposite.

### Nextdoor is in fact one of Fresh's strongest assets

- **19 faves**, **2024 Neighborhood Fave award** ("annual award recognizing businesses loved by
  locals"), **4 recommendations & 9 mentions**.
- Website field is **correct** (`freshmobiledetail.com`) — no Drive Fresh contamination here.
- Email `info@freshmobiledetail.com`; phone `(216) 359-1034` ✓ matches canonical.
- Categories: *Auto detailer*, *Carpet cleaner*. Address **hidden** (correct for a mobile business).

**The 2024 Neighborhood Fave award is a third-party trust signal that appears nowhere on the
website, GBP, or any other surface.** That is a wasted asset — it is exactly the kind of
corroborating, human-voted proof both Google and answer engines weight. Surface it.

### 🔴 NEW NAP conflict found on Nextdoor

| Surface | Street address |
|---|---|
| Google Business Profile | **6605 Kingswood Dr**, Mayfield Heights, OH 44124 |
| **Nextdoor** | **24815 Tunbridge Ln** |
| MapQuest | *(Beachwood, OH 44122 — wrong city/ZIP)* |

**Three surfaces, three different addresses.** Even hidden, the address is part of the entity
record. Pick the canonical one and make every surface match.

Nextdoor's bio also still reads *"Cleveland's east side"* — include it in the copy rewrite.

## Actual presence map (corrected, per Lou)

| Surface | State |
|---|---|
| **Nextdoor** | ✅ Present — 19 faves, 2024 award. *Fix: address + "east side" copy.* |
| **Yelp** | ✅ Present (stale, Oct 2025) |
| **BBB** | ✅ Present |
| **Bing Places** | ✅ Present |
| **Google Business Profile** | ✅ Claimed + verified |
| Chamber of Commerce / Yahoo Local | ✅ Present (verify NAP + website field) |
| MapQuest | ⚠️ Present but **wrong city, ZIP, and services** |
| Trustindex | ⚠️ Indexed under the **dead domain** |
| **Apple Maps (Business Connect)** | ❌ Missing — free, feeds Siri. **Highest-value gap.** |
| **Foursquare** | ❌ Missing — free, feeds many downstream apps |
| Alignable / Manta / Cylex / Hotfrog / Brownbook | ❌ Missing — low value each, cheap in bulk |
| ~~Angi~~ | 🚫 N/A — does not list auto detailers |
| ~~Thumbtack~~ | 🚫 Paid only — skip |

So the real picture is **not a void**: Fresh has a decent core (GBP, Nextdoor+award, Yelp, BBB,
Bing). The problems are **(a) inconsistency across the ones that exist** — three addresses, a dead
domain, wrong services — and **(b) a handful of free gaps** (Apple Maps, Foursquare).

**Consistency beats quantity.** Fixing the contradictions in the six that exist is worth more than
adding ten new ones, because contradicting traces actively *subtract* entity confidence.

Canonical NAP to enforce everywhere:
`Fresh Mobile Detailing · <ONE canonical address> · Mayfield Heights, OH 44124 ·
(216) 359-1034 · freshmobiledetail.com · info@freshmobiledetail.com`

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
