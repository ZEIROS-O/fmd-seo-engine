"""Review-floor and velocity derivation with explicit missing measurements."""

from __future__ import annotations

from datetime import datetime, timezone
from statistics import median
from typing import Any


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def derive_review_velocity(
    current: dict[str, Any],
    history: list[dict[str, Any]],
) -> dict[str, int | float | None]:
    observed = _time(current["observed_at"])
    eligible = [
        item for item in history
        if 25 <= (observed - _time(item["observed_at"])).total_seconds() / 86_400 <= 35
    ]
    prior = min(
        eligible,
        key=lambda item: abs((observed - _time(item["observed_at"])).days - 28),
    ) if eligible else None

    competitors = current.get("competitors") or []
    competitor_counts = [int(item["reviews"]) for item in competitors]
    fmd_reviews = int(current["fmd"]["reviews"])
    fmd_velocity: int | None = None
    competitor_velocity: int | None = None
    if prior is not None:
        fmd_velocity = fmd_reviews - int(prior["fmd"]["reviews"])
        prior_by_name = {
            str(item["name"]): int(item["reviews"])
            for item in prior.get("competitors") or []
        }
        deltas = [
            int(item["reviews"]) - prior_by_name[str(item["name"])]
            for item in competitors if str(item["name"]) in prior_by_name
        ]
        if deltas:
            competitor_velocity = int(median(deltas))

    floor = min(competitor_counts) if competitor_counts else fmd_reviews
    gap = max(floor - fmd_reviews, 0)
    static_months = (
        gap / fmd_velocity if fmd_velocity is not None and fmd_velocity > 0 else None
    )
    net_velocity = (
        fmd_velocity - competitor_velocity
        if fmd_velocity is not None and competitor_velocity is not None else None
    )
    net_months = gap / net_velocity if net_velocity is not None and net_velocity > 0 else None
    return {
        # local.review_velocity's thresholds guard on these two booleans so a
        # missing prior reading is never evaluated as a measured zero. They are
        # part of the check's declared records: omitting them makes the
        # observation unrecordable, not merely less informative.
        "prior_measured": prior is not None,
        "net_velocity_positive": bool(net_velocity is not None and net_velocity > 0),
        "fmd_reviews": fmd_reviews,
        "fmd_rating": float(current["fmd"]["rating"]),
        "fmd_new_reviews_28d": fmd_velocity,
        "competitor_median_reviews": int(median(competitor_counts)) if competitor_counts else 0,
        "competitor_median_new_reviews_28d": competitor_velocity,
        "pack_floor_reviews": floor,
        "reviews_to_floor": gap,
        "static_months_to_floor": static_months,
        "net_months_to_floor": net_months,
    }
