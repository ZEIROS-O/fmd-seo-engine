"""Phase 3 vertical slice: build the one supporting-article PagePackage for
the query "car detailing prices cleveland".

Grounding rules: FMD-specific numbers come ONLY from the hash-bound fact
snapshot and are declared as claims; market figures come ONLY from fetched
QueryEvidence and are declared in evidence_figures with their evidence IDs.
"""

from __future__ import annotations

from pathlib import Path

from .contracts import PagePackage
from .facts import load_snapshot
from .receipts import now_iso

SLICE_INTENT_KEY = "supporting:car-detailing-prices-cleveland"

FACT_KEYS = [
    "identity.name",
    "identity.phone",
    "identity.positioning",
    "service_area.base",
    "service_area.places",
    "pricing.one_time.full_interior.price",
    "pricing.one_time.full_interior.duration_hours",
    "pricing.one_time.ultimate_interior.price",
    "pricing.one_time.ultimate_interior.duration_hours",
    "pricing.membership_per_visit.monthly",
    "pricing.membership_per_visit.bi_monthly",
    "pricing.membership_per_visit.quarterly",
    "pricing.neighbor_discount",
    "guarantee.name",
    "guarantee.summary",
    "autonomy.posting",
]


def build_slice_package(facts_file: Path, evidence_refs: list[str]) -> PagePackage:
    snapshot = load_snapshot(facts_file, FACT_KEYS)
    facts = snapshot.facts_used
    phone = facts["identity.phone"]
    p_full = facts["pricing.one_time.full_interior.price"]
    p_ult = facts["pricing.one_time.ultimate_interior.price"]
    h_full = facts["pricing.one_time.full_interior.duration_hours"]
    h_ult = facts["pricing.one_time.ultimate_interior.duration_hours"]
    m_mo = facts["pricing.membership_per_visit.monthly"]
    m_bi = facts["pricing.membership_per_visit.bi_monthly"]
    m_q = facts["pricing.membership_per_visit.quarterly"]
    neighbor = facts["pricing.neighbor_discount"]
    guarantee = facts["guarantee.name"]

    content = {
        "buyer_read": (
            "East-side Cleveland homeowner comparison-shopping detailing for the first "
            "time in a while; problem-aware and price-anchoring, wary of quote-only "
            "pricing and upsells; wants a straight local number before talking to anyone."
        ),
        "slug": "car-detailing-prices-cleveland",
        "title": "How Much Does Car Detailing Cost in Cleveland? (2026 Pricing Guide)",
        "description": (
            "Real 2026 car detailing prices in Cleveland: typical ranges by service "
            "type, what drives the cost up, and what a mobile interior detail "
            "actually costs on the east side."
        ),
        "canonical": "https://freshmobiledetail.com/blog/car-detailing-prices-cleveland",
        "date_published": "2026-07-14",
        "hero_image": {"src": "/icon-512.png", "alt": "Fresh Mobile Detailing logo"},
        "blocks": [
            {"type": "p", "text": (
                "Most car detailing in Cleveland runs between $80 and $600 depending on "
                "what you're getting: quick express details sit around $40–$100, "
                "interior-only details typically land between $190 and $300, and a full "
                "interior-plus-exterior detail on a sedan usually costs $250–$450. Those "
                "ranges come from the price lists Cleveland-area detailing shops publish "
                "on their own websites and listings, surveyed in July 2026 — they're the "
                "numbers you'd find yourself if you spent an evening comparing quotes."
            )},
            {"type": "h2", "text": "Cleveland detailing prices by service type"},
            {"type": "ul", "items": [
                "Express or quick detail: roughly $40–$100.",
                "Exterior-only detail: roughly $160–$300.",
                "Interior-only detail: roughly $190–$300.",
                "Full detail (interior + exterior): roughly $250–$450 for most sedans.",
                "Premium and coating packages: $450–$600 and up.",
            ]},
            {"type": "h2", "text": "What actually moves the price"},
            {"type": "ul", "items": [
                "Vehicle size — most Cleveland shops tier pricing from coupes up to full-size SUVs and trucks, often with a $50–$100 spread between the smallest and largest tier.",
                "Condition — heavy soiling and pet hair commonly add a surcharge at local shops.",
                "Mobile vs. shop — mobile detailers come to your driveway; some price that convenience in, others charge the same as a shop visit.",
            ]},
            {"type": "h2", "text": "What an interior detail costs on the east side"},
            {"type": "p", "text": (
                f"Fresh Mobile Detailing is an interior-first mobile service based in the "
                f"Beachwood / Mayfield Heights area. A Full Interior Detail is ${p_full} "
                f"and takes about {h_full} hours. The Ultimate Interior Detail is "
                f"${p_ult} and takes about {h_ult} hours. Membership visits bring the "
                f"per-visit price down: ${m_mo} monthly, ${m_bi} bi-monthly, or ${m_q} "
                f"quarterly, and booking alongside a neighbor takes ${neighbor} off. "
                f"Every job carries the {guarantee}: wow when you open the door, or you "
                f"don't pay."
            )},
            {"type": "h2", "text": "Is mobile detailing worth it in Cleveland?"},
            {"type": "p", "text": (
                "If you're east of the city — Beachwood, Solon, Orange, Pepper Pike, "
                "Shaker Heights and nearby — a mobile detailer works in your driveway "
                "while you keep your day. You skip the drop-off, the shuttle, and the "
                "waiting room, and the interior pricing above sits inside the typical "
                "Cleveland interior-detail range in this guide."
            )},
            {"type": "p", "text": (
                f"Want a firm number instead of a range? Call {phone} or book online."
            )},
        ],
        "internal_links": [
            {"href": "/", "label": "Home"},
            {"href": "/fresh-pro", "label": "Fresh Pro"},
        ],
        "cta": {"href": "/#booking", "label": "Book your interior detail"},
        "jsonld": {
            "@context": "https://schema.org",
            "@type": "BlogPosting",
            "headline": "How Much Does Car Detailing Cost in Cleveland? (2026 Pricing Guide)",
            "datePublished": "2026-07-14",
            "author": {"@type": "Organization", "name": facts["identity.name"]},
            "publisher": {"@type": "Organization", "name": facts["identity.name"]},
        },
        "claims": [
            {"fact_key": "identity.phone", "value": phone},
            {"fact_key": "pricing.one_time.full_interior.price", "value": p_full},
            {"fact_key": "pricing.one_time.full_interior.duration_hours", "value": h_full},
            {"fact_key": "pricing.one_time.ultimate_interior.price", "value": p_ult},
            {"fact_key": "pricing.one_time.ultimate_interior.duration_hours", "value": h_ult},
            {"fact_key": "pricing.membership_per_visit.monthly", "value": m_mo},
            {"fact_key": "pricing.membership_per_visit.bi_monthly", "value": m_bi},
            {"fact_key": "pricing.membership_per_visit.quarterly", "value": m_q},
            {"fact_key": "pricing.neighbor_discount", "value": neighbor},
            {"fact_key": "guarantee.name", "value": guarantee},
        ],
        "evidence_figures": [40, 50, 80, 100, 160, 190, 250, 300, 450, 600],
        "mentioned_places": [
            "Cleveland", "Beachwood", "Mayfield Heights", "Solon",
            "Orange", "Pepper Pike", "Shaker Heights",
        ],
    }

    return PagePackage.create(
        intent_key=SLICE_INTENT_KEY,
        tier="supporting-post",
        created_at=now_iso(),
        fact_snapshot=snapshot.to_dict(),
        evidence_refs=evidence_refs,
        content=content,
        internal_links=content["internal_links"],
        assets=[{
            "src": "/icon-512.png",
            "alt": "Fresh Mobile Detailing logo",
            "provenance": "pre-existing site asset in fresh-mobile-detailing public/",
        }],
    )
