from fmd_seo.brain import load_brain
from fmd_seo.observations import latest_observation
from fmd_seo.site_facts import (
    compare_fact_surface,
    compare_public_facts,
    generate_site_fact_files,
    public_fact_payload,
    sync_public_facts,
)


def test_generated_site_facts_are_hash_bound_and_omit_blocked_review_claim(tmp_path):
    facts = tmp_path / "business-facts.yaml"
    facts.write_text("""\
schema_version: 1
reviewed_at: 2026-08-01
review_after_days: 30
identity: {name: Fresh Mobile Detailing, phone: "(440) 555-1234"}
service_area: {base: Beachwood / Mayfield Heights, radius_miles: 30, places: [Beachwood, Solon]}
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


def test_compare_public_facts_counts_hash_or_value_drift():
    expected = {"sourceHash": "abc", "facts": {"phone": "1", "price": 209}}
    assert compare_public_facts(expected, expected) == 0
    assert compare_public_facts(expected, {"sourceHash": "old", "facts": expected["facts"]}) == 1
    assert compare_public_facts(expected, {"sourceHash": "abc", "facts": {"phone": "2"}}) == 2


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
