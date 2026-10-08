"""
Treasury Auction Results — Fiscal Data `auctions_query`
=======================================================
Demand at US Treasury auctions: how much was bid against what was sold, and
who took it. Treasury always sells the full offering, so "sold" and "bought"
are equal by construction; the signal is the cover and the bidder mix.

SOURCE (D-0098)
    https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/
        accounting/od/auctions_query
    Public, no key, paginated JSON. Amounts are whole dollars. Nulls are the
    string "null"; an absent key or empty string is treated the same way so a
    change of encoding can never turn into a zero.

THE LOAD-BEARING RULE (ORDER auction-demand §2, A-0025)
    `total_tendered` / `total_accepted` INCLUDE the Fed's SOMA add-on.
    Treasury's published bid-to-cover excludes it. So:

        b2c_recomputed = (total_tendered - soma_tendered)
                       / (total_accepted - soma_accepted)

    and it is compared to the reported figure on every row. A ratio of the raw
    totals is well-formed, plausible and wrong (2.62 against a true 2.76 for
    the 26-week bill of 2026-06-15). Where SOMA was not reported the recompute
    is NULL, not "SOMA = 0".

    Disagreement beyond 0.01 stores both values, flags `mismatch`, and puts
    the auction in the run's ANOMALIES line, which the watchdog surfaces
    (D-0046). Nothing is silently chosen.

ABSENT IS A CATEGORY (§3)
    Every NULL column has a reason in `null_reasons`. A share with a missing
    input is NULL. Bidder shares that do not sum to 1 are stored and flagged
    `gap` (D-0104, F-0111), never forced.

SCHEDULE
    Weekdays 22:00 UTC, after the day's auctions close and results publish.
    The first run backfills from 2008-01-01 (D-0100); later runs re-read the
    trailing 30 days so a revised result is picked up.
"""
import argparse
import datetime
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from decimal import Decimal, InvalidOperation

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import TreasuryAuction, UpdateLog
from pipelines.fetch_failure import classify_fetch_error, format_failure

logger = logging.getLogger(__name__)

PIPELINE_NAME = "Treasury_Auctions"
SOURCE_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/"
    "accounting/od/auctions_query"
)
BACKFILL_START = datetime.date(2008, 1, 1)  # D-0100
REREAD_DAYS = 30
PAGE_SIZE = 10000
B2C_TOLERANCE = Decimal("0.01")      # §2
SHARE_TOLERANCE = Decimal("0.000001")  # §1, ±1e-6
ERROR_FIELD_LIMIT = 480              # update_logs.error_message is varchar(500)
ANOMALY_MARKER = "ANOMALIES:"        # read by freshness_watchdog (D-0046)

USER_AGENT = os.getenv(
    "TREASURY_USER_AGENT",
    "Sentinel/2.0 (sovereign stress monitor; contact: admin)",
)

AMOUNT_FIELDS = (
    "offering_amt", "total_tendered", "total_accepted", "soma_tendered",
    "soma_accepted", "comp_tendered", "comp_accepted", "noncomp_accepted",
    "fima_noncomp_tendered", "fima_noncomp_accepted",
    "primary_dealer_tendered", "primary_dealer_accepted",
    "direct_bidder_tendered", "direct_bidder_accepted",
    "indirect_bidder_tendered", "indirect_bidder_accepted",
)
# Model column -> source field, where the names differ.
RATE_FIELDS = {
    "high_yield": "high_yield",
    "high_discnt_rate": "high_discnt_rate",
    "high_investment_rate": "high_investment_rate",
    "allocation_pct": "allocation_pctage",
    "b2c_reported": "bid_to_cover_ratio",
}
# All null means the auction is announced but not yet held.
RESULT_FIELDS = ("total_tendered", "total_accepted", "bid_to_cover_ratio")
SHARE_FIELDS = {
    "primary_dealer_share": "primary_dealer_accepted",
    "direct_bidder_share": "direct_bidder_accepted",
    "indirect_bidder_share": "indirect_bidder_accepted",
}


# ─────────────────────────────────────────────────────────────────────────────
# Parse
# ─────────────────────────────────────────────────────────────────────────────

def _null_reason(raw):
    if raw is None:
        return "absent"
    if isinstance(raw, str) and raw.strip() == "":
        return "empty"
    if isinstance(raw, str) and raw.strip().lower() == "null":
        return "source_null"
    return None


