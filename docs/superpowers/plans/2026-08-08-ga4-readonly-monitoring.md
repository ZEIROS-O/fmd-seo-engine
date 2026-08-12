# GA4 Read-Only Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a weekly read-only GA4 traffic observation for property `541970582` to the existing `fmd-seo sync` loop and live-verify GA4 plus GSC property access.

**Architecture:** A focused `ga4.py` provider uses the existing `google-auth` plus `requests` stack to call the GA4 Data API REST endpoint and normalize one bounded report. The provider follows the existing GBP cadence/observation pattern, while `loop_cli.cmd_sync` owns aggregation and failure reporting through `sync.health`.

**Tech Stack:** Python 3.10+, PyYAML, google-auth, requests, pytest, Google Analytics Data API v1beta REST.

## Global Constraints

- Runtime OAuth scope is exactly `https://www.googleapis.com/auth/analytics.readonly`.
- Property ID is `541970582`; account, stream, and measurement IDs are not request identifiers.
- The reporting window is `28daysAgo` through `yesterday`.
- The key stays outside the repo at `/home/lucascoh/.gsc-service-account.json` with mode `0600`.
- No GA4 Admin API or configuration writes are allowed.
- Raw API payloads, access tokens, and key material are never committed or logged.
- Missing configuration skips honestly; configured provider failures surface through `sync.health`.
- Implementation remains isolated on `codex/ga4-readonly-monitoring`; the dirty `main` checkout is untouched.
- A valid zero-row GA4 response includes exact requested headers, metadata, and `rowCount: 0`; missing response structure fails closed.
- GA4 is `engine_api` only when its property ID is configured and its key file exists; otherwise its fallback is `human`.

---

### Task 1: Register GA4 configuration and the strict observation contract

**Files:**
- Modify: `config/engine.yaml:39-48`
- Modify: `src/fmd_seo/paths.py:52-55`
- Modify: `brain/checks.yaml` before the existing `gbp.performance` check
- Modify: `pyproject.toml:15-18`
- Modify: `tests/test_paths.py:12-39`
- Create: `tests/test_ga4.py`

**Interfaces:**
- Consumes: `paths.load_config(path: Path | None = None) -> dict` and the brain check schema.
- Produces: `config["ga4"]` with `key_path`, `property_id`, and `days`; brain check `analytics.traffic`; optional dependency extra `ga4`.

- [ ] **Step 1: Write failing configuration and schema tests**

Add `ga4` to the test config in `tests/test_paths.py` and assert the Google-key override:

```python
"ga4": {
    "key_path": "/home/local/google.json",
    "property_id": "541970582",
    "days": 28,
},
```

```python
assert config["ga4"]["key_path"] == "/ci/google.json"
assert config["ga4"]["property_id"] == "541970582"
```

Create `tests/test_ga4.py` with the contract check:

```python
from fmd_seo.brain import load_brain


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
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_paths.py tests/test_ga4.py -q
```

Expected: failure because `ga4.key_path` is not overridden and `analytics.traffic` is unknown.

- [ ] **Step 3: Add minimal configuration, dependency, and check definitions**

Add to `config/engine.yaml`:

```yaml
ga4:
  key_path: "/home/lucascoh/.gsc-service-account.json"
  property_id: "541970582"
  days: 28
```

Extend `FMD_SEO_GOOGLE_KEY` handling in `paths.load_config`:

```python
cfg.setdefault("ga4", {})["key_path"] = value
```

Add to `pyproject.toml`:

```toml
ga4 = ["google-auth>=2.0", "requests>=2.0"]
```

Add the check to `brain/checks.yaml`:

```yaml
  - id: analytics.traffic
    domain: analytics
    title: GA4 acquisition and conversion measurement
    cadence: weekly
    cost: free
    method:
      kind: console
      run: |
        Fetch a read-only 28-day GA4 Data API report grouped by session source
        and default channel group. Record total, engaged, organic-search, known
        AI-referral sessions, and key events without estimating missing data.
    records:
      - {name: sessions, type: int}
      - {name: engaged_sessions, type: int}
      - {name: organic_search_sessions, type: int}
      - {name: ai_referral_sessions, type: int}
      - {name: key_events, type: int}
    thresholds:
      - expr: sessions > 0 and key_events == 0
        severity: high
        finding: "GA4 records traffic but no key events, so acquisition cannot be tied to business outcomes."
        action: "Design and verify booking conversion measurement before optimizing traffic sources."
    why: "First-party acquisition and conversion measurement prevents rankings or clicks from becoming outcome proxies."
```

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_paths.py tests/test_ga4.py -q
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit the contract**

