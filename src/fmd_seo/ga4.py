"""Read-only Google Analytics 4 acquisition and conversion monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import urlsplit

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
