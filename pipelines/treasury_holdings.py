"""
Treasury Holdings Data Pipeline
--------------------------------
Fetches US Treasury holdings by country from TIC (Treasury International
Capital).

Data source: SLT Table 5, "Major Foreign Holders of Treasury Securities".
Runs monthly on day 15 via scheduler.

F-0088: this pointed at `Publish/mfhhis01.txt` for nine months. That file is
still served, still 200, still updated in place by every release - and it
stopped being extended past December 2025, because Treasury retired the
standalone MFH release in March 2023 and folded the table into the SLT
dataset. It is the *history* file. The current table is Table 5 of SLT.
"""

import re
import requests
import logging
from datetime import datetime
from decimal import Decimal
from sqlalchemy.orm import Session
from database.models import Metric, Country, TimeSeries, UpdateLog

logger = logging.getLogger(__name__)

TIC_BASE = "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents"

# SLT Table 5 - "Major Foreign Holders of Treasury Securities".
#
# F-0088. Not `Publish/mfhhis01.txt`, which this used for nine months. Both
# files are served by the same release and both carried a September 2026
# last-modified; only this one contains September 2026 *data*. The landing
# page names this URL as "direct link to the MFH table", and the file names
# itself in its own fourth line - the one authority on which file is current
# was inside the file all along.
TIC_MFH_URL = f"{TIC_BASE}/slt_table5.txt"

# The history file, kept for backfill only. It holds years of monthly data
# that Table 5's rolling 13-month window does not, so it is worth having a
# name for - but nothing scheduled reads it, because reading it is the bug.
TIC_MFH_HISTORY_URL = "https://ticdata.treasury.gov/Publish/mfhhis01.txt"

# D-0045 / F-0050. The age at which this pipeline refuses the file outright.
#
# F-0089: this was 100, on the reasoning that "a healthy newest row is about
# 60 days old and 75 at the end of a cycle". Both figures are too low by about
# a month. Rows are dated to the first of the data month and the release runs
# ~2.5 months behind, so the newest row is 77 days old the day it is published
# and ~106 the day before the next release. 100 sits inside that range: the
# guard would have refused a perfectly current file for the last two weeks of
# every cycle.
#
# It never did, because the source was frozen at 303 days the whole time this
# number existed - the bug was masked by the bug it was written for.
#
# 140 refuses a file that has missed two releases while passing one that has
# missed none.
#
# F-0087: this is the age at which this pipeline REFUSES THE FILE, which is a
# different question from the age at which a reader should be told the source
# has missed its release. The latter is `tic.max_age_days` in
# pipelines/freshness_watchdog.py, which is 55. Both numbers are right; they
# are not interchangeable, and the UI briefly used this one to answer the
# watchdog's question.
#
# This exists because the pipeline reported `success` for nine months while
# re-importing a file frozen at December 2025: 10,009 rows updated, 0 inserted,
# every run. Nothing errored. The fetch worked, the parse worked, the write
# worked, and the data never moved. A pipeline that cannot tell "I imported
# current data" from "I re-imported a frozen year" is not reporting success,
# it is reporting completion.
MAX_SOURCE_AGE_DAYS = 140


class StaleSourceError(RuntimeError):
    """The fetch and parse both worked and the data is frozen.

    Distinct from the per-country parse errors that legitimately make a run
    `partial`: this one means the whole import is worthless, so it must be
    `failed`. D-0027 - a guard that stands aside is not a guard, and `partial`
    is exactly standing aside.
    """

MONTH_ABBR_SET = {"Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"}

# SLT Table 5 column headers: "2026-07". Anchored on four digits so a stray
# "2026" year cell from the legacy layout cannot match.
ISO_MONTH_RE = re.compile(r"\d{4}-(0[1-9]|1[0-2])")

SKIP_ROWS = {
    "All Other", "Grand Total", "For. Official",
    "Treasury Bills", "T-Bonds & Notes", "Of which:",
    "Country",
}

