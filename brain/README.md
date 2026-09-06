# brain/ — the engine's decision layer

This directory is what makes the engine autonomous. Before it existed, the
engine could *fetch and verify* but had no standing answer to "what should I be
doing and checking right now?" — so Lou was the middle manager, deciding that
every time. The brain removes him from that seat.

## Files

| File | Role | Who edits |
|---|---|---|
| `thesis.md` | Standing beliefs (T1–T8) + the hard gates. The judgment layer. | Human, or agent with measured evidence |
| `checks.yaml` | Check ownership, instrument, cadence, records, thresholds, and actions. | Human / agent |
| `instruments.yaml` | Active/retired measurement authority and retirement rationale. | Human / agent |
| `priorities.yaml` | Human-authored strategic order and action path. | Human / agent |
| `warroom.yaml` | Evidence-derived query/page scores; blockers zero executable score. | `score --refresh` |
| `seasonal_calendar.yaml` | Evidence-linked existing-page/GBP seasonal queue. | engine |
| `gates.yaml` | Single rule registry for machine-managed gate thresholds and transition requirements. | Human / agent |
| `state.yaml` | Measured world-state + machine-owned gate state. Every value traces to an evidence file + date. | Indexation observations machine-manage GATE-1 |
| `observations/` | Time-series of every recorded check result. Committed evidence. | `observe` only |

## How the loop thinks

```
beat     → what's due now, ordered, labeled by who can fulfill it
  ↓
(fetch)  → scheduled provider | session/web judgment | Lou-owned console
  ↓
observe  → record the measurement; strict field validation
  ↓
assess   → thresholds → ranked findings; gate-drift detection; exit 4 on critical
  ↓
act      → work findings in the thesis priority order (schema first while GATE-1 closed)
```

## Two fulfillment paths for the same data

Semrush is reachable two ways for active Semrush instruments, and the engine
uses whichever is available:

- **MCP** (`mcp__semrush__*`) — works **only inside a Claude Code session**. This
  is the interactive path. A headless script can never call it.
- **REST API** (`SEMRUSH_API_KEY` in the creds env file) — callable by **headless
  Python**, so a **cron job** can run the Semrush-backed checks with no session
  and no Lou. This is what `sync` uses.

A check labeled `mcp` in `checks.yaml` becomes `engine_api`-fulfillable the
moment a key is present. No key → it stays on the session path. The engine never
fakes data to paper over a missing key (GATE-4).

`seo.organic_footprint` is retired: historical Semrush artifacts remain
auditable, but no active adapter or assessment routes to them. `gsc-sync` now
records `seo.query_footprint` from two finalized Search Analytics datasets — a
query-only pull for query totals, CTR and position, and a query/page pull for
page coverage — persisted as one artifact.

## Human residue — what still needs Lou

The intentional human/console residue is:

1. **GA4/GBP administration** — access grants, key-event designation, selected
   GBP resource, and controlled booking/DebugView proof.
2. **AEO recurring spend approval and faithfulness review** after the canary.
3. **Any merge / deploy / external send** — deliberately human, per CONTRACT.md.

**`seo.indexation` is now headless** (`fmd-seo gsc-sync`) via the GSC URL Inspection
API — the former "one true human dependency" and GATE-1 input. Index coverage has
no bulk API, so the engine inspects each sitemap URL and tallies the coverageState
(~20 URLs/day, far inside quota). Setup (one-time, Lou-side):

1. Google Cloud project → enable the **Search Console API**.
2. Create a **service account**, download its JSON key to `gsc.key_path`.
3. In Search Console → the property → Settings → Users → add the service account's
   email as a **Full** user.
4. `pip install -e .[gsc]` (google-auth + google-api-python-client).

Without the key it degrades to the manual console reading — never a guess (GATE-4).

## Headless and session fulfillment paths

- **Semrush REST** (`SEMRUSH_API_KEY`) → `sync`, headless.
- **GSC URL Inspection** (service-account key) → `gsc-sync`, headless.
- **GA4 Data API** (same service-account key + GA4 property access) → `sync`,
  weekly headless `analytics.traffic` observations.
- **GBP Performance** → **blocked, session-fulfilled.** The Business Profile
  APIs are disabled in the Cloud project and the location id the Performance API
  needs is only obtainable from one of them, so `gbp.performance` is
  `execution_mode: session` with no producer. Measurements and unblock path:
  `brain/blockers/gbp-performance.md`.
- **DataForSEO standard queue** → `serp-bulk` positions and `geogrid` map-pack panels.
- **Semrush MCP** / **live HTTP** / **model judgment** → session, via the
  `fmd-seo-loop` skill.

Paid SERP commands require an explicit mode. `--dry-run` computes the full
bounded cost and posts nothing; `--post` creates/resumes the durable task
manifest; `--collect` retrieves ready tasks and records normalized observations.
The position and geogrid caps are independent in `config/engine.yaml`.

Checks declare `execution_mode: scheduled|session|console`, `thesis_refs`, and
`instrument_ref`. Missing credentials do not fabricate a pass: scheduled checks
stay due, console checks name Lou and a next action, and paid work remains blocked
until a displayed cap and spend reservation pass.

## Gates (enforced, not advisory)

- **GATE-1 publish gate** — CLOSED while indexation fails. No new pages/posts.
  This is the single most important line in the system.
- **GATE-2 suburb-page gate** — CLOSED; zero-volume suburbs.
- **GATE-3 fact gate** — every claim binds to `business-facts.yaml`.
- **GATE-4 no-invention gate** — no manufactured volumes/rankings/reviews/facts.

## Invariants

- A check whose threshold references a field it doesn't record is rejected at
  load time (`fmd-seo beat` will error). Thresholds can't silently never-fire.
- A never-observed check is always "due" — the engine never assumes an
  unmeasured check is passing.
- Threshold expressions run through a restricted AST evaluator: comparisons and
  boolean ops over observation fields only. No `eval`, no calls, no attributes.
