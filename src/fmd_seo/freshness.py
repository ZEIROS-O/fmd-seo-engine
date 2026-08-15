"""Compute watchdog records from the committed observation time series."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .brain import Brain, OVERDUE_CADENCE_MULTIPLIER, due_checks
from .facts import days_until_stale
from .observations import latest_observation, record_observation


class FreshnessDataError(ValueError):
    """The committed observation store cannot support a truthful verdict."""


def _parse_observed_at(value: Any, path: Path) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise FreshnessDataError(f"observation missing observed_at: {path}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as err:
        raise FreshnessDataError(
            f"observation has invalid observed_at: {path}: {value!r}"
        ) from err
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _raw_latest_observations(observations_dir: Path) -> tuple[dict[str, datetime], int]:
    if not observations_dir.exists():
        raise FreshnessDataError(
            f"observations directory missing: {observations_dir}"
        )
    if not observations_dir.is_dir():
        raise FreshnessDataError(
            f"observations path is not a directory: {observations_dir}"
        )
    latest: dict[str, datetime] = {}
    relevant_count = 0
    try:
        paths = sorted(observations_dir.glob("*/*.json"))
    except OSError as err:
        raise FreshnessDataError(
            f"observations directory unreadable: {observations_dir}: {err}"
        ) from err
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError) as err:
            raise FreshnessDataError(f"observation unreadable: {path}: {err}") from err
        except json.JSONDecodeError as err:
            raise FreshnessDataError(f"malformed observation: {path}: {err}") from err
        if not isinstance(data, dict):
            raise FreshnessDataError(f"observation must be an object: {path}")
        check_id = data.get("check_id")
        if not isinstance(check_id, str) or not check_id:
            raise FreshnessDataError(f"observation missing check_id: {path}")
        observed_at = _parse_observed_at(data.get("observed_at"), path)
        if check_id == "engine.freshness":
            continue
        relevant_count += 1
        if check_id not in latest or observed_at > latest[check_id]:
            latest[check_id] = observed_at
    return latest, relevant_count


def freshness_report(
    brain: Brain,
    observations_dir: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a read-only liveness verdict from raw committed observations."""
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    latest, observations_found = _raw_latest_observations(observations_dir)
    scheduled = {
        check.id: check
        for check in brain.checks
        if check.execution_mode == "scheduled"
        and check.cadence_days is not None
        and check.id != "engine.freshness"
    }
    last_seen = {
        check_id: stamp.isoformat()
        for check_id, stamp in latest.items()
        if check_id in scheduled
    }
    due = [
        (check, reason)
        for check, reason in due_checks(brain, last_seen, now=current)
        if check.id in scheduled
    ]
    never_observed = sorted(
        check.id for check, reason in due if reason == "never observed"
    )
    ages = [
        max((current - stamp).days, 0)
        for check_id, stamp in latest.items()
        if check_id in scheduled
    ]
    if observations_found == 0:
        state = "no_observations_found"
    elif due:
        state = "observations_stale"
    else:
        state = "observations_current"
    return {
        "state": state,
        "observations_found": observations_found,
        "stalest_check_age_days": max(ages, default=0),
        "checks_overdue": len(due),
        "never_observed": never_observed,
    }


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
        if (
            check.id == "engine.freshness"
            or check.execution_mode != "scheduled"
            or check.cadence_days is None
        ):
            continue
        observation = latest_observation(check.id, observations_dir)
        if observation is None:
            continue
        observed_at = datetime.fromisoformat(observation.observed_at)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        age = current - observed_at
        ages.append(max(age.days, 0))
        if age >= timedelta(
            days=OVERDUE_CADENCE_MULTIPLIER * check.cadence_days
        ):
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