# Table 5's aggregate rows. They are not countries and have no ISO code, so
# they were already dropped at the mapping step - but only after being parsed
# into the result dict, where "Of Which: Foreign Official" at 3773.1 sat above
# Japan looking exactly like the largest holder. Matched by prefix because the
# suffixes vary ("Treasury Bills", "T-Bonds & Notes") and because the existing
# SKIP_ROWS entry is "Of which:", which does not match a capital W.
SKIP_PREFIXES = ("Of Which:", "Of which:", "Table 5", "Holdings at end", "Link:")

# D-0079 / A-0019 option 2. Table 5's own aggregate rows, captured as global
# series (country_id NULL) rather than as countries.
#
# `F-0097` established that a country absent from Table 5 is inside its "All
# Other" row, not at zero, and `D-0078` put that on the screen. This is the
# other half: the row itself is published, so the non-reporters' combined
# position is knowable in aggregate even though no individual position is.
#
# GRAND TOTAL is captured with it because All Other alone is close to
# uninterpretable - a rise could mean the non-reporters bought, or simply that
# the whole market grew. The share of total is the meaningful figure.
#
# What this must NEVER do is attribute an aggregate move to an individual
# country. One observation cannot become 28 findings; that is `F-0097` in a new
# costume, and `tests/test_tic_all_other.py` asserts no country's score moves.
TIC_AGGREGATES = {
    "All Other": {
        "code": "TIC_ALL_OTHER",
        "name": "TIC All Other Holders",
        "description": (
            "Combined US Treasury holdings of every foreign holder too small to "
            "be named in SLT Table 5. The 28 scored countries outside the "
            "table's twenty are inside this figure (F-0097)."
        ),
    },
    # D-0080. A SUBSET of Grand Total, not a peer of All Other, so it must
    # never be added to either. It is the cut that separates central-bank
    # holdings from private ones, which is closer to this application's thesis
    # than anything else on the table.
    #
    # The two components are captured with it because Table 5 publishes them and
    # they must sum to the headline - a free integrity check on every run, and
    # the bills/bonds mix is a duration posture in its own right.
    #
    # Exact-label matched, not prefix matched: all three begin "Of Which:
    # Foreign Official".
    "Of Which: Foreign Official": {
        "code": "TIC_FOREIGN_OFFICIAL",
        "name": "TIC Foreign Official Holdings",
        "description": (
            "US Treasuries held by foreign official institutions - central banks "
            "and sovereign funds - across all holders, named and unnamed. A "
            "subset of Grand Total, never additive with All Other."
        ),
    },
    "Of Which: Foreign Official Treasury Bills": {
        "code": "TIC_FOREIGN_OFFICIAL_BILLS",
        "name": "TIC Foreign Official - Treasury Bills",
        "description": (
            "The bill component of foreign official holdings. With T-bonds it "
            "must sum to the headline; the share in bills is a duration posture."
        ),
    },
    "Of Which: Foreign Official T-Bonds & Notes": {
        "code": "TIC_FOREIGN_OFFICIAL_BONDS",
        "name": "TIC Foreign Official - T-Bonds and Notes",
        "description": (
            "The long component of foreign official holdings. With bills it must "
            "sum to the headline (D-0080)."
        ),
    },
    "Grand Total": {
        "code": "TIC_GRAND_TOTAL",
        "name": "TIC Grand Total Foreign Holdings",
        "description": (
            "Total foreign holdings of US Treasury securities. Captured so All "
            "Other can be read as a share rather than an absolute."
        ),
    },
}

COUNTRY_MAPPING = {
    "Japan": "JPN",
    "United Kingdom": "GBR",
    "China, Mainland": "CHN",
    "Belgium": "BEL",
    "Canada": "CAN",
    "Luxembourg": "LUX",
    "Cayman Islands": "CYM",
    "France": "FRA",
    "Ireland": "IRL",
    "Germany": "DEU",
    "Netherlands": "NLD",
    "Switzerland": "CHE",
    "Australia": "AUS",
    "Taiwan": "TWN",
    "Korea, South": "KOR",
    "South Korea": "KOR",
    "India": "IND",
    "Mexico": "MEX",
    "Brazil": "BRA",
    "Russia": "RUS",
    "Saudi Arabia": "SAU",
    "Singapore": "SGP",
    "Hong Kong": "HKG",
    "Norway": "NOR",
    "Sweden": "SWE",
    "Spain": "ESP",
    "Italy": "ITA",
    "Austria": "AUT",
    "Denmark": "DNK",
    "Finland": "FIN",
    "Greece": "GRC",
    "Portugal": "PRT",
    "Turkey": "TUR",
    "Israel": "ISR",
    "United Arab Emirates": "ARE",
    "Thailand": "THA",
    "Malaysia": "MYS",
    "Indonesia": "IDN",
    "Philippines": "PHL",
    "Vietnam": "VNM",
    "New Zealand": "NZL",
    "Chile": "CHL",
    "Argentina": "ARG",
    "South Africa": "ZAF",
    "Egypt": "EGY",
    "Bermuda": "BMU",
    "El Salvador": "SLV",
    "Kuwait": "KWT",
    "Poland": "POL",
    "Colombia": "COL",
    "Peru": "PER",
}