def _decimal(rec: dict, field: str, reasons: dict, column: str = None):
    raw = rec.get(field)
    reason = _null_reason(raw)
    if reason is None:
        try:
            return Decimal(str(raw).replace(",", "").strip())
        except InvalidOperation:
            reason = "unparseable"
    reasons[column or field] = reason
    return None


def _date(rec: dict, field: str, reasons: dict):
    raw = rec.get(field)
    reason = _null_reason(raw)
    if reason is None:
        try:
            return datetime.date.fromisoformat(raw.strip())
        except ValueError:
            reason = "unparseable"
    reasons[field] = reason
    return None


def _flag(rec: dict, field: str):
    raw = (rec.get(field) or "").strip().lower()
    return True if raw == "yes" else False if raw == "no" else None


def _text(rec: dict, field: str):
    raw = rec.get(field)
    return None if _null_reason(raw) else raw.strip()


def term_group(security_type, security_term, original_term, *, tips, frn, cmb):
    """D-0103. Returns (group, reason). Group None means never charted."""
    if cmb:
        return None, "cash_management_bill"
    if tips:
        return None, "tips"
    if frn:
        return None, "frn"
    if security_type == "Bill":
        return security_term, None
    if security_type in ("Note", "Bond"):
        return original_term or security_term, None
    return None, "unknown_security_type"


def is_pending(rec: dict) -> bool:
    return all(_null_reason(rec.get(f)) for f in RESULT_FIELDS)


def parse_record(rec: dict):
    """One source record -> a row dict for TreasuryAuction, or None if pending.

    Every column the model has is present in the result. `null_reasons` is a
    dict here and JSON text once stored.
    """
    if is_pending(rec):
        return None

    reasons = {}
    row = {
        "cusip": rec["cusip"].strip(),
        "auction_date": _date(rec, "auction_date", reasons),
        "issue_date": _date(rec, "issue_date", reasons),
        "maturity_date": _date(rec, "maturity_date", reasons),
        "source_record_date": _date(rec, "record_date", reasons),
        "security_type": _text(rec, "security_type"),
        "security_term": _text(rec, "security_term"),
        "original_security_term": _text(rec, "original_security_term"),
        "reopening": _flag(rec, "reopening"),
        "inflation_indexed": _flag(rec, "inflation_index_security"),
        "floating_rate": _flag(rec, "floating_rate"),
        "cash_management_bill": _flag(rec, "cash_management_bill_cmb"),
    }
    for field in AMOUNT_FIELDS:
        row[field] = _decimal(rec, field, reasons)
    for column, field in RATE_FIELDS.items():
        row[column] = _decimal(rec, field, reasons, column)

    group, why = term_group(
        row["security_type"], row["security_term"], row["original_security_term"],
        tips=row["inflation_indexed"], frn=row["floating_rate"],
        cmb=row["cash_management_bill"],
    )
    row["term_group"] = group
    if why:
        reasons["term_group"] = why

    _bid_to_cover(row, reasons)
    _identity(row)
    _shares(row, reasons)

    row["null_reasons"] = reasons
    row["raw"] = json.dumps(rec, sort_keys=True)
    return row


def _bid_to_cover(row: dict, reasons: dict):
    tt, ta = row["total_tendered"], row["total_accepted"]
    st, sa = row["soma_tendered"], row["soma_accepted"]
    recomputed, why = None, None
    if tt is None or ta is None:
        why = "totals_not_reported"
    elif st is None or sa is None:
        why = "soma_not_reported"
    elif ta - sa <= 0:
        why = "zero_accepted"
    else:
        recomputed = (tt - st) / (ta - sa)
    row["b2c_recomputed"] = recomputed
    if why:
        reasons["b2c_recomputed"] = why

    reported = row["b2c_reported"]
    if recomputed is None or reported is None:
        row["b2c_check"] = "unverifiable"
        reasons["b2c_check"] = why or "reported_missing"
    elif abs(recomputed - reported) <= B2C_TOLERANCE:
        row["b2c_check"] = "ok"
    else:
        row["b2c_check"] = "mismatch"


def _identity(row: dict):
    """A-0025: total - SOMA == competitive + non-competitive + FIMA, tendered."""
    parts = [row[f] for f in ("total_tendered", "soma_tendered", "comp_tendered",
                              "noncomp_accepted", "fima_noncomp_tendered")]
    if any(p is None for p in parts):
        row["identity_check"] = "unverifiable"
        return
    tt, st, ct, na, fn = parts
    row["identity_check"] = "ok" if tt - st == ct + na + fn else "fail"


