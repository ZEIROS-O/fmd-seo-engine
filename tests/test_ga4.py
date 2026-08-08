from pathlib import Path

import pytest

from fmd_seo.brain import load_brain
from fmd_seo.ga4 import Ga4Config, Ga4Unavailable, fetch_traffic, normalize_report


def test_analytics_traffic_check_has_strict_record_shape():
    check = load_brain().check("analytics.traffic")

    assert check.cadence == "weekly"
    assert check.method_kind == "engine"
    assert check.record_names == [
        "sessions",
        "engaged_sessions",
        "organic_search_sessions",
        "ai_referral_sessions",
        "key_events",
    ]


def _row(source, channel, sessions, engaged, key_events):
    return {
        "dimensionValues": [{"value": source}, {"value": channel}],
        "metricValues": [
            {"value": sessions},
            {"value": engaged},
            {"value": key_events},
        ],
    }


def test_normalize_report_sums_total_organic_ai_and_key_events():
    response = {"rows": [
        _row("google", "Organic Search", "8", "6", "1.0"),
        _row("chatgpt.com", "Referral", "2", "2", "0"),
        _row("www.perplexity.ai", "Referral", "1", "1", "0.0"),
        _row("example.com", "Referral", "3", "1", "0"),
    ]}

    assert normalize_report(response) == {
        "sessions": 14,
        "engaged_sessions": 10,
        "organic_search_sessions": 8,
        "ai_referral_sessions": 3,
        "key_events": 1,
    }


def test_normalize_report_rejects_fractional_counts():
    response = {
        "rows": [_row("google", "Organic Search", "1", "1", "0.5")],
    }

    with pytest.raises(Ga4Unavailable, match="whole count"):
        normalize_report(response)


def test_normalize_report_rejects_malformed_rows():
    response = {"rows": [{"dimensionValues": [], "metricValues": []}]}

    with pytest.raises(Ga4Unavailable, match="GA4 row shape"):
        normalize_report(response)


class FakeResponse:
    ok = True
    status_code = 200

    def json(self):
        return {"rows": []}


class FakeSession:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or FakeResponse()

    def post(self, url, *, json, timeout):
        self.calls.append((url, json, timeout))
        return self.response


def test_fetch_traffic_calls_bounded_read_only_report():
    session = FakeSession()

    records = fetch_traffic(
        Ga4Config(Path("unused.json"), "541970582", 28),
        session=session,
    )

    assert records == {
        "sessions": 0,
        "engaged_sessions": 0,
        "organic_search_sessions": 0,
        "ai_referral_sessions": 0,
        "key_events": 0,
    }
    url, body, timeout = session.calls[0]
    assert url.endswith("/v1beta/properties/541970582:runReport")
    assert body["dateRanges"] == [
        {"startDate": "28daysAgo", "endDate": "yesterday"},
    ]
    assert [value["name"] for value in body["dimensions"]] == [
        "sessionSource",
        "sessionDefaultChannelGroup",
    ]
    assert [value["name"] for value in body["metrics"]] == [
        "sessions",
        "engagedSessions",
        "keyEvents",
    ]
    assert timeout == 30


def test_fetch_traffic_fails_closed_on_http_error():
    response = FakeResponse()
    response.ok = False
    response.status_code = 403

    with pytest.raises(Ga4Unavailable, match="GA4 Data API HTTP 403"):
        fetch_traffic(
            Ga4Config(Path("unused.json"), "541970582"),
            session=FakeSession(response),
        )


def test_fetch_traffic_fails_closed_on_invalid_json():
    response = FakeResponse()
    response.json = lambda: (_ for _ in ()).throw(ValueError("invalid"))

    with pytest.raises(Ga4Unavailable, match="returned invalid JSON"):
        fetch_traffic(
            Ga4Config(Path("unused.json"), "541970582"),
            session=FakeSession(response),
        )


def test_fetch_traffic_names_missing_key_without_exposing_contents(tmp_path):
    missing = tmp_path / "missing.json"

    with pytest.raises(Ga4Unavailable, match="service-account key not found"):
        fetch_traffic(Ga4Config(missing, "541970582"))
