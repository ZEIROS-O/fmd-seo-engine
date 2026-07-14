import pytest

from fmd_seo import contracts
from fmd_seo.contracts import (
    ContractError, ExportManifest, FactSnapshot, PagePackage, QueryEvidence,
    RunReceipt, from_dict, load_package, write_package,
)


def _package(**overrides):
    kwargs = dict(
        intent_key="interior-detailing-solon",
        tier="supporting-post",
        created_at="2026-07-14T00:00:00+00:00",
        fact_snapshot={"source_hash": "abc"},
        evidence_refs=["ev-1"],
        content={"title": "T", "slug": "t", "meta": {}, "body_blocks": [], "schema_jsonld": {}},
        internal_links=[],
        assets=[],
    )
    kwargs.update(overrides)
    return PagePackage.create(**kwargs)


def test_round_trips():
    fs = FactSnapshot("p", "h", "2026-07-04", "2026-07-12", 30, "now", {"a": 1})
    qe = QueryEvidence("ev-1", "serp_snapshot", "q", "now", "/v3/serp", {"items": []}, "rawhash", 0.01)
    rr = RunReceipt("r1", "DONE", "t0", "t1", "preflight", 1, [], 0.0, [], None, {})
    em = ExportManifest("pp-x", "hash", ["a.html"], "https://x/blog/t/", "sha", "base", "now")
    for name, obj in [("FactSnapshot", fs), ("QueryEvidence", qe), ("RunReceipt", rr), ("ExportManifest", em)]:
        assert from_dict(name, obj.to_dict()) == obj
    pkg = _package()
    assert from_dict("PagePackage", pkg.to_dict()) == pkg


def test_invalid_enums_rejected():
    with pytest.raises(ContractError):
        QueryEvidence("e", "bogus_kind", "q", "t", "ep", {}, "r", 0.0)
    with pytest.raises(ContractError):
        RunReceipt("r", "MAYBE", "t0", "t1", "c", 1, [], 0.0, [], None, {})
    with pytest.raises(ContractError):
        _package(tier="landing-page")


def test_schema_version_enforced():
    data = _package().to_dict()
    data["schema_version"] = 99
    with pytest.raises(ContractError):
        from_dict("PagePackage", data)


def test_package_id_deterministic_and_content_bound():
    a, b = _package(), _package()
    assert a.package_id == b.package_id
    c = _package(content={"title": "Other", "slug": "t", "meta": {}, "body_blocks": [], "schema_jsonld": {}})
    assert c.package_id != a.package_id


def test_package_immutable_on_disk(tmp_path):
    pkg = _package()
    path = write_package(pkg, tmp_path)
    assert write_package(pkg, tmp_path) == path  # identical rewrite is a no-op
    tampered = path.read_text().replace('"title":"T"', '"title":"X"')
    path.write_text(tampered)
    with pytest.raises(ContractError):
        write_package(_package(content={"title": "T", "slug": "t", "meta": {}, "body_blocks": [], "schema_jsonld": {}}), tmp_path)
    with pytest.raises(ContractError):  # tampered file fails ID re-derivation on load
        load_package(path)


def test_canonical_json_stable():
    assert contracts.canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'
