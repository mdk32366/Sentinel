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
import time
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlparse

import requests
from sqlalchemy.orm import Session

from config import settings
from database.models import Metric, TimeSeries, Country, UpdateLog

logger = logging.getLogger(__name__)

PIPELINE_NAME = "Gold_Reserves_IMF"

# SDMX 2.1. Key order is COUNTRY.INDICATOR.SECTOR.FREQUENCY; country and sector
# are left blank to mean "all". The legacy `dataservices.imf.org` SDMX endpoint
# no longer resolves at all - api.imf.org is the current host.
#
# 2026-11-10: the flowRef MUST name its agency. `/data/IRFCL/...` used to
# resolve to IMF.STA; IMF's gateway now defaults a missing agency to `all`,
# finds no `all:IRFCL(latest)` and returns 404, while `/data/IMF.STA,IRFCL/...`
# returns the same series. Base and flowRef come from settings
# (`imf_sdmx_base`, `imf_irfcl_flow_ref`) so the next upstream change is a
# config change, not a code hunt.
IMF_GOLD_INDICATOR = "IRFCLDT1_IRFCL56V_FTO"
EXPECTED_AGENCY = "IMF.STA"
EXPECTED_FLOW = "IRFCL"
EXPECTED_FREQUENCY = "M"

# Coverage floor (2026-11-10). The live feed carries 84 countries; a response
# parsing to fewer than this is a truncated or partial publication, and is
# refused before anything is written rather than "succeeding" on a handful.
IMF_MIN_COUNTRIES = 40

# One retry after this many seconds, on 5xx, 429 and network errors only.
RETRY_DELAY_SECONDS = 10


def imf_gold_url() -> str:
    """The IRFCL gold URL, built from settings at call time."""
    base = settings.imf_sdmx_base.rstrip("/")
    return f"{base}/data/{settings.imf_irfcl_flow_ref}/.{IMF_GOLD_INDICATOR}..M"


# The URL as configured at import. Kept as a module constant for the tests and
# for anything that only needs to read it; the fetch always calls imf_gold_url().
IMF_GOLD_URL = imf_gold_url()

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

# F-0095. A country can carry more than one series differing only in SECTOR -
# Germany has S1X and S1XS1311 with identical values. Both must be READ (losing
# one is how Brazil's bad series hid its good one) and then collapsed to one
# observation per country-month, because `ix_metric_country_date` is unique on
# (metric, country, date) and two rows for one month is a constraint violation,
# not a second data point.
#
# The one sector that means official reserve assets. All 84 countries in the
# feed carry it, and it is the series that reproduces every published figure:
# USA 8,133.5t, Germany 3,349.1, Italy 2,451.8, France 2,437.0, UK 310.3.
#
# `F-0095`. The other two sectors are different concepts, not second opinions,
# and neither is a usable fallback:
#
#   S1311  central government's OWN gold. Usually zero, because a country's
#          gold sits at its central bank - Belgium reads S1XS1311=227.4t and
#          S1311=0.0t and both are correct.
#   S1X    zero for the United Kingdom, equal to S1XS1311 for Germany. Whatever
#          it decomposes, it is not reliably the same measure.
#
# I tried both as ranked fallbacks with a disagreement report first. Against the
# live feed that produced 868 "conflicts", then 140 after excluding S1311 -
# every one of them two different concepts correctly disagreeing, and every run
# marked `partial` forever. That is the cry-wolf shape of F-0089 and F-0091
# appearing in a brand-new guard, so the guard went and the rule got simpler:
# take the series that means what we need and ignore the decompositions.
RESERVE_ASSET_SECTOR = "S1XS1311"

_SERIES_SPLIT = re.compile(r"<Series ")
_COUNTRY_RE = re.compile(r'COUNTRY="([^"]+)"')
_SECTOR_RE = re.compile(r'SECTOR="([^"]+)"')
_OBS_RE = re.compile(r'<Obs TIME_PERIOD="([^"]+)" OBS_VALUE="([^"]+)"')
# "2026-M08" -> year 2026, month 8
_PERIOD_RE = re.compile(r"^(\d{4})-M(\d{2})$")


class ImfUpstreamError(RuntimeError):
    """IMF answered with an HTTP error, or could not be reached.

    Carries the status, IMF's own JSON `message` (truncated) and the URL path
    without its query. Never the request headers, which may carry a key.
    """


