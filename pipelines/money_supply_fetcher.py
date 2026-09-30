"""
Broad Money Growth Pipeline
----------------------------
Annual broad money growth (% YoY) per country, from the World Bank's
`FM.LBL.BMNY.ZG` indicator (sourced by the World Bank from IMF IFS).

`F-0091`: this used to read a local JSON file and raise `FileNotFoundError`
with a `curl` command in the message if it was missing. Three things were
wrong with that, and only the first was obvious:

  1. Nothing fetched. The data arrived when a person remembered to run the
     curl, and the file's `lastupdated` was whatever that day's release said.
  2. **Nothing scheduled it.** There was no `add_job` for this pipeline at
     all, so even with a fetcher it would never have run. It fed composite
     dimension 3 - 35 of 165 points - and ran only when called by hand.
  3. The watchdog's tolerance for it was unreachable, for the same reason
     TIC's was (`F-0089`). See `MAX_*` notes in `freshness_watchdog.py`.

Signal thresholds (composite dimension 3):
  >15%  Elevated - watch
  >30%  Significant debasement - pressure on currency and reserves
  >50%  Crisis-level - reserve drawdown typically follows
  >100% Hyperinflationary episode
"""

import json
import logging
from datetime import datetime
from decimal import Decimal

import requests
from sqlalchemy.orm import Session

from database.models import Metric, TimeSeries, Country, UpdateLog
from pipelines.paths import DATA_DIR

logger = logging.getLogger(__name__)

# Kept as the offline fallback and as the seed for a fresh database. It is not
# the primary path any more; `fetch_money_supply()` goes to the API.
JSON_PATH = DATA_DIR / "money_supply.json"

# The countries the composite scores. Held as a list rather than inlined in a
# URL string so it is greppable and so the URL cannot drift from it.
WB_COUNTRIES = [
    "JP", "CN", "GB", "BE", "CA", "LU", "FR", "IE", "TW", "CH", "SG", "HK",
    "NO", "IN", "BR", "SA", "KR", "DE", "NL", "AE", "TH", "IL", "TR", "MX",
    "SE", "AU", "PL", "PH", "ID", "ZA", "EG", "AR", "CL", "CO", "PE", "CZ",
    "HU", "RO", "KW", "QA", "RU", "MY", "VN", "BD", "KZ", "UA", "KY",
]

WB_INDICATOR = "FM.LBL.BMNY.ZG"
WB_URL = (
    f"https://api.worldbank.org/v2/country/{';'.join(WB_COUNTRIES)}"
    f"/indicator/{WB_INDICATOR}"
)
WB_PARAMS = {"format": "json", "mrv": 30, "per_page": 2000}

MONEY_METRIC = {
    "code": "BROAD_MONEY_GROWTH",
    "name": "Broad Money Growth (Annual %)",
    "category": "monetary",
    "unit": "%",
    "source": "WorldBank_IMF",
    "description": "Annual % growth in broad money supply. Source: World Bank / IMF IFS."
}

# A growth rate outside this range is not a growth rate. Zimbabwe 2008 was on
# the order of 10^7 %, so the ceiling is generous - it exists to catch a units
# change or an index level arriving where a percentage belongs, which is the
# F-0075 shape (Russia's 13,775bps "CDS spread" was an ISDA coupon).
PLAUSIBLE_PCT_RANGE = (-100.0, 100_000.0)


class SourceRegressionError(RuntimeError):
    """The source offers a year we did not manage to store.

    `F-0091`. For an annual series dated to 1 January, a data-age check is
    nearly useless - see the tolerance note in `freshness_watchdog.py`. The
    question that *is* answerable is "does the database contain the newest
    year the API is offering", and if it does not, something between the fetch
    and the write dropped it: a country that stopped resolving, a value that
    stopped parsing, a mapping that went stale.

    Raised rather than logged, because `D-0027` - a guard that stands aside is
    not a guard.
    """


def ensure_money_metric(db: Session) -> Metric:
    metric = db.query(Metric).filter_by(code=MONEY_METRIC["code"]).first()
    if not metric:
        metric = Metric(**MONEY_METRIC)
        db.add(metric)
        db.commit()
        logger.info("Created metric: BROAD_MONEY_GROWTH")
    return metric


