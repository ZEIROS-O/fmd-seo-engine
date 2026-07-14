---
name: fmd-seo-loop
description: >-
  Drive the FMD SEO/AEO engine's autonomous loop from a Claude Code session. Use
  when Lou says "run the SEO loop", "check FMD SEO", "what should the SEO engine
  do", opens the fmd-seo-engine repo to work on SEO/AEO/competitor/blog/schema,
  or wants the engine to tell him what's due instead of deciding himself. The
  engine is the brain (it decides what/why); this skill is the hands (it fetches
  via Semrush MCP + live HTTP and records results back).
---

# FMD SEO Loop — let the engine drive

The engine at `~/fmd-seo-engine` holds the judgment: the standing thesis, the
gates, the check registry with thresholds, and the measured state. You do not
re-decide any of that. You **consult it, do the fetching it can't do from a
session, and record what you found.** Then you act on its findings in its
priority order.

## The one thing that must not happen

**Never author a new blog post or money page while GATE-1 is CLOSED.** The engine
will tell you it's closed and why (14 pages Google won't index). Writing more
pages is the exact failure this whole system exists to prevent. If you feel the
urge to "just write one useful article," that urge is the bug. Route to schema /
entity / linking / copy instead.

## Loop

Run from `~/fmd-seo-engine`. All commands: `PYTHONPATH=src python3 -m fmd_seo <cmd>`.

### 1. Ask the engine what's due

```
PYTHONPATH=src python3 -m fmd_seo beat
```

Returns the gate states, the gate-respecting priority order, and every due
check with a `fulfillment` label:

- `engine_api` — the cron path already fetches this via the Semrush REST API.
  In a session you can skip it (a scheduled `sync` will get it) or force-refresh
  via MCP. Don't double-spend units.
- `session` — **your job.** Fetch it now (Semrush MCP or live HTTP or web-search
  judgment per the check's `run` field), then `observe` it.
- `human` — only Lou can open this console (GSC/GA4/GBP). Ask him for the numbers;
  do not guess them (GATE-4). Currently this is just `seo.indexation` — and it's
  the GATE-1 input, so it matters most.

### 2. Fulfill each `session` check

Read the check's `run` field — it is the exact instruction. Map it:

| Check | How you fulfill it |
|---|---|
| `schema.presence`, `schema.validate`, `seo.internal_links` | live `curl` with JS disabled against the sitemap URLs |
| `seo.organic_footprint`, `seo.positions`, `seo.site_health` | `mcp__semrush__organic_research` / `position_tracking` / `site_audit` |
| `competitor.authority_gap`, `competitor.serp_movement` | `mcp__semrush__backlinks_research` / `organic_research` / `competitors_research` |
| `market.demand`, `topics.related_clusters` | `mcp__semrush__keyword_research` |
| `aeo.answer_accuracy`, `aeo.entity_consistency` | live web search + read against `business-facts.yaml` |

Semrush MCP workflow: discovery tool → `get_report_schema` → `execute_report`.
Default database `us`. If a value can't be measured (e.g. position tracking
blocked over API), record the honest blocked=true — never substitute an estimate.

### 3. Record what you measured

```
PYTHONPATH=src python3 -m fmd_seo observe <check_id> \
  --records '{"field":value,...}' \
  --fulfillment mcp|agent|console \
  --source "<where it came from>" --note "<retrieval time / detail>"
```

`--records` must contain exactly the check's declared fields — the engine
rejects missing/extra/wrong-typed fields. `observe` prints the findings your
observation just triggered, so you see the consequence immediately.

### 4. Assess and act

```
PYTHONPATH=src python3 -m fmd_seo assess    # exit 4 if any critical finding or gate drift
```

Work the findings **top-down in the printed priority order**. Every finding
carries an `action` — that is what to do. While GATE-1 is CLOSED the order is
fixed: schema → entity decontamination → copy language → internal linking →
review velocity → only then reassess the gate.

For site changes: write to the isolated worktree (`.worktrees/fresh-site`),
never the live checkout (CONTRACT.md authority boundary #2). No publish, no
deploy, no external send without Lou's explicit go (GATE-3/4 + CONTRACT #6/#7).

### 5. Close

`brief` gives the one-call summary to hand back to Lou: gates, standing critical/
high findings, what's still due and who must do it.

```
PYTHONPATH=src python3 -m fmd_seo brief
```

## Adding the Semrush REST key (turns the cron path on)

Put `SEMRUSH_API_KEY=<key>` in the creds env file (`config/engine.yaml → creds_env`,
default `~/.dataforseo.env`). Then `sync` fetches the API-backed checks headlessly
and every `engine_api` check runs with no session and no Lou. Verify with:

```
PYTHONPATH=src python3 -m fmd_seo sync    # fetched: [...] instead of skipped_no_key
```

The cron wrapper is `bin/fmd-seo-cron` — schedule it daily; it runs `sync` then
`assess` and writes a receipt. It never publishes.

## What stays Lou's, always

- Opening GSC/GA4/GBP (until their APIs are wired) — the `human` checks.
- Any live publish / deploy / external send.
- Promoting a gate open, or overriding the thesis — those are judgment calls the
  engine surfaces but does not make.