class ImfContractError(ValueError):
    """IMF answered 200 with something that is not the IRFCL gold series:
    another dataflow, a renamed indicator, no series, or too few countries."""


_STRUCT_REF_RE = re.compile(r'<Ref agencyID="([^"]+)" id="([^"]+)" version="([^"]+)"')
_INDICATOR_RE = re.compile(r'INDICATOR="([^"]+)"')
_FREQ_RE = re.compile(r'FREQUENCY="([^"]+)"')


def structure_version(xml: str):
    """The IRFCL version the response says it is, e.g. "12.0.0", or None."""
    for agency, flow, version in _STRUCT_REF_RE.findall(xml):
        if agency == EXPECTED_AGENCY and flow == EXPECTED_FLOW:
            return version
    return None


def validate_irfcl_header(xml: str) -> str:
    """The response contract, checked before anything is parsed or written.

    Returns the structure version. Raises `ImfContractError` unless the
    response is IMF.STA:IRFCL, carries at least one series, every series is
    the gold indicator at monthly frequency, and the reserve-asset sector is
    present.
    """
    version = structure_version(xml)
    if version is None:
        found = [f"{a}:{f}({v})" for a, f, v in _STRUCT_REF_RE.findall(xml)]
        raise ImfContractError(
            f"IMF response is not {EXPECTED_AGENCY}:{EXPECTED_FLOW}: "
            f"structure refs {found[:3] or 'none'}"
        )

    heads = [block.split(">", 1)[0] for block in _SERIES_SPLIT.split(xml)[1:]]
    if not heads:
        # A 200 carrying only the dataset header. Treated as a failure rather
        # than as "no gold in the world this month": D-0045, a pipeline that
        # cannot tell no-data from no-news reports completion, not success.
        raise ImfContractError(
            f"IMF returned no series for {IMF_GOLD_INDICATOR}. "
            f"{len(xml)} bytes, no <Series> element - the indicator or the "
            f"key order has changed."
        )

    bad_indicators, bad_freqs, sectors = set(), set(), set()
    for head in heads:
        im = _INDICATOR_RE.search(head)
        indicator = im.group(1) if im else ""
        if indicator != IMF_GOLD_INDICATOR:
            bad_indicators.add(indicator or "<none>")
        fm = _FREQ_RE.search(head)
        freq = fm.group(1) if fm else ""
        if freq != EXPECTED_FREQUENCY:
            bad_freqs.add(freq or "<none>")
        sm = _SECTOR_RE.search(head)
        if sm:
            sectors.add(sm.group(1))

    if bad_indicators:
        raise ImfContractError(
            f"IMF IRFCL {version} returned unexpected INDICATOR "
            f"{sorted(bad_indicators)[:5]} (expected {IMF_GOLD_INDICATOR}) - "
            f"schema or key drift."
        )
    if bad_freqs:
        raise ImfContractError(
            f"IMF IRFCL {version} returned unexpected FREQUENCY "
            f"{sorted(bad_freqs)[:5]} (expected {EXPECTED_FREQUENCY})."
        )
    if RESERVE_ASSET_SECTOR not in sectors:
        raise ImfContractError(
            f"IMF IRFCL {version} carries no {RESERVE_ASSET_SECTOR} series "
            f"(sectors {sorted(sectors)[:5]})."
        )
    return version


# SPEC §4.2 names it for what it checks; same function.
validate_irfcl_response = validate_irfcl_header


def _describe(r, url: str) -> str:
    """`IMF upstream HTTP <status> at <path>: <IMF message>`. No headers, no query."""
    msg = ""
    try:
        body = r.json()
        if isinstance(body, dict):
            msg = str(body.get("message") or "")[:200]
    except ValueError:
        pass
    return f"IMF upstream HTTP {r.status_code} at {urlparse(url).path}: {msg}".rstrip(": ")


def fetch_imf_gold(start_period: str = "2015-01", timeout: int = 90, _sleep=None) -> str:
    """The raw SDMX response, contract-checked. Text, so the parser can be
    tested without a URL.

    One retry after RETRY_DELAY_SECONDS on 5xx, 429, connection errors and
    timeouts. No retry on any other 4xx: a 404 fails at once.
    """
    sleep = _sleep or time.sleep
    url = imf_gold_url()
    headers = {"Accept": "application/xml"}
    if settings.imf_api_key:
        headers["Ocp-Apim-Subscription-Key"] = settings.imf_api_key

    for attempt in (1, 2):
        try:
            r = requests.get(
                url, params={"startPeriod": start_period}, headers=headers,
                timeout=timeout,
            )
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == 2:
                raise ImfUpstreamError(
                    f"IMF upstream unreachable at {urlparse(url).path}: "
                    f"{type(exc).__name__}"
                ) from None
            sleep(RETRY_DELAY_SECONDS)
            continue

        if r.status_code >= 500 or r.status_code == 429:
            if attempt == 2:
                raise ImfUpstreamError(_describe(r, url))
            sleep(RETRY_DELAY_SECONDS)
            continue
        if r.status_code >= 400:
            raise ImfUpstreamError(_describe(r, url))

        validate_irfcl_header(r.text)
        return r.text


