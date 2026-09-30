"""
TIC SLT Table 3 - Treasury holdings for every reporting country
---------------------------------------------------------------
`D-0081` / `A-0019` option 3.

`F-0097` established that SLT Table 5 names only the **twenty largest** holders
and folds the rest into "All Other", so dimension 1 - 50 points, the largest in
the model - could speak about twenty countries and no more. `D-0078` disclosed
that; `D-0079` and `D-0080` measured the aggregates. This removes the limit.

**Table 3 is the same data, unabridged.** Same directory, same release, same
month, long format instead of wide:

    Country  Country Code  Date     Holdings  Net U.S. Sales  Valuation Change
    Austria  10189         2026-07     6,048             384              -23

**76 countries**, monthly back to 2020-01. Validated the way `D-0076` was, and
against a source we already hold: Japan, the United Kingdom, Belgium, Canada and
France match Table 5 **to the decimal**. The guard below refuses the import if
they ever stop matching.

**Units are MILLIONS here and billions in Table 5.** A units error is the
`F-0093` shape - Brazil read 172,446 tonnes because a scale changed mid-series -
so conversion happens once, at parse, and the plausibility ceiling is expressed
in the converted unit.

**What the extra columns make possible.** Dimension 1 currently reads a decline
in holdings and cannot tell selling from repricing. Table 3 separates them:
Germany's July was -$9.6bn of holdings, of which **-$7.2bn was actual selling**
and -$0.5bn was valuation. Both are stored; **neither changes any score today**.
Scoring on net sales rather than holdings change would alter every number in the
model, which is a decision rather than an implementation - `A-0021`.
"""

import logging
from datetime import datetime
from decimal import Decimal

import requests
from sqlalchemy.orm import Session

from database.models import Country, Metric, TimeSeries, UpdateLog

logger = logging.getLogger(__name__)

PIPELINE_NAME = "TIC_Table3"

TIC_TABLE3_URL = (
    "https://ticdata.treasury.gov/resource-center/data-chart-center/tic/"
    "Documents/slt_table3.txt"
)

# Column positions, from the file's own machine-readable header row:
#   country  country_code  date  for_treas_pos  for_treas_net
#   for_lt_treas_pos  for_lt_treas_net  for_lt_treas_valchg
#   for_st_treas_pos  for_st_treas_net
COL_COUNTRY, COL_DATE = 0, 2
COL_HOLDINGS, COL_NET = 3, 4
COL_LT_HOLDINGS = 5
COL_LT_VALCHG = 7

# Rows whose "country" is a region, a memo line or a total. `F-0088` is the
# standing example: "Of Which: Foreign Official" at 3,773.1 outranked Japan.
# Matched by prefix because the regional labels are open-ended ("Total Africa",
# "Total Regional Orgs.").
AGGREGATE_PREFIXES = (
    "All Countries", "Grand Total", "International",
    "Total ", "Memo:", "Of Which:",
)

# Table 3 labels our `countries` table does not carry under that name, with the
# ISO code each should have.
#
# Explicit rather than fuzzy-matched: a near-miss that silently maps Jersey to
# Germany is worse than a country we skip and can see we skipped. `D-0082`: a
# row is created for these when it does not exist, and ONLY for these - a label
# that is not on this list is reported as unmapped rather than turned into a
# country nobody vetted.
#
# Thirteen of the nineteen are offshore financial centres rather than sovereigns
# in the stress sense. They are included because the model already ranks the
# Cayman Islands and Bermuda, which are in Table 5's twenty, so excluding the
# smaller conduits would be inconsistent rather than principled. Their holdings
# are real and their rows are as reversible as any other.
EXTRA_ISO = {
    "Anguilla": "AIA", "Argentina": "ARG", "Aruba": "ABW", "Austria": "AUT",
    "Bahamas": "BHS", "Barbados": "BRB", "British Virgin Islands": "VGB",
    "Curacao": "CUW", "Greece": "GRC", "Guernsey": "GGY", "Jamaica": "JAM",
    "Jersey": "JEY", "Liberia": "LBR", "New Zealand": "NZL", "Panama": "PAN",
    "Portugal": "PRT", "Saint Kitts and Nevis": "KNA", "Syria": "SYR",
    "Trinidad and Tobago": "TTO",
}

