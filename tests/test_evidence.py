import json
from pathlib import Path

import pytest

from fmd_seo.evidence import FMD_OPERATING_COORDINATE, fetch_serp


class _Ledger:
    def reserve(self, _endpoint, _estimated):
        return "reservation"

    def settle(self, _reservation, _actual, _note):
        return None


class _Client:
    ledger = _Ledger()

    def __init__(self, result):
        self.result = result
        self.endpoint = None
        self.payload = None

    def _request(self, endpoint, payload):
        self.endpoint = endpoint
        self.payload = payload
        return {"cost": 0.002, "tasks": [{"result": self.result}]}


def test_fetch_serp_coordinate_preserves_local_pack_details(tmp_path: Path):
    client = _Client([{
        "datetime": "2026-07-19 12:00:00 +00:00",
        "check_url": "https://www.google.com/search?q=car+detailing",
        "se_results_count": 99,
        "items": [
            {
                "type": "local_pack",
                "rank_group": 1,
                "rank_absolute": 4,
                "title": "Fresh Mobile Detailing",
                "cid": "123",
                "domain": "freshmobiledetail.com",
                "phone": "(216) 359-1034",
                "url": "https://freshmobiledetail.com/",
                "booking_url": "https://example.test/book",
                "rating": {"value": 5, "votes_count": 13},
                "description": "Mayfield Heights",
                "is_paid": False,
            },
            {
                "type": "organic",
                "rank_absolute": 5,
                "domain": "freshmobiledetail.com",
                "title": "Fresh",
                "url": "https://freshmobiledetail.com/",
            },
        ],
    }])

    evidence = fetch_serp(
        client,
        "car detailing mayfield heights",
        tmp_path,
        device="mobile",
        location_coordinate=FMD_OPERATING_COORDINATE,
    )

    assert client.payload == [{
        "keyword": "car detailing mayfield heights",
        "language_code": "en",
        "device": "mobile",
        "location_coordinate": FMD_OPERATING_COORDINATE,
    }]
    assert evidence.normalized["location_name"] is None
    assert evidence.normalized["location_coordinate"] == FMD_OPERATING_COORDINATE
    assert evidence.normalized["provider_datetime"] == "2026-07-19 12:00:00 +00:00"
    assert evidence.normalized["local_pack"] == [{
        "order": 1,
        "rank_absolute": 4,
        "business_name": "Fresh Mobile Detailing",
        "cid": "123",
        "domain": "freshmobiledetail.com",
        "phone": "(216) 359-1034",
        "url": "https://freshmobiledetail.com/",
        "booking_url": "https://example.test/book",
        "rating": 5,
        "reviews": 13,
        "description": "Mayfield Heights",
        "is_paid": False,
    }]
    assert evidence.normalized["organic_top10"][0]["rank"] == 5
    assert json.loads(next(tmp_path.glob("*.json")).read_text())["cost"] == 0.002


def test_fetch_serp_named_location_remains_compatible(tmp_path: Path):
    client = _Client([{"items": []}])

    evidence = fetch_serp(client, "car detailing", tmp_path)

    assert client.payload[0]["location_name"] == "Cleveland,Ohio,United States"
    assert "location_coordinate" not in client.payload[0]
    assert evidence.normalized["location"] == "Cleveland,Ohio,United States"
    assert evidence.normalized["local_pack"] == []


def test_fetch_serp_rejects_unsupported_device(tmp_path: Path):
    with pytest.raises(ValueError, match="unsupported SERP device"):
        fetch_serp(_Client([]), "car detailing", tmp_path, device="tablet")
