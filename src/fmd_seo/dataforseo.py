"""DataForSEO client core: credential handling, capped probe, systemic-failure
tracking. Endpoint-specific fetchers are added in Phase 4.

Credentials live outside the repo (creds_env in config) and are never logged,
printed, or committed. Two systemic auth/transport failures trip the kill switch.
"""

from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

from . import health, killswitch, paths
from .spend import SpendLedger

API_BASE = "https://api.dataforseo.com"
PROBE_ENDPOINT = "/v3/appendix/user_data"  # account/balance info; no per-call charge


class CredsMissing(RuntimeError):
    pass


class ApiFailure(RuntimeError):
    pass


def load_creds(env_file: Path) -> tuple[str, str]:
    """Parse KEY=VALUE creds file. Returns (login, password); never log values."""
    if not env_file.exists():
        raise CredsMissing(f"Credentials file missing: {env_file}")
    values: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    login = values.get("DATAFORSEO_LOGIN", "")
    password = values.get("DATAFORSEO_PASSWORD", "")
    if not login or not password:
        raise CredsMissing(f"DATAFORSEO_LOGIN/DATAFORSEO_PASSWORD not set in {env_file}")
    return login, password


class DataForSeoClient:
    def __init__(self, env_file: Path, ledger: SpendLedger, *,
                 systemic_failures_to_kill: int = 2, timeout_s: int = 30,
                 health_file: Path | None = None):
        self.env_file = env_file
        self.ledger = ledger
        self.timeout_s = timeout_s
        self.systemic_failures_to_kill = systemic_failures_to_kill
        self.health_file = health_file or paths.HEALTH_FILE
        self._auth: str | None = None

    def _ensure_auth(self) -> str:
        if self._auth is None:
            login, password = load_creds(self.env_file)
            token = base64.b64encode(f"{login}:{password}".encode()).decode()
            self._auth = f"Basic {token}"
        return self._auth

    def _record_systemic_failure(self, reason: str) -> None:
        count = health.record_systemic_failure(self.health_file, "dataforseo")
        if count >= self.systemic_failures_to_kill:
            killswitch.engage(f"DataForSEO systemic failures x{count}: {reason}")

    def _request(self, endpoint: str, payload: list | None = None) -> dict:
        killswitch.assert_not_engaged()
        auth = self._ensure_auth()
        req = urllib.request.Request(
            API_BASE + endpoint,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={"Authorization": auth, "Content-Type": "application/json"},
            method="POST" if payload is not None else "GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as err:
            if err.code in (401, 402, 403):
                self._record_systemic_failure(f"HTTP {err.code} on {endpoint}")
            raise ApiFailure(f"HTTP {err.code} on {endpoint}") from err
        except (urllib.error.URLError, TimeoutError) as err:
            self._record_systemic_failure(f"transport error on {endpoint}")
            raise ApiFailure(f"Transport error on {endpoint}: {err.reason if hasattr(err, 'reason') else err}") from err
        if body.get("status_code") != 20000:
            code = body.get("status_code")
            if code in (40100, 40200, 40101):
                self._record_systemic_failure(f"API status {code} on {endpoint}")
            raise ApiFailure(f"API status {code} on {endpoint}: {body.get('status_message')}")
        health.clear_systemic_failures(self.health_file, "dataforseo")
        return body

    def probe(self) -> dict:
        """Capped account probe: verifies auth and returns balance/limits summary.
        Reserves against the 'probe' endpoint cap even though user_data is free,
        so a retry loop cannot spin unbounded."""
        reservation = self.ledger.reserve("probe", 0.0)
        body = self._request(PROBE_ENDPOINT)
        task = body["tasks"][0]["result"][0]
        money = task.get("money", {})
        self.ledger.settle(reservation, 0.0, "user_data probe")
        return {
            "balance_usd": money.get("balance"),
            "rates_known": bool(task.get("rates")),
            "backlinks_subscription": bool(task.get("backlinks_subscription_expiry_date")),
        }
