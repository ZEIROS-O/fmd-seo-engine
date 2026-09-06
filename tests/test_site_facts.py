import pytest

from fmd_seo.brain import load_brain
from fmd_seo.observations import latest_observation
from fmd_seo.site_facts import (
    _render_llms,
    compare_fact_surface,
    compare_public_facts,
    generate_site_fact_files,
    public_fact_payload,
    sync_public_facts,
    verify_generated_fact_hash,
)
from fmd_seo.facts import load_snapshot


def test_generated_site_facts_are_hash_bound_and_omit_blocked_review_claim(tmp_path):
    facts = tmp_path / "business-facts.yaml"
    facts.write_text("""\
schema_version: 1
reviewed_at: 2026-08-01
review_after_days: 30
identity: {name: Fresh Mobile Detailing, phone: "(440) 555-1234"}
service_area: {base: Beachwood / Mayfield Heights, radius_miles: 30, places: [Beachwood, Solon]}
hours: {days: [Monday, Tuesday, Wednesday, Thursday, Friday, Saturday], opens: "08:00", closes: "18:00"}
services: {duration_hours: {min: 1.5, max: 4}, offered: [Full Interior Detail, Ultimate Interior Detail], exterior_add_on: exterior hand wash, not_offered: [PPF]}
fleet_discount: {available: true, applies_to: [fleet, multi_car]}
pricing:
  one_time: {full_interior: {price: 209, duration_hours: 2}, ultimate_interior: {price: 279, duration_hours: 3}}
  membership_per_visit: {monthly: 149, bi_monthly: 169, quarterly: 189}
  neighbor_discount: 25
guarantee: {name: Door-Open Guarantee, summary: "Wow or you do not pay", remedy_window_hours: 24}
claim_gates:
  review_count_public_claim: {allowed: false, unlock_at_reviews: 30}
equipment: {steamer: {owned: false}, ozone_machine: {owned: false}}
""", encoding="utf-8")
    site = tmp_path / "site"

    result = generate_site_fact_files(facts, site)

    generated = (site / "src/lib/business-facts.ts").read_text(encoding="utf-8")
    assert result["source_hash"] in generated
    assert '"fullInterior": 209' in generated
    assert '"phoneE164": "+14405551234"' in generated
    assert '"reviewCount"' not in generated
    assert (site / "public/llms.txt").exists()
    verified = verify_generated_fact_hash(facts, site / "src/lib/business-facts.ts")
    assert verified["source_hash"] == result["source_hash"]

    generated_path = site / "src/lib/business-facts.ts"
    generated_path.write_text(
        generated_path.read_text(encoding="utf-8").replace(
            '"phoneDisplay": "(440) 555-1234"',
            '"phoneDisplay": "(440) 555-9999"',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="generated facts payload mismatch"):
        verify_generated_fact_hash(facts, generated_path)


REMEDY_FACTS_TEMPLATE = """\
schema_version: 1
identity: {name: Fresh Mobile Detailing, phone: "(216) 359-1034"}
service_area: {base: Beachwood, radius_miles: 30, places: [Beachwood]}
hours: {days: [Monday], opens: "08:00", closes: "18:00"}
services: {duration_hours: {min: 1.5, max: 4}, offered: [The Interior Reset, The Deep Interior Reset], exterior_add_on: exterior hand wash, not_offered: [PPF]}
fleet_discount: {available: true, applies_to: [fleet]}
pricing:
  one_time: {full_interior: {price: 209, duration_hours: 2}, ultimate_interior: {price: 289, duration_hours: 3}}
  membership_per_visit: {monthly: 149, bi_monthly: 169, quarterly: 189}
  neighbor_discount: 25
guarantee: {name: Fresh Finish Guarantee, summary: "We make missed work right", public_statement: "We return and correct it", remedy_window_hours: %d}
claim_gates: {review_count_public_claim: {allowed: false}}
equipment: {steamer: {owned: false}, ozone_machine: {owned: false}}
"""


def test_fact_verification_blocks_llms_text_drift(tmp_path):
    """Editing published llms.txt copy away from the renderer must BLOCK."""
    facts = tmp_path / "business-facts.yaml"
    facts.write_text(REMEDY_FACTS_TEMPLATE % 24, encoding="utf-8")
    site = tmp_path / "site"
    generate_site_fact_files(facts, site)
    llms = site / "public/llms.txt"

    verified = verify_generated_fact_hash(facts, site / "src/lib/business-facts.ts")
    assert verified["generated_files"] == [
        str(site / "src/lib/business-facts.ts"), str(llms),
    ]

    llms.write_text(
        llms.read_text(encoding="utf-8").replace(
            "We return and correct it", "We return within 72 hours",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="llms.txt mismatch"):
        verify_generated_fact_hash(facts, site / "src/lib/business-facts.ts")


def test_llms_price_lines_bind_to_named_tiers_not_offered_order(tmp_path):
    """Reordering services.offered used to put the $209 line on whoever was first."""
    facts = tmp_path / "business-facts.yaml"
    swapped = (REMEDY_FACTS_TEMPLATE % 24).replace(
        "offered: [The Interior Reset, The Deep Interior Reset]",
        "offered: [The Deep Interior Reset, The Interior Reset, pet hair removal]",
    )
    facts.write_text(swapped, encoding="utf-8")
    llms = _render_llms(public_fact_payload(facts))

    assert "- The Interior Reset: From $209 (about 2 hours)" in llms
    assert "- The Deep Interior Reset: From $289 (about 3 hours)" in llms
    assert "- The Deep Interior Reset: From $209" not in llms
    assert "- The Interior Reset: From $289" not in llms


def test_remedy_window_is_internal_and_never_reaches_a_public_surface(tmp_path):
    """The guarantee publishes no time limit, but the field stays hash-bound.

    terms-of-service and cancellation-refund-policy commit to correcting missed
    work "before we leave, or as soon as reasonably possible after the
    appointment". Publishing a 24-hour window narrowed that, so no rendered
    surface may carry ``remedy_window_hours`` -- while the TypeScript payload
    still binds it so an unreviewed policy change cannot slip through.
    """
    facts = tmp_path / "business-facts.yaml"
    facts.write_text(REMEDY_FACTS_TEMPLATE % 24, encoding="utf-8")
    site = tmp_path / "site"
    generate_site_fact_files(facts, site)
    llms_before = (site / "public/llms.txt").read_text(encoding="utf-8")
    hash_before = public_fact_payload(facts)["sourceHash"]

    guarantee_line = next(
        line for line in llms_before.splitlines() if line.startswith("- Guarantee:")
    )
    assert "24" not in guarantee_line
    assert "hours" not in guarantee_line

    facts.write_text(REMEDY_FACTS_TEMPLATE % 72, encoding="utf-8")

    assert _render_llms(public_fact_payload(facts)) == llms_before
    # Unpublished is not unbound: the TypeScript payload still moves, so the
    # generated site file goes stale and verification blocks until regenerated.
    assert public_fact_payload(facts)["sourceHash"] != hash_before
    with pytest.raises(ValueError, match="generated facts payload mismatch"):
        verify_generated_fact_hash(facts, site / "src/lib/business-facts.ts")


def test_compare_public_facts_counts_hash_or_value_drift():
    expected = {"sourceHash": "abc", "facts": {"phone": "1", "price": 209}}
    assert compare_public_facts(expected, expected) == 0
    assert compare_public_facts(expected, {"sourceHash": "old", "facts": expected["facts"]}) == 1
    assert compare_public_facts(expected, {"sourceHash": "abc", "facts": {"phone": "2"}}) == 2


def test_public_payload_hash_ignores_review_date_but_snapshot_hash_does_not(tmp_path):
    facts = tmp_path / "facts.yaml"
    source = """\
schema_version: 1
source_last_updated: 2026-08-01
reviewed_at: 2026-08-01
review_after_days: 30
identity: {name: Fresh Mobile Detailing, phone: "(216) 359-1034"}
service_area: {base: Beachwood, radius_miles: 30, places: [Beachwood]}
hours: {days: [Monday], opens: "08:00", closes: "18:00"}
services: {duration_hours: {min: 1.5, max: 4}, offered: [Full Interior Detail, Ultimate Interior Detail], exterior_add_on: exterior hand wash, not_offered: [PPF]}
fleet_discount: {available: true, applies_to: [fleet]}
pricing:
  one_time: {full_interior: {price: 209, duration_hours: 2}, ultimate_interior: {price: 279, duration_hours: 3}}
  membership_per_visit: {monthly: 149, bi_monthly: 169, quarterly: 189}
  neighbor_discount: 25
guarantee: {name: Door-Open Guarantee, summary: "Wow or you do not pay", remedy_window_hours: 24}
claim_gates: {review_count_public_claim: {allowed: false}}
equipment: {steamer: {owned: false}, ozone_machine: {owned: false}}
"""
    facts.write_text(source, encoding="utf-8")
    public_before = public_fact_payload(facts)["sourceHash"]
    snapshot_before = load_snapshot(facts, ["identity.phone"]).source_hash

    facts.write_text(source.replace("reviewed_at: 2026-08-01", "reviewed_at: 2026-08-02"), encoding="utf-8")

    assert public_fact_payload(facts)["sourceHash"] == public_before
    assert load_snapshot(facts, ["identity.phone"]).source_hash != snapshot_before


def test_public_statement_is_hash_bound_and_falls_back_to_summary(tmp_path):
    facts = tmp_path / "facts.yaml"
    source = """\
schema_version: 1
identity: {name: Fresh Mobile Detailing, phone: "(216) 359-1034"}
service_area: {base: Beachwood, radius_miles: 30, places: [Beachwood]}
hours: {days: [Monday], opens: "08:00", closes: "18:00"}
services: {duration_hours: {min: 1.5, max: 4}, offered: [The Interior Reset, The Deep Interior Reset], exterior_add_on: exterior hand wash, not_offered: [PPF]}
fleet_discount: {available: true, applies_to: [fleet]}
pricing:
  one_time: {full_interior: {price: 209, duration_hours: 2}, ultimate_interior: {price: 289, duration_hours: 3}}
  membership_per_visit: {monthly: 149, bi_monthly: 169, quarterly: 189}
  neighbor_discount: 25
guarantee: {name: Fresh Finish Guarantee, summary: "We make missed work right", remedy_window_hours: 24}
claim_gates: {review_count_public_claim: {allowed: false}}
equipment: {steamer: {owned: false}, ozone_machine: {owned: false}}
"""
    facts.write_text(source, encoding="utf-8")

    fallback = public_fact_payload(facts)
    assert fallback["facts"]["guarantee"]["publicStatement"] == "We make missed work right"

    facts.write_text(
        source.replace(
            'summary: "We make missed work right",',
            'summary: "We make missed work right", public_statement: "We return and correct it",',
        ),
        encoding="utf-8",
    )
    explicit = public_fact_payload(facts)

    assert explicit["facts"]["guarantee"]["publicStatement"] == "We return and correct it"
    assert explicit["sourceHash"] != fallback["sourceHash"]


def test_compare_fact_surface_requires_hash_and_selected_values():
    expected = {
        "sourceHash": "abc123",
        "facts": {"phoneDisplay": "(216) 359-1034", "pricing": {"fullInterior": 209}},
    }
    assert compare_fact_surface(
        expected,
        '<main data-business-facts-source="abc123">Call (216) 359-1034. From $209.</main>',
        ["phoneDisplay", "pricing.fullInterior"],
    ) == []
    assert compare_fact_surface(expected, "stale", ["phoneDisplay"]) == [
        "sourceHash", "phoneDisplay",
    ]


def test_sync_public_facts_records_live_drift(tmp_path):
    facts = tmp_path / "business-facts.yaml"
    facts.write_text("""\
schema_version: 1
reviewed_at: 2026-08-01
review_after_days: 30
identity: {name: Fresh Mobile Detailing, phone: "(216) 359-1034"}
service_area: {base: Beachwood, radius_miles: 30, places: [Beachwood]}
hours: {days: [Monday, Tuesday, Wednesday, Thursday, Friday, Saturday], opens: "08:00", closes: "18:00"}
services: {duration_hours: {min: 1.5, max: 4}, offered: [Full Interior Detail, Ultimate Interior Detail], exterior_add_on: exterior hand wash, not_offered: [PPF]}
fleet_discount: {available: true, applies_to: [fleet, multi_car]}
pricing:
  one_time: {full_interior: {price: 209, duration_hours: 2}, ultimate_interior: {price: 279, duration_hours: 3}}
  membership_per_visit: {monthly: 149, bi_monthly: 169, quarterly: 189}
  neighbor_discount: 25
guarantee: {name: Door-Open Guarantee, summary: "Wow or you do not pay", remedy_window_hours: 24}
claim_gates: {review_count_public_claim: {allowed: false, unlock_at_reviews: 30}}
equipment: {steamer: {owned: false}, ozone_machine: {owned: false}}
""", encoding="utf-8")
    observations = tmp_path / "observations"
    expected = public_fact_payload(facts)
    observed = {**expected, "sourceHash": "deployed-old-hash"}

    result = sync_public_facts(
        {
            "paths": {"facts_file": str(facts)},
            "site": {"facts_url": "https://example.test/api/business-facts"},
        },
        load_brain(),
        observations_dir=observations,
        fetcher=lambda _url: observed,
    )

    assert result == {
        "status": "fetched",
        "url": "https://example.test/api/business-facts",
        "fact_mismatches": 1,
        "surfaces": [],
    }
    observation = latest_observation("site.facts_drift", observations)
    assert observation is not None
    assert observation.records == {"fact_mismatches": 1}


def test_verification_blocks_a_rewritten_derived_facts_export(tmp_path):
    """The payload literal is not the fact surface; the derived export is.

    `CityPage.tsx`, `chat.ts` and all four MCP tools import `BUSINESS_FACTS`,
    not `BUSINESS_FACTS_PAYLOAD`. Rewriting that one line to a literal carrying
    a wrong phone number and a $999 price used to return DONE, because
    verification only ever regex-parsed the payload object.
    """
    facts = tmp_path / "business-facts.yaml"
    facts.write_text(REMEDY_FACTS_TEMPLATE % 24, encoding="utf-8")
    site = tmp_path / "site"
    generate_site_fact_files(facts, site)
    generated_ts = site / "src/lib/business-facts.ts"

    original = generated_ts.read_text(encoding="utf-8")
    tampered = original.replace(
        "export const BUSINESS_FACTS = BUSINESS_FACTS_PAYLOAD.facts;",
        'export const BUSINESS_FACTS = { ...BUSINESS_FACTS_PAYLOAD.facts, '
        '"phoneDisplay": "(216) 555-0000", '
        '"pricing": { ...BUSINESS_FACTS_PAYLOAD.facts.pricing, "fullInterior": 999 } };',
    )
    assert tampered != original, "tamper fixture no longer matches the renderer"
    generated_ts.write_text(tampered, encoding="utf-8")

    # The payload literal is untouched, so the old regex/parse check passed.
    assert '"phoneDisplay": "(216) 359-1034"' in tampered

    with pytest.raises(ValueError, match="not byte-identical"):
        verify_generated_fact_hash(facts, generated_ts)


def test_rendered_fact_surfaces_match_the_pinned_site_files():
    """The templates are the site's copy, so template drift is copy drift.

    The generators are only trustworthy if rendering the reconciled facts
    reproduces the live files byte for byte. Without this, a narrower template
    silently emits a patch that reverts published copy -- which is exactly what
    `packages/patch-4391be8a9e3b0a20.json` did.

    The pinned rendered bytes live in-repo so this always asserts, including in
    CI where no site worktree is checked out. When the worktree *is* present,
    the second half proves the pins are still the site's live copy.
    """
    from pathlib import Path

    from fmd_seo.paths import load_config
    from fmd_seo.site_facts import _render_typescript

    fixtures = Path(__file__).resolve().parents[1] / "fixtures/facts"
    payload = public_fact_payload(fixtures / "business-facts-site-current.yaml")
    rendered_llms = _render_llms(payload)
    rendered_ts = _render_typescript(payload)

    assert rendered_llms == (fixtures / "llms-site-current.txt").read_text(encoding="utf-8")
    assert rendered_ts == (
        fixtures / "business-facts-site-current.ts"
    ).read_text(encoding="utf-8")

    site = Path((load_config().get("paths") or {}).get("site_worktree", ""))
    if not (site / "public/llms.txt").is_file():
        return

    assert rendered_llms == (site / "public/llms.txt").read_text(encoding="utf-8")
    assert rendered_ts == (
        site / "src/lib/business-facts.ts"
    ).read_text(encoding="utf-8")


def test_rendered_typescript_hash_matches_its_own_payload():
    """A payload whose sourceHash disagrees with its facts binds nothing."""
    import hashlib
    import json
    from pathlib import Path

    from fmd_seo.contracts import canonical_json
    from fmd_seo.site_facts import _render_typescript

    pinned = Path(__file__).resolve().parents[1] / "fixtures/facts/business-facts-site-current.yaml"
    rendered = _render_typescript(public_fact_payload(pinned))
    parsed = json.loads(rendered[rendered.index("{"): rendered.rindex("} as const;") + 1])

    assert parsed["sourceHash"] == hashlib.sha256(
        canonical_json(parsed["facts"]).encode("utf-8")
    ).hexdigest()
