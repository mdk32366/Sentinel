# IMF IRFCL fixtures — provenance

Recorded 2026-11-10 ~6:55 AM PT (14:55 UTC) from the public, unauthenticated IMF SDMX 2.1 API.

- `irfcl_gold_2026-11-10_trimmed.xml` — real response from
  `GET https://api.imf.org/external/sdmx/2.1/data/IMF.STA,IRFCL/.IRFCLDT1_IRFCL56V_FTO..M?startPeriod=2015-01`
  (HTTP 200, application/xml, 999,339 bytes; full-body sha256 in `evidence/v21-all-full.sha256`).
  Trimmed to 14 series: USA, CHN, DEU, GBR, BEL, BRA, AGO, G163 (all sectors kept for BEL/DEU/GBR/G163),
  last 3 observations each; BRA keeps 2026-M01..M04 (spans the x1000 scale break). Header untouched.
- `irfcl_404_no_such_dataflow.json` — real body of the URL the job uses today
  (`.../2.1/data/IRFCL/.IRFCLDT1_IRFCL56V_FTO..M?startPeriod=2015-01`), HTTP 404.
- `irfcl_drift_renamed_indicator.xml` — SYNTHETIC: the trimmed fixture with the indicator renamed, simulating schema drift.
- `irfcl_header_only.xml` — SYNTHETIC: the real header with zero `<Series>`.
