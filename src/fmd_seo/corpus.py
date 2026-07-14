"""Corpus checks: near-duplicate and geo-swap doorway detection between a
candidate package and the existing site content."""

from __future__ import annotations

import json
import re
from pathlib import Path

SHINGLE_SIZE = 5
NEAR_DUP_BLOCK = 0.5
NEAR_DUP_WARN = 0.3


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


def corpus_checks(candidate_content: dict, site_content_dir: Path,
                  places: list[str]) -> list[tuple[str, str, str]]:
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
        results.append(("corpus", "PASS", "no existing content to collide with"))
    return results