def ensure_metric(db: Session) -> Metric:
    metric = db.query(Metric).filter_by(code="TIC_UST_HOLDINGS").first()
    if not metric:
        metric = Metric(
            code="TIC_UST_HOLDINGS",
            name="Foreign Holdings of US Treasury Securities",
            category="holdings",
            unit="billions_usd",
            source="TIC",
            description="Foreign holdings of US Treasury securities by country (billions USD)",
        )
        db.add(metric)
        db.commit()
        logger.info("Created metric: TIC_UST_HOLDINGS")
    return metric


def ensure_country(db: Session, iso_code: str, country_name: str) -> Country:
    country = db.query(Country).filter_by(iso_code=iso_code).first()
    if not country:
        country = Country(iso_code=iso_code, name=country_name)
        db.add(country)
        db.commit()
        logger.info(f"Created country: {iso_code} ({country_name})")
    return country


def fetch_tic_mfh_data() -> str:
    r = requests.get(TIC_MFH_URL, timeout=30)
    r.raise_for_status()
    return r.text


def parse_tic_mfh(text: str, admit: frozenset = frozenset()) -> dict:
    """
    Parse a tab-delimited TIC MFH file, in either published layout.

    `admit` names rows that are normally skipped but are wanted by this caller -
    Table 5's "All Other" and "Grand Total" aggregates (`D-0079`). Passed in
    rather than handled by a second parser, because the two would then each own
    a copy of the month-column logic and an off-by-one in either would silently
    date July's figure to May.

    **SLT Table 5** (the current release) heads its columns with ISO months
    on the same row as the `Country` label:

        Country\t2026-07\t2026-06\t2026-05\t...
        Japan\t1103.9\t1116.7\t1143.1\t...

    **mfhhis01.txt** (the history file) splits the header across two rows and
    stacks a fresh pair for every year:

        \tDec\tNov\t...
        Country\t2025\t2025\t...

    Both are handled, and both are exercised by fixtures. The history layout
    is not dead code kept for sentiment: it is a real format still served,
    and the reason this function must be able to tell them apart is that
    reading the wrong one silently yields a frozen year (`F-0088`).

    Legacy structure:
      - Leading header rows (ignore)
      - Month row: \tDec\tNov\t... (first col blank)
      - Year row: Country\t2025\t2025\t...
      - Separator row: \t------\t...
      - Data rows: Japan\t1185.5\t...
      - Summary rows: Grand Total\t... (skipped)
      - Repeats for prior years

    Returns: {country_name: {date_str: value_billions}}
    """
    result = {}
    # Normalise line endings
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    current_dates = []
    pending_months = []

    for line in lines:
        cols = [c.strip() for c in line.split("\t")]
        non_empty = [c for c in cols if c and c != "------"]

        if not non_empty:
            continue

        # SLT Table 5 header: "Country" followed by ISO months, one row.
        #
        # Checked before the legacy year row below, which also starts with
        # "Country" but requires `pending_months` from a preceding month row.
        # Normalised to the same "%b %Y" strings the legacy path produces, so
        # the caller's strptime contract is untouched.
        if cols[0] == "Country":
            iso = [c for c in non_empty if ISO_MONTH_RE.fullmatch(c)]
            if iso:
                current_dates = [
                    datetime.strptime(c, "%Y-%m").strftime("%b %Y") for c in iso
                ]
                pending_months = []
                continue

        # Month header row: first col blank, first non-empty value is a month abbr
        if cols[0] == "" and non_empty[0] in MONTH_ABBR_SET:
            pending_months = [c for c in non_empty if c in MONTH_ABBR_SET]
            continue

        # Year row: first col is "Country", rest are 4-digit years
        if cols[0] == "Country" and pending_months:
            years = [c for c in non_empty if c.isdigit() and len(c) == 4]
            if years:
                current_dates = [f"{m} {y}" for m, y in zip(pending_months, years)]
            pending_months = []
            continue

        # Country data row
        country = cols[0].strip('"').strip()

        # D-0079. An explicitly admitted aggregate row, read with the same
        # column-to-month mapping as a country row and checked before the skip
        # list, since every one of these labels is in it.
        if country in admit and current_dates:
            admitted = []
            for c in cols[1:]:
                if not c or c == "------":
                    continue
                try:
                    admitted.append(float(c))
                except ValueError:
                    continue
            if admitted:
                result.setdefault(country, {}).update(
                    dict(zip(current_dates[:len(admitted)], admitted))
                )
            continue

        if (not country
                or country in SKIP_ROWS
                or "---" in country
                or "HOLDINGS" in country
                or "billions" in country
                or "AT END" in country
                or "MAJOR" in country
                # Table 5 prose and aggregate rows. "Link:" is the line that
                # names the current file (F-0088) and is still a header, not a
                # country.
                or country.startswith(SKIP_PREFIXES)):
            continue

        if not current_dates:
            continue

        # Parse numeric values
        values = []
        for c in cols[1:]:
            if not c or c == "------":
                continue
            try:
                values.append(float(c))
            except ValueError:
                continue

        if values:
            if country not in result:
                result[country] = {}
            for date_str, val in zip(current_dates[:len(values)], values):
                result[country][date_str] = val

    logger.info(f"Parsed {len(result)} countries from TIC MFH data")
    return result


