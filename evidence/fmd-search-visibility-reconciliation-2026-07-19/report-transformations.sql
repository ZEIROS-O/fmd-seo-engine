-- Canonical report transformations, expressed in DuckDB SQL.
-- Paths are repository-relative; the Python report builder applies equivalent
-- typed transformations and embeds the reviewed result rows in artifact.json.

WITH semrush AS (
  SELECT * FROM read_csv_auto('evidence/semrush-position-tracking-2026-07-19/position-tracking-keywords.csv', header=true)
)
SELECT
  COUNT(*) FILTER (WHERE in_requested_467) AS requested_keywords,
  COUNT(*) FILTER (WHERE in_requested_467 AND fmd_position IS NOT NULL) AS requested_ranked,
  COUNT(*) FILTER (WHERE fmd_position BETWEEN 1 AND 3) AS fmd_top_3,
  COUNT(*) FILTER (WHERE fmd_position BETWEEN 1 AND 10) AS fmd_top_10,
  COUNT(*) FILTER (WHERE fmd_position BETWEEN 1 AND 20) AS fmd_top_20,
  COUNT(*) FILTER (WHERE fmd_position BETWEEN 1 AND 100) AS fmd_top_100
FROM semrush;

WITH geo AS (
  SELECT * FROM read_csv_auto('evidence/geo-top20-2026-07-19/geo-top20-keywords.csv', header=true)
)
SELECT
  COUNT(*) AS keywords_checked,
  COUNT(*) FILTER (WHERE fmd_organic_position BETWEEN 1 AND 20) AS fmd_organic_top_20,
  COUNT(*) FILTER (WHERE fmd_local_pack_position IS NOT NULL) AS fmd_local_pack,
  COUNT(*) FILTER (WHERE competitor_ranked_fmd_not) AS competitor_only_gaps,
  COUNT(*) FILTER (WHERE local_pack_near_win) AS local_pack_near_wins
FROM geo;

SELECT *
FROM read_json_auto('evidence/semrush-pdfs-2026-07-19/pdf-findings.json');

SELECT *
FROM read_json_auto('evidence/geo-map-pack-2026-07-19/summary.json');
