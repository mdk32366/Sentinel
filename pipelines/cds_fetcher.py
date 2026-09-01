"""
Sovereign CDS pipeline — World Government Bonds 5Y conventional/par spreads.

One POST to the WGB board JSON endpoint returns every name. We parse the 5Y
column's structured `sorttable_customkey` (not a regex over the whole page),
so the ISDA running coupon (25/100/500/1000) is not mistaken for the spread.
10Y is only stored/shown when it comes from this same source on the same as-of
date; WGB's 5Y board has no paired 10Y, so term structure stays blank.
"""

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from database.models import Metric, TimeSeries, UpdateLog

logger = logging.getLogger(__name__)


# ============================================================
# CDS INSTRUMENTS (5Y conventional spread)
# ============================================================
CDS_INSTRUMENTS = {
    "France": {"5Y": {"code": "FRANCE_CDS_5Y"}},
    "Germany": {"5Y": {"code": "GERMANY_CDS_5Y"}},
    "Greece": {"5Y": {"code": "GREECE_CDS_5Y"}},
    "Italy": {"5Y": {"code": "ITALY_CDS_5Y"}},
    "Spain": {"5Y": {"code": "SPAIN_CDS_5Y"}},
    "Switzerland": {"5Y": {"code": "SWITZERLAND_CDS_5Y"}},
    "Russia": {"5Y": {"code": "RUSSIA_CDS_5Y"}},
    "Turkey": {"5Y": {"code": "TURKEY_CDS_5Y"}},
    "Saudi Arabia": {"5Y": {"code": "SAUDI_ARABIA_CDS_5Y"}},
    "Egypt": {"5Y": {"code": "EGYPT_CDS_5Y"}},
    "China": {"5Y": {"code": "CHINA_CDS_5Y"}},
    "Japan": {"5Y": {"code": "JAPAN_CDS_5Y"}},
    "South Korea": {"5Y": {"code": "SOUTH_KOREA_CDS_5Y"}},
    "India": {"5Y": {"code": "INDIA_CDS_5Y"}},
    "Indonesia": {"5Y": {"code": "INDONESIA_CDS_5Y"}},
    "United States": {"5Y": {"code": "UNITED_STATES_CDS_5Y"}},
    "Canada": {"5Y": {"code": "CANADA_CDS_5Y"}},
    "Mexico": {"5Y": {"code": "MEXICO_CDS_5Y"}},
    "Brazil": {"5Y": {"code": "BRAZIL_CDS_5Y"}},
    "Australia": {"5Y": {"code": "AUSTRALIA_CDS_5Y"}},
    "South Africa": {"5Y": {"code": "SOUTH_AFRICA_CDS_5Y"}},
}


CDS_PIPELINE_NAME = "CDS_MultiTenor"
CDS_ERROR_TRUNCATE = 500
CDS_SOURCE = "World Government Bonds"
CDS_SOURCE_URL = "https://www.worldgovernmentbonds.com/sovereign-cds/"
WGB_CDS_MAIN_URL = "https://www.worldgovernmentbonds.com/wp-json/cds/v1/main"

# Real IG prints can be single-digit bps. Distressed names can exceed 10,000.
CDS_MIN_BPS = Decimal("0.01")
CDS_MAX_BPS = Decimal("50000")
# ISDA standard running coupons — never use these as a floor/ceiling filter,
# but a whole board collapsing to one of them is a parse failure, not a market.
ISDA_RUNNING_COUPONS = frozenset({Decimal("25"), Decimal("100"), Decimal("500"), Decimal("1000")})