def parse_tic_aggregates(text: str) -> dict:
    """`{metric_code: {date_str: value_billions}}` for Table 5's aggregate rows.

    A second pass over the same text rather than a change to `parse_tic_mfh`,
    whose contract is "countries" and whose fixtures pin exactly that. Mixing
    aggregates into that dict is how "Of Which: Foreign Official" at 3,773.1
    came to outrank Japan (`F-0088`).

    Shares the header logic by asking `parse_tic_mfh` to admit these labels, so
    the two cannot disagree about which column is which month - the off-by-one
    that would silently date July's figure to May.

    A first attempt rewrote the text so the aggregates were the only data rows
    and got nothing back, because `SKIP_ROWS` drops them however they arrive.
    """
    parsed = parse_tic_mfh(text, admit=frozenset(TIC_AGGREGATES))

    out = {}
    for label, meta in TIC_AGGREGATES.items():
        if label in parsed:
            out[meta["code"]] = parsed[label]
    return out


def ensure_aggregate_metric(db: Session, code: str) -> Metric:
    meta = next(m for m in TIC_AGGREGATES.values() if m["code"] == code)
    metric = db.query(Metric).filter_by(code=code).first()
    if not metric:
        metric = Metric(
            code=code,
            name=meta["name"],
            category="holdings",
            unit="billions",
            source="US Treasury TIC",
            description=meta["description"],
        )
        db.add(metric)
        db.commit()
        logger.info("Created metric: %s", code)
    return metric


def import_tic_aggregates(db: Session, text: str) -> dict:
    """Write Table 5's aggregate rows as global series. Returns per-code counts."""
    result = {}
    for code, by_date in parse_tic_aggregates(text).items():
        metric = ensure_aggregate_metric(db, code)
        inserted = updated = 0
        for date_str, value in by_date.items():
            try:
                date_obj = datetime.strptime(f"01 {date_str}", "%d %b %Y")
            except ValueError:
                continue
            existing = db.query(TimeSeries).filter(
                TimeSeries.metric_id == metric.id,
                TimeSeries.country_id.is_(None),
                TimeSeries.date == date_obj,
            ).first()
            if existing:
                existing.value = Decimal(str(value))
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                db.add(TimeSeries(
                    metric_id=metric.id,
                    country_id=None,
                    date=date_obj,
                    value=Decimal(str(value)),
                ))
                inserted += 1
        db.commit()
        result[code] = {"inserted": inserted, "updated": updated,
                        "points": len(by_date)}
    return result


