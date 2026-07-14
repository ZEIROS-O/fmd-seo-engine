"""Parse the live Fresh blog's inline posts so cannibalization checks run
against real published content, not just the engine's own JSON directory.

The live route stores posts inline in `src/routes/blog.$slug.tsx`: a `POSTS`
metadata record, a `FAQS` array, and hand-written `<H2 id=...>` sections. We
extract the high-signal topic surface (slug, title, description, headline,
section headings, FAQ questions) with targeted regex — enough to detect that a
candidate intent already has a home on the site, without parsing arbitrary JSX.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

LIVE_ROUTE_CANDIDATES = [
    "src/routes/blog.$slug.tsx",
    "src/routes/blog/$slug.tsx",
]


@dataclass(frozen=True)
class LivePost:
    slug: str
    title: str = ""
    description: str = ""
    headline: str = ""
    headings: list[str] = field(default_factory=list)
    faq_questions: list[str] = field(default_factory=list)
    source: str = ""

    def topic_text(self) -> str:
        return " ".join([self.slug.replace("-", " "), self.title, self.headline,
                         *self.headings, *self.faq_questions])


def _unescape(s: str) -> str:
    return (s.replace('\\"', '"').replace("\\'", "'")
             .replace("&ldquo;", '"').replace("&rdquo;", '"')
             .replace("&rsquo;", "'").replace("&amp;", "&"))


def _first_string_after(key: str, text: str) -> str:
    # Matches `key: "value"` allowing a newline + indentation before the string.
    m = re.search(key + r":\s*\n?\s*\"((?:[^\"\\]|\\.)*)\"", text)
    return _unescape(m.group(1)) if m else ""


def parse_inline_posts_text(tsx: str, source: str = "") -> list[LivePost]:
    posts: list[LivePost] = []

    # Section headings shared across all posts in this route (H2 helper usage).
    headings = [_unescape(h) for h in
                re.findall(r"<H2[^>]*>([^<]+)</H2>", tsx)]
    # FAQ questions from the FAQS array (`q: "..."`).
    faqs = [_unescape(q) for q in
            re.findall(r"\bq:\s*\n?\s*\"((?:[^\"\\]|\\.)*)\"", tsx)]

    # Each POSTS entry: `"<slug>": {` ... nearest title/description/headline.
    for m in re.finditer(r"\"([a-z0-9][a-z0-9-]{3,}?)\":\s*\{", tsx):
        slug = m.group(1)
        block = tsx[m.end():m.end() + 800]
        posts.append(LivePost(
            slug=slug,
            title=_first_string_after("title", block),
            description=_first_string_after("description", block),
            headline=_first_string_after("headline", block),
            headings=headings,
            faq_questions=faqs,
            source=source,
        ))
    return posts


def parse_live_posts(site_root: Path) -> list[LivePost]:
    for rel in LIVE_ROUTE_CANDIDATES:
        path = site_root / rel
        if path.exists():
            return parse_inline_posts_text(path.read_text(encoding="utf-8"), source=rel)
    return []