def fetch_money_supply(timeout: int = 45) -> tuple[list, str]:
    """Return `(payload, origin)` — the World Bank response, or the cached file.

    `origin` is "api" or "cache" and the caller reports it. The fallback is
    deliberate but must never be silent: a run that quietly served a file
    frozen at some past release, while reporting plain `success`, is exactly
    the nine-month TIC failure (`F-0088`) with a different source.
    """
    try:
        r = requests.get(WB_URL, params=WB_PARAMS, timeout=timeout)
        r.raise_for_status()
        payload = r.json()
        if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
            raise ValueError(f"World Bank returned no records: {str(payload)[:200]}")
        return payload, "api"
    except Exception as exc:
        logger.warning(
            "World Bank fetch failed (%s); falling back to %s", exc, JSON_PATH
        )
        if not JSON_PATH.exists():
            raise
        with open(JSON_PATH, encoding="utf-8") as fh:
            payload = json.load(fh)
        if len(payload) < 2 or not payload[1]:
            raise ValueError(f"{JSON_PATH} has no data records")
        return payload, "cache"


def newest_year_offered(payload: list) -> int | None:
    """The most recent year the payload actually carries a value for.

    Not `max(date)`: the World Bank returns a row per country-year with
    `value: null` for years a country has not reported, and the newest year in
    the response is usually null for most of them.
    """
    years = [
        int(item["date"])
        for item in payload[1]
        if item.get("value") is not None and str(item.get("date", "")).isdigit()
    ]
    return max(years) if years else None


def run_money_supply_fetch(db: Session) -> dict:
    """Import broad money growth from the World Bank API."""
    start_time = datetime.utcnow()
    inserted = updated = skipped = 0
    rejected = []

    payload, origin = fetch_money_supply()
    source_last_updated = (payload[0] or {}).get("lastupdated")
    offered = newest_year_offered(payload)

    metric = ensure_money_metric(db)
    countries_found = set()
    years_written = set()

    for item in payload[1]:
        iso3 = item.get("countryiso3code")
        date_str = item.get("date")
        value = item.get("value")

        # Skip nulls — many countries have reporting gaps
        if not iso3 or not date_str or value is None:
            skipped += 1
            continue

        country = db.query(Country).filter_by(iso_code=iso3).first()
        if not country:
            skipped += 1
            continue

        try:
            year = int(date_str)
            date = datetime(year, 1, 1)
            pct_f = float(value)
        except (ValueError, TypeError):
            skipped += 1
            continue

        low, high = PLAUSIBLE_PCT_RANGE
        if not (low <= pct_f <= high):
            # Recorded and named, not silently dropped: a value out of range
            # means the indicator changed shape, and a count of "skipped" would
            # hide that among the reporting gaps.
            rejected.append(f"{iso3}/{year}={pct_f:.4g}")
            skipped += 1
            continue

        pct = Decimal(str(round(pct_f, 4)))
        countries_found.add(iso3)
        years_written.add(year)

        existing = db.query(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id == country.id,
            TimeSeries.date == date,
        ).first()

        if existing:
            existing.value = pct
            existing.updated_at = datetime.utcnow()
            updated += 1
        else:
            db.add(TimeSeries(
                metric_id=metric.id,
                country_id=country.id,
                date=date,
                value=pct,
            ))
            inserted += 1

    db.commit()
    logger.info(
        "Money supply import (%s, source lastupdated %s): %d inserted, "
        "%d updated, %d skipped, %d countries, newest year %s",
        origin, source_last_updated, inserted, updated, skipped,
        len(countries_found), max(years_written) if years_written else None,
    )

    # The guard that is actually meaningful for an annual series.
    if offered is not None and offered not in years_written:
        raise SourceRegressionError(
            f"World Bank offers {offered} data but none was stored. "
            f"Years written: {sorted(years_written)[-3:] or 'none'}. "
            f"The fetch and parse succeeded, so this is a mapping or "
            f"plausibility regression, not an outage."
            + (f" Rejected: {', '.join(rejected[:5])}" if rejected else "")
        )

    status = "success" if origin == "api" and not rejected else "partial"
    notes = []
    if origin == "cache":
        notes.append(
            f"served from cached {JSON_PATH.name}; World Bank API unreachable"
        )
    if rejected:
        notes.append(f"{len(rejected)} implausible: {', '.join(rejected[:5])}")

    db.add(UpdateLog(
        pipeline_name="Broad_Money_Growth",
        status=status,
        records_inserted=inserted,
        records_updated=updated,
        error_message="; ".join(notes)[:480] or None,
        started_at=start_time,
        completed_at=datetime.utcnow(),
    ))
    db.commit()

    return {
        "status": status,
        "origin": origin,
        "source_last_updated": source_last_updated,
        "newest_year": max(years_written) if years_written else None,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "rejected": rejected,
        "countries": len(countries_found),
    }
