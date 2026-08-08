# GA4 Read-Only Monitoring Design

## Goal

Connect Google Analytics 4 property `541970582` to the existing headless SEO
engine so the weekly `fmd-seo sync` run records a truthful 28-day traffic and
conversion snapshot. The same protected service-account credential already used
for Google Search Console supplies authentication.

This is the smallest useful increment toward broader Analytics autonomy. It is
strictly read-only and does not change GA4 property configuration, tags, events,
key events, attribution, retention, users, data streams, or the website.

## Selected Approach

Call the GA4 Data API REST endpoint with `google-auth` and `requests`, following
the existing Google Business Profile provider pattern. This avoids adding the
`google-analytics-data` client package while retaining short-lived OAuth access
tokens and the least-privilege scope:

```text
https://www.googleapis.com/auth/analytics.readonly
```

The engine will call:

```text
POST https://analyticsdata.googleapis.com/v1beta/properties/541970582:runReport
```

The request will cover `28daysAgo` through `yesterday`, group rows by
`sessionSource` and `sessionDefaultChannelGroup`, and request `sessions`,
`engagedSessions`, and `keyEvents`.

The official Python client was rejected for this increment because its only
material benefit here is typed request objects, while it introduces another
runtime dependency. A connectivity-only command was rejected because it would
not produce durable monitoring evidence.

## Configuration

Add a dedicated configuration section:

```yaml
ga4:
  key_path: "/home/lucascoh/.gsc-service-account.json"
  property_id: "541970582"
  days: 28
```

`FMD_SEO_GOOGLE_KEY` will override the `ga4.key_path` in addition to the existing
GSC and GBP key paths. GitHub Actions can therefore reuse the current
`GSC_SERVICE_ACCOUNT_JSON` secret and `/home/runner/.gsc-service-account.json`
runtime file; no new credential or repository secret is required.

The GA4 account ID `398272317`, web stream ID `15085986065`, and measurement ID
`G-Z5GNPKY73K` are not API request identifiers for this feature and will not be
stored in engine configuration.

## Provider Boundary

Create `src/fmd_seo/ga4.py` with four responsibilities:

1. Build an authorized session from the configured service-account JSON using
   only `analytics.readonly`.
2. Submit a bounded GA4 `runReport` request with a 30-second timeout.
3. Normalize GA4 rows into the engine's strict observation record.
4. Fetch and record the check only when its weekly cadence is due.

Authentication failures, missing configuration, invalid responses, and non-2xx
responses must never expose the key contents. Missing configuration is an honest
skip. A configured provider failure is reported through `sync.health` and makes
the sync partial or blocked according to the existing provider rules.

## Observation Contract

Add a weekly, free, engine-backed check named `analytics.traffic` with these
integer records:

```text
sessions
engaged_sessions
organic_search_sessions
ai_referral_sessions
key_events
```

Normalization rules:

- `sessions` is the sum of all returned session rows.
- `engaged_sessions` is the sum of all returned engaged-session rows.
- `organic_search_sessions` includes rows whose default channel group is
  `Organic Search`.
- `ai_referral_sessions` includes rows whose normalized session source is one
  of `chatgpt.com`, `perplexity.ai`, `claude.ai`, `copilot.microsoft.com`, or
  `gemini.google.com`, including subdomains of those hosts.
- `key_events` is the integer sum of the GA4 key-event metric. Decimal strings
  are accepted only when they represent a whole count; fractional values fail
  closed rather than being rounded into invented data.

The recorded source is `google_analytics:data_api`. The note states the property
ID, date window, and source-classification rule without including credentials or
raw payloads.

The first increment adds one actionable threshold: when sessions are greater
than zero and key events are zero, emit a high-severity finding that conversion
measurement is absent. Zero sessions alone is not treated as a site-performance
conclusion because it can also indicate a configuration or collection problem.

## Sync Integration

`fmd-seo sync` will call `ga4.sync_if_due(...)` alongside the existing Semrush,
GBP, and public-facts providers.

- `fetched` adds `analytics.traffic` to the fetched-check list.
- `not_due` and `skipped_config` do not count as attempted failures.
- Provider exceptions add `analytics.traffic` to the error map.
- The returned sync payload includes a `ga4` status object.
- `sync.health` includes the GA4 attempt in its succeeded/failed counts.

The integration does not add a separate mutating CLI command. The existing
lock, kill switch, receipt, observation, and scheduled workflow behavior remains
the single execution path.

## Security and Authority

This increment uses read-only OAuth scope even though the service account has
GA4 Editor permission. Runtime scope is an independent restriction and prevents
this client from issuing Analytics Admin API writes.

The JSON key remains outside the repository at
`/home/lucascoh/.gsc-service-account.json` with mode `0600`. Tests use injected
sessions or pure normalization payloads and never load the real key. Logs,
receipts, observations, and errors never contain access tokens or key material.

Broader GA4 setup and optimization is deferred. It requires a separate design
for Admin API allowlists, dry-run diffs, approvals, rollback, and destructive
operation blocks.

## Testing

Implementation follows test-driven development.

Unit coverage will prove:

- totals are normalized correctly from representative GA4 rows;
- organic and known AI sources are classified correctly;
- unrelated referral sources are not counted as AI;
- malformed or fractional whole-count fields fail closed;
- a configured due check records an `analytics.traffic` observation;
- a recent observation returns `not_due` without an API call;
- missing configuration returns `skipped_config`;
- `FMD_SEO_GOOGLE_KEY` overrides the GA4 key path;
- `fmd-seo sync` reports GA4 success and failure through its existing health
  contract.

The full repository test suite must pass from the isolated worktree. The three
HTML-check tests require permission to open a temporary localhost socket.

## Live Verification

After automated tests pass:

1. Issue a read-only GA4 Data API report for property `541970582` and confirm a
   valid response without recording raw provider data.
2. Issue a read-only Search Console URL Inspection request for the configured
   `sc-domain:freshmobiledetail.com` property.
3. Run the GA4 sync path against a temporary observation directory so live
   verification does not add generated evidence to the feature commit.
4. Report GA4 and GSC outcomes separately. Credential validity does not imply
   property authorization, and one provider succeeding does not prove the other.

## Worktree and Handoff

All work occurs on branch `codex/ga4-readonly-monitoring` in
`/home/lucascoh/fmd-seo-engine/.worktrees/ga4-readonly-monitoring`. The user's
dirty `main` checkout remains unchanged. The implementation commit will be based
on `e7f7db3`; integrating it with the user's overlapping uncommitted changes is a
separate, explicit handoff step.
