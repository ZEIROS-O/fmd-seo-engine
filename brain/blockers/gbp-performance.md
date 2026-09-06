# Blocker — `gbp.performance` cannot be produced headlessly

**Measured 2026-08-17. Not inferred.**

`gbp.performance` was `execution_mode: scheduled` with an empty
`config/engine.yaml -> gbp.location_id`, so `gbp.sync_if_due` returned
`skipped_config` forever. Phase 1 turned that into a standing critical failure,
which is the correct signal. This records why the obvious fix — "put the id in
the config" — does not work, so nobody spends the afternoon again.

## What was tested

The service account at `config/engine.yaml -> gbp.key_path`
(`fmd-seo-engine@local-lead-machine-498016.iam.gserviceaccount.com`, Cloud
project `local-lead-machine-498016`, project number `759072837709`) minted a
token for `https://www.googleapis.com/auth/business.manage` successfully. Every
API it needs then refused:

| endpoint | result |
|---|---|
| `mybusinessaccountmanagement.googleapis.com/v1/accounts` | `403 PERMISSION_DENIED`, `reason: SERVICE_DISABLED` |
| `mybusinessbusinessinformation.googleapis.com/v1/accounts/-/locations` | `403 PERMISSION_DENIED`, `reason: SERVICE_DISABLED` |
| `businessprofileperformance.googleapis.com/v1/locations/…` | `403 PERMISSION_DENIED`, `reason: SERVICE_DISABLED` |

The service account also cannot enable them itself — `serviceusage.services.get`
on the same project returns `403 PERMISSION_DENIED`.

## Why the config-only fix fails

The Performance API addresses a location as `locations/{location_id}` using the
**unobfuscated** id. That id is only served by `accounts.locations.list` on the
Business Information API — one of the three disabled endpoints. The id visible
in the `business.google.com/dashboard/l/…` URL is the *obfuscated* listing id
and the Performance API does not accept it. So the id cannot be obtained without
first obtaining API access; there is no dashboard shortcut.

A profile definitely exists — `brain/observations/seo.map_pack/`
`20260719T210317+0000.json` records `median_rank: 3.0` with
`competitors_above: 2`, and nothing ranks in the map pack without one. The
blocker is access, not existence.

## Disposition

Reclassified `scheduled -> session` (Lou's call, 2026-08-17). The check stays
live at its weekly cadence with its thresholds intact; the producer is Lou
reading the dashboard and running `fmd-seo observe`. It has no entry in
`brain/producers.yaml`, which is what `load_brain` now enforces: a scheduled
check must name something that can actually write it.

`gbp.sync_if_due` and `fetch_performance` are untouched and still correct. No
number was invented to make the check green (GATE-4).

## Unblock path, in order

1. Enable the three APIs on project `local-lead-machine-498016`. The Business
   Profile family is gated: Google's Business Profile APIs access-request form
   must approve the project first. Turnaround is Google's, not ours.
2. Grant the service account access to the profile. Business Profile manages
   permissions per Google identity — invite
   `fmd-seo-engine@local-lead-machine-498016.iam.gserviceaccount.com` as a
   manager, then accept the invitation via
   `mybusinessaccountmanagement accounts.invitations.accept` (a service account
   cannot accept through the UI). If Google rejects a service account as a
   profile manager, the fallback is an installed-app OAuth client consented by
   Lou's own Google identity, with a stored refresh token — a different
   credential model from the one `gbp.py` uses today.
3. `accounts.locations.list` → take the `name` field (`locations/<digits>`).
4. Fill `config/engine.yaml -> gbp.location_id`, run one real
   `fmd-seo sync --source gbp`, and confirm an observation with real numbers.
5. Flip `gbp.performance` back to `execution_mode: scheduled` and add its
   `brain/producers.yaml` entry
   (`command: fmd-seo sync --source gbp`, `entrypoint: fmd_seo.gbp:sync_if_due`)
   in the same commit. `load_brain` will not accept one without the other.