def parse_imf_gold(xml: str) -> tuple[list[dict], list[str], list[str]]:
    """`(observations, rejected, conflicts)`.

    Each observation is `{iso, date, tonnes, ounces, sector}` with `date` on the
    FIRST of the data month, matching the convention the WGC importer uses for
    quarters (`A-0016` covers why that convention is what it is), and **at most
    one observation per country-month** - see `SECTOR_PREFERENCE`.
    """
    # (iso, date) -> {sector: observation}
    candidates: dict[tuple, dict] = {}
    rejected: list[str] = []

    for block in _SERIES_SPLIT.split(xml)[1:]:
        head = block.split(">", 1)[0]
        m = _COUNTRY_RE.search(head)
        if not m:
            continue
        iso = m.group(1)
        if iso in NOT_COUNTRIES:
            continue
        sm = _SECTOR_RE.search(head)
        if (sm.group(1) if sm else "") != RESERVE_ASSET_SECTOR:
            continue
        sector = RESERVE_ASSET_SECTOR

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

            date = datetime(int(pm.group(1)), int(pm.group(2)), 1)
            candidates.setdefault((iso, date), {})[sector] = {
                "iso": iso,
                "date": date,
                "tonnes": round(tonnes, 2),
                "ounces": ounces,
                "sector": sector,
            }

    # One series per country-month by construction now, but collapsed anyway
    # and asserted: `ix_metric_country_date` is unique on (metric, country,
    # date), and a second row for one month is a constraint violation that the
    # pre-flush existence check cannot see. Production returned
    # `duplicate key ... (36, 4, 2015-02-01) already exists` when this function
    # returned both sector series (`F-0095`).
    out, duplicates = [], []
    for (iso, date), by_sector in candidates.items():
        if len(by_sector) > 1:
            duplicates.append(f"{iso}/{date:%Y-%m}: {sorted(by_sector)}")
        out.append(by_sector[sorted(by_sector)[0]])

    out.sort(key=lambda o: (o["iso"], o["date"]))
    return out, rejected, duplicates


def run_imf_gold_fetch(
    db: Session, start_period: str = "2015-01", min_countries: int = IMF_MIN_COUNTRIES,
) -> dict:
    """Import monthly gold holdings from IMF IRFCL into `GOLD_RESERVES`.

    Everything that can refuse the response - HTTP status, the contract, the
    coverage floor - runs before the first DB write.
    """
    started = datetime.utcnow()
    inserted = updated = skipped = 0

    try:
        xml = fetch_imf_gold(start_period)
        version = structure_version(xml)
        observations, rejected, duplicates = parse_imf_gold(xml)

        if not observations:
            raise ValueError("IMF response parsed to zero usable observations")

        parsed_countries = len({o["iso"] for o in observations})
        if parsed_countries < min_countries:
            raise ImfContractError(
                f"IMF IRFCL {version} coverage floor: {parsed_countries} "
                f"countries parsed, expected at least {min_countries} - a "
                f"truncated or partial publication. Nothing written."
            )

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

        status = "partial" if (rejected or duplicates) else "success"
        notes = []
        if rejected:
            notes.append(f"{len(rejected)} implausible: {', '.join(rejected[:5])}")
        if duplicates:
            notes.append(f"{len(duplicates)} duplicate keys: {', '.join(duplicates[:3])}")
        note = "; ".join(notes) or None
        logger.info(
            "IMF gold: %s - %d inserted, %d updated, %d skipped, %d countries, "
            "newest %s, %d rejected",
            status, inserted, updated, skipped, len(seen),
            newest.date() if newest else None, len(rejected),
        )
        if duplicates:
            logger.warning("IMF gold duplicate country-months: %s", duplicates[:5])

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
            "duplicates": duplicates,
            "structure_version": version,
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
