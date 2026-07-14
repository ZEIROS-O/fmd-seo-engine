# Semrush Site Audit + Live HTML Verification — 2026-07-14

**Sources:** Semrush Site Audit (project 30426612, snapshot `6a56ad279ccf5fa799f3db94`,
22 pages crawled, 6,090 checks) + `curl` (raw HTML) + **headless-Chromium render (post-JS DOM)**.
Position Tracking is configured but **not yet readable over API** — see §6.

> ## ⚠️ CORRECTION (2026-07-14, same day)
> **The original §1 headline of this file — "ZERO structured data" — was WRONG. The site has
> comprehensive, well-formed schema on every page.** Both sources that "agreed" shared the same
> blind spot: they read *pre-JavaScript* HTML. This is a TanStack/React SPA that injects
> `application/ld+json` **client-side**, so `curl` and the Semrush crawler's markup detector both
> missed it. A real browser render (headless Chromium, `waitUntil: networkidle`) is the only
> valid test, and it shows the schema is present and strong. See the corrected §1 below.
> Lesson recorded in memory as `js-rendered-site-schema-verification`.

---

## 1. Structured data: PRESENT and strong (corrected) — site is also technically clean

| Metric | Value |
|---|---|
| **Site Health** | **95 / 100** |
| **Errors** | **0** |
| Warnings | 47 |
| Notices | 2 |
| Broken pages | 0 |
| Blocked from crawling | 0 |
| Pages crawled | 22 |

**Rendered-DOM schema audit (headless Chromium, post-JS):**

| Page | ld+json blocks | Types |
|---|---|---|
| `/` (home) | 2 | `LocalBusiness` + `FAQPage` |
| `/areas/beachwood` | 2 | `LocalBusiness` (with `areaServed: Beachwood`) + `FAQPage` |
| `/interior-detailing` | 2 | `Service` (with `provider: LocalBusiness`) + `FAQPage` |

The homepage `LocalBusiness` node is **more complete than what I would have recommended adding**:
NAP (name/`+1-216-359-1034`/Beachwood 44122), `priceRange`, `openingHoursSpecification`,
`serviceArea` `GeoCircle` (lat 41.4639 / lng −81.5089, 30-mi/48,280 m radius), **`areaServed`
listing 21 cities**, **`aggregateRating` 5.0**, and **`sameAs`** → GBP (share.google), Instagram,
Facebook, Nextdoor, Yelp, MapQuest. Plus a 14-question `FAQPage` (pricing, photo-quote flow,
Door-Open Guarantee, pet hair/salt, Fresh Club).

> **So schema is NOT the lever it looked like.** The entity-corroboration layer already exists and
> is good. The indexing bottleneck (14 pages "Discovered – not indexed", AScore 2) therefore is
> **not** an on-page markup gap — it points back at *off-site* authority/citations and the GBP,
> exactly where `baseline-2026-07-14.md` and the citation sweep already pointed. This correction
> removes a distraction rather than adding a task.

### Two small, real schema nits (worth fixing, low effort)

1. **`aggregateRating.reviewCount` = 11, but GBP shows 13 reviews** (baseline §3). Keep the
   number in sync with GBP, or Google may distrust the rating markup.
2. Homepage `image` is a **relative** path (`/assets/og-card-NBbqGlM2.jpg`). Schema `image` should
   be an absolute URL.

### What Semrush *did* report on markup (for the record)

| Markup type (Semrush, raw-HTML) | Pages |
|---|---|
| Open Graph | 18 |
| Twitter Card | 18 |
| Schema.org | 0 ⟵ **false negative — JS-injected, see correction above** |
| Microformats | 0 (genuinely none; the site uses JSON-LD, not microdata — correct & preferred) |

<!-- superseded / archived — original claim was a false negative -->
> ~~Two independent sources agree: there is no structured data anywhere on the site. It is not
> "write more pages." It is marking up pages that already exist.~~ — **RETRACTED, see §1 correction.**

### The schema already does the entity-anchoring job