_HEADER_COUNTRY = re.compile(r"country", re.I)
_HEADER_5Y = re.compile(r"5\s*y(?:ear)?s?\s*cds|5\s*years?\s*credit\s*default", re.I)
_HEADER_DATE = re.compile(r"^date$", re.I)
_ISO_DATE = re.compile(r"(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class CdsQuote:
    country: str
    spread_bps: Decimal
    as_of: date
    tenor: str = "5Y"
    source: str = CDS_SOURCE


def cds_instrument_codes() -> List[str]:
    """All configured CDS metric codes (5Y conventional spread)."""
    codes: List[str] = []
    for tenors in CDS_INSTRUMENTS.values():
        for info in tenors.values():
            codes.append(info["code"])
    return codes


def cds_country_for_code(code: str) -> str:
    """Human country name for a metric code, else a cleaned prefix."""
    for name, tenors in CDS_INSTRUMENTS.items():
        for info in tenors.values():
            if info["code"] == code:
                return name
    prefix = code.replace("_CDS_5Y", "").replace("_CDS_10Y", "")
    return prefix.replace("_", " ").title()


def cds_fetch_status(attempted: int, ok: int) -> str:
    """Pipeline status: failed if every attempt missed, partial if mixed, else success."""
    if attempted > 0 and ok == 0:
        return "failed"
    if ok < attempted:
        return "partial"
    return "success"


def _truncate_error(message: Optional[str], limit: int = CDS_ERROR_TRUNCATE) -> Optional[str]:
    if not message:
        return None
    if len(message) <= limit:
        return message
    if limit <= 3:
        return message[:limit]
    return message[: limit - 3] + "..."


def get_cds_coverage(db: Session, error_truncate: int = CDS_ERROR_TRUNCATE) -> dict:
    """Coverage of configured CDS instruments vs latest TimeSeries points."""
    codes = cds_instrument_codes()
    configured = len(codes)

    metrics = {
        m.code: m
        for m in db.query(Metric).filter(Metric.code.in_(codes)).all()
    } if codes else {}
    metric_ids = [m.id for m in metrics.values()]

    have_data_ids = set()
    if metric_ids:
        latest_rows = db.query(TimeSeries.metric_id).filter(
            TimeSeries.metric_id.in_(metric_ids),
        ).distinct().all()
        have_data_ids = {row[0] for row in latest_rows}

    missing_codes = []
    with_data = 0
    for code in codes:
        metric = metrics.get(code)
        if metric is not None and metric.id in have_data_ids:
            with_data += 1
        else:
            missing_codes.append(code)

    log = (
        db.query(UpdateLog)
        .filter_by(pipeline_name=CDS_PIPELINE_NAME)
        .order_by(UpdateLog.completed_at.desc())
        .first()
    )
    last_pipeline = None
    if log:
        last_pipeline = {
            "status": log.status,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "inserted": log.records_inserted,
            "updated": log.records_updated,
            "error_message": _truncate_error(log.error_message, error_truncate),
        }

    return {
        "configured": configured,
        "with_data": with_data,
        "without_data": configured - with_data,
        "missing_codes": missing_codes,
        "last_pipeline": last_pipeline,
    }


def ensure_metric(db: Session, code: str, name: str, description: str = "") -> Metric:
    metric = db.query(Metric).filter_by(code=code).first()
    if not metric:
        metric = Metric(
            code=code,
            name=name,
            category="sovereign_cds",
            unit="bps",
            source=CDS_SOURCE,
            description=description,
        )
        db.add(metric)
        db.commit()
        logger.info(f"Created CDS metric: {code}")
        return metric
    changed = False
    if metric.source != CDS_SOURCE:
        metric.source = CDS_SOURCE
        changed = True
    if description and metric.description != description:
        metric.description = description
        changed = True
    if changed:
        db.commit()
    return metric


def _parse_bps(raw) -> Optional[Decimal]:
    if raw is None:
        return None
    text = str(raw).strip().replace(",", "").replace("\xa0", " ")
    text = text.replace("bps", "").replace("bp", "").strip()
    if not text:
        return None
    try:
        val = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if val.is_nan() or val.is_infinite():
        return None
    if not (CDS_MIN_BPS <= val <= CDS_MAX_BPS):
        return None
    return val


def _parse_as_of(raw) -> Optional[date]:
    if raw is None:
        return None
    if isinstance(raw, date) and not isinstance(raw, datetime):
        return raw
    if isinstance(raw, datetime):
        return raw.date()
    text = str(raw).strip()
    match = _ISO_DATE.search(text)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _cell_key(cell) -> str:
    if cell is None:
        return ""
    key = cell.get("sorttable_customkey")
    if key is not None and str(key).strip():
        return str(key).strip()
    return cell.get_text(" ", strip=True)


def _header_labels(table) -> List[str]:
    """Flatten the last header row; fall back to first row of th cells."""
    thead = table.find("thead")
    rows = thead.find_all("tr") if thead else table.find_all("tr")[:2]
    if not rows:
        return []
    last = rows[-1]
    return [th.get_text(" ", strip=True) for th in last.find_all("th")]


def _column_index(labels: List[str], pattern: re.Pattern, default: Optional[int] = None) -> Optional[int]:
    for i, label in enumerate(labels):
        if pattern.search(label or ""):
            return i
    return default


def parse_wgb_cds_table(html: str) -> List[CdsQuote]:
    """
    Extract 5Y conventional/par spreads from a WGB board table.

    Reads the 5Y CDS and Date columns' `sorttable_customkey` attributes — the
    structured fields the page already uses for sorting — not a scan of every
    number on the page (which includes the ISDA coupon).
    """
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table")
    if table is None:
        return []

    labels = _header_labels(table)
    country_idx = _column_index(labels, _HEADER_COUNTRY, default=1)
    cds5_idx = _column_index(labels, _HEADER_5Y, default=3)
    date_idx = _column_index(labels, _HEADER_DATE, default=len(labels) - 1 if labels else None)
    if country_idx is None or cds5_idx is None or date_idx is None:
        logger.warning("WGB CDS table: could not identify Country / 5Y CDS / Date columns")
        return []

    tbody = table.find("tbody") or table
    quotes: List[CdsQuote] = []
    seen = set()
    for row in tbody.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) <= max(country_idx, cds5_idx, date_idx):
            continue
        country = _cell_key(cells[country_idx])
        spread = _parse_bps(_cell_key(cells[cds5_idx]))
        as_of = _parse_as_of(_cell_key(cells[date_idx]))
        if not country or spread is None or as_of is None:
            continue
        key = country.casefold()
        if key in seen:
            continue
        seen.add(key)
        quotes.append(CdsQuote(country=country, spread_bps=spread, as_of=as_of))
    return quotes


