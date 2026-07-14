"""Hash-bound loader for the Fresh-owned business facts authority.

Fresh-owned documents are the sole mutable business-fact authority; this module
only reads, hashes, and extracts. Missing or stale facts fail closed.
"""

from __future__ import annotations

import hashlib
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


def verify_binding(snapshot: FactSnapshot) -> bool:
    """True if the source file still hashes to the snapshot's source_hash."""
    path = Path(snapshot.canonical_path)
    if not path.exists():
        return False
    return hashlib.sha256(path.read_bytes()).hexdigest() == snapshot.source_hash
