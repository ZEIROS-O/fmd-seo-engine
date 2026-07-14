"""The live post already owns Cleveland pricing; a pricing article must be
blocked as cannibalization. This is the failure the corpus checker missed
originally (it only indexed engine JSON, never the live inline post)."""

from pathlib import Path

from fmd_seo.corpus import cannibalization_checks, corpus_checks
from fmd_seo.live_site import LivePost, parse_inline_posts_text

# Trimmed excerpt of the live blog.$slug.tsx inline registry.
LIVE_TSX = '''
const POSTS: Record<string, PostMeta> = {
  "what-to-know-before-car-detailing-cleveland": {
    title: "Car Detailing Cleveland: What to Know | Fresh",
    description:
      "Salt stains, crumbs, pet hair, odors. What Cleveland drivers should know.",
    canonical: "https://freshmobiledetail.com/blog/what-to-know-before-car-detailing-cleveland",
    headline:
      "Your Car Isn't A Little Dirty.",
  },
};
const FAQS = [
  { q: "How much does car detailing cost in Cleveland?", a: "..." },
  { q: "Can detailing remove Cleveland salt stains?", a: "..." },
];
<H2 id="cost">What Car Detailing Actually Costs in Cleveland</H2>
<H2 id="salt-stains">The Salt Problem Nobody Deals With</H2>
'''

PRICING_CANDIDATE = {
    "slug": "car-detailing-prices-cleveland",
    "title": "How Much Does Car Detailing Cost in Cleveland? (2026 Pricing Guide)",
    "blocks": [
        {"type": "h2", "text": "Cleveland detailing prices by service type"},
        {"type": "h2", "text": "What an interior detail costs on the east side"},
    ],
}

DISTINCT_CANDIDATE = {
    "slug": "how-often-detail-family-suv",
    "title": "How Often Should You Detail a Family SUV?",
    "blocks": [
        {"type": "h2", "text": "Kids, spills, and the three-month reset"},
        {"type": "h2", "text": "Membership cadence for busy households"},
    ],
}


def test_parser_extracts_live_topic_surface():
    posts = parse_inline_posts_text(LIVE_TSX)
    assert len(posts) == 1
    p = posts[0]
    assert p.slug == "what-to-know-before-car-detailing-cleveland"
    assert "What to Know" in p.title
    assert any("Costs in Cleveland" in h for h in p.headings)
    assert any("cost in Cleveland" in q for q in p.faq_questions)


def test_pricing_article_blocked_as_cannibalization():
    live = parse_inline_posts_text(LIVE_TSX)
    results = cannibalization_checks(PRICING_CANDIDATE, live)
    verdicts = {n: (v, d) for n, v, d in results}
    key = "cannibal:what-to-know-before-car-detailing-cleveland"
    assert verdicts[key][0] == "BLOCK", verdicts


def test_distinct_topic_not_blocked():
    live = parse_inline_posts_text(LIVE_TSX)
    results = cannibalization_checks(DISTINCT_CANDIDATE, live)
    assert all(v != "BLOCK" for _, v, _ in results), results


def test_same_slug_blocks():
    live = parse_inline_posts_text(LIVE_TSX)
    same = {"slug": "what-to-know-before-car-detailing-cleveland", "title": "x"}
    results = cannibalization_checks(same, live)
    assert any(v == "BLOCK" and "slug already live" in d for _, v, d in results)


def test_corpus_checks_folds_in_live_posts(tmp_path):
    live = parse_inline_posts_text(LIVE_TSX)
    results = corpus_checks(PRICING_CANDIDATE, tmp_path, ["Cleveland", "Beachwood"], live_posts=live)
    assert any(n.startswith("cannibal:") and v == "BLOCK" for n, v, d in results)
