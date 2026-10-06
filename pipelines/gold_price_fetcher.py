"""Gold spot price — gold-api.com daily, World Bank Pink Sheet monthly fallback.

D-0094 re-rules D-0041. LBMA's ``prices.lbma.org.uk/json/gold_pm.json`` has
answered Cloudflare 403 since 2026-09-30; its own terms now require an IBA
licence. FRED deleted every IBA gold series in 2022. No US Government daily
spot source exists.

Primary (Matt, 2026-10-06): ``https://api.gold-api.com/price/XAU``. Spot
snapshot at the 02:30 UTC job, dated by the provider's ``updatedAt`` (UTC
date). A weekend read that returns Friday's price must not mint a Saturday
row. History is keyed and is not used — the Sep 30–Oct 5 gap stays empty.

Fallback: World Bank Pink Sheet monthly XLSX (``CMO-Historical-Data-Monthly``),
with attribution. Monthly cadence only; never invents daily values from a
monthly mean.

Phase A (same PR): fetch failures are classified via
``pipelines.fetch_failure`` so a block and a temporary outage stop looking
identical in UpdateLog.
"""
from __future__ import annotations

import io
import json
import logging
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional
from urllib.parse import urljoin, urlparse

from sqlalchemy.orm import Session

from database.models import Metric, TimeSeries, UpdateLog
from pipelines.fetch_failure import (
    ClassifiedFetchError,
    classify_fetch_error,
    format_failure,
)

logger = logging.getLogger(__name__)

PIPELINE_NAME = "Gold_Spot_Price"

# Primary — real-time spot, no key (D-0094 / gold-api.com terms §9).
PRIMARY_URL = "https://api.gold-api.com/price/XAU"
PRIMARY_HOST = "api.gold-api.com"

# Fallback — World Bank Pink Sheet monthly. The landing page is scraped for
# the current XLSX href because thedocs.worldbank.org paths change each release.
WB_LANDING_URL = "https://www.worldbank.org/en/research/commodity-markets"
WB_FALLBACK_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)
WB_ATTRIBUTION = (
    "World Bank Commodity Price Data (The Pink Sheet). "
    "https://www.worldbank.org/en/research/commodity-markets"
)

METRIC = {
    "code": "GOLD_SPOT_USD",
    "name": "Gold Spot Price (USD/oz)",
    "category": "gold",
    "unit": "USD/oz",
    "source": "gold-api.com; World Bank Pink Sheet (fallback)",
    "description": (
        "Spot gold, USD per troy ounce. Daily snapshot from gold-api.com at "
        "02:30 UTC (provider updatedAt date); World Bank Pink Sheet monthly "
        "average as fallback. Attribution: World Bank Commodity Price Data "
        "(The Pink Sheet)."
    ),
}

# USD per troy ounce. Wide on purpose: rejects a decimal-point error or a
# currency mix-up, not a market move.
PLAUSIBLE_RANGE = (100.0, 20000.0)

# Do not rewrite history. The series carries years of WGC/LBMA-sourced values.
DEFAULT_WRITE_WINDOW_DAYS = 400

# F-0050 pattern: an upstream stamp older than this is a parse failure, not a
# success with a stale date.
MAX_UPSTREAM_AGE_DAYS = 4

ERROR_FIELD_LIMIT = 480

_USER_AGENT = "Sentinel/2.0 (sovereign stress monitor)"


def _truncate(text):
    if text and len(text) > ERROR_FIELD_LIMIT:
        return text[: ERROR_FIELD_LIMIT - 3] + "..."
    return text


def _urlopen(url: str, timeout: float = 45):
    request = urllib.request.Request(
        url, headers={"User-Agent": _USER_AGENT}
    )
    return urllib.request.urlopen(request, timeout=timeout)


def _is_cloudflare_response(exc: urllib.error.HTTPError) -> bool:
    """Peek without depending on fetch_failure's internal helpers."""
    failure = classify_fetch_error(exc, url=getattr(exc, "url", None))
    return failure.cloudflare


