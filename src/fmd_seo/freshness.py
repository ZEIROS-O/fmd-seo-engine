"""Compute watchdog records from the committed observation time series."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from .brain import Brain
from .facts import days_until_stale
from .observations import latest_observation, record_observation


def freshness_records(
    brain: Brain,
    observations_dir: Path | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    current = now or datetime.now(timezone.utc)
    ages: list[int] = []
    overdue = 0
    for check in brain.checks:
        if check.id == "engine.freshness" or check.cadence_days is None:
            continue
        observation = latest_observation(check.id, observations_dir)
        if observation is None:
            continue
        observed_at = datetime.fromisoformat(observation.observed_at)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        age = current - observed_at
        ages.append(max(age.days, 0))
        if age > timedelta(days=2 * check.cadence_days):
            overdue += 1
    return {
        "stalest_check_age_days": max(ages, default=0),
        "checks_overdue": overdue,
    }


def record_daily_engine_checks(
    config: dict,
    brain: Brain,
    observations_dir: Path | None = None,
) -> list[str]:
    facts_file = Path(config["paths"]["facts_file"])
    record_observation(
        brain,
        "facts.freshness",
        {"days_until_stale": days_until_stale(facts_file)},
        fulfillment="engine",
        source=str(facts_file),
        directory=observations_dir,
    )
    record_observation(
        brain,
        "engine.freshness",
        freshness_records(brain, observations_dir),
        fulfillment="engine",
        source="agent:observation-time-series",
        directory=observations_dir,
    )
    return ["facts.freshness", "engine.freshness"]