```bash
git add config/engine.yaml src/fmd_seo/paths.py brain/checks.yaml pyproject.toml tests/test_paths.py tests/test_ga4.py
git commit -m "feat: register GA4 traffic monitoring contract"
```

---

### Task 2: Implement pure GA4 normalization and the bounded REST fetch

**Files:**
- Create: `src/fmd_seo/ga4.py`
- Modify: `tests/test_ga4.py`

**Interfaces:**
- Consumes: GA4 `runReport` JSON rows in request order: dimensions `sessionSource`, `sessionDefaultChannelGroup`; metrics `sessions`, `engagedSessions`, `keyEvents`.
- Produces: `Ga4Config`, `Ga4Unavailable`, `normalize_report(response: dict) -> dict[str, int]`, and `fetch_traffic(config: Ga4Config, session=None) -> dict[str, int]`.

- [ ] **Step 1: Write failing normalization and request tests**

Add representative normalization tests:

```python
import pytest

from fmd_seo.ga4 import Ga4Config, Ga4Unavailable, fetch_traffic, normalize_report


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


def test_normalize_report_rejects_fractional_or_malformed_counts():
    with pytest.raises(Ga4Unavailable, match="whole count"):
        normalize_report({"rows": [_row("google", "Organic Search", "1", "1", "0.5")]})
    with pytest.raises(Ga4Unavailable, match="GA4 row shape"):
        normalize_report({"rows": [{"dimensionValues": [], "metricValues": []}]})
```

Use a fake response/session to prove the exact endpoint and body:

```python
class FakeResponse:
    ok = True
    status_code = 200

    def json(self):
        return {"rows": []}


class FakeSession:
    def __init__(self):
        self.calls = []

    def post(self, url, *, json, timeout):
        self.calls.append((url, json, timeout))
        return FakeResponse()


def test_fetch_traffic_calls_bounded_read_only_report(tmp_path):
    session = FakeSession()
    records = fetch_traffic(
        Ga4Config(tmp_path / "unused.json", "541970582", 28),
        session=session,
    )
    assert records["sessions"] == 0
    url, body, timeout = session.calls[0]
    assert url.endswith("/v1beta/properties/541970582:runReport")
    assert body["dateRanges"] == [{"startDate": "28daysAgo", "endDate": "yesterday"}]
    assert [value["name"] for value in body["dimensions"]] == [
        "sessionSource", "sessionDefaultChannelGroup",
    ]
    assert [value["name"] for value in body["metrics"]] == [
        "sessions", "engagedSessions", "keyEvents",
    ]
    assert timeout == 30
```

- [ ] **Step 2: Run the provider tests and verify RED**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ga4.py -q
```

Expected: import failure because `fmd_seo.ga4` does not exist.

- [ ] **Step 3: Implement the minimal provider**

Create `src/fmd_seo/ga4.py` with these public contracts and fail-closed parsing:

```python
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
    pass


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
    return any(host == domain or host.endswith(f".{domain}") for domain in AI_SOURCE_HOSTS)


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
    except Exception as err:
        raise Ga4Unavailable(f"GA4 auth failed: {type(err).__name__}") from err


