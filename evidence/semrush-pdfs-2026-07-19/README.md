# Semrush PDF exports — 2026-07-19

Four Semrush PDFs, fully extracted. `source-manifest.json` records the files,
their SHA-256s, and how each was parsed and validated.

| File | What it holds |
|---|---|
| `pdf-findings.json` | First-pass summary (pass 1). Kept as-is; superseded in detail, not contradicted. |
| `position-tracking-479.json` / `.csv` | All 479 campaign keywords with KD%, CPC, volume, and the 19 Jul position + week-change for all five tracked domains. |
| `brand-performance.json` | ChatGPT/Cleveland: share of voice, mentions, average position, sentiment, cited domains and pages, the 25-question non-branded breakdown, topic and intent distributions, drivers, and every Semrush recommendation. |
| `competitor-research.json` | All-AI-platforms/US: AI visibility, mentions, audience, 25 topics, 25 prompts, 25 sources. |
| `map-rank-heatmaps/` | 23 native-resolution heatmap rasters plus `heatmap-grids.json` — all 1,127 grid points as integers. |

## Three measurement systems, three grains

These PDFs are **not** interchangeable with the engine's own measurements, and
none of them was recorded as an observation for that reason:

- **Semrush Position Tracking** — Google organic, **desktop**, **United States**,
  **national** volume. FMD: 0 top-3, 0 top-10, 2 top-20, 17 top-100 of 479.
- **Semrush Map Rank Tracker** — a **7×7 grid** over the east-side service area,
  23 keywords, GBP-based.
- **DataForSEO coordinate pull** (`evidence/geo-top20-2026-07-19/`) — **mobile**,
  depth 20, anchored at `41.4645,-81.5087,200`. FMD: 1 top-3, 8 top-10, 41 top-20
  of 467.

The 41-vs-2 gap between the last two is the instrument, not a contradiction:
national desktop and coordinate-anchored mobile are different questions.
`evidence/position-tracking-map-pack-reconciliation-2026-07-19.md` states the
standing rule — compare them at their own grain, never average them.

The only check these PDFs legitimately fulfil is `aeo.share_of_voice`, and that
observation already exists (`brain/observations/aeo.share_of_voice/20260719T0000000400.json`).
`seo.positions`, `seo.map_pack`, `seo.organic_footprint` and
`competitor.serp_movement` all specify a different instrument in their `run`
field; `aeo.answer_accuracy` needs a `wrong_facts` count these exports cannot
support. Recording any of them from this source would have corrupted a live
series — the same failure family as
`docs/incidents/2026-08-03-fixture-overwrote-evidence.md`.

## What the full extraction surfaced that the summary pass did not

1. **freshmobiledetail.com is cited 0 times** in the ChatGPT/Cleveland universe
   while the *brand* is mentioned 8 times. Every citation FMD earns comes from
   somebody else's property — trustindex.io (11), reddit.com (8), itsawash.net
   (8), zayasmobiledetailing.com (7), cledetailing.com (3). The site itself is
   not a source ChatGPT quotes.

2. **The map pack contradicts the brand positioning.** Semrush's own Brand
   Performance report says FMD's strongest asset is interior-first family work.
   In the heatmaps, the `interior *` queries are the weakest set on the board:
   `interior auto detailing` is absent from all 49 points, `interior detailing`
   and `interior car detailing` return one visible point each (rank 17), and
   `interior detailing service` peaks at 13. Every point of real strength —
   all 7 top-3 points on the entire board — sits on `mobile detailing service`,
   `mobile detailing near me`, and `mobile car detailing near me`. FMD ranks for
   *mobile*, and is invisible for the thing it claims to be.

3. **Of the 25 non-branded questions in the breakdown, FMD appears in 8 — and
   ranks 1–3 with 100% sentiment in every one of them.** The 17 it misses
   include "kid messes, car seats, and snack stains" and "dog hair and pet
   odors", which is the same contradiction as (2) from the answer-engine side.

4. **Presence, not placement, is the constraint.** 287 of 1,127 grid points
   (25.5%) return FMD at all; median rank where present is 12. Best rank
   anywhere on the board is 3.

5. **The 17 keywords FMD ranks for nationally are all branded or hyper-local**
   ("fresh mobile detail", "interior car detailing moreland hills",
   "mobile car detailing mayfield heights"). No generic head term ranks at all.
