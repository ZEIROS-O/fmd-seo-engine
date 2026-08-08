from pathlib import Path

import pytest

from fmd_seo.brain import load_brain
from fmd_seo.ga4 import (
    Ga4Config,
    Ga4Unavailable,
    fetch_traffic,
    normalize_report,
    sync_if_due,
)
from fmd_seo.observations import latest_observation, record_observation


def test_analytics_traffic_check_has_strict_record_shape():
    check = load_brain().check("analytics.traffic")

    assert check.cadence == "weekly"
    assert check.method_kind == "console"
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


def _report(*, rows=None, row_count=None, metadata=None):
    payload = {
        "dimensionHeaders": [
            {"name": "sessionSource"},
            {"name": "sessionDefaultChannelGroup"},
        ],
        "metricHeaders": [
            {"name": "sessions", "type": "TYPE_INTEGER"},
            {"name": "engagedSessions", "type": "TYPE_INTEGER"},
            {"name": "keyEvents", "type": "TYPE_FLOAT"},
        ],
        "metadata": {} if metadata is None else metadata,
        "rowCount": len(rows or []) if row_count is None else row_count,
    }
    if rows is not None:
        payload["rows"] = rows
    return payload


def test_normalize_report_sums_total_organic_ai_and_key_events():
    response = _report(rows=[
        _row("google", "Organic Search", "8", "6", "1.0"),
        _row("chatgpt.com", "Referral", "2", "2", "0"),
        _row("www.perplexity.ai", "Referral", "1", "1", "0.0"),
        _row("example.com", "Referral", "3", "1", "0"),
    ])

    assert normalize_report(response) == {
        "sessions": 14,
        "engaged_sessions": 10,
        "organic_search_sessions": 8,
        "ai_referral_sessions": 3,
        "key_events": 1,
    }


def test_normalize_report_rejects_fractional_counts():
    response = _report(
        rows=[_row("google", "Organic Search", "1", "1", "0.5")],
    )

    with pytest.raises(Ga4Unavailable, match="whole count"):
        normalize_report(response)


def test_normalize_report_rejects_malformed_rows():
    response = _report(rows=[{"dimensionValues": [], "metricValues": []}])

    with pytest.raises(Ga4Unavailable, match="GA4 row shape"):
        normalize_report(response)


@pytest.mark.parametrize(
    "missing",
    ["dimensionHeaders", "metricHeaders", "metadata", "rowCount"],
)
def test_normalize_report_rejects_missing_response_contract(missing):
    response = _report(rows=[])
    response.pop(missing)

    with pytest.raises(Ga4Unavailable, match="GA4 response"):
        normalize_report(response)


@pytest.mark.parametrize(
    ("field", "headers", "message"),
    [
        (
            "dimensionHeaders",
            [
                {"name": "sessionDefaultChannelGroup"},
                {"name": "sessionSource"},
            ],
            "dimension headers",
        ),
        (
            "metricHeaders",
            [
                {"name": "engagedSessions", "type": "TYPE_INTEGER"},
                {"name": "sessions", "type": "TYPE_INTEGER"},
                {"name": "keyEvents", "type": "TYPE_FLOAT"},
            ],
            "metric headers",
        ),
    ],
)
def test_normalize_report_rejects_unexpected_headers(field, headers, message):
    response = _report(rows=[])
    response[field] = headers

    with pytest.raises(Ga4Unavailable, match=message):
        normalize_report(response)


def test_normalize_report_accepts_complete_zero_row_response():
    assert normalize_report(_report(rows=None, row_count=0)) == {
        "sessions": 0,
        "engaged_sessions": 0,
        "organic_search_sessions": 0,
        "ai_referral_sessions": 0,
        "key_events": 0,
    }


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"dataLossFromOtherRow": True}, "data loss"),
        (
            {
                "samplingMetadatas": [
                    {"samplesReadCount": "10", "samplingSpaceSize": "100"},
                ],
            },
            "sampled",
        ),
        ({"subjectToThresholding": True}, "thresholded"),
        (
            {
                "schemaRestrictionResponse": {
                    "activeMetricRestrictions": [
                        {"metricName": "keyEvents"},
                    ],
                },
            },
            "restricted",
        ),
    ],
)
def test_normalize_report_rejects_incomplete_metadata(metadata, message):
    response = _report(
        rows=[_row("google", "Organic Search", "1", "1", "0")],
        metadata=metadata,
    )

    with pytest.raises(Ga4Unavailable, match=message):
        normalize_report(response)


def test_normalize_report_rejects_truncated_rows():
    response = _report(
        row_count=2,
        rows=[_row("google", "Organic Search", "1", "1", "0")],
    )

    with pytest.raises(Ga4Unavailable, match="truncated"):
        normalize_report(response)


class FakeResponse:
    ok = True
    status_code = 200

    def json(self):
        return _report(rows=[])


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


def test_sync_if_due_records_weekly_ga4_observation(tmp_path, monkeypatch):
    records = {
        "sessions": 12,
        "engaged_sessions": 8,
        "organic_search_sessions": 7,
        "ai_referral_sessions": 2,
        "key_events": 1,
    }
    monkeypatch.setattr("fmd_seo.ga4.fetch_traffic", lambda config: records)
    brain = load_brain()

    result = sync_if_due(
        {
            "ga4": {
                "key_path": str(tmp_path / "key.json"),
                "property_id": "541970582",
                "days": 28,
            }
        },
        brain,
        observations_dir=tmp_path / "observations",
    )

    assert result == {"status": "fetched", "records": records}
    observation = latest_observation(
        "analytics.traffic", tmp_path / "observations",
    )
    assert observation is not None
    assert observation.records == records
    assert observation.fulfillment == "engine_api"
    assert observation.source == "google_analytics:data_api"


def test_sync_if_due_skips_missing_config_and_recent_observation(tmp_path, monkeypatch):
    brain = load_brain()
    observations_dir = tmp_path / "observations"
    assert sync_if_due({}, brain, observations_dir=observations_dir) == {
        "status": "skipped_config",
    }

    records = {
        "sessions": 1,
        "engaged_sessions": 1,
        "organic_search_sessions": 1,
        "ai_referral_sessions": 0,
        "key_events": 0,
    }
    record_observation(
        brain,
        "analytics.traffic",
        records,
        fulfillment="engine_api",
        source="test",
        directory=observations_dir,
    )
    monkeypatch.setattr(
        "fmd_seo.ga4.fetch_traffic",
        lambda config: pytest.fail("recent observations must suppress GA4 fetches"),
    )

    result = sync_if_due(
        {
            "ga4": {
                "key_path": str(tmp_path / "key.json"),
                "property_id": "541970582",
            }
        },
        brain,
        observations_dir=observations_dir,
    )

    assert result["status"] == "not_due"
    assert result["observed_at"]
