# Position Tracking and geo-anchored map-pack reconciliation

## Completion status

Complete. The July 19 Semrush Position Tracking PDF yielded 479 unique campaign rows, including exact matches for all 467 requested keywords and 12 preserved campaign-only phrases. The separate DataForSEO run returned all 467 mobile SERPs at `41.4645,-81.5087,200` for a paid POST cost of `$0.5604`.

The primary deliverable is `evidence/fmd-search-visibility-reconciliation-2026-07-19/report.html`. Its source artifact, transformation notes, extracted CSVs, and raw evidence remain alongside it.

## Semrush campaign result

The completed July 19 PDF is a Google organic, United States, desktop campaign rather than a Mayfield Heights mobile panel. Across all 479 campaign rows, FMD has 0 top-three, 0 top-ten, 2 top-20, and 17 top-100 rankings; 462 are unranked. Within the requested 467-keyword corpus, 16 rank in the top 100.

The PDF does not expose FMD landing pages or a machine-readable organic-versus-local ownership field. Those fields therefore come from the separate live coordinate pull and are not presented as historical Semrush attributes.

## Coordinate-level result

The 467-keyword mobile pull found FMD organically in the top 20 for 41 keywords and in a returned local pack for one keyword. It identified three defined near-wins and 348 keywords where ATF, Refresh, Nathan's, or Diamond Finish appeared while FMD appeared in neither the organic top 20 nor the local pack.

The two focus queries also demonstrate pack volatility. At 21:03 UTC, FMD appeared third for `car detailing mayfield heights`; at 22:04 UTC, a same-coordinate mobile observation returned Refresh, Geauga, and Zoom Express, with FMD absent. FMD was absent for `car detailing beachwood` in both observations. Both snapshots and their GBP identities are preserved rather than selecting one as the sole truth.

## Reconciliation rule

Use Semrush Position Tracking for stable daily panel trend, Map Rank Tracker for multi-point grid coverage, and the DataForSEO pull for point-in-time mobile results at the operating coordinate. Compare them at their own grain; do not average their ranks into one score.
