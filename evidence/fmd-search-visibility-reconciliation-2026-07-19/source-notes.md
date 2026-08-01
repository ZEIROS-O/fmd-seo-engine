# Source notes

## Audience and structure

- Audience: product stakeholders / owner-operator.
- Delivery mode: portable HTML.
- Required structure mapping: title; Executive Summary; Semrush, live geo, map-grid, and AI findings; recommendations; further questions; caveats.

## Metric and grain definitions

- Semrush requested-ranked count: requested 467-keyword rows with FMD position 1-100 on July 19, 2026.
- DataForSEO organic top 20: target domain appears in an organic item with rank_group 1-20 at the operating coordinate on mobile.
- Local-pack win: FMD appears in the returned three-business local pack.
- Near-win: a local pack is present, FMD is absent from it, and FMD is organic top 10.
- Competitor-only gap: at least one of ATF, Refresh, Nathan's, or Diamond Finish appears organic top 20 or in the local pack while FMD appears in neither.

## Chart map

- Semrush coverage: category comparison / bar; top-100 counts by business; blue single-root palette; supports competitor-breadth finding.
- Live organic coverage: category comparison / bar; 467-keyword organic top-20 counts; blue single-root palette; supports coordinate-level competitive comparison.
- AI share of voice: category comparison / bar; Cleveland ChatGPT SOV; blue single-root palette; supports reach-gap finding.

## Omitted or qualified fields

- Semrush PDF does not contain landing pages or a machine-readable organic-versus-local ownership field.
- Diamond Finish has Semrush distribution counts but no keyword-level PDF column.
- The PDF text layer loses the color-coded sign of position changes. Absolute positions are preserved and validated; change magnitudes are retained with direction marked unavailable.
- The provisional July 20 Semrush API values are disclosed but do not replace the user-verifiable July 19 PDF.
- Heatmap grid ranks were visually reviewed rather than transcribed into a synthetic coordinate table.
- The Mayfield focus-query local pack changed between 21:03 and 22:04 UTC even though coordinate, device, and query were held constant; both observations are preserved.

## Reproducibility

- Semrush PDF rows: `scripts/extract_semrush_position_pdf.py`.
- Geo batch: `scripts/reconstruct_geo_serps.py`.
- Report artifact: `scripts/build_fmd_reconciliation_report.py`.
- DataForSEO paid POST cost: $0.5604; GET collection was free.
