"""Read-only Google Analytics 4 acquisition and conversion monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

if TYPE_CHECKING:
    from .brain import Brain

GA4_SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
DATA_BASE = "https://analyticsdata.googleapis.com"
AI_SOURCE_HOSTS = (
    "chatgpt.com",
    "perplexity.ai",
    "claude.ai",
    "copilot.microsoft.com",
    "gemini.google.com",
)


class Ga4Unavailable(RuntimeError):
    """Missing credentials, invalid data, or an Analytics API failure."""


@dataclass(frozen=True)
class Ga4Config:
    key_path: Path
    property_id: str
    days: int = 28


def _whole_count(raw: object) -> int:
    try:
        value = Decimal(str(raw))
    except InvalidOperation as err:
        raise Ga4Unavailable(f"GA4 metric is not a whole count: {raw!r}") from err
    if not value.is_finite() or value != value.to_integral_value() or value < 0:
        raise Ga4Unavailable(f"GA4 metric is not a whole count: {raw!r}")
    return int(value)


def _source_host(raw: str) -> str:
    value = raw.strip().casefold()
    parsed = urlsplit(value if "://" in value else f"//{value}")
    return (parsed.hostname or value.split("/", 1)[0]).rstrip(".")


def _is_ai_source(raw: str) -> bool:
    host = _source_host(raw)
    return any(
        host == domain or host.endswith(f".{domain}")
        for domain in AI_SOURCE_HOSTS
    )


def normalize_report(response: dict) -> dict[str, int]:
    metadata = response.get("metadata") or {}
    if not isinstance(metadata, dict):
        raise Ga4Unavailable("invalid GA4 response metadata")
    if metadata.get("dataLossFromOtherRow"):
        raise Ga4Unavailable("GA4 report has dimension data loss")
    if metadata.get("samplingMetadatas"):
        raise Ga4Unavailable("GA4 report is sampled")
    if metadata.get("subjectToThresholding"):
        raise Ga4Unavailable("GA4 report is thresholded")
    restrictions = metadata.get("schemaRestrictionResponse") or {}
    if not isinstance(restrictions, dict):
        raise Ga4Unavailable("invalid GA4 schema restriction metadata")
    if restrictions.get("activeMetricRestrictions"):
        raise Ga4Unavailable("GA4 report has restricted metrics")

    records = {
        "sessions": 0,
        "engaged_sessions": 0,
        "organic_search_sessions": 0,
        "ai_referral_sessions": 0,
        "key_events": 0,
    }
    rows = response.get("rows") or []
    if not isinstance(rows, list):
        raise Ga4Unavailable("invalid GA4 row shape")
    row_count = response.get("rowCount")
    if row_count is not None:
        expected_rows = _whole_count(row_count)
        if expected_rows > len(rows):
            raise Ga4Unavailable(
                f"GA4 report is truncated: received {len(rows)}/{expected_rows} rows"
            )
        if expected_rows != len(rows):
            raise Ga4Unavailable("GA4 report row count does not match response rows")
    for row in rows:
        dimensions = row.get("dimensionValues") or []
        metrics = row.get("metricValues") or []
        if len(dimensions) != 2 or len(metrics) != 3:
            raise Ga4Unavailable("invalid GA4 row shape")
        source = str(dimensions[0].get("value") or "")
        channel = str(dimensions[1].get("value") or "")
        sessions = _whole_count(metrics[0].get("value"))
        engaged = _whole_count(metrics[1].get("value"))
        key_events = _whole_count(metrics[2].get("value"))
        records["sessions"] += sessions
        records["engaged_sessions"] += engaged
        records["key_events"] += key_events
        if channel.casefold() == "organic search":
            records["organic_search_sessions"] += sessions
        if _is_ai_source(source):
            records["ai_referral_sessions"] += sessions
    return records


def _authorized_session(key_path: Path):
    if not key_path.exists():
        raise Ga4Unavailable(f"service-account key not found: {key_path}")

    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
    except ImportError as err:
        raise Ga4Unavailable(
            "google-auth requests transport not installed (`pip install -e .[ga4]`)"
        ) from err
    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(key_path), scopes=[GA4_SCOPE],
        )
        return AuthorizedSession(credentials)
    except Exception as err:  # noqa: BLE001 - fail closed without key details
        raise Ga4Unavailable(f"GA4 auth failed: {type(err).__name__}") from err


def fetch_traffic(
    config: Ga4Config,
    *,
    session=None,
) -> dict[str, int]:
    client = session or _authorized_session(config.key_path)
    body = {
        "dateRanges": [
            {"startDate": f"{config.days}daysAgo", "endDate": "yesterday"},
        ],
        "dimensions": [
            {"name": "sessionSource"},
            {"name": "sessionDefaultChannelGroup"},
        ],
        "metrics": [
            {"name": "sessions"},
            {"name": "engagedSessions"},
            {"name": "keyEvents"},
        ],
        "limit": "100000",
    }
    try:
        response = client.post(
            f"{DATA_BASE}/v1beta/properties/{config.property_id}:runReport",
            json=body,
            timeout=30,
        )
    except Exception as err:  # noqa: BLE001 - provider/network boundary
        raise Ga4Unavailable(f"GA4 Data API request failed: {type(err).__name__}") from err

    if not response.ok:
        raise Ga4Unavailable(f"GA4 Data API HTTP {response.status_code}")

    try:
        payload = response.json()
    except Exception as err:  # noqa: BLE001 - provider response boundary
        raise Ga4Unavailable("GA4 Data API returned invalid JSON") from err

    return normalize_report(payload)


def sync_if_due(
    config: dict,
    brain: Brain,
    *,
    observations_dir: Path | None = None,
) -> dict:
    """Fetch and record a weekly normalized GA4 observation when configured."""
    from .observations import latest_observation, record_observation

    raw = config.get("ga4") or {}
    key_path = raw.get("key_path")
    property_id = raw.get("property_id")
    if not key_path or not property_id:
        return {"status": "skipped_config"}

    latest = latest_observation("analytics.traffic", observations_dir)
    if latest is not None:
        observed_at = datetime.fromisoformat(latest.observed_at.replace("Z", "+00:00"))
        if observed_at > datetime.now(timezone.utc) - timedelta(days=7):
            return {"status": "not_due", "observed_at": latest.observed_at}

    days = int(raw.get("days", 28))
    records = fetch_traffic(
        Ga4Config(
            key_path=Path(str(key_path)),
            property_id=str(property_id),
            days=days,
        )
    )
    record_observation(
        brain,
        "analytics.traffic",
        records,
        fulfillment="engine_api",
        source="google_analytics:data_api",
        note=(
            f"property={property_id}; window={days}daysAgo..yesterday; "
            "ai_sources=host_allowlist"
        ),
        directory=observations_dir,
    )
    return {"status": "fetched", "records": records}
