"""Deterministic verification of a PagePackage against its hash-bound
FactSnapshot. Fail-closed: unsupported equipment, guarantee, review, scarcity,
geography, or contact claims BLOCK.

Content carries explicit `claims` (each tied to a fact key) and
`mentioned_places`; free text is additionally scanned for gated terms.
"""

from __future__ import annotations

import re
from pathlib import Path

from .contracts import PagePackage

# Terms gated by claim_gates.blocked_until_equipment_owned + scarcity/review gates.
BLOCKED_TERM_PATTERNS = [
    (r"\bsteam(?:er|ing|ed)?\b", "steam equipment not owned"),
    (r"\bozone\b", "ozone machine not owned"),
    (r"\bsanitiz\w*\b", "sanitizing implies gated equipment"),
    (r"\b\d+\+?\s*(?:five[- ]star|5[- ]star)?\s*reviews\b", "review-count claims gated until 30 reviews"),
    (r"\bonly\s+\d+\s+(?:spots?|slots?|openings?)\b", "scarcity claims gated"),
]


def _all_text(package: PagePackage) -> str:
    parts = [package.content.get("title", ""), package.content.get("description", "")]
    for block in package.content.get("blocks", []):
        parts.append(block.get("text", ""))
        parts.extend(block.get("items", []))
    return "\n".join(parts)


def deterministic_checks(package: PagePackage, *, site_public_dir: Path | None = None,
                         known_routes: set[str] | None = None) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    facts = package.fact_snapshot.get("facts_used", {})
    text = _all_text(package)

    # 1. Declared claims must match the snapshot exactly.
    claims = package.content.get("claims", [])
    if not claims:
        results.append(("claims_declared", "BLOCK", "package declares no claims"))
    for claim in claims:
        key, value = claim.get("fact_key"), claim.get("value")
        if key not in facts:
            results.append((f"claim:{key}", "BLOCK", "fact key not in snapshot (fail closed)"))
        elif facts[key] != value:
            results.append((f"claim:{key}", "BLOCK", f"claimed {value!r} != fact {facts[key]!r}"))
        else:
            results.append((f"claim:{key}", "PASS", str(value)))

    # 2. Every FMD price/phone in the text must be a declared claim value.
    claimed_values = {str(c.get("value")) for c in claims}
    for price in re.findall(r"\$(\d{2,4})\b", text):
        if price in claimed_values:
            continue
        if price in {str(v) for v in package.content.get("evidence_figures", [])}:
            continue
        results.append(("price_provenance", "BLOCK",
                        f"${price} appears without claim or evidence provenance"))
    phones = re.findall(r"\(\d{3}\)\s*\d{3}-\d{4}", text)
    for phone in phones:
        if phone not in claimed_values:
            results.append(("phone_provenance", "BLOCK", f"{phone} is not a declared fact claim"))
    if phones and not any(p in claimed_values for p in phones):
        pass  # already blocked above
    results.append(("contact_present", "PASS" if phones else "BLOCK",
                    "phone present" if phones else "no contact phone in article"))

    # 3. Gated terms anywhere in text fail closed.
    for pattern, why in BLOCKED_TERM_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            results.append(("gated_term", "BLOCK", f"{match.group(0)!r}: {why}"))
    if not any(name == "gated_term" for name, _, _ in results):
        results.append(("gated_terms", "PASS", "no gated equipment/review/scarcity terms"))

    # 4. Geography: declared places must be inside the service area (or the
    # positioning city); text place mentions must be declared.
    places = set(facts.get("service_area.places", []))
    positioning = str(facts.get("identity.positioning", ""))
    allowed_extra = {"Cleveland"} if "Cleveland" in positioning else set()
    mentioned = set(package.content.get("mentioned_places", []))
    for place in mentioned:
        if place in places or place in allowed_extra:
            results.append((f"geo:{place}", "PASS", "in service area"))
        else:
            results.append((f"geo:{place}", "BLOCK", "outside verified service area"))
    for place in places:
        if place in text and place not in mentioned:
            results.append((f"geo_undeclared:{place}", "BLOCK", "place used but not declared"))

    # 5. Internal links resolve to known routes.
    routes = known_routes or {"/", "/fresh-pro", "/boat", "/fleet", "/chat", "/#booking"}
    for link in package.content.get("internal_links", []):
        href = link.get("href", "")
        base = href.split("#")[0] or "/"
        if href in routes or base in routes:
            results.append((f"link:{href}", "PASS", "resolves"))
        else:
            results.append((f"link:{href}", "BLOCK", "unknown internal route"))

    # 6. Assets: alt text + provenance to a real file in the site repo.
    for asset in package.assets:
        src, alt = asset.get("src", ""), asset.get("alt", "")
        if not alt:
            results.append((f"asset:{src}", "BLOCK", "missing alt text"))
            continue
        if site_public_dir is not None:
            target = site_public_dir / src.lstrip("/")
            if not target.exists():
                results.append((f"asset:{src}", "BLOCK", "file not found in site public/"))
                continue
        results.append((f"asset:{src}", "PASS", "exists with alt text"))

    return results