def fetch_traffic(config: Ga4Config, *, session=None) -> dict[str, int]:
    client = session or _authorized_session(config.key_path)
    body = {
        "dateRanges": [{"startDate": f"{config.days}daysAgo", "endDate": "yesterday"}],
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
    response = client.post(
        f"{DATA_BASE}/v1beta/properties/{config.property_id}:runReport",
        json=body,
        timeout=30,
    )
    if not response.ok:
        raise Ga4Unavailable(f"GA4 Data API HTTP {response.status_code}")
    try:
        payload = response.json()
    except Exception as err:
        raise Ga4Unavailable("GA4 Data API returned invalid JSON") from err
    return normalize_report(payload)
```

Use the code above as the minimal implementation. Keep all key and token values out of exception text.

- [ ] **Step 4: Run provider tests and verify GREEN**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ga4.py -q
```

Expected: all provider tests pass.

- [ ] **Step 5: Commit the provider**

```bash
git add src/fmd_seo/ga4.py tests/test_ga4.py
git commit -m "feat: add read-only GA4 Data API provider"
```

---

### Task 3: Add weekly cadence and durable observation recording

**Files:**
- Modify: `src/fmd_seo/ga4.py`
- Modify: `tests/test_ga4.py`

**Interfaces:**
- Consumes: `latest_observation`, `record_observation`, brain check `analytics.traffic`, and `fetch_traffic`.
- Produces: `sync_if_due(config: dict, brain: Brain, observations_dir: Path | None = None) -> dict` with statuses `skipped_config`, `not_due`, or `fetched`.

- [ ] **Step 1: Write failing cadence and observation tests**

```python
def test_sync_if_due_records_weekly_ga4_observation(tmp_path, monkeypatch):
    from fmd_seo import ga4
    from fmd_seo.brain import load_brain
    from fmd_seo.observations import latest_observation

    expected = {
        "sessions": 14,
        "engaged_sessions": 10,
        "organic_search_sessions": 8,
        "ai_referral_sessions": 3,
        "key_events": 1,
    }
    monkeypatch.setattr(ga4, "fetch_traffic", lambda *_args, **_kwargs: expected)
    observations = tmp_path / "observations"
    result = ga4.sync_if_due(
        {"ga4": {"key_path": str(tmp_path / "key.json"), "property_id": "541970582", "days": 28}},
        load_brain(),
        observations_dir=observations,
    )
    assert result == {"status": "fetched", "records": expected}
    observation = latest_observation("analytics.traffic", observations)
    assert observation.records == expected
    assert observation.source == "google_analytics:data_api"


def test_sync_if_due_skips_missing_config_and_recent_observation(tmp_path, monkeypatch):
    from fmd_seo import ga4
    from fmd_seo.brain import load_brain
    from fmd_seo.observations import record_observation

    brain = load_brain()
    observations = tmp_path / "observations"
    assert ga4.sync_if_due({}, brain, observations_dir=observations) == {"status": "skipped_config"}
    records = {"sessions": 1, "engaged_sessions": 1, "organic_search_sessions": 1, "ai_referral_sessions": 0, "key_events": 0}
    record_observation(brain, "analytics.traffic", records, "engine_api", "test", directory=observations)
    monkeypatch.setattr(ga4, "fetch_traffic", lambda *_args, **_kwargs: pytest.fail("must not fetch"))
    assert ga4.sync_if_due({"ga4": {"key_path": "key.json", "property_id": "541970582"}}, brain, observations_dir=observations)["status"] == "not_due"
```

- [ ] **Step 2: Run cadence tests and verify RED**

Run:

```bash
PYTHONPATH=src python3 -m pytest tests/test_ga4.py -q
```

Expected: failure because `sync_if_due` is not defined.

- [ ] **Step 3: Implement cadence and recording**

Add these imports and function to `ga4.py`:

```python
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .brain import Brain


def sync_if_due(
    config: dict,
    brain: "Brain",
    *,
    observations_dir: Path | None = None,
) -> dict:
    from .observations import latest_observation, record_observation

    raw = config.get("ga4") or {}
    key_path = str(raw.get("key_path") or "").strip()
    property_id = str(raw.get("property_id") or "").strip()
    if not key_path or not property_id:
        return {"status": "skipped_config"}
    latest = latest_observation("analytics.traffic", observations_dir)
    if latest is not None:
        observed_at = datetime.fromisoformat(latest.observed_at)
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - observed_at < timedelta(days=7):
            return {"status": "not_due", "observed_at": latest.observed_at}
    days = int(raw.get("days", 28))
    records = fetch_traffic(
        Ga4Config(key_path=Path(key_path), property_id=property_id, days=days)
    )
    record_observation(
        brain,
        "analytics.traffic",
        records,
        fulfillment="engine_api",
        source="google_analytics:data_api",
        note=(f"property={property_id}; window={days}daysAgo..yesterday; "
              "ai_sources=host_allowlist"),
        directory=observations_dir,
    )
    return {"status": "fetched", "records": records}
```

- [ ] **Step 4: Run cadence tests and verify GREEN**

```bash
PYTHONPATH=src python3 -m pytest tests/test_ga4.py -q
```

Expected: all GA4 tests pass.

- [ ] **Step 5: Commit cadence integration**

```bash
git add src/fmd_seo/ga4.py tests/test_ga4.py
git commit -m "feat: record weekly GA4 traffic observations"
```

---

### Task 4: Integrate GA4 with the headless sync health contract

**Files:**
- Modify: `src/fmd_seo/loop_cli.py:139-195`
- Modify: `tests/test_failure_injection.py:95-119`

**Interfaces:**
- Consumes: `ga4.sync_if_due` status objects.
- Produces: `payload["ga4"]`, `analytics.traffic` in fetched/errors, and accurate `sync.health` counts.

- [ ] **Step 1: Write failing sync success and failure tests**

Import the provider modules and monkeypatch unrelated providers so the test is deterministic:

```python
def test_sync_command_includes_ga4_success(tmp_path, monkeypatch):
    from fmd_seo import ga4, gbp, site_facts, sync
    from fmd_seo.loop_cli import cmd_sync
    from fmd_seo.sync import SyncResult

    monkeypatch.setattr(sync, "sync_due", lambda *_args, **_kwargs: SyncResult([], [], {}))
    monkeypatch.setattr(gbp, "sync_if_due", lambda *_args, **_kwargs: {"status": "skipped_config"})
    monkeypatch.setattr(site_facts, "sync_public_facts", lambda *_args, **_kwargs: {"status": "skipped_config"})
    monkeypatch.setattr(ga4, "sync_if_due", lambda *_args, **_kwargs: {"status": "fetched", "records": {}})
    payload, code = cmd_sync({}, observations_dir=tmp_path / "observations")
    assert payload["ga4"]["status"] == "fetched"
    assert "analytics.traffic" in payload["fetched"]
    assert code == 0
```

Add the failure case:

```python
def test_sync_command_surfaces_ga4_failure(tmp_path, monkeypatch):
    from fmd_seo import ga4, gbp, site_facts, sync
    from fmd_seo.loop_cli import cmd_sync
    from fmd_seo.sync import SyncResult

    monkeypatch.setattr(sync, "sync_due", lambda *_args, **_kwargs: SyncResult([], [], {}))
    monkeypatch.setattr(gbp, "sync_if_due", lambda *_args, **_kwargs: {"status": "skipped_config"})
    monkeypatch.setattr(site_facts, "sync_public_facts", lambda *_args, **_kwargs: {"status": "skipped_config"})

    def fail_ga4(*_args, **_kwargs):
        raise RuntimeError("GA4 denied")

    monkeypatch.setattr(ga4, "sync_if_due", fail_ga4)
    payload, code = cmd_sync({}, observations_dir=tmp_path / "observations")
    assert payload["ga4"] == {"status": "failed", "error": "GA4 denied"}
    assert payload["errors"]["analytics.traffic"] == "GA4 denied"
    assert code == 4
```

- [ ] **Step 2: Run sync tests and verify RED**

```bash
PYTHONPATH=src python3 -m pytest tests/test_failure_injection.py -q
```

Expected: GA4 is absent from the payload and error map.

- [ ] **Step 3: Wire GA4 into `cmd_sync`**

Immediately after GBP handling, import `sync_if_due` from `.ga4`, call it in its own `try` block, append `analytics.traffic` only for `fetched`, and add exceptions to `errors["analytics.traffic"]`. Include `"ga4": ga4_result` in the payload. Preserve the existing exit-code rules and provider isolation.

- [ ] **Step 4: Run focused and full offline tests**

```bash
PYTHONPATH=src python3 -m pytest tests/test_ga4.py tests/test_paths.py tests/test_failure_injection.py -q
PYTHONPATH=src python3 -m pytest -q
```

The full suite must report 0 failed and 0 errors. If the sandbox blocks the localhost HTML fixture, rerun the same full command with localhost permission.

- [ ] **Step 5: Commit sync integration**

```bash
git add src/fmd_seo/loop_cli.py tests/test_failure_injection.py
git commit -m "feat: include GA4 in headless sync health"
```

---

### Task 5: Document and live-verify both Google APIs without durable writes

**Files:**
- Modify: `README.md` under Credentials and command reference
- Modify: `brain/README.md` under fulfillment paths
- Verification only: `/home/lucascoh/.gsc-service-account.json`

**Interfaces:**
- Consumes: configured GA4/GSC providers and live Google property permissions.
- Produces: documented setup plus separate read-only GA4 and GSC verification evidence in terminal output only.

- [ ] **Step 1: Add concise operator documentation**

Document that `fmd-seo sync` includes weekly GA4 property `541970582`, uses `analytics.readonly`, and reuses `FMD_SEO_GOOGLE_KEY`. State that the account, stream, and measurement IDs are not used by the Data API call and that Admin API writes remain out of scope.

- [ ] **Step 2: Run documentation drift checks**

```bash
rg -n "541970582|analytics.readonly|analytics.traffic|FMD_SEO_GOOGLE_KEY" README.md brain/README.md config/engine.yaml src/fmd_seo/ga4.py
git diff --check
```

Expected: each contract is named and no whitespace errors are reported.

- [ ] **Step 3: Commit documentation**

```bash
git add README.md brain/README.md
git commit -m "docs: explain GA4 monitoring setup"
```

- [ ] **Step 4: Live-verify GA4 in a temporary observation directory**

Run a short Python process that prints only normalized fields:

```bash
PYTHONPATH=src python3 -c 'import json; from pathlib import Path; from fmd_seo.ga4 import Ga4Config, fetch_traffic; from fmd_seo.paths import load_config; c=load_config()["ga4"]; r=fetch_traffic(Ga4Config(Path(c["key_path"]), str(c["property_id"]), int(c.get("days", 28)))); print(json.dumps(r, sort_keys=True))'
```

The command exits nonzero on auth, property, or API failure and does not print the credential, access token, or raw response.

- [ ] **Step 5: Live-verify GSC without recording an observation**

Run a short Python process that prints only the returned coverage state:

```bash
PYTHONPATH=src python3 -c 'import json; from pathlib import Path; from fmd_seo.gsc import _build_service, inspect_url; from fmd_seo.paths import load_config; c=load_config()["gsc"]; state=inspect_url(_build_service(Path(c["key_path"])), c["site_url"], "https://freshmobiledetail.com/"); print(json.dumps({"coverage_state": state, "nonempty": bool(state)}))'
```

Do not run `gsc-sync`, update GATE-1, or write evidence.

- [ ] **Step 6: Run final verification**

```bash
PYTHONPATH=src python3 -m pytest -q
git diff --check
git status --short
git log --oneline --decorate -6
```

Expected: full suite passes; diff check is clean; only intentionally uncommitted temporary verification artifacts are absent; feature commits are on `codex/ga4-readonly-monitoring`.

---

### Task 6: Harden the reviewed response and planner contracts

**Files:**
- Modify: `src/fmd_seo/ga4.py`
- Modify: `src/fmd_seo/planner.py`
- Modify: `src/fmd_seo/loop_cli.py`
- Modify: `brain/checks.yaml`
- Modify: `tests/test_ga4.py`
- Modify: `tests/test_planner.py`

**Interfaces:**
- Consumes: GA4 `RunReportResponse` and `build_plan(..., has_ga4: bool = False)` availability input.
- Produces: fail-closed normalization and truthful `human` versus `engine_api` GA4 fulfillment.

- [ ] **Step 1: Write response-contract regression tests**

Use a complete response helper in `tests/test_ga4.py`:

```python
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
```

Prove `normalize_report({})` raises `Ga4Unavailable`, reordered headers raise,
and `_report(rows=None, row_count=0)` returns the five literal zero records.

- [ ] **Step 2: Run the GA4 tests and verify RED**

```bash
PYTHONPATH=src python3 -m pytest tests/test_ga4.py -q
```

Expected: the incomplete response is accepted as zeros before the fix.

- [ ] **Step 3: Validate the structural contract minimally**

Add ordered constants for the two requested dimensions and three metrics.
Require `metadata` to be a dictionary, `rowCount` to be present and whole, and
header `.name` lists to equal those constants before reading optional rows.

- [ ] **Step 4: Write planner availability regression tests and verify RED**

Add tests asserting:

```python
plan = build_plan(brain, has_semrush_key=False, has_ga4=True,
                  observations_dir=empty_obs)
traffic = next(pc for pc in plan.due if pc.check_id == "analytics.traffic")
assert traffic.fulfillment == "engine_api"
assert traffic.api_reports == ["ga4:runReport"]
```

Repeat with `has_ga4=False` and assert `traffic.fulfillment == "human"`.

- [ ] **Step 5: Implement configuration-aware GA4 fulfillment**

Change the check fallback kind to `console`, add `has_ga4=False` to
`build_plan`, and return `("engine_api", ["ga4:runReport"])` for the traffic
check when true. Add `_has_ga4(config)` in `loop_cli.py`; it returns true only
when `property_id` exists and `key_path` names an existing file. Pass it from
both `cmd_beat` and `cmd_brief`.

- [ ] **Step 6: Remove the dirty-main registry overlap**

Move the GA4 check after `gbp.performance`, then three-way-check the branch
version against committed `main` and dirty-main `brain/checks.yaml`. Both
`analytics.traffic` and `seo.local_visibility` must survive without conflict.

- [ ] **Step 7: Verify and publish**

```bash
PYTHONPATH=src python3 -m pytest tests/test_ga4.py tests/test_planner.py tests/test_gsc.py -q
PYTHONPATH=src python3 -m pytest -q
git diff --check
```

Review the scoped diff, commit, push, wait for required checks, resolve the
addressed review thread, and merge PR #1 only while its expected head SHA is
unchanged.