def run_treasury_holdings_fetch(db: Session) -> dict:
    """Main TIC holdings fetch pipeline."""
    start_time = datetime.utcnow()
    total_inserted = 0
    total_updated = 0
    newest_source_date = None
    errors = []
    countries_loaded = 0

    try:
        tic_text = fetch_tic_mfh_data()
        holdings_by_country = parse_tic_mfh(tic_text)
        # D-0079. The aggregate rows, as global series. Written before the
        # per-country loop so a country-mapping failure does not lose them.
        aggregates = import_tic_aggregates(db, tic_text)

        if not holdings_by_country:
            raise ValueError("No holdings data parsed from TIC file — format may have changed")

        metric = ensure_metric(db)

        for country_name, date_values in holdings_by_country.items():
            iso_code = COUNTRY_MAPPING.get(country_name)
            if not iso_code:
                logger.debug(f"Skipping {country_name!r} — no ISO mapping")
                continue

            country = ensure_country(db, iso_code, country_name)
            countries_loaded += 1

            for date_str, value_billions in date_values.items():
                try:
                    date_obj = datetime.strptime(f"01 {date_str}", "%d %b %Y")
                    if newest_source_date is None or date_obj > newest_source_date:
                        newest_source_date = date_obj
                    value = Decimal(str(value_billions))

                    existing = db.query(TimeSeries).filter(
                        TimeSeries.metric_id == metric.id,
                        TimeSeries.country_id == country.id,
                        TimeSeries.date == date_obj,
                    ).first()

                    if existing:
                        existing.value = value
                        existing.updated_at = datetime.utcnow()
                        total_updated += 1
                    else:
                        db.add(TimeSeries(
                            metric_id=metric.id,
                            country_id=country.id,
                            date=date_obj,
                            value=value,
                        ))
                        total_inserted += 1

                except Exception as e:
                    logger.error(f"Error processing {country_name} {date_str}: {e}")
                    errors.append(f"{country_name}/{date_str}: {str(e)}")

            db.commit()

        logger.info(
            f"TIC holdings: {countries_loaded} countries, "
            f"{total_inserted} inserted, {total_updated} updated; "
            f"aggregates: {aggregates}"
        )

        # D-0045: refuse to call a frozen source a success.
        if newest_source_date is None:
            raise StaleSourceError(
                f"TIC source at {TIC_MFH_URL} yielded no parseable dates. "
                f"Refusing to report success."
            )
        age_days = (datetime.utcnow() - newest_source_date).days
        if age_days > MAX_SOURCE_AGE_DAYS:
            raise StaleSourceError(
                f"TIC source at {TIC_MFH_URL} is stale: newest row "
                f"{newest_source_date.date()} is {age_days} days old, limit is "
                f"{MAX_SOURCE_AGE_DAYS}. The fetch and parse both succeeded - "
                f"the upstream file is frozen, or the URL now points at a "
                f"historical year rather than the current release. See F-0050."
            )

        stale = False
    except StaleSourceError as e:
        logger.error(f"TIC holdings source is frozen: {e}")
        errors.append(str(e))
        stale = True
    except Exception as e:
        logger.error(f"TIC holdings fetch failed: {e}")
        errors.append(str(e))
        stale = False

    # A frozen source is `failed`, not `partial`. `partial` reads as "mostly
    # fine" and is what let this sit for nine months.
    status = "failed" if stale else ("success" if not errors else "partial")
    db.add(UpdateLog(
        pipeline_name="TIC_Holdings",
        status=status,
        records_inserted=total_inserted,
        records_updated=total_updated,
        error_message="; ".join(errors) if errors else None,
        started_at=start_time,
        completed_at=datetime.utcnow(),
    ))
    db.commit()

    return {
        "status": status,
        "countries": countries_loaded,
        "inserted": total_inserted,
        "updated": total_updated,
        "errors": errors,
    }
