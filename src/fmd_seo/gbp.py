"""Read-only Google Business Profile Performance API client."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .contracts import PagePackage
from .facts import load_snapshot
from .receipts import now_iso
from .verify import checks_pass, deterministic_checks

GBP_SCOPE = "https://www.googleapis.com/auth/business.manage"
PERFORMANCE_BASE = "https://businessprofileperformance.googleapis.com/v1"
DAILY_METRICS = (
    "CALL_CLICKS",
    "BUSINESS_DIRECTION_REQUESTS",
    "WEBSITE_CLICKS",
)


class GbpUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class GbpConfig:
    key_path: Path
    location_id: str

    @property
    def location(self) -> str:
        value = self.location_id.strip()
        return value if value.startswith("locations/") else f"locations/{value}"


def _sum_daily(response: dict) -> dict[str, int]:
    totals: dict[str, int] = {}
    for group in response.get("multiDailyMetricTimeSeries") or []:
        for series in group.get("dailyMetricTimeSeries") or []:
            metric = series.get("dailyMetric")
            totals[str(metric)] = sum(
                int(point.get("value") or 0)
                for point in (series.get("timeSeries") or {}).get("datedValues") or []
            )
    return totals


def _insight_count(insight: dict) -> tuple[int, bool]:
    # A threshold means the actual value is unknown but below that number. It is
    # not a count and must never be promoted into measured truth (GATE-4).
    if insight.get("value") is not None:
        return int(insight["value"]), False
    return 0, insight.get("threshold") is not None


def normalize_performance(daily: dict, keywords: dict) -> dict[str, int]:
    totals = _sum_daily(daily)
    discovery = 0
    thresholded = 0
    for row in keywords.get("searchKeywordsCounts") or []:
        keyword = str(row.get("searchKeyword") or "").casefold()
        if "fresh mobile" in keyword or keyword.startswith("fresh detail"):
            continue
        count, was_thresholded = _insight_count(row.get("insightsValue") or {})
        discovery += count
        thresholded += int(was_thresholded)
    return {
        "calls": totals.get("CALL_CLICKS", 0),
        "direction_requests": totals.get("BUSINESS_DIRECTION_REQUESTS", 0),
        "website_clicks": totals.get("WEBSITE_CLICKS", 0),
        "searches_discovery": discovery,
        "search_keywords_thresholded": thresholded,
    }


def _authorized_session(key_path: Path):
    if not key_path.exists():
        raise GbpUnavailable(f"service-account key not found: {key_path}")
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import AuthorizedSession
    except ImportError as err:
        raise GbpUnavailable(
            "google-auth requests transport not installed (`pip install -e .[gbp]`)"
        ) from err
    try:
        credentials = service_account.Credentials.from_service_account_file(
            str(key_path), scopes=[GBP_SCOPE],
        )
        return AuthorizedSession(credentials)
    except Exception as err:  # noqa: BLE001 - fail closed without key details
        raise GbpUnavailable(f"GBP auth failed: {type(err).__name__}") from err


def _date_params(prefix: str, value: date) -> dict[str, int]:
    return {
        f"{prefix}.year": value.year,
        f"{prefix}.month": value.month,
        f"{prefix}.day": value.day,
    }


def fetch_performance(
    config: GbpConfig,
    *,
    end: date | None = None,
    days: int = 28,
) -> dict[str, int]:
    if not config.location_id.strip():
        raise GbpUnavailable("GBP location_id is not configured")
    end_date = end or (date.today() - timedelta(days=1))
    start_date = end_date - timedelta(days=days - 1)
    session = _authorized_session(config.key_path)
    daily_params: list[tuple[str, object]] = [
        ("dailyMetrics", metric) for metric in DAILY_METRICS
    ]
    daily_params.extend(_date_params("dailyRange.startDate", start_date).items())
    daily_params.extend(_date_params("dailyRange.endDate", end_date).items())
    daily_url = (
        f"{PERFORMANCE_BASE}/{config.location}:fetchMultiDailyMetricsTimeSeries"
    )
    daily_response = session.get(daily_url, params=daily_params, timeout=30)
    if not daily_response.ok:
        raise GbpUnavailable(f"GBP daily metrics HTTP {daily_response.status_code}")

    monthly_params = {
        "monthlyRange.startMonth.year": start_date.year,
        "monthlyRange.startMonth.month": start_date.month,
        "monthlyRange.endMonth.year": end_date.year,
        "monthlyRange.endMonth.month": end_date.month,
        "pageSize": 100,
    }
    monthly_url = (
        f"{PERFORMANCE_BASE}/{config.location}/searchkeywords/impressions/monthly"
    )
    keyword_rows: list[dict] = []
    while True:
        response = session.get(monthly_url, params=monthly_params, timeout=30)
        if not response.ok:
            raise GbpUnavailable(f"GBP search-keyword metrics HTTP {response.status_code}")
        page = response.json()
        keyword_rows.extend(page.get("searchKeywordsCounts") or [])
        token = page.get("nextPageToken")
        if not token:
            break
        monthly_params["pageToken"] = token
    return normalize_performance(
        daily_response.json(),
        {"searchKeywordsCounts": keyword_rows},
    )


def sync_if_due(config: dict, brain, *, observations_dir: Path | None = None) -> dict:
    """Fetch and record GBP performance when configured and weekly-due."""
    from .observations import latest_observation, record_observation

    raw = config.get("gbp") or {}
    location_id = str(raw.get("location_id") or "").strip()
    key_path = str(raw.get("key_path") or "").strip()
    if not location_id or not key_path:
        return {"status": "skipped_config"}
    latest = latest_observation("gbp.performance", observations_dir)
    if latest is not None:
        observed_at = datetime.fromisoformat(latest.observed_at)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - observed_at < timedelta(days=7):
            return {"status": "not_due", "observed_at": latest.observed_at}
    records = fetch_performance(
        GbpConfig(key_path=Path(key_path), location_id=location_id),
        days=int(raw.get("days", 28)),
    )
    record_observation(
        brain,
        "gbp.performance",
        records,
        fulfillment="engine_api",
        source="Google Business Profile Performance API",
        note=(f"daily actions cover prior {int(raw.get('days', 28))} days; search impressions "
              "cover API calendar months, exclude branded keywords, and omit threshold-only counts"),
        directory=observations_dir,
    )
    return {"status": "fetched", "records": records}


def draft_gbp_assets(facts_file: Path, output_dir: Path) -> dict:
    """Write fact-bound GBP/review drafts; never publish or contact a customer."""
    keys = [
        "identity.name",
        "identity.phone",
        "identity.positioning",
        "service_area.base",
        "pricing.one_time.full_interior.price",
        "pricing.one_time.ultimate_interior.price",
        "guarantee.name",
        "autonomy.customer_contact",
        "autonomy.posting",
    ]
    snapshot = load_snapshot(facts_file, keys)
    facts = snapshot.facts_used
    full = facts["pricing.one_time.full_interior.price"]
    ultimate = facts["pricing.one_time.ultimate_interior.price"]
    phone = facts["identity.phone"]
    post_text = (
        f"A cleaner car without the drop-off. {facts['identity.name']} brings "
        f"mobile interior car detailing to {facts['service_area.base']} and nearby "
        f"east-side communities. Full Interior is ${full}; Ultimate Interior is "
        f"${ultimate}. Text {phone} for a photo quote. Every job carries the "
        f"{facts['guarantee.name']}."
    )
    content = {
        "slug": "gbp-draft",
        "title": "Mobile interior car detailing on Cleveland's east side",
        "description": post_text,
        "blocks": [{"type": "p", "text": post_text}],
        "claims": [
            {"fact_key": "identity.phone", "value": phone},
            {"fact_key": "pricing.one_time.full_interior.price", "value": full},
            {"fact_key": "pricing.one_time.ultimate_interior.price", "value": ultimate},
            {"fact_key": "guarantee.name", "value": facts["guarantee.name"]},
        ],
        "evidence_figures": [],
        "mentioned_places": [],
        "internal_links": [{"href": "/", "label": "Book online"}],
    }
    package = PagePackage.create(
        intent_key="gbp:weekly-post",
        tier="supporting-post",
        created_at=now_iso(),
        fact_snapshot=snapshot.to_dict(),
        evidence_refs=[],
        content=content,
        internal_links=content["internal_links"],
        assets=[],
    )
    checks = deterministic_checks(package, known_routes={"/"})
    if not checks_pass(checks):
        return {"status": "BLOCK", "posting": facts["autonomy.posting"], "checks": checks}

    output_dir.mkdir(parents=True, exist_ok=True)
    shared = {
        "source_hash": snapshot.source_hash,
        "generated_at": package.created_at,
        "posting": facts["autonomy.posting"],
    }
    (output_dir / "gbp-post.json").write_text(
        json.dumps({**shared, "kind": "gbp_post", "text": post_text}, indent=2) + "\n",
        encoding="utf-8",
    )
    review_text = (
        f"Hey — thanks again for choosing {facts['identity.name']}. If opening "
        "your car door made you say wow, would you mind leaving a quick Google "
        "review? It helps a local business a ton."
    )
    (output_dir / "review-request.json").write_text(
        json.dumps({
            **shared,
            "kind": "review_request",
            "customer_contact": facts["autonomy.customer_contact"],
            "text": review_text,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "status": "DONE",
        "posting": facts["autonomy.posting"],
        "customer_contact": facts["autonomy.customer_contact"],
        "checks": checks,
        "files": [
            str(output_dir / "gbp-post.json"),
            str(output_dir / "review-request.json"),
        ],
    }
