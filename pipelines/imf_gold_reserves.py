"""
IMF Gold Reserves Pipeline
---------------------------
Monthly official gold holdings per country, from the IMF's **IRFCL** dataset
(International Reserves and Foreign Currency Liquidity), indicator
`IRFCLDT1_IRFCL56V_FTO` - Reserves Data Template line 56, "gold (including
gold deposits and, if appropriate, gold swapped)", volume in fine troy ounces.

`D-0076`. This is the ticker behind the download. `pipelines/gold_reserves.py`
reads a World Gold Council CSV that a person downloads by hand, and the files
in `data/incoming/` are named `World_official_gold_holdings_..._IFS.xlsx` -
WGC's own source is IMF International Financial Statistics. We were reading a
quarterly re-publication of a monthly feed, three months behind it, by hand.

**Validated before it was wired in.** 68 countries appear in both this feed and
the WGC data already in the database; 55 agree within 10% and every large
holder agrees to the decimal - USA 8133.5/8133.5, Germany 3350.2/3349.1, Italy
2451.8/2451.8, France 2437.0/2437.0. Most of the disagreements are real
accumulation that the 272-day-old WGC file had missed: Turkey 534.9 -> 791.4
tonnes, Poland 581.6 -> 648.0, Czechia 76.6 -> 85.8.

**The feed has scale defects and they are not uniform.** Brazil's series
carries `5544278.72` for 2026-M01 and `5544278722.99` from 2026-M03 - the same
holding, the same constant, rescaled by exactly 1000 mid-series. Read naively
that is 172,446 tonnes, which is roughly five times all the gold every central
bank on earth holds. Angola reads 18,441. So every value is checked against a
ceiling rather than trusted, and a rejected value leaves the previous one
standing (`F-0093`).
"""

import logging
import re
from datetime import datetime
from decimal import Decimal

import requests
from sqlalchemy.orm import Session

from database.models import Metric, TimeSeries, Country, UpdateLog

logger = logging.getLogger(__name__)

PIPELINE_NAME = "Gold_Reserves_IMF"

# SDMX 2.1. Key order is COUNTRY.INDICATOR.SECTOR.FREQUENCY; country and sector
# are left blank to mean "all". The legacy `dataservices.imf.org` SDMX endpoint
# no longer resolves at all - this is the current host.
IMF_SDMX_BASE = "https://api.imf.org/external/sdmx/2.1/data"
IMF_GOLD_INDICATOR = "IRFCLDT1_IRFCL56V_FTO"
IMF_GOLD_URL = f"{IMF_SDMX_BASE}/IRFCL/.{IMF_GOLD_INDICATOR}..M"

# 1 tonne = 1,000,000 g / 31.1034768 g per fine troy ounce.
OZ_PER_TONNE = 32150.7466

# The United States holds 8,133.5 tonnes and is the largest holder there has
# ever been; every central bank on earth together holds roughly 36,000. A
# country reading above this is a units error, not a discovery - see the Brazil
# case in the module docstring.
MAX_PLAUSIBLE_TONNES = 9000.0

# IRFCL reports aggregates in the same COUNTRY dimension as countries. G163 is
# a country group, EZB the ECB itself, WBG the World Bank Group. Excluded by
# name rather than left to fail Country lookup, so that a genuine country whose
# ISO code we have not mapped yet still shows up as a skipped row worth
# investigating.
NOT_COUNTRIES = {"G163", "EZB", "WBG"}

GOLD_METRIC_CODE = "GOLD_RESERVES"

_SERIES_SPLIT = re.compile(r"<Series ")
_COUNTRY_RE = re.compile(r'COUNTRY="([^"]+)"')
_OBS_RE = re.compile(r'<Obs TIME_PERIOD="([^"]+)" OBS_VALUE="([^"]+)"')
# "2026-M08" -> year 2026, month 8
_PERIOD_RE = re.compile(r"^(\d{4})-M(\d{2})$")


def fetch_imf_gold(start_period: str = "2015-01", timeout: int = 90) -> str:
    """The raw SDMX response. Text, so the parser can be tested without a URL."""
    r = requests.get(
        IMF_GOLD_URL, params={"startPeriod": start_period}, timeout=timeout
    )
    r.raise_for_status()
    if "<Series " not in r.text:
        # A 200 carrying only the dataset header. Treated as a failure rather
        # than as "no gold in the world this month": D-0045, a pipeline that
        # cannot tell no-data from no-news reports completion, not success.
        raise ValueError(
            f"IMF returned no series for {IMF_GOLD_INDICATOR}. "
            f"{len(r.text)} bytes, no <Series> element - the indicator or the "
            f"key order has changed."
        )
    return r.text


