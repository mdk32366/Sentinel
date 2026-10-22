# Foreign Bonds fixtures - provenance (Sentinel D-0111, vault:D-0057)

Every file here is a real response, fetched from the box on **2026-10-21**
(first fetch 22:14:55 UTC = 3:14:55 PM PT; the BoE archive at 22:15:23 UTC),
User-Agent `Sentinel/2.0 (sovereign stress monitor)`. Bytes are preserved;
"trimmed" means rows were dropped, never edited. No secrets: none of these
sources takes a key. Tests read only these files - no live network in CI.

| Fixture | Source URL (HTTP status, bytes) | sha256 of the original response | Trim |
|---|---|---|---|
| `bundesbank_R{02,05,07,10,30}XX.csv` | `https://api.statistiken.bundesbank.de/rest/data/BBSIS/D.I.ZST.ZI.EUR.S1311.B.A604.R{TT}XX.R.A.A._Z._Z.A?lastNObservations=10`, `Accept: text/csv` (200; 3968 / 3970 / 3970 / 3981 / 3078) | 02 `9cfcc468…`, 05 `8b3946d8…`, 07 `cb148fb6…`, 10 `ca16e16d…`, 30 `63a05095…` | none |
| `bundesbank_header_only.csv` | header line of the R10XX response above | - | first line only. Reproduces the shape of the header-only 200 Trinity saw on R07XX on 2026-10-21; that response itself was not captured |
| `boe_glc_nominal_current_month.xlsx` | `https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/latest-yield-curve-data.zip` (200, 362,099 B, no redirect), member `GLC Nominal daily data current month.xlsx` (zip stamp 2026-10-21 10:06) | zip `72dff96a…`; member `5ec59608…` | sheet `4. spot curve` only, values, rows to the last dated row (2026-10-20) |
| `boe_glc_nominal_archive_2025_trimmed.xlsx` | `https://www.bankofengland.co.uk/-/media/boe/files/statistics/yield-curves/glcnominalddata.zip` (200, 39,192,649 B, no redirect), member `GLC Nominal daily data_2025 to present.xlsx` | zip `bde17136…`; member `44a1facf…` | sheet 4, the 5 banner rows + first 3 and last 3 dated rows (2025-01-01..03, 2026-09-28..30) |
| `mof_jgbcm.csv` | `https://www.mof.go.jp/jgbs/reference/interest_rate/jgbcm.csv` (200, 1,556 B, no redirect) | `add13289…` | none (Shift-JIS bytes) |
| `mof_jgbcm_all_trimmed.csv` | `https://www.mof.go.jp/jgbs/reference/interest_rate/data/jgbcm_all.csv` (200, 1,178,227 B, 13,311 lines, no redirect) | `3ed93b15…` | first 3 + last 3 lines (title, header, S49.9.24 with `-` cells; R8.9.28, R8.9.29, R8.9.30) |

## Banque de France Webstat TEC (Sentinel D-0112) - SYNTHETIC-FROM-DOCS

These are **not** real responses. No Webstat API key was available to the
build (`WEBSTAT_API_KEY` is a secret Sentinel has not been given), so nothing
was fetched. The CSV shapes come from Banque de France's own API guide,
<https://webstat.banque-france.fr/pages/guide-migration-api/?flg=fr-fr>, read
2026-10-22. The values are invented and sit near plausible October 2026 French
TEC levels. Replace the CSVs with a captured response once a key exists. The two
error bodies are real (below); they need no key to capture.

| Fixture | Shaped from (guide section) | Synthetic content |
|---|---|---|
| `bdf_tec.csv` | "Observations d'une série": fields `series_key`, `time_period`, `time_period_start`, `obs_value`; "Exports EXCEL": `exports/json` -> `exports/csv`; the guide's CSV example is `;`-separated with a header line | 40 rows: series `FM.D.FR.EUR.FR2.BB.FRMOYTEC{2,5,7,10,30}.HSTA` x 8 business days 2026-10-12..2026-10-21, values invented |
| `bdf_tec_header_only.csv` | the header line of `bdf_tec.csv` | header only, no observation (a 200 that must fail closed) |
| `bdf_tec_404.json` | **Real response, not synthetic.** `GET https://webstat.banque-france.fr/api/explore/v2.1/catalog/datasets/observations/exports/csv?where=series_key%20in%20(%22FM.D.FR.EUR.FR2.BB.FRMOYTEC10.HSTA%22)&limit=1` with **no** key, from the box 2026-10-22 16:06:29 UTC (9:06:29 AM PT): HTTP 404, 105 B, sha256 `31a2ec0e474b8cbb…`. Matches the guide's "Authentification" note: an absent or unknown key answers `NotFoundResource` / "The requested dataset observations does not exist." | bytes preserved |
| `bdf_tec_401.json` | **Real response, not synthetic.** The same endpoint with header `Authorization: Apikey not-a-real-key`, same time: HTTP 401, 33 B, sha256 `0d81b5f645b6f216…`. The guide does not document this answer; it was measured (`F-0118`). No secret: the key sent was a made-up string | bytes preserved |

## Sentinel D-0115 (FB batch 2a) fixtures

All synthetic, hand-built from the shapes in each source's documentation and
a read-only shape probe on 2026-10-22. No value is a real observation.

| File | Shape of |
|---|---|
| boc_valet.json, boc_valet_empty.json | BoC Valet `group/bond_yields_benchmark/json` (observations[{d, SERIES:{v}}]); one blank 7Y cell |
| riksbank_SEGVB10YC.json, riksbank_empty.json | Riksbank SWEA `Observations/{series}/{from}/{to}` ([{date, value}]) |
| rba_f2.csv, rba_f2_header_only.csv | RBA F2 `f02d.csv`: metadata, `Series ID` row, CRLF, blank and comma-only tails |
| norges_govt.csv, norges_header_only.csv | Norges Bank SDMX `GOVT_GENERIC_RATES/B..GBON` CSV, `;`-separated |
| bde_ti_1_3.csv, bde_ti_1_3_shuffled.csv | BdE `ti_1_3.csv`, Latin-1, 6 metadata rows, `"_"` missing, FUENTE/NOTAS footer (a row after the footer must be ignored); the shuffled file reorders columns |
| ecb_yc.csv, ecb_yc_header_only.csv | ECB Data Portal `YC/B.U2.EUR.4F.G_N_A+G_N_C.SV_C_YM.SR_2Y+…` csvdata, trimmed columns |
| html_body.html | an HTML page returned where CSV was expected (spec@0.3 anomaly, T-0119) |
