"""Evidence-derived opportunity scoring; gates always outrank scores."""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml


class WarroomError(ValueError):
    pass


SCORE_VERSION = 1
COST_BY_GENERATOR = {
    "canonical": 15,
    "sitemap": 10,
    "schema": 20,
    "internal-links": 25,
    "copy": 50,
    "page": 100,
    "console": 5,
}
RISK_BY_CLAIM_CLASS = {
    "none": 0,
    "fact_bound": 20,
    "service": 35,
    "pricing": 60,
    "review": 70,
    "guarantee": 80,
}


def traction_score(position: float | int | None, *, has_impressions: bool = True) -> int:
    if position is None:
        return 25 if has_impressions else 0
    if 4 <= position <= 10:
        return 100
    if 11 <= position <= 20:
        return 80
    if 21 <= position <= 50:
        return 50
    return 25 if has_impressions else 0


def _component(value: Any, name: str) -> float:
    number = float(value)
    if not 0 <= number <= 100:
        raise WarroomError(f"{name} must be between 0 and 100")
    return number


def authority_gap_score(sources: list[dict[str, Any]]) -> int:
    competitors: set[str] = set()
    cites_fmd = False
    for source in sources:
        if int(source.get("frequency", 0)) < 2:
            continue
        for subject in source.get("supports") or []:
            normalized = str(subject).strip().lower()
            if normalized in {"fmd", "fresh mobile detailing"}:
                cites_fmd = True
            elif normalized:
                competitors.add(normalized)
    if cites_fmd:
        return 0
    if len(competitors) >= 2:
        return 100
    if len(competitors) == 1:
        return 50
    return 0


def freshness_score(opportunity: dict[str, Any]) -> int:
    if "seasonal_window_days" not in opportunity:
        return 50
    days = int(opportunity["seasonal_window_days"])
    if days < 0:
        return 0
    if days <= 30:
        return 100
    return 50


def _derived_component(
    opportunity: dict[str, Any],
    name: str,
    fallback: Any,
) -> float:
    return _component(opportunity[name] if name in opportunity else fallback, name)


def _expiration_instant(value: Any) -> datetime:
    """Parse an override expiration, failing closed on anything unreadable.

    A bare date expires at that day's UTC midnight rather than its end: an
    override that lapses a few hours early merely stops forcing a score, while
    one that lingers keeps overriding evidence past its authorization.
    """
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day)
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as err:
            raise WarroomError(f"manual override expiration is unreadable: {value!r}") from err
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def score_opportunity(
    opportunity: dict[str, Any], *, now: datetime | None = None,
) -> dict[str, Any]:
    consensus = opportunity.get("serp_consensus") or {}
    components = {
        "commercial": _component(opportunity["commercial"], "commercial"),
        "traction": float(traction_score(
            opportunity.get("position"),
            has_impressions=bool(opportunity.get("has_impressions", True)),
        )),
        "beatability": _derived_component(
            opportunity, "beatability", consensus.get("weakness_score", 0),
        ),
        "authority_gap": _derived_component(
            opportunity,
            "authority_gap",
            authority_gap_score(opportunity.get("citation_sources") or []),
        ),
        "freshness": _derived_component(
            opportunity, "freshness", freshness_score(opportunity),
        ),
        "cost": _derived_component(
            opportunity,
            "cost",
            COST_BY_GENERATOR.get(str(opportunity.get("generator", "")), 100),
        ),
        "risk": _derived_component(
            opportunity,
            "risk",
            RISK_BY_CLAIM_CLASS.get(str(opportunity.get("claim_class", "")), 100),
        ),
    }
    raw = (
        0.35 * components["commercial"]
        + 0.25 * components["traction"]
        + 0.20 * components["beatability"]
        + 0.10 * components["authority_gap"]
        + 0.10 * components["freshness"]
        - 0.05 * components["cost"]
        - 0.05 * components["risk"]
    )
    blockers = list(opportunity.get("blockers") or [])
    override = opportunity.get("override")
    if override is not None:
        missing = {"owner", "reason", "timestamp", "expiration", "score"} - set(override)
        if missing:
            label = "expiration" if "expiration" in missing else ", ".join(sorted(missing))
            raise WarroomError(f"manual override missing {label}")
        # Requiring an expiration and never reading it is the same as having no
        # expiration: the override would force the score forever.
        expires = _expiration_instant(override["expiration"])
        if (now or datetime.now(timezone.utc)) >= expires:
            blockers.append(f"manual override expired {override['expiration']}")
        else:
            raw = _component(override["score"], "override score")
    raw = round(max(0.0, min(100.0, raw)), 2)
    return {
        "id": opportunity["id"],
        "score_version": SCORE_VERSION,
        "components": {
            key: int(value) if value.is_integer() else value
            for key, value in components.items()
        },
        "score_raw": raw,
        "score_executable": 0 if blockers else raw,
        "blockers": blockers,
        "override": override,
    }


def write_warroom(
    opportunities: list[dict[str, Any]],
    *,
    output_path: Path,
    generated_at: str,
) -> Path:
    payload = {
        "schema_version": 1,
        "score_version": SCORE_VERSION,
        "generated_at": generated_at,
        "status": "BLOCKED" if any(item.get("blockers") for item in opportunities) else "READY",
        "formula": (
            "0.35 commercial + 0.25 traction + 0.20 beatability + "
            "0.10 authority_gap + 0.10 freshness - 0.05 cost - 0.05 risk"
        ),
        "cost_lookup": COST_BY_GENERATOR,
        "risk_lookup": RISK_BY_CLAIM_CLASS,
        "opportunities": opportunities,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return output_path