def fetch_bytes(url: str, attempts: int = 3, backoff: float = 4.0) -> bytes:
    """GET bytes with retries. Cloudflare / non-429 4xx are not retried."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            with _urlopen(url) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            # Classify once — reading the body empties it — and wrap so the
            # caller does not re-classify a spent response.
            failure = classify_fetch_error(exc, url=url)
            wrapped = ClassifiedFetchError(failure, exc)
            if failure.kind == "blocked" or (
                failure.http_status is not None
                and 400 <= failure.http_status < 500
                and failure.http_status != 429
            ):
                raise wrapped from exc
            last_error = wrapped
        except ClassifiedFetchError:
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = ClassifiedFetchError(
                classify_fetch_error(exc, url=url), exc
            )

        if attempt < attempts:
            wait = backoff * (2 ** (attempt - 1))
            logger.warning(
                "Gold price attempt %d/%d failed (%s); retrying in %.0fs",
                attempt, attempts, last_error, wait,
            )
            time.sleep(wait)

    if isinstance(last_error, ClassifiedFetchError):
        raise last_error
    raise last_error


def fetch_gold_api_json(url: str = PRIMARY_URL) -> dict:
    """Fetch the gold-api.com real-time XAU payload."""
    raw = fetch_bytes(url)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"gold-api payload was not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(
            f"gold-api payload was {type(payload).__name__}, expected object"
        )
    return payload


def parse_gold_api(payload: dict, now: Optional[datetime] = None) -> dict:
    """Return ``{date: datetime, usd: Decimal, source: 'gold-api.com'}``.

    Observation date is the UTC date of ``updatedAt``, not the fetch time.
    An ``updatedAt`` older than ``MAX_UPSTREAM_AGE_DAYS`` is
    ``FETCH_PARSE stale_upstream`` (F-0050 pattern).
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    price = payload.get("price")
    updated_at = payload.get("updatedAt")
    if price is None:
        raise ValueError("gold-api payload missing price")
    if not updated_at:
        raise ValueError("gold-api payload missing updatedAt")

    try:
        # "2026-10-06T15:19:40Z"
        stamp = datetime.strptime(str(updated_at)[:19], "%Y-%m-%dT%H:%M:%S")
    except ValueError as exc:
        raise ValueError(f"gold-api updatedAt unparseable: {updated_at!r}") from exc

    age_days = (now - stamp).days
    if age_days > MAX_UPSTREAM_AGE_DAYS:
        raise ValueError(
            f"stale_upstream updatedAt={stamp.date().isoformat()} "
            f"age_days={age_days}"
        )

    try:
        usd = Decimal(str(price))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"gold-api price unparseable: {price!r}") from exc

    if not (PLAUSIBLE_RANGE[0] <= float(usd) <= PLAUSIBLE_RANGE[1]):
        raise ValueError(f"gold-api price out of plausible range: {usd}")

    # Date by provider stamp (UTC calendar day). A Friday stamp on Saturday
    # keeps Friday's row — we never mint a day the provider did not publish.
    when = datetime(stamp.year, stamp.month, stamp.day)
    return {"date": when, "usd": usd, "source": "gold-api.com"}


