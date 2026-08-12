# 2026-08-03 — a test suite overwrote a real measurement with fixture data

**Severity:** high (fabricated numbers reached the observation store)
**Detected:** minutes after it happened, by an aggregate that was arithmetically
impossible — `pairs_in_pack: 4` when only two of the observed ranks were <= 3.
**Committed:** no. Both artifacts were still untracked and were deleted.

## What happened

`local_finder.run()` was written with the evidence path hardcoded:

```python
out_dir = paths.EVIDENCE_DIR / f"local-finder-{stamp}"
```

Two new tests called `run()` with a fake client. They passed `observations_dir`
as a temp path — so the observation store was protected — but nothing redirected
the *evidence* write. Both tests therefore wrote to the real
`evidence/local-finder-2026-08-03/`, replacing 18 rows of measured Places-tab
data with 4 rows of `_FakeClient` output claiming rank 2 everywhere.

An observation was then recorded from that clobbered file, putting fabricated
records into `brain/observations/seo.local_visibility/`.

## Why it mattered

The engine's entire value rests on `brain/state.yaml`'s rule that nothing enters
without a source and a date, and on GATE-4 forbidding manufactured numbers. This
produced a file that looked like evidence, an observation that cited it, and a
rank claim for Solon that no measurement supported. Nothing about the artifacts
looked wrong from the outside — provenance pointed at a real path, the timestamp
was real, the shape validated against the check's declared records.

The measured aggregate was recoverable from the session log (18 pairs tested, 4
ranked, 2 in pack, best rank 2, 16 reviews). The per-row detail — competitor
lists and their review counts per cell — was not, and is simply gone.

## Root cause

A write to committed state with no injection point. The test could not isolate
what the module did not let it isolate.

The secondary cause is that the failure was silent: overwriting an existing
evidence file is indistinguishable from writing a new one, so nothing raised.

## Fixes applied

- `local_finder.run()` takes `evidence_dir`, defaulting to `paths.EVIDENCE_DIR`
  only in production. Both tests pass `tmp_path / "evidence"`.
- CONTRACT.md "State rules" now requires an injectable output directory for any
  function writing committed evidence or observations.

## Standing rule

Before a module writes anything under `evidence/`, `brain/observations/`,
`packages/`, or `state/`, check that the destination is a parameter. If a test
can reach the real path, it eventually will.

## Worth considering later

- Have `record_observation` refuse a source file whose mtime is newer than the
  measurement it claims to describe.
- Write evidence with `open("x")` like `observations.py` already does, so an
  accidental overwrite raises instead of succeeding quietly.
