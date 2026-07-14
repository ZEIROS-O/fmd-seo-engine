# Semrush Site Audit + Live HTML Verification — 2026-07-14

**Sources:** Semrush Site Audit (project 30426612, snapshot `6a56ad279ccf5fa799f3db94`,
22 pages crawled, 6,090 checks) + direct `curl` verification against live HTML.
Position Tracking is configured but **not yet readable over API** — see §6.

---

## 1. The headline: the site is technically clean — and has ZERO structured data

| Metric | Value |
|---|---|
| **Site Health** | **95 / 100** |
| **Errors** | **0** |
| Warnings | 47 |
| Notices | 2 |
| Broken pages | 0 |
| Blocked from crawling | 0 |
| Pages crawled | 22 |

Semrush markup detection across the 18 content pages:

| Markup type | Pages |
|---|---|
| Open Graph | 18 |
| Twitter Card | 18 |
| **Schema.org** | **0** |
| Microformats | 0 |

**Verified independently against live HTML** (9 fetches, byte-identical, md5
`ad2858bec362020193076fbe44157058`, tested as curl-default / Googlebot / Chrome UAs):

```
LocalBusiness  -> 0      schema.org -> 0      ld+json -> 0
itemtype       -> 0      @context   -> 0      @type   -> 0
```

Two independent sources agree: **there is no structured data anywhere on the site.**
Someone configured social sharing meta (OG + Twitter on every page) and stopped short of
the one markup type that search engines actually use to resolve *entities*.

> **This is the highest-leverage finding available right now, and it fits the standing thesis
> exactly.** The bottleneck is entity trust: Google has "discovered" 14 pages and declines to
> index them because nothing corroborates that this business is real and is what it claims.
> `LocalBusiness`/`AutoDetailing` + `Service` + `AggregateRating` schema is the *machine-readable*
> version of that corroboration — it ties the site to the GBP NAP, the 13 five-star reviews, the
> service area, and the categories.
>
> **It is not "write more pages."** It is marking up pages that already exist — fully consistent
> with `baseline-2026-07-14.md`'s "writing more pages right now would be actively
> counterproductive."

### Why this matters more than the usual "add schema" advice

The citation sweep found **"Drive Fresh" NAP contamination** across directories. Schema is how you
assert the canonical entity *from the property you control*: one `LocalBusiness` node with the
exact GBP name/address/phone, `sameAs` pointing at the real GBP + social profiles, and
`areaServed` listing the suburbs. It's the anchor the off-site citation cleanup gets measured
against.

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

## 5. Recommended order (unchanged thesis, one addition)

1. **NAP cleanup** — kill "Drive Fresh" contamination (citation sweep).
2. **GBP** — Service Area Business, drop bleeding categories, reviews.
3. **NEW: `LocalBusiness` schema** on homepage + `Service` schema on the money pages, `sameAs` →
   GBP/socials, `areaServed` → the suburbs, `aggregateRating` → the 13 reviews. Cheap, entirely
   within our control, directly targets the measured constraint.
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
