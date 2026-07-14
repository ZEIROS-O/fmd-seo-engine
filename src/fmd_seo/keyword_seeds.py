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