def parse_wgb_cds_payload(payload) -> List[CdsQuote]:
    """Accept the WGB JSON envelope `{success, table}` or a raw table HTML string."""
    if payload is None:
        return []
    if isinstance(payload, str):
        return parse_wgb_cds_table(payload)
    if isinstance(payload, dict):
        table = payload.get("table")
        if isinstance(table, str):
            return parse_wgb_cds_table(table)
    return []


def board_looks_like_coupon_collapse(quotes: List[CdsQuote], min_names: int = 5) -> bool:
    """True when many names share one ISDA coupon — the old Investing.com failure mode."""
    if len(quotes) < min_names:
        return False
    values = {q.spread_bps for q in quotes}
    return len(values) == 1 and next(iter(values)) in ISDA_RUNNING_COUPONS


def fetch_wgb_cds_board(timeout: int = 20) -> dict:
    """POST the WGB sovereign-CDS board endpoint (same call the public page makes)."""
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Origin": "https://www.worldgovernmentbonds.com",
        "Referer": CDS_SOURCE_URL,
        "Content-Type": "application/json; charset=UTF-8",
    }
    resp = requests.post(
        WGB_CDS_MAIN_URL,
        headers=headers,
        json={"DUMMY": None},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, dict):
        raise ValueError("WGB CDS board did not return a JSON object")
    return data


def _as_of_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def latest_cds_observation(db: Session, code: str) -> Optional[dict]:
    """Latest TimeSeries point for a CDS metric, with as-of date and metric source."""
    metric = db.query(Metric).filter_by(code=code).first()
    if not metric:
        return None
    row = (
        db.query(TimeSeries)
        .filter(TimeSeries.metric_id == metric.id, TimeSeries.country_id == None)
        .order_by(TimeSeries.date.desc())
        .first()
    )
    if not row:
        return None
    return {
        "value": float(row.value),
        "date": _as_of_date(row.date),
        "source": metric.source,
        "code": code,
    }


