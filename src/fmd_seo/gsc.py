"""Google Search Console client — the headless index-coverage path.

Index coverage ("Discovered – currently not indexed" etc.) has NO bulk API. The
only programmatic route is the URL Inspection API: inspect each sitemap URL, read
its coverageState, and tally. For ~20 URLs/day that is far inside the quota
(2000/day, 600/min per property).

Auth is a Google service account (JSON key), added as a user on the GSC property.
This needs RSA-JWT signing, which the stdlib can't do — hence the optional
`google-auth` + `google-api-python-client` deps, imported lazily so the core
engine (and its tests) never require them. The key path is config-driven and its
contents are never logged or committed (it lives outside the repo).

This removes the last human-bound check: seo.indexation, the GATE-1 input.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/webmasters.readonly"]


class GscUnavailable(RuntimeError):
    """Missing key, missing libs, or an API failure. Always fails closed —
    never a degraded/guessed reading (GATE-4)."""


# ─────────────────── pure classifier: coverageState -> bucket ───────────────────
#
# coverageState strings mirror the GSC UI. Kept as substring rules so a wording
# tweak on Google's side degrades to "not_indexed" (safe) rather than crashing.

def classify_coverage(coverage_state: str) -> str:
    """Return one of: indexed | discovered_not_indexed | crawled_not_indexed |
    not_indexed. Unknown/redirect/excluded all fall to not_indexed — they are not
    indexed, which is what the gate cares about."""
    s = (coverage_state or "").strip().lower()
    if s.startswith("discovered"):
        return "discovered_not_indexed"
    if s.startswith("crawled"):
        return "crawled_not_indexed"
    # "Submitted and indexed", "Indexed, not submitted in sitemap", "Indexed"
    if "indexed" in s and "not indexed" not in s:
        return "indexed"
    return "not_indexed"


def tally(coverage_states: list[str], *, inspected_ok: int | None = None) -> dict:
    """Aggregate coverageState strings into the seo.indexation record shape."""
    buckets = {"indexed": 0, "discovered_not_indexed": 0,
               "crawled_not_indexed": 0, "not_indexed_other": 0}
    for state in coverage_states:
        b = classify_coverage(state)
        if b == "indexed":
            buckets["indexed"] += 1
        elif b == "discovered_not_indexed":
            buckets["discovered_not_indexed"] += 1
        elif b == "crawled_not_indexed":
            buckets["crawled_not_indexed"] += 1
        else:
            buckets["not_indexed_other"] += 1
    not_indexed = (buckets["discovered_not_indexed"] + buckets["crawled_not_indexed"]
                   + buckets["not_indexed_other"])
    return {
        "indexed": buckets["indexed"],
        "not_indexed": not_indexed,
        "discovered_not_indexed": buckets["discovered_not_indexed"],
        "crawled_not_indexed": buckets["crawled_not_indexed"],
        "inspected_ok": len(coverage_states) if inspected_ok is None else inspected_ok,
    }


# ─────────────────────────── client ───────────────────────────

@dataclass
class GscConfig:
    key_path: Path       # service-account JSON key
    site_url: str        # "sc-domain:example.com" or "https://example.com/"


def _build_service(key_path: Path):
    """Lazy-import the google libs and build the Search Console service. Raises
    GscUnavailable (never leaks the key) on any auth/lib problem."""
    if not key_path.exists():
        raise GscUnavailable(f"service-account key not found: {key_path}")
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as err:
        raise GscUnavailable(
            "google-auth/google-api-python-client not installed "
            "(`pip install -e .[gsc]`)"
        ) from err
    try:
        creds = service_account.Credentials.from_service_account_file(
            str(key_path), scopes=SCOPES)
        return build("searchconsole", "v1", credentials=creds,
                     cache_discovery=False)
    except Exception as err:  # noqa: BLE001 - any auth error fails closed, no key leak
        raise GscUnavailable(f"GSC auth failed: {type(err).__name__}") from err


def inspect_url(service, site_url: str, url: str) -> str:
    """Return the coverageState string for one URL. Empty string if the API
    doesn't report one (treated as not_indexed by the classifier)."""
    body = {"inspectionUrl": url, "siteUrl": site_url}
    resp = service.urlInspection().index().inspect(body=body).execute()
    return (resp.get("inspectionResult", {})
                .get("indexStatusResult", {})
                .get("coverageState", ""))


def fetch_indexation(cfg: GscConfig, urls: list[str]) -> dict:
    """Inspect every URL and return the seo.indexation record dict. Raises
    GscUnavailable if the service can't be built; a per-URL error is recorded as
    not_indexed rather than aborting the whole tally (one bad URL != no reading)."""
    service = _build_service(cfg.key_path)
    if not urls:
        raise GscUnavailable("GSC inspection received no URLs")
    states: list[str] = []
    succeeded = 0
    for url in urls:
        try:
            states.append(inspect_url(service, cfg.site_url, url))
            succeeded += 1
        except Exception:  # noqa: BLE001 - a single inspect failure -> not_indexed bucket
            states.append("")
    if succeeded / len(urls) < 0.9:
        raise GscUnavailable(
            f"GSC URL Inspection succeeded for only {succeeded}/{len(urls)} URLs"
        )
    return tally(states, inspected_ok=succeeded)