The citation sweep found **"Drive Fresh" NAP contamination** across directories. The canonical
assertion *from the property we control* — one `LocalBusiness` node with exact GBP NAP, `sameAs` →
real GBP + socials, `areaServed` → the suburbs — **already exists on the live site** (§1). So the
on-page anchor for the off-site citation cleanup is in place; the remaining work is the off-site
half (fixing the contaminated citations to match), not adding markup. Keep `reviewCount` synced to
GBP (nit #1) so the anchor stays trustworthy.

## 2. No errors ⇒ the indexing problem is not technical

Zero 4xx/5xx, zero broken links, zero broken canonicals, zero redirect chains, no crawl blocks,
robots.txt valid and sitemap declared:

```
User-agent: *
Allow: /
Disallow: /api/
Sitemap: https://freshmobiledetail.com/sitemap.xml
```

This **rules out the entire class of "Google can't index it" explanations.** Nothing is blocking
the crawler. Google is choosing not to index — which is a trust/authority judgment, not a
technical fault. Combined with Semrush AScore 2 (`semrush-research-2026-07-14.md`), the picture
is consistent and unambiguous.

Content *is* server-rendered — raw HTML carries real text before any JS runs (homepage 2,009
visible words; `/areas/beachwood` 821; `/interior-detailing` 1,063). The TanStack SSR decision in
`m1-rendering-decision.md` is working.

## 3. Warnings that actually matter

### Low text-to-HTML ratio — 9 pages (issue 112)

`/fresh-pro` · `/blog` · and **7 of the 9 suburb pages**: solon, shaker-heights, pepper-pike,
moreland-hills, mayfield-heights, chagrin-falls, beachwood.

`/areas/beachwood` = 821 visible words in 53,971 bytes of HTML (~1.5% text). The craft in that
copy is real (per baseline) — but the page is mostly framework payload. For pages Google has
already deemed not worth indexing, a thin text-to-chrome ratio is corroborating evidence for
that judgment, not the cause of it.

### Low word count — 2 pages (issue 117)

`/fresh-pro` and `/blog`. `/blog` is an index page so it's expected; **`/fresh-pro` is a real
money page and is thin.**

### Orphaned sitemap page — `/chat` (issue 207)

`https://freshmobiledetail.com/chat` is **in the sitemap but has no internal links pointing at
it**. It's an 11 KB chat-widget page with nothing to index. It is pure crawl-budget waste, and
submitting junk in a sitemap is a low-quality signal for a site already fighting a trust deficit.
**Remove it from the sitemap.**

### Blog post has exactly one internal link (issue 213)

`/blog/what-to-know-before-car-detailing-cleveland` — the single piece of content with genuine
ranking potential (it already draws GA4 pageviews) is nearly orphaned. Cheap fix: link it from
the homepage and the interior-detailing page.

### Performance hygiene — 18 pages each

Uncached JS/CSS (issue 132) and unminified JS/CSS (issue 135). Low priority; not what's blocking
indexing.

## 4. Sitemap drift since the baseline

Sitemap now ships **19 URLs** (baseline recorded 20) and includes three pages the baseline's
enumeration didn't list: **`/fleet`, `/boat`, `/fresh-pro`**.

`/boat` is worth a note: GBP's top surfacing terms include **"mobile rv wash near cleveland, oh"**
(baseline §3), which was attributed to category bleed. There's a `/boat` page and RV/boat
detailing has real local volume in the Planner export ("mobile rv detailing near me", "rv
detailing" — 50/mo local each). Worth deciding deliberately whether RV/boat is a service line or
noise, rather than leaving it as an accident of category configuration.

## 5. Recommended order (schema step removed — already done on-site)

1. **NAP cleanup** — kill "Drive Fresh" contamination (citation sweep). The on-site `sameAs`
   anchor is already in place (§1); this is the off-site half.
2. **GBP** — Service Area Business, drop bleeding categories, reviews.
3. **Schema nits only** (§1): sync `aggregateRating.reviewCount` 11 → 13 to match GBP; make the
   homepage `image` an absolute URL. The schema itself is already comprehensive — no build-out
   needed.
4. **Remove `/chat` from the sitemap; internally link the blog post.**
5. Tier 1/2 citations + the two listicles (theclevelandbucketlist.com, esotericdetail.com).
6. *Then* the seat-stain content cluster — after indexing unblocks.

## 6. Position Tracking — configured but not yet exposed by the API

`list_projects` shows the project with `tracking` enabled, but `campaigns` returns
`targets: null` and both `tracking_campaign_dates` and `tracking_position_organic` return
`campaign not found`. This is expected timing behaviour: Semrush exposes a tracking campaign to
the API only after its **first rank harvest completes** (typically a few hours for ~467
keywords). Nothing to fix — retry the pull tomorrow.

First read should be: `tracking_position_organic` with `linktype_filter=0` (includes local pack)
against `*.freshmobiledetail.com/*`, plus `tracking_competitors_organic` for the ATF / Refresh /
Nathan's / Diamond Finish comparison.
