"""Hash-bound loader for the Fresh-owned business facts authority.

Fresh-owned documents are the sole mutable business-fact authority; this module
only reads, hashes, and extracts. Missing or stale facts fail closed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import yaml

from .contracts import FactSnapshot
from .receipts import now_iso


class FactError(ValueError):
    pass


class FactMissing(FactError):
    pass


class FactsStale(FactError):
    pass


def days_until_stale(facts_file: Path, *, today: date | None = None) -> int:
    """Return calendar days remaining in the business-facts review window."""
    data = yaml.safe_load(facts_file.read_bytes())
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise FactError(f"Unsupported business-facts schema in {facts_file}")
    reviewed_at = date.fromisoformat(str(data["reviewed_at"]))
    deadline = reviewed_at + timedelta(days=int(data["review_after_days"]))
    return (deadline - (today or date.today())).days


def _dig(data: Any, dotted_key: str) -> Any:
    node = data
    for part in dotted_key.split("."):
        if isinstance(node, list):
            try:
                node = node[int(part)]
                continue
            except (ValueError, IndexError):
                raise FactMissing(f"Fact key not found: {dotted_key}")
        if not isinstance(node, dict) or part not in node:
            raise FactMissing(f"Fact key not found: {dotted_key}")
        node = node[part]
    return node


def load_snapshot(facts_file: Path, keys: list[str], *, today: date | None = None) -> FactSnapshot:
    raw = facts_file.read_bytes()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise FactError(f"Unsupported business-facts schema in {facts_file}")

    reviewed_at = date.fromisoformat(str(data["reviewed_at"]))
    review_after_days = int(data["review_after_days"])
    today = today or date.today()
    if today > reviewed_at + timedelta(days=review_after_days):
        raise FactsStale(
            f"business-facts reviewed_at {reviewed_at} is past its {review_after_days}-day window"
        )

    facts_used = {key: _dig(data, key) for key in keys}
    return FactSnapshot(
        canonical_path=str(facts_file),
        source_hash=hashlib.sha256(raw).hexdigest(),
        source_last_updated=str(data["source_last_updated"]),
        reviewed_at=str(data["reviewed_at"]),
        review_after_days=review_after_days,
        captured_at=now_iso(),
        facts_used=facts_used,
    )


def write_fact_snapshot_evidence(snapshot: FactSnapshot, directory: Path) -> str:
    """Persist a FactSnapshot as a committed evidence record.

    information_gain.evidence_ref must resolve through the evidence store, not
    by comparing a fact-snapshot:<hash> alias to the package's own snapshot.
    The id is derived from source_hash so a given facts file rewrites the same
    record rather than minting a new one each draft.
    """
    evidence_id = f"ev-fact-snapshot-{snapshot.source_hash[:12]}"
    payload = {
        "evidence_id": evidence_id,
        "kind": "fact_snapshot",
        "source_hash": snapshot.source_hash,
        "canonical_path": snapshot.canonical_path,
        "captured_at": snapshot.captured_at,
        "facts_used": snapshot.facts_used,
    }
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{evidence_id}.json"
    rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing.get("source_hash") != snapshot.source_hash:
            raise FactError(f"immutable evidence id collision: {evidence_id}")
        return evidence_id
    path.write_text(rendered, encoding="utf-8")
    return evidence_id


def verify_binding(snapshot: FactSnapshot) -> bool:
    """True if the source file still hashes to the snapshot's source_hash."""
    path = Path(snapshot.canonical_path)
    if not path.exists():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == snapshot.source_hash
