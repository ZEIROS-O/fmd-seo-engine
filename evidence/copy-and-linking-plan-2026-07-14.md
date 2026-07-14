# Copy Rewrite + Internal Linking Plan — 2026-07-14

Grounded in **Lou's own GSC/GBP query data**, not keyword guesses. Two jobs:
(A) retire "east side" and start using the words people actually type;
(B) fix the internal linking that is starving 14 pages of crawl priority.

---

## A. The keyword gap nobody noticed: the site never says "car" or "auto"

What people **actually search** (GSC 28d + GBP search terms):

| Query | Source | Signal |
|---|---|---|
| auto detailers **near me** | GSC (1 click) | head term |
| mobile detailing **near me** | GSC (5 impr) | head term |
| auto detailing **near me** | GSC (4 impr) | head term |
| **car detailing mayfield** | GSC (3 impr) | **service + suburb** |
| fresh car detailing | GBP | branded |
| fresh mobile detailing | GBP / GSC (42 impr) | branded |

The head terms are **"car detailing"**, **"auto detailing"**, **"mobile detailing"** — usually with
**"near me"** or a **suburb name**.

The site's own language is **"Mobile Interior Detailing."** It contains neither **"car"** nor
**"auto."** Competitors title their pages *"Mobile **Car** Detailing in Mayfield Heights, OH"*
(Nathan's) and *"**Car** Detailing in Solon, OH"* (Ceramic Pro).

> **Fresh is optimised for a phrase nobody types, in a category vocabulary it doesn't use.**
> "Interior" is the *differentiator* — it should qualify the head term, not replace it.

### "East side" — retire it (70 occurrences across 14 files)

```
public/llms.txt              src/components/CityPage.tsx     src/components/SiteChrome.tsx
src/lib/mcp/index.ts         src/lib/mcp/tools/get-service-areas.ts
src/routes/api/chat.ts       src/routes/areas.index.tsx      src/routes/blog.$slug.tsx
src/routes/blog.index.tsx    src/routes/chat.tsx             src/routes/fleet.tsx
src/routes/index.tsx         src/routes/interior-detailing.tsx
src/routes/mobile-detailing.tsx
```

Three reasons, all independent: **zero search volume** (GSC proves it), the **East Cleveland
connotation** Lou flagged, and it **displaces the words that do get searched**.

**Replacement rules**
- **Default:** name the suburbs — *"Beachwood, Solon, Pepper Pike, Mayfield Heights."*
- **When a collective noun is needed:** *"Cleveland's eastern suburbs"* (reads affluent;
  *"east side"* reads urban-core).
- **Never:** "east side" / "eastside".

### Proposed metadata

| Page | Now | Proposed |
|---|---|---|
| **Home** `<title>` | `Mobile Interior Detailing — Cleveland's East Side \| Fresh` | `Mobile Car Detailing — Mayfield Heights & Beachwood, OH` *(54 ch)* |
| **Home** meta desc | — | `Interior-first mobile car detailing in Beachwood, Solon, Pepper Pike & Mayfield Heights. We come to your driveway. Full Interior $209.` *(133 ch)* |
| **Area** `<title>` | `Mobile Interior Detailing in {city}, OH \| Fresh` | `Mobile Car Detailing in {city}, OH \| Fresh` — **adds the head term**, keeps the geo |
| **H1 (home)** | "…Cleveland's East Side" | `Mobile Interior Car Detailing — We Come To Your Driveway` |

Keep every FMD number bound to `business-facts.yaml` ($209 / $279 / memberships / Door-Open
Guarantee). The engine's deterministic verifier enforces this.

---

## B. Internal linking — the likely mechanical cause of "Discovered – not indexed"

Measured link graph today:

```
Home ──► /areas (index) ──► /areas/<city> ×9      ← each city page has exactly ONE inbound link
Home ──► /mobile-detailing
/interior-detailing ◄── ONLY from the (unindexed) city pages   ← near-orphan
Blog post ──► "/" only
```

Every money page hangs off a single link from one index page. That is the weakest possible
crawl-priority signal — and crawl priority is precisely what "Discovered – currently not indexed"
is about. Combined with the entity/citation deficit, it is a sufficient explanation.

### Fix (site-code proposal, Lou/Lovable applies)

1. **Home → all 9 city pages directly.** Add an "Areas we serve" grid on the homepage linking each
   `/areas/<city>` by name. Turns 1 inbound link into 2, from the site's highest-authority page.
2. **Home → `/interior-detailing`.** It is the primary service page and is currently reachable only
   through unindexed pages.
3. **Blog post → city + service pages.** The live post mentions Beachwood, Solon, Orange, Pepper
   Pike in prose — link them. *(This is the ZEIROS "supporting content exists to link, not to rank"
   principle: the blog's job is to pass equity to money pages.)*
4. **City → 2–3 neighbouring city pages** ("Also serving nearby: Solon · Pepper Pike").
5. **Then request indexing** in GSC for the 9 area + 2 service pages — after 1–4 ship, not before.

**KPI (per the plan): internal-link coverage of money pages.** Target ≥3 inbound internal links per
money page, from at least 2 distinct source pages.

---

## Sequencing (don't skip)

Citations/NAP → internal links → **then** request indexing → then measure. Requesting indexing
before the entity and link signals improve just burns the request on a page Google will decline
again.