# Japan, the largest holder, is $1,103.9bn. A country reading above this is a
# units error, not a discovery - the same guard shape as MAX_PLAUSIBLE_TONNES.
MAX_PLAUSIBLE_HOLDINGS_BN = 2000.0

# Countries whose Table 5 figure must be reproduced before anything is written,
# and the tolerance. They are the largest holders, so an error in the units or
# the column positions shows up here first and hugely.
VALIDATION_TOLERANCE_BN = 0.5

METRICS = {
    "TIC_UST_HOLDINGS": None,  # created by treasury_holdings.py; shared
    "TIC_UST_NET_SALES": {
        "name": "TIC Net U.S. Sales of Treasuries by Country",
        "description": (
            "Net sales to foreign residents, per country, per month. Positive "
            "is an increase in the foreign position. Distinct from the change "
            "in holdings, which also moves with price (D-0081)."
        ),
    },
    "TIC_UST_LT_HOLDINGS": {
        "name": "TIC Long-Term Treasury Holdings by Country",
        "description": (
            "Long-term Treasury holdings per country. Sixteen reporters publish "
            "this while suppressing their total as 'n.a.' - Poland, Egypt, "
            "Hungary, Romania, Serbia, Ukraine and Lebanon among them - so it "
            "is the only figure available for them. A DIFFERENT measure from "
            "total holdings, stored separately rather than substituted (D-0081)."
        ),
    },
    "TIC_UST_LT_VALUATION": {
        "name": "TIC Long-Term Treasury Valuation Change by Country",
        "description": (
            "The part of the change in long-term holdings attributable to price "
            "rather than transactions. Stored so selling can be told from "
            "repricing; not yet scored (A-0021)."
        ),
    },
}


class Table3ValidationError(RuntimeError):
    """Table 3 stopped reproducing Table 5 for the largest holders.

    Both are published in the same release and describe the same measure, so a
    mismatch means the column positions, the units or the source layout has
    changed. Raised rather than logged, because importing 76 countries of
    silently wrong holdings into the largest scoring dimension is worse than
    importing nothing (`D-0027`).
    """


def fetch_table3(timeout: int = 90) -> str:
    r = requests.get(TIC_TABLE3_URL, timeout=timeout)
    r.raise_for_status()
    if "for_treas_pos" not in r.text:
        raise ValueError(
            "Table 3 response is missing its machine-readable header row; the "
            "layout has changed and column positions cannot be trusted."
        )
    return r.text


def is_aggregate(label: str) -> bool:
    return label.startswith(AGGREGATE_PREFIXES)


