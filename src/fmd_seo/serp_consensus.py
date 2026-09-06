"""Deterministic consensus summaries over accessible top-ten winners."""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from typing import Any


class ConsensusUnavailable(ValueError):
    pass


def _percentile(values: list[int], fraction: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def _majority(rows: list[dict[str, Any]], key: str, minimum: int) -> list[str]:
    counts: Counter[str] = Counter()
    for row in rows:
        counts.update(set(str(value) for value in row.get(key) or []))
    return sorted(value for value, count in counts.items() if count >= minimum)


def build_consensus(query: str, winners: list[dict[str, Any]]) -> dict[str, Any]:
    accessible = [row for row in winners[:10] if row.get("accessible")]
    if len(accessible) < 6:
        raise ConsensusUnavailable(
            f"at least 6 accessible winners required; received {len(accessible)}"
        )
    minimum = math.ceil(len(accessible) * 0.5)
    page_types = Counter(str(row.get("page_type", "unknown")) for row in accessible)
    words = [int(row["word_count"]) for row in accessible if row.get("word_count") is not None]
    dates = [str(row["last_modified"]) for row in accessible if row.get("last_modified")]
    weakness = round(100 * sum(bool(row.get("weak")) for row in accessible) / len(accessible))
    payload: dict[str, Any] = {
        "schema_version": 1,
        "query": query,
        "accessible_winners": len(accessible),
        "dominant_page_type": page_types.most_common(1)[0][0],
        "page_type_distribution": dict(sorted(page_types.items())),
        "repeated_headings": _majority(accessible, "headings", minimum),
        "repeated_entities": _majority(accessible, "entities", minimum),
        "repeated_schema": _majority(accessible, "schema", minimum),
        "repeated_surfaces": _majority(accessible, "surfaces", minimum),
        "content_depth": {
            "p25": _percentile(words, 0.25),
            "p50": _percentile(words, 0.50),
            "p75": _percentile(words, 0.75),
        },
        "freshness": {"known_dates": len(dates), "unknown_dates": len(accessible) - len(dates)},
        "weakness_score_version": 1,
        "weakness_score": weakness,
        "winners": accessible,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    payload["artifact_id"] = f"serp-consensus-{digest[:16]}"
    return payload
