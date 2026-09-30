# IMF IRFCL — gold volume scale anomalies (Angola, Brazil)

`A-0018`. Drafted for sending to **datahelp@imf.org**, the contact given in the
IRFCL dataset metadata. **Not sent** — an outbound message on the maintainer's
behalf is theirs to send, not mine.

Copy the section below as the body.

---

**Subject:** IRFCL — `IRFCLDT1_IRFCL56V_FTO` scale anomalies for Angola and Brazil

Dataflow: `IMF.STA:IRFCL(12.0.0)`
Indicator: `IRFCLDT1_IRFCL56V_FTO` (Reserves Data Template line 56, gold,
volume in fine troy ounces)
Sector: `S1XS1311`
Retrieved: 2026-09-30 via
`https://api.imf.org/external/sdmx/2.1/data/IRFCL/.IRFCLDT1_IRFCL56V_FTO..M?startPeriod=2015-01`

Two economies return values for this series that appear to be misscaled by a
factor of 1,000. Converting at 32,150.7466 fine troy ounces per tonne:

**Brazil — the scale changes mid-series, and the underlying holding does not.**

| period | `OBS_VALUE` | implied tonnes |
|---|---|---|
| 2026-M01 | 5544278.72299948 | 172.4 |
| 2026-M02 | 5544278.72299967 | 172.4 |
| 2026-M03 | 5544278722.9986 | **172,446.3** |
| 2026-M04 | 5544278722.99981 | 172,446.3 |
| … | … | … |
| 2026-M08 | 5544278722.99971 | 172,446.3 |

The same constant holding is reported at two scales within one series, changing
at 2026-M03. Every series-level attribute is identical across the break —
`SCALE="6"`, `SECTOR="S1XS1311"`, `METHODOLOGY="IRFCL13"` — and each observation
carries `DERIVATION_TYPE="O"`, so nothing in the metadata distinguishes the two
segments. The pre-2026-M03 value of 172.4 tonnes is consistent with other
published figures for Brazil; 172,446 tonnes would be roughly five times total
world official gold holdings.

**Angola — the whole recent series is affected.**

70 consecutive monthly observations from 2020-M10 onward, for example
2026-M07 = `592900000`, implying 18,441.3 tonnes. Angola's official gold
holdings are reported elsewhere as well under one tonne.

**Why it matters to a consumer.** Read at face value these make Angola the
world's second-largest holder of monetary gold and Brazil the largest by a
factor of twenty. For comparison, the same series reproduces the published
figures exactly for the large holders — USA 8,133.5 t, Germany 3,349.1 t, Italy
2,451.8 t, France 2,437.0 t, United Kingdom 310.3 t — so the anomaly looks
confined to these two reporters rather than to the series definition or the unit.

No action needed on our side; we reject implausible values rather than importing
them. Flagging it in case the submissions can be corrected at source.

---

## What we do about it meanwhile

`F-0093`. `pipelines/imf_gold_reserves.py` refuses any value implying more than
`MAX_PLAUSIBLE_TONNES = 9000` — between the largest real holder (the USA at
8,133.5 t, the largest there has ever been) and total world official holdings of
roughly 36,000 t. A rejected value is named with its country and period, and
leaves the previous reading standing. It is not rescaled: inferring the intended
scale is guessing.

Current effect, from the production run of 2026-09-30:

- **76 of 13,127 values rejected (0.6%)**, in exactly two countries: Angola 70,
  Brazil 6.
- **Brazil is fine.** Its pre-2026-M03 observations are correctly scaled, so it
  carries 172.4 tonnes from the good part of its own series.
- **Angola has no gold data at all.** All of its recent observations are
  rejected and it is absent from the World Gold Council set, so it now has *no*
  data rather than wrong data. Dimension 2 cannot score Angola. Angola is not
  in the composite's scored set, so the cost today is nil.

## How this stays visible without anyone re-deriving it

The rejection count and the first few rejected values are written to
`UpdateLog.error_message` on every run of `Gold_Reserves_IMF`, and the run
reports `partial` rather than `success` while any value is rejected. Both appear
in the PIPELINE LOG on the ADMIN tab.

**What to check when this is next looked at:** whether the rejection list has
grown, and in particular whether any country in the composite's *scored* set
has joined it. Angola is not scored; the same defect arriving in Turkey or
Poland would remove a country the model relies on.
