from fmd_seo.brain import load_brain


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
