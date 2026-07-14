"""Corpus checks: near-duplicate, geo-swap doorway, and topic-level
cannibalization detection between a candidate package and existing site
content — including the live site's inline blog posts, not just engine JSON."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .live_site import LivePost

SHINGLE_SIZE = 5
NEAR_DUP_BLOCK = 0.5
NEAR_DUP_WARN = 0.3

# Topic-level cannibalization: how much of the candidate's commercial intent a
# live post already covers. Full-body Jaccard misses this (two pages about the
# same intent worded differently), so we compare intent-token coverage.
CANNIBAL_BLOCK = 0.55
CANNIBAL_WARN = 0.4

_STOP = frozenset(
    "a an and are as at be before but by for from get how in is it of on or the to "
    "what when where which who why with you your car cars know need should this that "
    "guide 2026 fresh".split()
)


def _text_of(content: dict) -> str:
    parts = [content.get("title", ""), content.get("description", "")]
    for block in content.get("blocks", []):
        parts.append(block.get("text", ""))
        parts.extend(block.get("items", []))
    return " ".join(parts).lower()


def _shingles(text: str, size: int = SHINGLE_SIZE) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-z0-9']+", text)
    return {tuple(words[i:i + size]) for i in range(max(0, len(words) - size + 1))}


def jaccard(a: str, b: str) -> float:
    sa, sb = _shingles(a), _shingles(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def geo_swapped(a: str, b: str, places: list[str]) -> bool:
    """True if the two texts become near-identical once place names are
    masked — the geo-token-swap doorway signature."""
    mask_re = re.compile("|".join(re.escape(p.lower()) for p in places))
    return jaccard(mask_re.sub("<place>", a), mask_re.sub("<place>", b)) >= NEAR_DUP_BLOCK


def _intent_tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9']+", text.lower())
            if len(w) > 2 and w not in _STOP}


def candidate_intent(content: dict) -> set[str]:
    """Primary commercial-intent tokens: the slug and title. This is the
    clearest statement of what query the page competes on; incidental section
    headings are deliberately excluded so a broad post can't dilute the signal."""
    slug_words = content.get("slug", "").replace("-", " ")
    return _intent_tokens(slug_words + " " + content.get("title", ""))


def cannibalization_checks(candidate_content: dict,
                           live_posts: list[LivePost]) -> list[tuple[str, str, str]]:
    """Flag a candidate whose primary commercial intent a live post already owns."""
    results: list[tuple[str, str, str]] = []
    cand = candidate_intent(candidate_content)
    cand_slug = candidate_content.get("slug", "")

    for post in live_posts:
        if post.slug == cand_slug:
            results.append((f"cannibal:{post.slug}", "BLOCK", "slug already live on site"))
            continue
        if not cand:
            results.append((f"cannibal:{post.slug}", "WARN", "candidate has no intent tokens"))
            continue
        live = _intent_tokens(post.topic_text())
        if not live:
            continue
        coverage = len(cand & live) / len(cand)
        shared = ", ".join(sorted(cand & live)[:8])
        if coverage >= CANNIBAL_BLOCK:
            results.append((f"cannibal:{post.slug}", "BLOCK",
                            f"live post covers {coverage:.0%} of candidate intent ({shared})"))
        elif coverage >= CANNIBAL_WARN:
            results.append((f"cannibal:{post.slug}", "WARN",
                            f"live post covers {coverage:.0%} of candidate intent ({shared})"))
        else:
            results.append((f"cannibal:{post.slug}", "PASS", f"{coverage:.0%} intent overlap"))

    if not live_posts:
        results.append(("cannibalization", "WARN", "no live posts indexed — pass a site_root"))
    return results


def corpus_checks(candidate_content: dict, site_content_dir: Path,
                  places: list[str],
                  live_posts: list[LivePost] | None = None) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    cand_text = _text_of(candidate_content)
    cand_slug = candidate_content.get("slug", "")
    existing = sorted(site_content_dir.glob("*.json")) if site_content_dir.exists() else []

    for path in existing:
        other = json.loads(path.read_text(encoding="utf-8"))
        if other.get("slug") == cand_slug:
            results.append((f"corpus:{path.stem}", "BLOCK", "slug already exists on site"))
            continue
        other_text = _text_of(other)
        sim = jaccard(cand_text, other_text)
        if sim >= NEAR_DUP_BLOCK:
            results.append((f"corpus:{path.stem}", "BLOCK", f"near-duplicate (jaccard {sim:.2f})"))
        elif geo_swapped(cand_text, other_text, places):
            results.append((f"corpus:{path.stem}", "BLOCK", "geo-token-swap doorway signature"))
        elif sim >= NEAR_DUP_WARN:
            results.append((f"corpus:{path.stem}", "WARN", f"similar (jaccard {sim:.2f})"))
        else:
            results.append((f"corpus:{path.stem}", "PASS", f"jaccard {sim:.2f}"))

    if not existing:
        results.append(("corpus", "PASS", "no existing engine JSON to collide with"))

    # Topic-level cannibalization against the live site's inline posts.
    results.extend(cannibalization_checks(candidate_content, live_posts or []))
    return results
