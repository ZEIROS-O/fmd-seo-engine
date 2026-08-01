from fmd_seo.gbp import normalize_performance


def test_normalize_gbp_performance_sums_clicks_and_nonbrand_searches():
    daily = {
        "multiDailyMetricTimeSeries": [{
            "dailyMetricTimeSeries": [
                {"dailyMetric": "CALL_CLICKS", "timeSeries": {"datedValues": [
                    {"date": {"year": 2026, "month": 7, "day": 1}, "value": "2"},
                    {"date": {"year": 2026, "month": 7, "day": 2}, "value": "3"},
                ]}},
                {"dailyMetric": "BUSINESS_DIRECTION_REQUESTS", "timeSeries": {
                    "datedValues": [{"value": "4"}],
                }},
                {"dailyMetric": "WEBSITE_CLICKS", "timeSeries": {
                    "datedValues": [{"value": "7"}],
                }},
            ],
        }],
    }
    keywords = {
        "searchKeywordsCounts": [
            {"searchKeyword": "fresh mobile detailing", "insightsValue": {"value": "8"}},
            {"searchKeyword": "mobile detailing near me", "insightsValue": {"value": "11"}},
            {"searchKeyword": "car detailing", "insightsValue": {"threshold": "5"}},
        ],
    }

    assert normalize_performance(daily, keywords) == {
        "calls": 5,
        "direction_requests": 4,
        "website_clicks": 7,
        "searches_discovery": 11,
    }


def test_sync_gbp_records_weekly_observation(tmp_path, monkeypatch):
    from fmd_seo import gbp
    from fmd_seo.brain import load_brain
    from fmd_seo.observations import latest_observation

    expected = {
        "calls": 5,
        "direction_requests": 4,
        "website_clicks": 7,
        "searches_discovery": 11,
    }
    monkeypatch.setattr(gbp, "fetch_performance", lambda *_args, **_kwargs: expected)
    observations = tmp_path / "observations"
    result = gbp.sync_if_due(
        {
            "gbp": {
                "key_path": str(tmp_path / "key.json"),
                "location_id": "12345",
                "days": 28,
            },
        },
        load_brain(),
        observations_dir=observations,
    )

    assert result == {"status": "fetched", "records": expected}
    observation = latest_observation("gbp.performance", observations)
    assert observation is not None
    assert observation.records == expected
