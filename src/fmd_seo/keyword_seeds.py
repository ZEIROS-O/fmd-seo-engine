"""Seed keyword list for the one Google Ads search-volume request.

Google Ads charges the same for 1 keyword or 1000, so we build the widest
defensible list in a single call. Seeds are grounded in:
  - the head terms GSC proves people actually type (car/auto/mobile detailing,
    "near me", suburb names) — the site currently uses none of "car"/"auto";
  - the verified service area in business-facts.yaml;
  - the pain topics the live blog post and FMD's own positioning already own
    (salt, pet hair, odor, interior).
"""

from __future__ import annotations

import re

# Head terms — GSC shows searchers use "car"/"auto"/"mobile" + "detailing".
SERVICE_TERMS = [
    "car detailing",
    "auto detailing",
    "mobile detailing",
    "mobile car detailing",
    "mobile auto detailing",
    "interior car detailing",
    "car interior cleaning",
    "car detailing prices",
]

# business-facts.yaml service_area.places (+ the metro anchor).
PLACES = [
    "cleveland", "beachwood", "mayfield heights", "lyndhurst", "pepper pike",
    "orange", "solon", "shaker heights", "university heights", "cleveland heights",
    "chagrin falls", "moreland hills", "gates mills", "highland heights",
    "south euclid", "mentor", "willoughby", "euclid", "wickliffe", "bedford",
    "twinsburg", "hudson",
]

# One shared classification taxonomy for PDF extraction and queue SERP results.
# Include both the canonical business-facts spelling ("Orange") and the legacy
# campaign spelling ("Orange Village") so old and new evidence classify alike.
CLASSIFICATION_SUBURBS = tuple(dict.fromkeys([
    *PLACES,
    "orange village", "richmond heights", "aurora", "streetsboro",
    "warrensville",
]))

CLASSIFICATION_SERVICE_TERMS = (
    "detail", "car wash", "interior clean", "car clean", "vehicle clean",
    "ceramic", "paint correction", "odor", "pet hair", "seat shampoo",
    "headlight", "wax", "polish", "scratch", "stain", "rust proof",
)

INFO_PREFIXES = (
    "how ", "what ", "why ", "when ", "where ", "which ", "can ",
    "does ", "do ", "is ", "are ", "should ", "tips ",
)


def classify(keyword: str) -> dict[str, bool]:
    value = keyword.casefold()
    branded = value.startswith("fresh ") or "fresh mobile" in value
    return {
        "branded": branded,
        "non_branded": not branded,
        "near_me": bool(re.search(
            r"\bnear me\b|\bnearby\b|\bin my area\b|\baround me\b", value,
        )),
        "cleveland": "cleveland" in value,
        "suburb": any(term in value for term in CLASSIFICATION_SUBURBS),
        "service": any(term in value for term in CLASSIFICATION_SERVICE_TERMS),
        "informational": (
            value.startswith(INFO_PREFIXES)
            or any(term in value for term in (
                " cost", " price", " prices", "best ", " vs ", "how much",
            ))
        ),
    }

# Problem-aware / buyer-intent topics FMD genuinely serves (interior-first).
PAIN_TERMS = [
    "car pet hair removal",
    "pet hair removal car interior",
    "remove pet hair from car",
    "car salt stain removal",
    "remove salt stains from car carpet",
    "car odor removal",
    "remove smell from car interior",
    "car upholstery cleaning",
    "car carpet cleaning",
    "car seat cleaning service",
    "car interior detailing cost",
    "how much does car detailing cost",
    "interior detailing cost",
    "car detailing cost",
    "is mobile detailing worth it",
    "how often should you detail your car",
    "car interior deep cleaning",
    "steam clean car interior",
    "car detailing membership",
    "monthly car cleaning service",
]

NEAR_ME_SUFFIXES = ["near me"]

BRAND_TERMS = [
    "fresh mobile detailing",
    "fresh car detailing",
    "fresh mobile detail",
    "freshmobiledetail",
]


def build_seeds(max_keywords: int = 1000) -> list[str]:
    seeds: list[str] = []

    def add(kw: str) -> None:
        kw = " ".join(kw.split()).lower()
        if kw and kw not in seeds:
            seeds.append(kw)

    # Bare head terms.
    for term in SERVICE_TERMS:
        add(term)
    # "near me" — the shape GSC shows converting.
    for term in SERVICE_TERMS:
        for suffix in NEAR_ME_SUFFIXES:
            add(f"{term} {suffix}")
    # Service x place — the money-page vocabulary.
    for term in SERVICE_TERMS:
        for place in PLACES:
            add(f"{term} {place}")
    # Place-led variants for the primary cluster.
    for place in PLACES:
        add(f"detailing {place}")
        add(f"car wash {place}")
    for term in PAIN_TERMS:
        add(term)
    for term in BRAND_TERMS:
        add(term)

    return seeds[:max_keywords]
