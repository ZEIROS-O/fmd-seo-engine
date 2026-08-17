# Retired observations

Observations for check ids the registry no longer declares. They are kept for
audit — a measurement that was true when taken stays true — but they are outside
`brain/observations/`, so no freshness surface, planner, or assessment reads
them.

Both entries here are **retired, not migrated**. Migrating would have meant
writing a value the instrument never produced (GATE-4).

| directory | renamed to | why not migrated |
|---|---|---|
| `seo.organic_footprint/` | `seo.query_footprint` | Different instrument, not a rename of the same measurement. The retired record is a Semrush *estimate* (`total_keywords`, `page1_keywords`, `nonbranded_keywords`); T7 retired that estimate in favour of first-party GSC rows. `seo.query_footprint` declares twelve GSC fields with no overlap. There is no value to carry across. |
| `aeo.share_of_voice/` | `aeo.recommendation_share` | Different instrument. The retired record is a share-of-voice percentage read off a Semrush PDF (`ai_sov_percent`, `competitor_top_sov`, `fmd_cited_count`); `aeo.recommendation_share` counts mentions and mean position across a frozen 25-query ChatGPT/Perplexity panel. Neither field set derives from the other. |

Leaving these in place inflated `freshness_report`'s `observations_found` — two
dead directories read as live coverage. `freshness_report` now reports any such
id under `unregistered_observations` rather than counting it, so the next rename
surfaces itself instead of quietly padding the number.