def parse_table3(text: str) -> tuple[list[dict], list[str]]:
    """`(observations, rejected)` with values converted to billions.

    Each observation is `{label, date, holdings_bn, net_sales_bn,
    lt_valuation_bn}`. Aggregates are dropped; implausible holdings are
    rejected by name so they can be chased rather than silently lost.
    """
    out, rejected = [], []

    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        cols = line.split("\t")
        if len(cols) <= COL_LT_VALCHG:
            continue

        label = cols[COL_COUNTRY].strip()
        period = cols[COL_DATE].strip()
        if not label or is_aggregate(label):
            continue
        # "2026-07". The header rows fail this and so are skipped without
        # needing to be named.
        if len(period) != 7 or period[4] != "-" or not period[:4].isdigit():
            continue

        def num(i):
            raw = cols[i].strip()
            if not raw:
                return None
            try:
                return float(raw) / 1000.0  # millions -> billions
            except ValueError:
                return None

        # D-0081. Sixteen reporters publish `n.a.` for TOTAL holdings while
        # publishing the long-term figure - Treasury suppresses the total, not
        # the position. Dropping a row for a missing total loses Poland, Egypt,
        # Hungary, Romania, Serbia, Ukraine and Lebanon, several of them scored.
        #
        # Long-term is NOT substituted for total. It is a different measure -
        # it excludes bills, which are ~9% of official holdings - and quietly
        # labelling one as the other is the substitution that made F-0097 a
        # fabrication. Both are stored; the scorer decides.
        holdings = num(COL_HOLDINGS)
        lt_holdings = num(COL_LT_HOLDINGS)
        if holdings is None and lt_holdings is None:
            continue

        implausible = [
            (name, v) for name, v in (("total", holdings), ("long-term", lt_holdings))
            if v is not None and not (0.0 <= v <= MAX_PLAUSIBLE_HOLDINGS_BN)
        ]
        if implausible:
            rejected.extend(
                f"{label}/{period} {n}={v:,.1f}bn" for n, v in implausible
            )
            continue

        try:
            date = datetime(int(period[:4]), int(period[5:7]), 1)
        except ValueError:
            continue

        out.append({
            "label": label,
            "date": date,
            "holdings_bn": round(holdings, 3) if holdings is not None else None,
            "lt_holdings_bn": round(lt_holdings, 3) if lt_holdings is not None else None,
            "net_sales_bn": num(COL_NET),
            "lt_valuation_bn": num(COL_LT_VALCHG),
        })

    return out, rejected


def validate_against_table5(observations: list[dict], table5: dict) -> list[str]:
    """Discrepancies against Table 5's wide table, for the months both carry.

    `table5` is `{country_label: {date_str: value_bn}}` as `parse_tic_mfh`
    returns it. Both come from the same release and describe the same measure,
    so any difference beyond rounding is a defect in one of the two readings.
    """
    by_key = {
        (o["label"], o["date"].strftime("%b %Y")): o["holdings_bn"]
        for o in observations
        if o["holdings_bn"] is not None
    }
    problems = []
    for label, by_date in table5.items():
        for date_str, expected in by_date.items():
            got = by_key.get((label, date_str))
            if got is None:
                continue
            if abs(got - expected) > VALIDATION_TOLERANCE_BN:
                problems.append(
                    f"{label} {date_str}: Table 3 {got:,.1f} vs Table 5 {expected:,.1f}"
                )
    return problems


def _ensure_metric(db: Session, code: str) -> Metric:
    metric = db.query(Metric).filter_by(code=code).first()
    if metric:
        return metric
    meta = METRICS[code]
    if meta is None:
        raise ValueError(
            f"{code} should have been created by treasury_holdings.py. Refusing "
            f"to create the shared holdings metric from here, where its name and "
            f"description would be a second opinion about what it is."
        )
    metric = Metric(
        code=code, name=meta["name"], category="holdings", unit="billions",
        source="US Treasury TIC", description=meta["description"],
    )
    db.add(metric)
    db.commit()
    logger.info("Created metric: %s", code)
    return metric