def parse_imf_gold(xml: str) -> tuple[list[dict], list[str]]:
    """`(observations, rejected)`.

    Each observation is `{iso, date, tonnes, ounces}` with `date` on the FIRST
    of the data month, matching the convention the WGC importer uses for
    quarters (`A-0016` covers why that convention is what it is).
    """
    out, rejected = [], []

    for block in _SERIES_SPLIT.split(xml)[1:]:
        head = block.split(">", 1)[0]
        m = _COUNTRY_RE.search(head)
        if not m:
            continue
        iso = m.group(1)
        if iso in NOT_COUNTRIES:
            continue

        for period, raw in _OBS_RE.findall(block):
            pm = _PERIOD_RE.match(period)
            if not pm:
                continue
            try:
                ounces = float(raw)
            except ValueError:
                continue

            tonnes = ounces / OZ_PER_TONNE
            if not (0.0 <= tonnes <= MAX_PLAUSIBLE_TONNES):
                rejected.append(f"{iso}/{period}={tonnes:,.1f}t")
                continue

            out.append({
                "iso": iso,
                "date": datetime(int(pm.group(1)), int(pm.group(2)), 1),
                "tonnes": round(tonnes, 2),
                "ounces": ounces,
            })

    return out, rejected


def run_imf_gold_fetch(db: Session, start_period: str = "2015-01") -> dict:
    """Import monthly gold holdings from IMF IRFCL into `GOLD_RESERVES`."""
    started = datetime.utcnow()
    inserted = updated = skipped = 0

    try:
        xml = fetch_imf_gold(start_period)
        observations, rejected = parse_imf_gold(xml)

        if not observations:
            raise ValueError("IMF response parsed to zero usable observations")

        metric = db.query(Metric).filter_by(code=GOLD_METRIC_CODE).first()
        if not metric:
            raise ValueError(
                f"Metric {GOLD_METRIC_CODE} does not exist. The WGC importer "
                f"creates it; this pipeline adds to the same series rather "
                f"than starting a parallel one."
            )

        countries = {}
        seen = set()
        newest = None

        for obs in observations:
            iso = obs["iso"]
            if iso not in countries:
                countries[iso] = db.query(Country).filter_by(iso_code=iso).first()
            country = countries[iso]
            if not country:
                skipped += 1
                continue

            seen.add(iso)
            if newest is None or obs["date"] > newest:
                newest = obs["date"]

            existing = db.query(TimeSeries).filter(
                TimeSeries.metric_id == metric.id,
                TimeSeries.country_id == country.id,
                TimeSeries.date == obs["date"],
            ).first()

            value = Decimal(str(obs["tonnes"]))
            if existing:
                existing.value = value
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                db.add(TimeSeries(
                    metric_id=metric.id,
                    country_id=country.id,
                    date=obs["date"],
                    value=value,
                ))
                inserted += 1

        db.commit()

        status = "partial" if rejected else "success"
        note = f"{len(rejected)} implausible: {', '.join(rejected[:6])}" if rejected else None
        logger.info(
            "IMF gold: %s - %d inserted, %d updated, %d skipped, %d countries, "
            "newest %s, %d rejected",
            status, inserted, updated, skipped, len(seen),
            newest.date() if newest else None, len(rejected),
        )

        db.add(UpdateLog(
            pipeline_name=PIPELINE_NAME,
            status=status,
            records_inserted=inserted,
            records_updated=updated,
            error_message=(note or "")[:480] or None,
            started_at=started,
            completed_at=datetime.utcnow(),
        ))
        db.commit()

        return {
            "status": status,
            "inserted": inserted,
            "updated": updated,
            "skipped": skipped,
            "countries": len(seen),
            "newest_date": newest.date().isoformat() if newest else None,
            "rejected": rejected,
        }

    except Exception as exc:
        db.rollback()
        logger.error("IMF gold fetch failed: %s", exc)
        db.add(UpdateLog(
            pipeline_name=PIPELINE_NAME,
            status="failed",
            records_inserted=0,
            records_updated=0,
            error_message=str(exc)[:480],
            started_at=started,
            completed_at=datetime.utcnow(),
        ))
        db.commit()
        raise