def _shares(row: dict, reasons: dict):
    comp = row["comp_accepted"]
    classes = [row[f] for f in SHARE_FIELDS.values()]
    if comp is None or any(c is None for c in classes):
        why = "input_missing"
    elif comp <= 0:
        why = "zero_denominator"
    else:
        why = None

    if why:
        for share in SHARE_FIELDS:
            row[share] = None
            reasons[share] = why
        row["shares_check"] = "unverifiable"
        row["bidder_gap"] = None
        reasons["bidder_gap"] = why
        return

    for share, field in SHARE_FIELDS.items():
        row[share] = row[field] / comp
    row["bidder_gap"] = comp - sum(classes)
    total = sum(row[s] for s in SHARE_FIELDS)
    row["shares_check"] = "ok" if abs(total - 1) <= SHARE_TOLERANCE else "gap"


# ─────────────────────────────────────────────────────────────────────────────
# Persist
# ─────────────────────────────────────────────────────────────────────────────

def _label(row) -> str:
    return f"{row['cusip']} {row['auction_date']} {row['security_term']}"


def ingest_records(db: Session, records) -> dict:
    """Idempotent upsert on (cusip, auction_date). A record whose raw source is
    unchanged is left alone, so re-running a backfill writes nothing."""
    summary = {
        "inserted": 0, "updated": 0, "unchanged": 0, "pending": 0,
        "mismatches": [], "unverifiable": 0, "share_gaps": [],
        "identity_failures": [], "latest_date": None,
    }
    parsed = {}
    for rec in records:
        row = parse_record(rec)
        if row is None:
            summary["pending"] += 1
            continue
        parsed[(row["cusip"], row["auction_date"])] = row

    if parsed:
        oldest = min(d for _, d in parsed)
        existing = {
            (a.cusip, a.auction_date): a
            for a in db.query(TreasuryAuction)
            .filter(TreasuryAuction.auction_date >= oldest).all()
        }
    else:
        existing = {}

    for key, row in parsed.items():
        values = dict(row, null_reasons=json.dumps(row["null_reasons"], sort_keys=True))
        current = existing.get(key)
        if current is None:
            db.add(TreasuryAuction(**values))
            summary["inserted"] += 1
        elif current.raw != values["raw"]:
            for column, value in values.items():
                setattr(current, column, value)
            summary["updated"] += 1
        else:
            summary["unchanged"] += 1

        if row["b2c_check"] == "mismatch":
            summary["mismatches"].append(
                f"{_label(row)}: b2c reported {row['b2c_reported']} "
                f"recomputed {row['b2c_recomputed']:.4f}"
            )
        elif row["b2c_check"] == "unverifiable":
            summary["unverifiable"] += 1
        if row["shares_check"] == "gap":
            summary["share_gaps"].append(f"{_label(row)}: bidder gap {row['bidder_gap']}")
        if row["identity_check"] == "fail":
            summary["identity_failures"].append(f"{_label(row)}: total-SOMA != comp+noncomp+FIMA")
        if summary["latest_date"] is None or key[1] > summary["latest_date"]:
            summary["latest_date"] = key[1]

    db.commit()
    for line in summary["mismatches"]:
        logger.warning("Auction bid-to-cover mismatch: %s", line)
    for line in summary["share_gaps"]:
        logger.info("Auction bidder shares do not sum to 1: %s", line)
    for line in summary["identity_failures"]:
        logger.warning("Auction A-0025 identity failed: %s", line)
    return summary


# ─────────────────────────────────────────────────────────────────────────────
# Fetch
# ─────────────────────────────────────────────────────────────────────────────

def _url(start: datetime.date, cusip, page: int) -> str:
    filters = [f"auction_date:gte:{start.isoformat()}"]
    if cusip:
        filters.append(f"cusip:eq:{cusip}")
    query = urllib.parse.urlencode({
        "filter": ",".join(filters),
        "sort": "auction_date",
        "page[size]": PAGE_SIZE,
        "page[number]": page,
    })
    return f"{SOURCE_URL}?{query}"


