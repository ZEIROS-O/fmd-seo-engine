from datetime import date, timedelta

import pytest

from fmd_seo.facts import (
    FactMissing,
    FactsStale,
    days_until_stale,
    load_snapshot,
    verify_binding,
)

TODAY = date.today()


def test_snapshot_extracts_only_requested_keys(facts_file):
    snap = load_snapshot(facts_file, ["identity.name", "pricing.one_time.full_interior.price"], today=TODAY)
    assert snap.facts_used == {
        "identity.name": "Fresh Mobile Detailing",
        "pricing.one_time.full_interior.price": 209,
    }
    assert len(snap.source_hash) == 64


def test_missing_key_fails_closed(facts_file):
    with pytest.raises(FactMissing):
        load_snapshot(facts_file, ["equipment.ozone_machine.owned"], today=TODAY)


def test_stale_review_blocks(facts_file):
    with pytest.raises(FactsStale):
        load_snapshot(facts_file, ["identity.name"], today=TODAY + timedelta(days=31))


def test_days_until_stale_exposes_warning_and_deadline_boundaries(facts_file):
    assert days_until_stale(facts_file, today=TODAY + timedelta(days=23)) == 7
    assert days_until_stale(facts_file, today=TODAY + timedelta(days=30)) == 0
    assert days_until_stale(facts_file, today=TODAY + timedelta(days=31)) == -1


def test_hash_binding_detects_source_change(facts_file):
    snap = load_snapshot(facts_file, ["identity.name"], today=TODAY)
    assert verify_binding(snap)
    facts_file.write_text(facts_file.read_text().replace("209", "219"), encoding="utf-8")
    assert not verify_binding(snap)


def test_real_facts_file_loads_if_present():
    from pathlib import Path
    real = Path("/mnt/c/Users/lucas/OneDrive/Documents/Cowork Detailing Folder/business-facts.yaml")
    if not real.exists():
        pytest.skip("real facts file not mounted")
    snap = load_snapshot(real, ["autonomy.posting"], today=TODAY)
    assert snap.facts_used["autonomy.posting"] == "human_only"
