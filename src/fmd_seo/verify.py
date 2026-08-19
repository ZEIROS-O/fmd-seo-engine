"""Deterministic verification of a PagePackage against its hash-bound
FactSnapshot. Fail-closed: unsupported equipment, guarantee, review, scarcity,
geography, or contact claims BLOCK.

Content carries explicit `claims` (each tied to a fact key) and
`mentioned_places`; free text is additionally scanned for gated terms.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import paths
from .contracts import PagePackage

# Terms gated by claim_gates.blocked_until_equipment_owned + scarcity/review gates.
BLOCKED_TERM_PATTERNS = [
    (r"\bsteam(?:er|ing|ed)?\b", "steam equipment not owned"),
    (r"\bozone\b", "ozone machine not owned"),
    (r"\bsanitiz\w*\b", "sanitizing implies gated equipment"),
    (r"\b\d+\+?\s*(?:five[- ]star|5[- ]star)?\s*reviews\b", "review-count claims gated until 30 reviews"),
    (r"\bonly\s+\d+\s+(?:spots?|slots?|openings?)\b", "scarcity claims gated"),
]


def checks_pass(results: list[tuple[str, str, str]]) -> bool:
    """Aggregate deterministic checks; one BLOCK makes the package ineligible."""
    return bool(results) and all(verdict != "BLOCK" for _, verdict, _ in results)


def _all_text(package: PagePackage) -> str:
    parts = [package.content.get("title", ""), package.content.get("description", "")]
    for block in package.content.get("blocks", []):
        parts.append(block.get("text", ""))
        parts.extend(block.get("items", []))
    parts.append(json.dumps(package.content.get("jsonld") or {}, ensure_ascii=False))
    parts.append(str((package.content.get("cta") or {}).get("label", "")))
    parts.extend(str(asset.get("alt", "")) for asset in package.assets)
    return "\n".join(str(part) for part in parts)


# Content-addressed evidence ids only. Anything else could reach rglob as a
# wildcard and bind a figure to whatever file the filesystem happens to yield.
EVIDENCE_ID_PATTERN = re.compile(r"\A[A-Za-z0-9_-]+\Z")

# Schema.org carries prices as bare numerics, so the `$N` scan never sees them.
JSONLD_PRICE_KEYS = {"price", "lowprice", "highprice", "minprice", "maxprice", "pricerange"}


def _resolve_evidence(evidence_id: str, evidence_dir: Path) -> Path | None:
    """Resolve one committed evidence record by exact content-addressed ID."""
    if not EVIDENCE_ID_PATTERN.match(evidence_id):
        return None
    # Sorted so a duplicated id across subdirectories resolves deterministically.
    return next(iter(sorted(evidence_dir.rglob(f"{evidence_id}.json"))), None)


def _resolve_verified_evidence(
    evidence_id: str, evidence_dir: Path,
) -> tuple[dict | None, str]:
    """Resolve exactly one JSON record whose declared ID matches its filename."""
    if not EVIDENCE_ID_PATTERN.match(evidence_id):
        return None, f"unsafe evidence id: {evidence_id or '<missing>'}"
    matches = sorted(evidence_dir.rglob(f"{evidence_id}.json"))
    if not matches:
        return None, f"{evidence_id} evidence file is missing"
    if len(matches) != 1:
        return None, f"multiple evidence files resolve {evidence_id}"
    try:
        payload = json.loads(matches[0].read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as err:
        return None, f"{evidence_id} evidence file is unreadable: {err}"
    if not isinstance(payload, dict):
        return None, f"{evidence_id} evidence record must be an object"
    if payload.get("evidence_id") != evidence_id:
        return None, (
            f"evidence record id {payload.get('evidence_id')!r} does not match {evidence_id}"
        )
    return payload, f"bound to {evidence_id}"


def _jsonld_price_values(node: object) -> list[str]:
    """Every numeric value sitting under a price-bearing schema.org key."""
    found: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if str(key).lower() in JSONLD_PRICE_KEYS:
                for token in re.findall(r"\d{2,4}", str(value)):
                    found.append(token)
            found.extend(_jsonld_price_values(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_jsonld_price_values(item))
    return found


def contains_currency_token(text: str, value: str | int) -> bool:
    """Return true only for an explicit dollar figure of the requested value."""
    return re.search(
        rf"\$\s*{re.escape(str(value))}(?!\d)", text,
    ) is not None


def _figure_evidence(
    package: PagePackage,
    value: str,
    evidence_dir: Path,
) -> tuple[bool, str]:
    entries = package.content.get("evidence_figures") or []
    matching = [entry for entry in entries if isinstance(entry, dict) and str(entry.get("value")) == value]
    if not matching:
        return False, "no evidence_figures entry"
    referenced = set(package.evidence_refs)
    failures: list[str] = []
    for entry in matching:
        evidence_id = str(entry.get("evidence_id") or "")
        if evidence_id not in referenced:
            failures.append(f"{evidence_id or '<missing id>'} is not in package.evidence_refs")
            continue
        evidence_path = _resolve_evidence(evidence_id, evidence_dir)
        if evidence_path is None:
            failures.append(f"{evidence_id} evidence file is missing")
            continue
        try:
            evidence_text = evidence_path.read_text(encoding="utf-8", errors="replace")
        except OSError as err:  # unreadable evidence proves nothing - fail closed
            failures.append(f"{evidence_id} evidence file is unreadable: {err}")
            continue
        if not contains_currency_token(evidence_text, value):
            failures.append(f"{evidence_id} does not contain {value}")
            continue
        return True, f"bound to {evidence_id}"
    return False, "; ".join(failures)


def deterministic_checks(package: PagePackage, *, site_public_dir: Path | None = None,
                         known_routes: set[str] | None = None,
                         evidence_dir: Path | None = None) -> list[tuple[str, str, str]]:
    results: list[tuple[str, str, str]] = []
    facts = package.fact_snapshot.get("facts_used", {})
    text = _all_text(package)

    # PagePackage v2's information-gain declaration is meaningful only if the
    # named committed artifact resolves uniquely and identifies itself.
    if package.schema_version >= 2:
        gain_ref = str((package.information_gain or {}).get("evidence_ref", ""))
        _record, detail = _resolve_verified_evidence(
            gain_ref, evidence_dir or paths.EVIDENCE_DIR,
        )
        results.append((
            "information_gain_evidence",
            "PASS" if _record is not None else "BLOCK",
            detail,
        ))

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
    scanned = re.findall(r"\$(\d{2,4})\b", text)
    for price in scanned:
        if price in claimed_values:
            continue
        proven, detail = _figure_evidence(package, price, evidence_dir or paths.EVIDENCE_DIR)
        if proven:
            continue
        results.append(("price_provenance", "BLOCK",
                        f"${price} appears without resolved evidence provenance: {detail}"))
    # Structured data states prices without a currency symbol, so it needs its
    # own pass or a figure can hide in JSON-LD that the `$N` scan cannot see.
    already_scanned = set(scanned)
    for price in _jsonld_price_values(package.content.get("jsonld") or {}):
        if price in claimed_values or price in already_scanned:
            continue
        already_scanned.add(price)
        proven, detail = _figure_evidence(package, price, evidence_dir or paths.EVIDENCE_DIR)
        if proven:
            continue
        results.append(("jsonld_price_provenance", "BLOCK",
                        f"jsonld price {price} lacks resolved evidence provenance: {detail}"))
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
