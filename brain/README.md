# brain/ — the engine's decision layer

This directory is what makes the engine autonomous. Before it existed, the
engine could *fetch and verify* but had no standing answer to "what should I be
doing and checking right now?" — so Lou was the middle manager, deciding that
every time. The brain removes him from that seat.

## Files

| File | Role | Who edits |
|---|---|---|
| `thesis.md` | Standing beliefs (T1–T8) + the hard gates. The judgment layer. | Human, or agent with measured evidence |
| `checks.yaml` | The check registry: what to check, how, how often, and what each result means (thresholds → findings → actions). | Human / agent |
| `state.yaml` | Measured world-state + machine-owned gate state. Every value traces to an evidence file + date. | `observe` writes observations; gates hand-managed |
| `observations/` | Time-series of every recorded check result. Committed evidence. | `observe` only |

## How the loop thinks

```
beat     → what's due now, ordered, labeled by who can fulfill it
  ↓
(fetch)  → engine sync (Semrush API) | session (MCP/HTTP) | Lou (console)
  ↓
observe  → record the measurement; strict field validation
  ↓
assess   → thresholds → ranked findings; gate-drift detection; exit 4 on critical
  ↓
act      → work findings in the thesis priority order (schema first while GATE-1 closed)
```

## Two fulfillment paths for the same data

Semrush is reachable two ways, and the engine uses whichever is available:

- **MCP** (`mcp__semrush__*`) — works **only inside a Claude Code session**. This
  is the interactive path. A headless script can never call it.
- **REST API** (`SEMRUSH_API_KEY` in the creds env file) — callable by **headless
  Python**, so a **cron job** can run the Semrush-backed checks with no session
  and no Lou. This is what `sync` uses.

A check labeled `mcp` in `checks.yaml` becomes `engine_api`-fulfillable the
moment a key is present. No key → it stays on the session path. The engine never
fakes data to paper over a missing key (GATE-4).

## Human residue — what still needs Lou

The goal is zero, but three things are genuinely human-bound today:

1. **`seo.indexation`** — Google Search Console has no Semrush equivalent and no
   wired API here yet. It is also the **GATE-1 input**, so it's the highest-value
   thing to automate next. Wiring the GSC API (service-account OAuth) would drop
   the human residue to near-zero.
2. **`aeo.*`** — model judgment over live AI answers. A session does this well;
   a cron can't judge answer *correctness* without a model in the loop.
3. **Any publish / deploy / external send** — deliberately human, per CONTRACT.md.
   This is a safety boundary, not a missing feature.

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
