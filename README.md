# fmd-seo-engine

Standalone SEO intelligence and content-package engine for Fresh Mobile
Detailing. Owns query evidence, source packs, PagePackages, verification
receipts, export manifests, and run state. Website JSON/HTML is *generated
output* — the site repo is never a competing content authority.

## Boot

```bash
cd ~/fmd-seo-engine
bin/fmd-seo preflight            # offline checks
bin/fmd-seo preflight --online   # adds the capped DataForSEO account probe
PYTHONPATH=src python3 -m pytest  # test suite
```

The core engine only requires PyYAML. Google provider support is opt-in with
`pip install -e .[google]`.

## Layout

| Path | Role |
|---|---|
| `src/fmd_seo/` | engine package |
| `config/engine.yaml` | paths, budget caps, limits |
| `evidence/` `packages/` `receipts/` `baselines/` | committed normalized outputs |
| `state/` | committed spend, provider-health, and resumable task state |
| `fixtures/` | failure-mode fixtures |
| `.run/` | **ignored** raw API payloads, locks, and per-run scratch files |
| `.worktrees/fresh-site` | **ignored** isolated Fresh site worktree |
| `DISABLED` | committed kill switch for local and cloud provider work |

## Command reference

### Loop and measurement

| Command | Purpose |
|---|---|
| `fmd-seo beat` | List due checks in priority order and show their fulfillment path. |
| `fmd-seo assess` | Evaluate observations and gate state. Exit 4 means a critical finding or gate drift. |
| `fmd-seo brief` | Combine gates, due checks, findings, and the next priority. |
| `fmd-seo tick` | Record credential-free facts and observation-freshness watchdogs. |
| `fmd-seo sync` | Fetch due headless provider checks with honest partial/block outcomes. |
| `fmd-seo gsc-sync` | Fetch URL Inspection coverage and machine-update GATE-1. |
| `fmd-seo observe CHECK --records JSON --fulfillment KIND --source SOURCE` | Record one validated manual or engine observation. |

### Data spine

| Command | Purpose |
|---|---|
| `fmd-seo serp-bulk --dry-run\|--post\|--collect` | Estimate, post, or collect the capped coordinate-anchored ranking queue. |
| `fmd-seo geogrid --dry-run\|--post\|--collect` | Estimate, post, or collect the capped 5x5 map-grid queue. |

Spend, provider failure counters, and post/collect manifests live under committed
`state/`. Raw provider payloads remain in ignored `.run/raw/`.

### Site action and reconciliation

| Command | Purpose |
|---|---|
| `fmd-seo act --dry-run [--package packages/pp-*.json]` | Inspect the site action queue and optional package diff without writing. |
| `fmd-seo act --package packages/pp-*.json` | Verify, export, build, check raw HTML, push a branch, and open a draft PR when GATE-1 is open. |
| `fmd-seo reverify` | Reconcile active export manifests against `origin/main` and live HTML; archived manifests are skipped. |
| `fmd-seo site-reset` | Report the isolated worktree branch, dirtiness, and divergence. |
| `fmd-seo site-reset --force` | Preserve the divergent branch ref while detaching the worktree at `origin/main`. |
| `fmd-seo facts-check` | Compare canonical facts with generated `business-facts.ts` by public payload hash. |
| `fmd-seo report --since YYYY-MM-DD` | Align measured outcome deltas with the intervention ledger. |
| `fmd-seo gbp-draft` | Generate fact-bound GBP and review-request drafts without publishing or customer contact. |

To engage the cloud kill switch, create `DISABLED`, commit it, and push that
commit. Removing it in a later commit re-enables scheduled provider work.

## Authority boundaries (see CONTRACT.md)

Fresh-owned docs = fact/voice authority (read-only, hash-bound).
`operator-agent` = read-only verifier context, SHA-guarded.
ZEIROS = read-only strategic evidence. No publish command exists in V1;
`business-facts.yaml` sets posting to `human_only`.

## Credentials

DataForSEO creds go in `~/.dataforseo.env` (`DATAFORSEO_LOGIN=…`,
`DATAFORSEO_PASSWORD=…`). Never committed, never printed, loaded only by the
engine's client. Spend is reserved before every call against the committed $50
monotonic ledger with per-endpoint sub-caps (`config/engine.yaml`).

### Google Search Console and GA4

The two integrations share one service account and JSON key, but Google grants
access separately in each product. One-time setup:

1. In the selected Google Cloud project, enable **Google Search Console API**
   and **Google Analytics Data API**. A service-account flow does not need an
   OAuth consent-screen scope entry.
2. Create a service account and place its JSON key outside the repository with
   owner-only permissions. This repo expects
   `/home/lucascoh/.gsc-service-account.json`; never commit or print the key.
3. In Search Console, open `sc-domain:freshmobiledetail.com` → Settings → Users
   and permissions, then add the service-account email as a **Full** user.
4. In GA4 property `541970582`, open Admin → Property access management and add
   the same email. **Viewer** is sufficient for this read-only implementation;
   Editor also works.
5. Confirm `gsc` and `ga4` in `config/engine.yaml`, install
   `pip install -e .[google]`, then run `bin/fmd-seo sync` for weekly GA4
   acquisition/conversion monitoring and `bin/fmd-seo gsc-sync` for URL
   Inspection coverage.

Runtime credentials are explicitly restricted to
`analytics.readonly` for GA4 and `webmasters.readonly` for Search Console. The
GA4 sync records only aggregate sessions, engaged sessions, organic sessions,
allowlisted AI-referral sessions, and key events; it does not retain raw API
responses or perform Analytics Admin mutations.