def run_tic_table3_fetch(db: Session, validate: bool = True) -> dict:
    """Import per-country Treasury holdings, net sales and valuation change."""
    started = datetime.utcnow()

    try:
        text = fetch_table3()
        observations, rejected = parse_table3(text)
        if not observations:
            raise ValueError("Table 3 parsed to zero usable observations")

        if validate:
            from pipelines.treasury_holdings import (
                fetch_tic_mfh_data,
                parse_tic_mfh,
            )

            problems = validate_against_table5(
                observations, parse_tic_mfh(fetch_tic_mfh_data())
            )
            if problems:
                raise Table3ValidationError(
                    f"Table 3 no longer reproduces Table 5 for "
                    f"{len(problems)} country-months: {'; '.join(problems[:4])}"
                )

        holdings_metric = _ensure_metric(db, "TIC_UST_HOLDINGS")
        lt_metric = _ensure_metric(db, "TIC_UST_LT_HOLDINGS")
        net_metric = _ensure_metric(db, "TIC_UST_NET_SALES")
        val_metric = _ensure_metric(db, "TIC_UST_LT_VALUATION")

        # Resolve labels once. Name first, because the countries table is the
        # authority; EXTRA_ISO covers what it does not carry under that name.
        by_name = {c.name.lower(): c for c in db.query(Country).all()}
        by_iso = {c.iso_code: c for c in db.query(Country).all()}

        resolved, unmapped, created = {}, set(), []
        for label in {o["label"] for o in observations}:
            country = by_name.get(label.lower())
            if country is None:
                iso = EXTRA_ISO.get(label)
                if iso:
                    country = by_iso.get(iso)
                    if country is None:
                        # D-0082. Created only for a vetted label. These are
                        # real reporters with real holdings whose absence was an
                        # accident of which countries happened to be seeded, not
                        # a decision about scope.
                        country = Country(iso_code=iso, name=label)
                        db.add(country)
                        db.commit()
                        by_iso[iso] = country
                        by_name[label.lower()] = country
                        created.append(f"{iso} ({label})")
            if country is None:
                unmapped.add(label)
            resolved[label] = country

        if created:
            logger.info("TIC Table 3 created %d countries: %s",
                        len(created), ", ".join(sorted(created)))

        inserted = updated = skipped = 0
        countries = set()
        newest = None

        for obs in observations:
            country = resolved.get(obs["label"])
            if country is None:
                skipped += 1
                continue

            countries.add(country.iso_code)
            if newest is None or obs["date"] > newest:
                newest = obs["date"]

            for metric, value in (
                (holdings_metric, obs["holdings_bn"]),
                (lt_metric, obs["lt_holdings_bn"]),
                (net_metric, obs["net_sales_bn"]),
                (val_metric, obs["lt_valuation_bn"]),
            ):
                if value is None:
                    continue
                existing = db.query(TimeSeries).filter(
                    TimeSeries.metric_id == metric.id,
                    TimeSeries.country_id == country.id,
                    TimeSeries.date == obs["date"],
                ).first()
                if existing:
                    existing.value = Decimal(str(value))
                    existing.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    db.add(TimeSeries(
                        metric_id=metric.id, country_id=country.id,
                        date=obs["date"], value=Decimal(str(value)),
                    ))
                    inserted += 1

        db.commit()

        status = "partial" if (rejected or unmapped) else "success"
        notes = []
        if created:
            notes.append(f"created {len(created)} countries: {', '.join(sorted(created)[:6])}")
        if rejected:
            notes.append(f"{len(rejected)} implausible: {', '.join(rejected[:4])}")
        if unmapped:
            notes.append(
                f"{len(unmapped)} labels with no country row: "
                f"{', '.join(sorted(unmapped)[:6])}"
            )

        logger.info(
            "TIC Table 3: %s - %d inserted, %d updated, %d skipped, "
            "%d countries, newest %s",
            status, inserted, updated, skipped, len(countries),
            newest.date() if newest else None,
        )

        db.add(UpdateLog(
            pipeline_name=PIPELINE_NAME, status=status,
            records_inserted=inserted, records_updated=updated,
            error_message="; ".join(notes)[:480] or None,
            started_at=started, completed_at=datetime.utcnow(),
        ))
        db.commit()

        return {
            "status": status, "inserted": inserted, "updated": updated,
            "skipped": skipped, "countries": len(countries),
            "newest_date": newest.date().isoformat() if newest else None,
            "rejected": rejected, "unmapped": sorted(unmapped),
            "created_countries": sorted(created),
        }

    except Exception as exc:
        db.rollback()
        logger.error("TIC Table 3 fetch failed: %s", exc)
        db.add(UpdateLog(
            pipeline_name=PIPELINE_NAME, status="failed",
            records_inserted=0, records_updated=0,
            error_message=str(exc)[:480],
            started_at=started, completed_at=datetime.utcnow(),
        ))
        db.commit()
        raise