def resolve_world_bank_xlsx_url(landing_html: Optional[bytes] = None) -> str:
    """Find the current CMO-Historical-Data-Monthly.xlsx href, else fallback."""
    if landing_html is None:
        try:
            landing_html = fetch_bytes(WB_LANDING_URL, attempts=2, backoff=2.0)
        except Exception as exc:
            logger.warning(
                "World Bank landing fetch failed (%s); using pinned URL", exc
            )
            return WB_FALLBACK_URL

    try:
        text = landing_html.decode("utf-8", errors="replace")
    except Exception:
        return WB_FALLBACK_URL

    # Prefer absolute hrefs; accept relative.
    patterns = [
        r'href="(https://[^"]+CMO-Historical-Data-Monthly\.xlsx)"',
        r"href='(https://[^']+CMO-Historical-Data-Monthly\.xlsx)'",
        r'href="([^"]+CMO-Historical-Data-Monthly\.xlsx)"',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            href = m.group(1)
            if href.startswith("http"):
                return href
            return urljoin(WB_LANDING_URL, href)
    return WB_FALLBACK_URL


def parse_world_bank_monthly(xlsx_bytes: bytes) -> list:
    """Parse Pink Sheet monthly gold $/troy oz → [{date, usd}, ...], oldest first.

    Rows look like ``2026M09`` with Gold in the header row. Dated to the first
    of the data month (same convention as other monthly series).
    """
    try:
        import openpyxl
    except ImportError as exc:
        raise ValueError("openpyxl is required for World Bank Pink Sheet") from exc

    try:
        wb = openpyxl.load_workbook(
            io.BytesIO(xlsx_bytes), read_only=True, data_only=True
        )
    except Exception as exc:
        raise ValueError(f"World Bank xlsx unreadable: {exc}") from exc

    if "Monthly Prices" not in wb.sheetnames:
        raise ValueError(
            f"World Bank xlsx missing 'Monthly Prices' "
            f"(have {wb.sheetnames!r})"
        )
    ws = wb["Monthly Prices"]

    header = None
    gold_col = None
    out = []
    skipped = 0
    for i, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if i <= 4:
            continue
        if header is None:
            header = row
            for idx, cell in enumerate(header):
                if cell and "gold" in str(cell).lower():
                    gold_col = idx
                    break
            if gold_col is None:
                raise ValueError("World Bank Monthly Prices has no Gold column")
            continue

        raw_period = row[0] if row else None
        if not raw_period:
            skipped += 1
            continue
        period = str(raw_period).strip()
        m = re.match(r"^(\d{4})M(\d{2})$", period)
        if not m:
            skipped += 1
            continue
        year, month = int(m.group(1)), int(m.group(2))
        if not (1 <= month <= 12):
            skipped += 1
            continue
        try:
            when = datetime(year, month, 1)
        except ValueError:
            skipped += 1
            continue

        raw_val = row[gold_col] if gold_col < len(row) else None
        if raw_val is None or raw_val == "" or raw_val == "…":
            skipped += 1
            continue
        try:
            usd = Decimal(str(raw_val))
        except (InvalidOperation, ValueError):
            skipped += 1
            continue
        if not (PLAUSIBLE_RANGE[0] <= float(usd) <= PLAUSIBLE_RANGE[1]):
            logger.warning(
                "World Bank gold %s out of plausible range: %s", when.date(), usd
            )
            skipped += 1
            continue
        out.append({
            "date": when,
            "usd": usd,
            "source": "world-bank-pink-sheet",
        })

    if not out:
        raise ValueError(
            f"World Bank gold column yielded no usable rows ({skipped} skipped)"
        )
    out.sort(key=lambda r: r["date"])
    logger.info(
        "World Bank Pink Sheet: parsed %d gold rows, skipped %d (%s)",
        len(out), skipped, WB_ATTRIBUTION,
    )
    return out


def fetch_world_bank_monthly() -> list:
    url = resolve_world_bank_xlsx_url()
    # Host-only in logs.
    logger.info(
        "Gold price fallback: fetching World Bank Pink Sheet from host=%s",
        urlparse(url).hostname,
    )
    raw = fetch_bytes(url, attempts=2, backoff=3.0)
    return parse_world_bank_monthly(raw)



def _failure_of(exc: BaseException, url: str):
    if isinstance(exc, ClassifiedFetchError):
        return exc.failure
    return classify_fetch_error(exc, url=url)

def ensure_metric(db: Session) -> Metric:
    metric = db.query(Metric).filter_by(code=METRIC["code"]).first()
    if metric is None:
        metric = Metric(**METRIC)
        db.add(metric)
        db.commit()
        db.refresh(metric)
        logger.info("Created metric %s", METRIC["code"])
        return metric
    # Keep catalogue fields current when the source changes (D-0094).
    dirty = False
    for field in ("name", "source", "description", "unit", "category"):
        if getattr(metric, field) != METRIC[field]:
            setattr(metric, field, METRIC[field])
            dirty = True
    if dirty:
        db.commit()
        db.refresh(metric)
    return metric


def _upsert_rows(db: Session, metric: Metric, rows: list, cutoff: datetime):
    inserted = updated = 0
    latest_date = None
    for row in rows:
        if row["date"] < cutoff:
            continue
        existing = db.query(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id == None,  # noqa: E711
            TimeSeries.date == row["date"],
        ).first()
        if existing:
            if Decimal(str(existing.value)) != row["usd"]:
                existing.value = row["usd"]
                existing.updated_at = datetime.utcnow()
                updated += 1
        else:
            db.add(TimeSeries(
                metric_id=metric.id,
                country_id=None,
                date=row["date"],
                value=row["usd"],
            ))
            inserted += 1
        latest_date = (
            row["date"] if latest_date is None
            else max(latest_date, row["date"])
        )
    return inserted, updated, latest_date


def run_gold_price_fetch(
    db: Session,
    write_window_days: int = DEFAULT_WRITE_WINDOW_DAYS,
) -> dict:
    """Fetch gold spot: gold-api.com primary, World Bank monthly fallback."""
    started = datetime.utcnow()
    errors = []
    inserted = updated = 0
    latest_date = None
    used_source = None

    try:
        primary_error = None
        try:
            payload = fetch_gold_api_json()
            row = parse_gold_api(payload, now=started)
            cutoff = started - timedelta(days=write_window_days)
            metric = ensure_metric(db)
            inserted, updated, latest_date = _upsert_rows(
                db, metric, [row], cutoff
            )
            db.commit()
            used_source = "gold-api.com"
            status = "success"
        except Exception as primary_exc:
            primary_error = primary_exc
            failure = _failure_of(primary_exc, PRIMARY_URL)
            if failure.kind == "blocked":
                logger.error(
                    "FETCH_BLOCKED %s: %s", PIPELINE_NAME, failure.detail
                )
            elif failure.kind == "transient":
                logger.warning(
                    "FETCH_TRANSIENT %s: %s", PIPELINE_NAME, failure.detail
                )
            else:
                logger.warning(
                    "FETCH_%s %s: %s",
                    failure.kind.upper(), PIPELINE_NAME, failure.detail,
                )

            # Fallback — monthly, with attribution. Never invents the daily gap.
            logger.warning(
                "Gold primary failed (%s); trying World Bank Pink Sheet fallback. %s",
                failure.kind, WB_ATTRIBUTION,
            )
            try:
                rows = fetch_world_bank_monthly()
                cutoff = started - timedelta(days=write_window_days)
                metric = ensure_metric(db)
                inserted, updated, latest_date = _upsert_rows(
                    db, metric, rows, cutoff
                )
                db.commit()
                used_source = "world-bank-pink-sheet"
                # Partial: we stayed alive on monthly cadence after daily failed.
                status = "partial"
                logger.info(
                    "Gold price fallback succeeded via World Bank Pink Sheet "
                    "(%d inserted, %d updated). %s",
                    inserted, updated, WB_ATTRIBUTION,
                )
            except Exception as fb_exc:
                # Both failed — record the PRIMARY classification (the one that
                # matters for "blocked at source") and raise.
                db.rollback()
                human = f"{METRIC['code']}: {primary_exc}"
                msg = format_failure(failure, human)
                # Also note fallback failure kind, redacted.
                fb_failure = _failure_of(fb_exc, WB_FALLBACK_URL)
                msg = _truncate(
                    f"{msg} ; fallback={fb_failure.kind}:{fb_failure.detail}"
                )
                errors.append(msg)
                if failure.kind == "blocked":
                    logger.error("FETCH_BLOCKED %s: %s", PIPELINE_NAME, msg)
                else:
                    logger.error("Gold price fetch failed: %s", msg)
                status = "failed"

        if status != "failed" and primary_error is None:
            pass  # success path already committed
        elif status == "failed":
            pass
        # partial path already committed

    except Exception as exc:
        # Unexpected outer failure
        db.rollback()
        failure = _failure_of(exc, PRIMARY_URL)
        msg = format_failure(failure, f"{METRIC['code']}: {exc}")
        errors.append(msg)
        if failure.kind == "blocked":
            logger.error("FETCH_BLOCKED %s: %s", PIPELINE_NAME, msg)
        else:
            logger.error("Gold price fetch failed: %s", msg)
        status = "failed"

    # When primary succeeded we have no errors; when both failed, errors set.
    # When fallback saved us, leave a note in error_message so the log shows
    # the primary miss without marking the run failed.
    error_message = None
    if status == "failed":
        error_message = _truncate("; ".join(errors)) if errors else None
    elif status == "partial" and primary_error is not None:
        failure = _failure_of(primary_error, PRIMARY_URL)
        error_message = _truncate(
            format_failure(
                failure,
                f"primary failed; served by World Bank Pink Sheet. {WB_ATTRIBUTION}",
            )
        )

    db.add(UpdateLog(
        pipeline_name=PIPELINE_NAME,
        status=status,
        records_inserted=inserted,
        records_updated=updated,
        error_message=error_message,
        started_at=started,
        completed_at=datetime.utcnow(),
    ))
    db.commit()

    result = {
        "status": status,
        "inserted": inserted,
        "updated": updated,
        "errors": errors,
        "latest_date": latest_date.date().isoformat() if latest_date else None,
        "series": METRIC["code"],
        "source": used_source,
        "attribution": WB_ATTRIBUTION if used_source == "world-bank-pink-sheet" else None,
    }
    if status == "failed":
        raise RuntimeError(f"Gold price fetch failed: {errors}")
    return result


# --- Back-compat aliases (tests / callers that still name the LBMA helpers) ---
SOURCE_URL = PRIMARY_URL  # D-0094: was LBMA


def fetch_lbma_json(url: str = PRIMARY_URL, attempts: int = 3,
                    backoff: float = 4.0) -> dict:
    """Deprecated name — fetches the primary gold-api payload."""
    raw = fetch_bytes(url, attempts=attempts, backoff=backoff)
    return json.loads(raw.decode("utf-8"))


def parse_lbma_json(payload):
    """Deprecated name — if given a gold-api dict, parse it; lists rejected."""
    if isinstance(payload, dict):
        row = parse_gold_api(payload)
        return [row]
    raise ValueError(
        f"LBMA list payload is no longer accepted (D-0094); "
        f"got {type(payload).__name__}"
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from database.connection import get_session

    session = get_session()
    try:
        print(run_gold_price_fetch(session))
    finally:
        session.close()
