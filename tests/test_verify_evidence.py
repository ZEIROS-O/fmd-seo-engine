import json

from fmd_seo.contracts import PagePackage
from fmd_seo.verify import deterministic_checks


def _package(evidence_id: str, *, jsonld: dict | None = None) -> PagePackage:
    return PagePackage.create(
        intent_key="evidence-test",
        tier="supporting-post",
        created_at="2026-08-02T00:00:00+00:00",
        fact_snapshot={
            "source_hash": "hash",
            "facts_used": {
                "identity.phone": "(216) 359-1034",
                "identity.positioning": "Cleveland",
                "service_area.places": [],
            },
        },
        evidence_refs=["ev-good"],
        content={
            "title": "Evidence test",
            "description": "Call (216) 359-1034",
            "blocks": [],
            "claims": [{"fact_key": "identity.phone", "value": "(216) 359-1034"}],
            "evidence_figures": [{"value": 40, "evidence_id": evidence_id}],
            "cta": {"label": "Compare the $40 market floor", "href": "/"},
            "jsonld": jsonld or {},
            "mentioned_places": [],
            "internal_links": [],
        },
        internal_links=[],
        assets=[{"src": "/image.png", "alt": "Plain image"}],
    )


def test_evidence_figure_requires_referenced_existing_evidence(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "ev-good.json").write_text(
        json.dumps({"answer": "Express details start at $40"}), encoding="utf-8",
    )

    valid = deterministic_checks(_package("ev-good"), evidence_dir=evidence)
    unreferenced = deterministic_checks(_package("ev-other"), evidence_dir=evidence)
    missing = deterministic_checks(_package("ev-good"), evidence_dir=tmp_path / "missing")

    assert not any(name == "price_provenance" and verdict == "BLOCK" for name, verdict, _ in valid)
    assert any("not in package.evidence_refs" in detail for name, verdict, detail in unreferenced if name == "price_provenance" and verdict == "BLOCK")
    assert any("evidence file is missing" in detail for name, verdict, detail in missing if name == "price_provenance" and verdict == "BLOCK")


def test_evidence_id_cannot_be_a_glob_pattern(tmp_path):
    """A wildcard id would otherwise bind a figure to an arbitrary file."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "ev-good.json").write_text(
        json.dumps({"answer": "Express details start at $40"}), encoding="utf-8",
    )
    package = _package("*")
    package.evidence_refs.append("*")  # declared, so the refs gate alone passes

    checks = deterministic_checks(package, evidence_dir=evidence)

    assert any(
        name == "price_provenance" and verdict == "BLOCK" and "evidence file is missing" in detail
        for name, verdict, detail in checks
    )


def test_bare_numeric_price_in_jsonld_needs_provenance(tmp_path):
    """Schema.org states prices without a `$`, so the currency scan never sees them."""
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "ev-good.json").write_text(
        json.dumps({"answer": "Express details start at $40"}), encoding="utf-8",
    )
    offer = {"@type": "Offer", "priceCurrency": "USD", "price": 399}

    checks = deterministic_checks(
        _package("ev-good", jsonld={"@type": "Service", "offers": offer}),
        evidence_dir=evidence,
    )

    assert any(
        name == "jsonld_price_provenance" and verdict == "BLOCK" and "399" in detail
        for name, verdict, detail in checks
    )


def test_evidence_figure_requires_an_exact_numeric_token(tmp_path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "ev-good.json").write_text(
        json.dumps({"answer": "A larger package costs $140"}), encoding="utf-8",
    )

    checks = deterministic_checks(_package("ev-good"), evidence_dir=evidence)

    assert any(
        name == "price_provenance" and verdict == "BLOCK"
        for name, verdict, _detail in checks
    )
