import json
from pathlib import Path

from fmd_seo.contracts import from_dict
from fmd_seo.semantic import semantic_review
from fmd_seo import slice as slice_module
from fmd_seo.slice import build_slice_package
from fmd_seo.verify import checks_pass, deterministic_checks


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "replay"


def _slice_facts(facts_file):
    text = facts_file.read_text(encoding="utf-8")
    facts_file.write_text(
        text.replace(
            '  phone: "(216) 359-1034"\n',
            '  phone: "(216) 359-1034"\n'
            '  positioning: "Interior-first mobile detailing for Cleveland\'s east side"\n',
        ),
        encoding="utf-8",
    )
    return facts_file


def test_recorded_query_evidence_replays_through_contract_and_slice(facts_file):
    evidence = []
    for path in sorted(FIXTURES.glob("ev-*.json")):
        item = from_dict("QueryEvidence", json.loads(path.read_text(encoding="utf-8")))
        evidence.append(item)

    package = build_slice_package(_slice_facts(facts_file), [item.evidence_id for item in evidence])
    checks = deterministic_checks(package)

    assert len(evidence) == 4
    assert {item.kind for item in evidence} == {
        "ai_response_snapshot", "serp_snapshot", "llm_mentions_baseline", "gbp_snapshot",
    }
    assert package.content["evidence_figures"] == [
        {"value": value, "evidence_id": "ev-ai_response_snapshot-9f5724aa0491"}
        for value in (40, 80, 100, 160, 190, 250, 300, 450, 600)
    ]
    assert "$50" not in json.dumps(package.content)
    assert checks_pass(checks)


def test_slice_does_not_bind_a_figure_from_a_larger_number(tmp_path, monkeypatch):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "ev-one.json").write_text(
        json.dumps({"answer": "The package costs $140"}), encoding="utf-8",
    )
    monkeypatch.setattr(slice_module.paths, "EVIDENCE_DIR", evidence)

    assert {item["value"] for item in slice_module._evidence_figures(["ev-one"])} == set()


def test_semantic_replay_accepts_only_exact_pass_sentinel(monkeypatch, facts_file):
    package = build_slice_package(_slice_facts(facts_file), ["fixture"])

    class FakeAdapter:
        def __init__(self, _repo):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def verifier_context(self):
            return {"voice.md": "Use direct, factual copy."}

    class Result:
        returncode = 0
        stdout = "analysis line\nSEMANTIC_PASS\n"

    monkeypatch.setattr("fmd_seo.semantic.OperatorAdapter", FakeAdapter)
    monkeypatch.setattr("fmd_seo.semantic.subprocess.run", lambda *_args, **_kwargs: Result())

    assert semantic_review(package, Path("/unused")) == (
        "PASS", "semantic checker passed",
    )
