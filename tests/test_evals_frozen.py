"""Critical audit constraints cannot change without a dated logged update."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EVALS = ROOT / "evals"


def _digest() -> str:
    digest = hashlib.sha256()
    files = sorted([
        * (EVALS / "invariants").glob("**/*"),
        * (EVALS / "10-must-pass").glob("**/*"),
    ])
    for path in files:
        if not path.is_file():
            continue
        digest.update(str(path.relative_to(EVALS)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def test_frozen_constraints_match_logged_digest():
    manifest = json.loads(
        (EVALS / "90-meta" / "frozen-digests.json").read_text(encoding="utf-8")
    )
    changelog = (EVALS / "90-meta" / "changelog.md").read_text(encoding="utf-8")

    assert _digest() == manifest["sha256"]
    assert f"## {manifest['updated_at']}" in changelog
    assert manifest["sha256"] in changelog
    spend_baseline = ROOT / "state" / "spend-reconciliation-baseline.json"
    spend_digest = hashlib.sha256(spend_baseline.read_bytes()).hexdigest()
    assert spend_digest == manifest["spend_baseline_sha256"]
    assert spend_digest in changelog


def test_grandfathered_observation_allowlist_can_only_shrink():
    current = set(json.loads(
        (EVALS / "grandfathered.json").read_text(encoding="utf-8")
    )["observations"])
    ceiling = set(json.loads(
        (EVALS / "90-meta" / "grandfathered-ceiling.json").read_text(encoding="utf-8")
    )["observations"])

    assert current <= ceiling
