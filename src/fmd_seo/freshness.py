"""Compute watchdog records from the committed observation time series."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .brain import Brain, Check, overdue_after
from .facts import days_until_stale
from .observations import latest_observation, record_observation


class FreshnessDataError(ValueError):
    """The committed observation store cannot support a truthful verdict."""


def _scheduled_checks(brain: Brain) -> dict[str, Check]:
    """The time-scheduled checks a watchdog is answerable for.

    One selector, both surfaces. It used to be two inline copies over different
    loaders, which is how `freshness_report` and `freshness_records` came to
    disagree on live data (9 overdue vs 3).
    """
    return {
        check.id: check
        for check in brain.checks
        if check.execution_mode == "scheduled"
        and check.cadence_days is not None
        and check.id != "engine.freshness"
    }


def _as_utc(value: datetime | None) -> datetime:
    """Normalize `now` the same way observation timestamps are normalized.

    A naive datetime is UTC, never local. `freshness_report` used to reinterpret
    a naive `now` as local time while `freshness_records` raised TypeError on the
    very same input.
    """
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _liveness(
    scheduled: dict[str, Check],
    latest: dict[str, datetime],
    current: datetime,
) -> dict[str, Any]:
    """The one liveness verdict over a scheduled set and its newest timestamps.

    A never-observed scheduled check is overdue. The engine never assumes an
    unmeasured check is passing — that assumption is exactly what made
    `engine.freshness` blind to six checks that had never produced anything.
    """
    overdue: list[str] = []
    never_observed: list[str] = []
    ages: list[int] = []
    for check_id, check in scheduled.items():
        stamp = latest.get(check_id)
        if stamp is None:
            never_observed.append(check_id)
            overdue.append(check_id)
            continue
        age = current - stamp
        ages.append(max(age.days, 0))
        if age >= overdue_after(check.cadence_days):
            overdue.append(check_id)
    return {
        "overdue": sorted(overdue),
        "never_observed": sorted(never_observed),
        "stalest_check_age_days": max(ages, default=0),
    }


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


def _raw_latest_observations(
    observations_dir: Path, known_ids: set[str],
) -> tuple[dict[str, datetime], int, list[str]]:
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
    unregistered: set[str] = set()
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
        # An observation for an id the registry no longer declares is orphaned
        # data — usually the residue of a check rename. Counting it as a live
        # observation inflated observations_found and made a dead directory look
        # like coverage, so it is surfaced by name instead.
        if check_id not in known_ids:
            unregistered.add(check_id)
            continue
        relevant_count += 1
        if check_id not in latest or observed_at > latest[check_id]:
            latest[check_id] = observed_at
    return latest, relevant_count, sorted(unregistered)


def freshness_report(
    brain: Brain,
    observations_dir: Path,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a read-only liveness verdict from raw committed observations."""
    current = _as_utc(now)
    scheduled = _scheduled_checks(brain)
    latest, observations_found, unregistered = _raw_latest_observations(
        observations_dir, {check.id for check in brain.checks},
    )
    liveness = _liveness(
        scheduled,
        {k: v for k, v in latest.items() if k in scheduled},
        current,
    )
    if observations_found == 0:
        state = "no_observations_found"
    elif liveness["overdue"]:
        state = "observations_stale"
    else:
        state = "observations_current"
    return {
        "state": state,
        "observations_found": observations_found,
        "stalest_check_age_days": liveness["stalest_check_age_days"],
        "checks_overdue": len(liveness["overdue"]),
        "never_observed": liveness["never_observed"],
        "unregistered_observations": unregistered,
    }


def freshness_records(
    brain: Brain,
    observations_dir: Path | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """The same verdict as `freshness_report`, reduced to the recorded fields.

    This is the surface `engine.freshness` writes, so it must not be the more
    forgiving of the two. It used to `continue` past a check with no observation,
    which silently excused every never-observed scheduled check from the count.
    """
    current = _as_utc(now)
    scheduled = _scheduled_checks(brain)
    latest: dict[str, datetime] = {}
    for check_id in scheduled:
        observation = latest_observation(check_id, observations_dir)
        if observation is None:
            continue
        latest[check_id] = _parse_observed_at(
            observation.observed_at, observations_dir or Path(check_id),
        )
    liveness = _liveness(scheduled, latest, current)
    return {
        "stalest_check_age_days": liveness["stalest_check_age_days"],
        "checks_overdue": len(liveness["overdue"]),
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
