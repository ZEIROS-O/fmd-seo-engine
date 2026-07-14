"""Semrush REST client — the headless fetch path.

Semrush MCP tools (mcp__semrush__*) exist only inside a Claude Code session.
The REST Analytics API is callable by headless Python, which is what lets a
cron job run the Semrush-backed checks with no session and no Lou in the loop.
The engine uses this client when a key is present; an interactive agent session
uses MCP instead. Same data, two fulfillment paths.

Credentials: an API key in the creds env file (`SEMRUSH_API_KEY=...`). Never
logged, never printed, never committed. Semrush bills in API *units*, not
dollars, so this tracks a units ledger separate from the DataForSEO USD ledger.

Analytics API returns `;`-separated CSV: header line then one line per row.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from . import killswitch

ANALYTICS_BASE = "https://api.semrush.com/"
BACKLINKS_BASE = "https://api.semrush.com/analytics/v1/"


class SemrushKeyMissing(RuntimeError):
    pass


class SemrushApiFailure(RuntimeError):
    pass


# Report types this client knows how to call, with the check they feed and the
# columns requested. Report types Semrush serves via the Projects API
# (site_audit, position_tracking) are NOT here — they need a project-scoped flow
# and stay on the MCP/agent path until wired. Honest gap, not a fake mapping.
ANALYTICS_REPORTS = {
    # organic footprint: ranked keywords for a domain
    "domain_organic": {
        "feeds": "seo.organic_footprint",
        "base": ANALYTICS_BASE,
        "columns": "Ph,Po,Nq,Ur,Kd",
    },
    # domain overview: authority + summary
    "domain_ranks": {
        "feeds": "seo.organic_footprint",
        "base": ANALYTICS_BASE,
        "columns": "Db,Dn,Rk,Or,Ot,Oc,Ad",
    },
    # competitors in organic
    "domain_organic_organic": {
        "feeds": "competitor.serp_movement",
        "base": ANALYTICS_BASE,
        "columns": "Dn,Cr,Np,Or,Ot",
    },
    # keyword overview: volume for a phrase
    "phrase_this": {
        "feeds": "market.demand",
        "base": ANALYTICS_BASE,
        "columns": "Ph,Nq,Cp,Co,Nr,Td",
    },
    # related keywords / topic discovery
    "phrase_related": {
        "feeds": "topics.related_clusters",
        "base": ANALYTICS_BASE,
        "columns": "Ph,Nq,Cp,Kd",
    },
    "phrase_questions": {
        "feeds": "topics.related_clusters",
        "base": ANALYTICS_BASE,
        "columns": "Ph,Nq,Cp,Kd",
    },
    # backlinks overview: authority score + referring domains
    "backlinks_overview": {
        "feeds": "competitor.authority_gap",
        "base": BACKLINKS_BASE,
        "columns": "ascore,total,domains_num",
    },
}


def load_key(env_file: Path) -> str:
    if not env_file.exists():
        raise SemrushKeyMissing(f"Credentials file missing: {env_file}")
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "SEMRUSH_API_KEY":
            val = value.strip().strip('"').strip("'")
            if val:
                return val
    raise SemrushKeyMissing(f"SEMRUSH_API_KEY not set in {env_file}")


@dataclass
class UnitsLedger:
    """Tracks API units consumed against a per-run cap. Semrush does not return
    unit cost per call in the response body, so cost is estimated from a static
    per-report table and reserved before the call — never after."""
    cap_units: int
    spent_units: int = 0

    def reserve(self, units: int) -> None:
        if self.spent_units + units > self.cap_units:
            raise SemrushApiFailure(
                f"units cap reached: {self.spent_units}+{units} > {self.cap_units}"
            )
        self.spent_units += units


# Static per-report unit estimate (Semrush lists live rates per report type;
# these are conservative upper bounds so the cap trips early, never late).
REPORT_UNITS = {
    "domain_organic": 10,
    "domain_ranks": 10,
    "domain_organic_organic": 10,
    "phrase_this": 10,
    "phrase_related": 40,
    "phrase_questions": 40,
    "backlinks_overview": 40,
}


def parse_csv(text: str, columns: list[str] | None = None) -> list[dict[str, str]]:
    """Semrush `;`-separated CSV → list of row dicts.

    The Analytics API returns a header line of *human-readable* names ("Keyword;
    Search Volume;...") — NOT the export_columns codes we request. When `columns`
    (the requested codes, in request order) is given, the header line is skipped
    and each row is keyed positionally by those codes, so downstream adapters can
    look up `Ph`/`Nq`/etc. reliably. Without `columns`, the header names are used
    (that path is for tests only). Empty body → [].
    """
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return []
    keys = columns if columns is not None else lines[0].split(";")
    rows = []
    for line in lines[1:]:  # always skip the header line
        cells = line.split(";")
        rows.append(dict(zip(keys, cells)))
    return rows


class SemrushClient:
    def __init__(self, env_file: Path, ledger: UnitsLedger, *,
                 systemic_failures_to_kill: int = 2, timeout_s: int = 30):
        self.env_file = env_file
        self.ledger = ledger
        self.timeout_s = timeout_s
        self.systemic_failures_to_kill = systemic_failures_to_kill
        self._systemic_failures = 0
        self._key: str | None = None

    def _ensure_key(self) -> str:
        if self._key is None:
            self._key = load_key(self.env_file)
        return self._key

    def _record_systemic_failure(self, reason: str) -> None:
        self._systemic_failures += 1
        if self._systemic_failures >= self.systemic_failures_to_kill:
            killswitch.engage(f"Semrush systemic failures x{self._systemic_failures}: {reason}")

    def fetch(self, report_type: str, **params) -> list[dict[str, str]]:
        """Call one Analytics report. Reserves units first, returns parsed rows.

        Never logs or echoes the key. Two auth/transport failures trip the kill
        switch, matching the DataForSEO client's systemic-failure contract.
        """
        killswitch.assert_not_engaged()
        if report_type not in ANALYTICS_REPORTS:
            raise SemrushApiFailure(f"unmapped report type: {report_type}")
        spec = ANALYTICS_REPORTS[report_type]
        self.ledger.reserve(REPORT_UNITS.get(report_type, 10))

        query = {
            "type": report_type,
            "key": self._ensure_key(),
            "export_columns": spec["columns"],
            **params,
        }
        url = spec["base"] + "?" + urllib.parse.urlencode(query)
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as err:
            if err.code in (401, 403):
                self._record_systemic_failure(f"HTTP {err.code} on {report_type}")
            raise SemrushApiFailure(f"HTTP {err.code} on {report_type}") from err
        except (urllib.error.URLError, TimeoutError) as err:
            self._record_systemic_failure(f"transport error on {report_type}")
            reason = getattr(err, "reason", err)
            raise SemrushApiFailure(f"transport error on {report_type}: {reason}") from err

        # Semrush returns a plain-text error line (e.g. "ERROR 50 :: NOTHING FOUND")
        # with HTTP 200. Treat the ERROR-prefixed body as an API failure.
        if body.strip().upper().startswith("ERROR"):
            first = body.strip().splitlines()[0]
            if "API KEY" in first.upper() or "AUTH" in first.upper():
                self._record_systemic_failure(first)
            # "NOTHING FOUND" is a legitimate empty result, not a failure.
            if "NOTHING FOUND" in first.upper():
                self._systemic_failures = 0
                return []
            raise SemrushApiFailure(f"Semrush error on {report_type}: {first}")

        self._systemic_failures = 0
        # Key rows positionally by the codes we requested — the response header
        # is display names, not codes.
        return parse_csv(body, columns=spec["columns"].split(","))


# The single source of truth for "the engine can fetch this headlessly": a check
# is engine_api-fulfillable only if `sync` actually implements an adapter for it.
# Having a report in ANALYTICS_REPORTS is necessary but NOT sufficient — e.g.
# domain_organic_organic exists, but competitor.serp_movement needs judgment
# (who holds page 1, new entrants) and stays on the session path. Keeping this
# explicit prevents the planner from promising a headless fetch sync won't do.
SYNC_IMPLEMENTED_CHECKS: dict[str, list[str]] = {
    "seo.organic_footprint": ["domain_organic"],
    "competitor.authority_gap": ["backlinks_overview"],
    "market.demand": ["phrase_this"],
    "topics.related_clusters": ["phrase_related"],
}


def which_checks_are_api_backed() -> dict[str, list[str]]:
    """check_id -> report types the engine can fetch headlessly. Exactly the
    checks `sync` implements. Used by the planner to label fulfillment and by
    `sync` to decide what to fetch — one source of truth, so they never diverge."""
    return {k: list(v) for k, v in SYNC_IMPLEMENTED_CHECKS.items()}
