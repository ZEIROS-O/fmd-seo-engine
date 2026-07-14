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
PYTHONPATH=src python3 -m pytest # test suite
```

No third-party dependencies beyond PyYAML (system Python 3.10 works as-is).

## Layout

| Path | Role |
|---|---|
| `src/fmd_seo/` | engine package |
| `config/engine.yaml` | paths, budget caps, limits |
| `evidence/` `packages/` `receipts/` `baselines/` | committed normalized outputs |
| `fixtures/` | failure-mode fixtures |
| `.run/` | **ignored** raw API payloads, locks, spend ledger |
| `.worktrees/fresh-site` | **ignored** isolated Fresh site worktree |
| `DISABLED` | kill switch — `touch DISABLED` halts every command |

## Authority boundaries (see CONTRACT.md)

Fresh-owned docs = fact/voice authority (read-only, hash-bound).
`operator-agent` = read-only verifier context, SHA-guarded.
ZEIROS = read-only strategic evidence. No publish command exists in V1;
`business-facts.yaml` sets posting to `human_only`.

## Credentials

DataForSEO creds go in `~/.dataforseo.env` (`DATAFORSEO_LOGIN=…`,
`DATAFORSEO_PASSWORD=…`). Never committed, never printed, loaded only by the
engine's client. Spend is reserved before every call against a $10 total cap
with per-endpoint sub-caps (`config/engine.yaml`).
