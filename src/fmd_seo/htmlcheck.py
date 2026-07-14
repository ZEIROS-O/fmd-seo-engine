"""Raw-HTML verification: fetch a page without JavaScript and assert every
artifact a real article needs is present in the initial HTML response.

Used by the Phase 2 rendering spike and later by export verification.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser


class _Extractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.canonical = ""
        self.jsonld: list[str] = []
        self.links: list[str] = []
        self.images: list[dict] = []
        self.text_chars = 0
        self._in_title = False
        self._in_jsonld = False
        self._in_body = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self._in_title = True
        elif tag == "body":
            self._in_body = True
        elif tag == "link" and a.get("rel") == "canonical":
            self.canonical = a.get("href", "")
        elif tag == "script" and a.get("type") == "application/ld+json":
            self._in_jsonld = True
            self.jsonld.append("")
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "img":
            self.images.append({"src": a.get("src", ""), "alt": a.get("alt")})

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        elif tag == "script":
            self._in_jsonld = False

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        elif self._in_jsonld:
            self.jsonld[-1] += data
        elif self._in_body:
            self.text_chars += len(data.strip())


def fetch_raw(url: str, timeout_s: int = 15) -> tuple[int, str, str]:
    """GET without JS. Returns (status, final_url, body). Follows redirects."""
    req = urllib.request.Request(url, headers={"User-Agent": "fmd-seo-htmlcheck/1"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return resp.status, resp.url, resp.read().decode("utf-8", errors="replace")


def check_page(url: str, *, min_body_chars: int = 400, require_cta: bool = True) -> dict:
    """Run all raw-HTML checks against one URL. Returns {check: (verdict, detail)}."""
    results: dict[str, tuple[str, str]] = {}
    try:
        status, final_url, body = fetch_raw(url)
    except (urllib.error.URLError, TimeoutError, OSError) as err:
        return {"fetch": ("BLOCK", f"{url}: {err}")}
    results["fetch"] = ("PASS", f"{status} {final_url}")

    ex = _Extractor()
    ex.feed(body)

    results["title"] = ("PASS", ex.title.strip()) if ex.title.strip() else ("BLOCK", "no <title>")
    results["canonical"] = ("PASS", ex.canonical) if ex.canonical else ("BLOCK", "no canonical link")
    results["body_substantial"] = (
        ("PASS", f"{ex.text_chars} chars") if ex.text_chars >= min_body_chars
        else ("BLOCK", f"only {ex.text_chars} body chars (<{min_body_chars})")
    )

    valid_jsonld = 0
    for blob in ex.jsonld:
        try:
            json.loads(blob)
            valid_jsonld += 1
        except json.JSONDecodeError:
            pass
    results["structured_data"] = (
        ("PASS", f"{valid_jsonld} JSON-LD block(s)") if valid_jsonld
        else ("BLOCK", "no parseable application/ld+json")
    )

    internal = [href for href in ex.links if href.startswith("/")]
    results["internal_links"] = (
        ("PASS", f"{len(internal)} internal link(s)") if internal
        else ("BLOCK", "no internal links")
    )

    if require_cta:
        has_cta = bool(re.search(r"book|call|quote|schedule", body, re.IGNORECASE))
        results["cta"] = ("PASS", "CTA text present") if has_cta else ("BLOCK", "no CTA")

    missing_alt = [img["src"] for img in ex.images if not img.get("alt")]
    if not ex.images:
        results["image_metadata"] = ("BLOCK", "no images")
    elif missing_alt:
        results["image_metadata"] = ("BLOCK", f"images missing alt: {missing_alt}")
    else:
        results["image_metadata"] = ("PASS", f"{len(ex.images)} image(s) with alt")

    return results


def check_slash_variants(base_url: str, path: str, **kwargs) -> dict:
    """Fetch both slash variants; each must end 200 (directly or via redirect)
    and the trailing-slash variant must pass every content check."""
    results: dict[str, tuple[str, str]] = {}
    bare = base_url.rstrip("/") + "/" + path.strip("/")
    for label, url in (("bare", bare), ("slash", bare + "/")):
        try:
            status, final_url, _ = fetch_raw(url)
            ok = status == 200
            results[f"variant:{label}"] = (
                ("PASS", f"{status} -> {final_url}") if ok else ("BLOCK", f"{status} {final_url}")
            )
        except (urllib.error.URLError, TimeoutError, OSError) as err:
            results[f"variant:{label}"] = ("BLOCK", f"{url}: {err}")
    results.update(check_page(bare + "/", **kwargs))
    return results