def _get_json(url: str, retries: int = 3, backoff: float = 4.0) -> dict:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            if "data" not in body or "meta" not in body:
                raise ValueError(f"unexpected response shape: {list(body)[:5]}")
            return body
        except urllib.error.HTTPError as e:
            if e.code < 500 and e.code != 429:
                raise
            if attempt == retries - 1:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries - 1:
                raise
        time.sleep(backoff * (2 ** attempt))


def fetch_records(start: datetime.date, cusip: str = None) -> list:
    """Every auction record with auction_date >= start, all pages."""
    records, page = [], 1
    while True:
        body = _get_json(_url(start, cusip, page))
        records.extend(body["data"])
        if page >= int(body["meta"].get("total-pages") or 1):
            return records
        page += 1


# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────

def default_start(db: Session) -> datetime.date:
    latest = db.query(func.max(TreasuryAuction.auction_date)).scalar()
    if latest is None:
        return BACKFILL_START
    return latest - datetime.timedelta(days=REREAD_DAYS)


def run_treasury_auctions_fetch(db: Session, start: datetime.date = None,
                                fetch=None) -> dict:
    """Entry point. Signature matches the other pipelines: run_*_fetch(db)."""
    started = datetime.datetime.utcnow()
    fetch = fetch or fetch_records
    start = start or default_start(db)

    try:
        records = fetch(start)
    except Exception as e:
        failure = classify_fetch_error(e, url=SOURCE_URL)
        msg = format_failure(failure, f"auctions fetch from {start}: {e}")
        logger.error("Treasury auctions fetch failed: %s", msg)
        db.add(UpdateLog(
            pipeline_name=PIPELINE_NAME, status="failed",
            records_inserted=0, records_updated=0, error_message=msg,
            started_at=started, completed_at=datetime.datetime.utcnow(),
        ))
        db.commit()
        return {"status": "failed", "start": start.isoformat(), "inserted": 0,
                "updated": 0, "mismatches": [], "error": msg}

    summary = ingest_records(db, records)

    notes = []
    anomalies = summary["mismatches"] + summary["identity_failures"]
    if anomalies:
        notes.append(f"{ANOMALY_MARKER} " + "; ".join(anomalies))
    if summary["share_gaps"]:
        notes.append("share gaps: " + "; ".join(summary["share_gaps"]))
    if summary["pending"]:
        notes.append(f"pending {summary['pending']}")
    message = " | ".join(notes)[:ERROR_FIELD_LIMIT] if notes else None

    db.add(UpdateLog(
        pipeline_name=PIPELINE_NAME, status="success",
        records_inserted=summary["inserted"], records_updated=summary["updated"],
        error_message=message,
        started_at=started, completed_at=datetime.datetime.utcnow(),
    ))
    db.commit()

    latest = summary["latest_date"]
    logger.info(
        "Treasury auctions from %s: %d inserted, %d updated, %d unchanged, "
        "%d pending, %d mismatches, %d unverifiable, latest=%s",
        start, summary["inserted"], summary["updated"], summary["unchanged"],
        summary["pending"], len(summary["mismatches"]), summary["unverifiable"],
        latest,
    )
    return dict(
        summary, status="success", start=start.isoformat(),
        latest_date=latest.isoformat() if latest else None,
    )


def null_count_report(db: Session) -> Counter:
    """§3. NULL counts keyed by (security_type, decade, field), from what is
    stored. Measured, not asserted from memory."""
    counts = Counter()
    for security_type, auction_date, reasons in db.query(
        TreasuryAuction.security_type, TreasuryAuction.auction_date,
        TreasuryAuction.null_reasons,
    ):
        decade = f"{auction_date.year // 10 * 10}s"
        for field in json.loads(reasons or "{}"):
            counts[(security_type, decade, field)] += 1
    return counts


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Treasury auction results")
    parser.add_argument("--start", type=datetime.date.fromisoformat,
                        help="auction_date to read from (default: backfill or trailing 30 days)")
    parser.add_argument("--null-report", action="store_true",
                        help="print NULL counts by security_type x decade x field and exit")
    args = parser.parse_args()

    from database.connection import get_session

    session = get_session()
    try:
        if args.null_report:
            for (kind, decade, field), n in sorted(null_count_report(session).items()):
                print(f"{kind}\t{decade}\t{field}\t{n}")
        else:
            result = run_treasury_auctions_fetch(session, start=args.start)
            print({k: v for k, v in result.items() if k not in ("share_gaps",)})
    finally:
        session.close()