def pair_cds_tenors(
    obs_5y: Optional[dict],
    obs_10y: Optional[dict],
) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """
    5Y always wins when present. 10Y and 10Y−5Y only when both points share
    the same source and the same as-of date. Do not mix a live 5Y with a stale 10Y.
    """
    if not obs_5y:
        return None, None, None
    cds5 = obs_5y["value"]
    if not obs_10y:
        return cds5, None, None
    same_source = (obs_5y.get("source") or "") == (obs_10y.get("source") or "")
    same_as_of = obs_5y.get("date") is not None and obs_5y.get("date") == obs_10y.get("date")
    if not (same_source and same_as_of):
        return cds5, None, None
    cds10 = obs_10y["value"]
    return cds5, cds10, round(cds10 - cds5, 1)


def _quotes_by_country(quotes: List[CdsQuote]) -> Dict[str, CdsQuote]:
    return {q.country.casefold(): q for q in quotes}


def run_cds_fetch(db: Session) -> dict:
    start_time = datetime.utcnow()
    total_inserted = 0
    total_updated = 0
    attempted = 0
    ok = 0
    errors = []
    as_of_seen: Optional[date] = None

    try:
        payload = fetch_wgb_cds_board()
        quotes = parse_wgb_cds_payload(payload)
    except Exception as e:
        logger.error(f"WGB CDS board fetch failed: {e}", exc_info=True)
        quotes = []
        errors.append(f"board fetch: {e}")

    if quotes and board_looks_like_coupon_collapse(quotes):
        logger.error(
            "WGB CDS board collapsed to a single ISDA coupon (%s) — refusing to persist",
            quotes[0].spread_bps,
        )
        errors.append(f"coupon-collapse: all {len(quotes)} names at {quotes[0].spread_bps}")
        quotes = []

    by_country = _quotes_by_country(quotes)
    if quotes:
        as_of_seen = quotes[0].as_of
        logger.info(
            "CDS board source=%s as-of=%s names=%s url=%s",
            CDS_SOURCE,
            as_of_seen.isoformat(),
            len(quotes),
            CDS_SOURCE_URL,
        )

    for country, tenors in CDS_INSTRUMENTS.items():
        info = tenors["5Y"]
        attempted += 1
        metric_name = info["code"]
        try:
            quote = by_country.get(country.casefold())
            if quote is None:
                errors.append(f"{metric_name}: not on {CDS_SOURCE} 5Y board")
                continue

            metric = ensure_metric(
                db,
                code=metric_name,
                name=f"{country} 5Y CDS Spread",
                description=(
                    f"{country} 5Y sovereign CDS conventional/par spread from "
                    f"{CDS_SOURCE} (not the ISDA running coupon)"
                ),
            )

            as_of_dt = datetime.combine(quote.as_of, datetime.min.time())
            existing = db.query(TimeSeries).filter(
                TimeSeries.metric_id == metric.id,
                TimeSeries.date == as_of_dt,
                TimeSeries.country_id == None,
            ).first()

            if existing:
                existing.value = quote.spread_bps
                existing.updated_at = datetime.utcnow()
                total_updated += 1
            else:
                db.add(TimeSeries(
                    metric_id=metric.id,
                    country_id=None,
                    date=as_of_dt,
                    value=quote.spread_bps,
                ))
                total_inserted += 1

            db.commit()
            ok += 1
            logger.info(
                "CDS %s: %s bps source=%s as-of=%s",
                metric_name,
                quote.spread_bps,
                quote.source,
                quote.as_of.isoformat(),
            )
        except Exception as e:
            logger.error(f"Error processing {country} 5Y: {e}")
            errors.append(f"{country} 5Y: {str(e)}")

    status = cds_fetch_status(attempted, ok)

    db.add(UpdateLog(
        pipeline_name=CDS_PIPELINE_NAME,
        status=status,
        records_inserted=total_inserted,
        records_updated=total_updated,
        error_message=_truncate_error("; ".join(errors) if errors else None),
        started_at=start_time,
        completed_at=datetime.utcnow(),
    ))
    db.commit()

    return {
        "status": status,
        "inserted": total_inserted,
        "updated": total_updated,
        "attempted": attempted,
        "ok": ok,
        "errors": errors,
        "source": CDS_SOURCE,
        "as_of": as_of_seen.isoformat() if as_of_seen else None,
        "source_url": CDS_SOURCE_URL,
    }
