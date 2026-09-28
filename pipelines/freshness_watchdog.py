"""
Data Freshness Watchdog
========================
One job that answers: is any source in Sentinel silently dead?

WHY THIS EXISTS
    On 2026-09-26 the Treasury yields looked three days stale and were in fact
    current to their upstream source, while GOLD_SPOT_USD had been dead since
    2026-07-01 with no signal of any kind. Gold spot feeds the 2.0x divergence
    multiplier — the largest in the composite scorer — so three months of
    scoring ran against a July price.

    The lesson baked into this module: thresholds must be per-source. A blanket
    "one business day" rule screams about healthy Treasury data every weekend
    and stays silent on the source that actually matters.

WHAT IT CHECKS
    1. Data age     — MAX(timeseries.date) per source group vs its own cadence.
    2. Pipeline age — last SUCCESSFUL update_logs row per pipeline.
    A source can fail either way: a pipeline that runs nightly but writes
    nothing is as dead as one that never runs.

STATUS LEVELS
    ok        age <= max_age_days
    stale     max_age_days < age <= 2x
    critical  age > 2x, or no data at all
    unknown   source not yet present in the database (never seeded)

OUTPUTS
    - Dict via get_freshness_report(db) for /api/health and /api/freshness.
    - An update_logs row named "Freshness" so the watchdog itself is auditable.
    - Optional POST to JARVIS_WEBHOOK_URL when anything is stale or critical.

TUNING — READ BEFORE CHANGING A THRESHOLD
    Thresholds allow for weekend + publication lag + one holiday before firing.

    MONTH_START: several importers call date.replace(day=1), so a monthly
    series reads up to 31 days older than it is, on top of the source's own
    publication lag. GOLD_SPOT_USD is the worked example: on 2026-09-26 a
    fully current series (August data, published early September, stored as
    2026-08-01) has an age of 56 days. A 45-day threshold alarms on healthy
    data. 75 is the corrected figure; see F-0030.

    Thresholds marked PROVISIONAL were set by reasoning, not measurement, and
    the reasoning has already been wrong once. Run with --calibrate against a
    populated database and set them from observed age before installing.

VALIDATION
    Pipeline names in CHECKS are matched against the distinct values actually
    present in update_logs. A name that matches nothing is reported loudly as
    a configuration error, never silently as "never ran" — that equivalence is
    what made F-0030 invisible.
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import Metric, TimeSeries, UpdateLog

logger = logging.getLogger(__name__)

PIPELINE_NAME = "Freshness"
ERROR_FIELD_LIMIT = 480

# patterns are SQL LIKE patterns matched against metrics.code
CHECKS = [
    {
        "key": "treasury_yields",
        "label": "US Treasury yield curve",
        "patterns": ["DGS%", "DFII%"],
        "max_age_days": 5,       # weekend + 1-day FRED lag + holiday headroom
        "pipelines": ["FRED", "TreasuryDirect"],
        "note": "FRED lags one business day; TreasuryDirect should be same-day.",
    },
    {
        "key": "oil",
        "label": "Crude oil (Brent / WTI)",
        "patterns": ["DCOIL%"],
        "max_age_days": 8,
        "pipelines": ["FRED"],
        "note": "Feeds composite dimension 5 (petrodollar pressure).",
    },
    {
        "key": "dollar_index",
        "label": "Broad dollar index",
        "patterns": ["DTWEXBGS"],
        "max_age_days": 12,      # H.10 is weekly
        "pipelines": ["FRED"],
        "note": "Weekly release (H.10, Mondays).",
    },
    {
        "key": "gold_price",
        "label": "Gold spot price",
        "patterns": ["GOLD_SPOT_USD"],
        "max_age_days": 8,       # D-0041: LBMA daily fix, not the month-end CSV.
                                 # 75 was calibrated for a monthly series normalised
                                 # to day-1. Left at 75 against a daily feed, a dead
                                 # source goes unnoticed for eleven weeks - the
                                 # decoration D-0024 exists to prevent.
        "pipelines": ["Gold_Spot_Price"],
        "note": "MANUAL CSV. Feeds the 2.0x divergence multiplier.",
    },
    {
        "key": "gold_reserves",
        "label": "Gold reserves by country",
        "patterns": ["GOLD_RESERVES"],
        "max_age_days": 200,     # PROVISIONAL — quarterly + month-start + reporting lag
        "pipelines": ["Gold_Reserves", "Gold_Reserve_Changes"],
        "note": "MANUAL CSV from World Gold Council.",
    },
    {
        "key": "tic",
        "label": "TIC Treasury holdings",
        "patterns": ["TIC%"],
        "max_age_days": 55,      # monthly, released ~45 days in arrears
        "pipelines": ["TIC_Holdings"],
        "note": "Release date drifts within the month.",
    },
    {
        "key": "cds",
        "label": "Sovereign CDS spreads",
        "patterns": ["%\\_CDS\\_%"],
        "max_age_days": 4,
        "pipelines": ["CDS_MultiTenor"],
        "note": "Blocked by Investing.com 403 from datacenter IPs pending proxy.",
    },
    {
        "key": "sovereign_yields",
        "label": "OECD sovereign 10Y yields",
        "patterns": ["IRLTLT01%"],
        "max_age_days": 70,      # monthly OECD series, published in arrears
        "pipelines": ["FRED"],
        "note": "Feeds composite dimension 4.",
    },
    {
        "key": "reserves_ex_gold",
        "label": "Total reserves ex-gold (TRESEG)",
        "patterns": ["TRESEG%"],
        "max_age_days": 100,
        "pipelines": ["FRED"],
        "note": "Feeds composite dimension 6.",
    },
    {
        "key": "money_supply",
        "label": "Broad money growth",
        "patterns": ["BROAD_MONEY_GROWTH"],
        "max_age_days": 420,     # annual World Bank series
        "pipelines": ["Broad_Money_Growth"],
        "note": "MANUAL JSON. Feeds composite dimension 3.",
    },
]


def _latest_dates_by_pattern(db: Session, patterns) -> dict:
    """Return {metric_code: latest_date} for every metric matching any pattern."""
    q = db.query(Metric.code, func.max(TimeSeries.date)) \
          .join(TimeSeries, TimeSeries.metric_id == Metric.id)

    clause = None
    for p in patterns:
        c = Metric.code.like(p, escape="\\")
        clause = c if clause is None else (clause | c)

    rows = q.filter(clause).group_by(Metric.code).all()
    return {code: dt for code, dt in rows if dt is not None}


def _last_success(db: Session, pipeline_names) -> dict:
    """Return {pipeline_name: (completed_at, status)} for the most recent run."""
    out = {}
    for name in pipeline_names:
        row = (
            db.query(UpdateLog.completed_at, UpdateLog.status,
                     UpdateLog.error_message)
            .filter(UpdateLog.pipeline_name == name,
                    UpdateLog.status.in_(["success", "partial"]))
            .order_by(UpdateLog.completed_at.desc())
            .first()
        )
        if row:
            out[name] = {"completed_at": row[0], "status": row[1],
                         "error_message": row[2]}
    return out


# D-0046. treasury_direct records a value that jumped more than MAX_JUMP_PP by
# prefixing its log field with this marker. It deliberately does not block -
# a blocking jump detector refuses to record a crisis - but until now the
# answer landed somewhere nobody reads, which is Principle 9's second form.
ANOMALY_MARKER = "ANOMALIES:"


def _anomalies_from(pipeline_info: dict) -> list:
    """Pull the anomaly lines out of a pipeline's most recent log row."""
    text = (pipeline_info or {}).get("error_message") or ""
    if ANOMALY_MARKER not in text:
        return []
    tail = text.split(ANOMALY_MARKER, 1)[1]
    return [part.strip() for part in tail.split(";") if part.strip()]


# F-0036. Pipeline names are validated against what the pipelines DECLARE, not
# against the rows update_logs happens to hold. A name absent from update_logs
# is ambiguous - it means either "the name is wrong" or "this pipeline has not
# run yet" - and those two must never render the same. Declaration resolves it.
#
# Both spellings are matched, because missing the constant form is exactly the
# error recorded in F-0013: a literal-only search reported a real pipeline as
# absent.
_PIPELINE_NAME_PATTERNS = (
    re.compile(r'pipeline_name\s*=\s*"([^"]+)"'),
    re.compile(r'^[A-Z0-9_]*PIPELINE_NAME\s*=\s*"([^"]+)"', re.M),
)


def declared_pipeline_names() -> set:
    """Every pipeline_name any module in this package writes, whether as a
    literal at the UpdateLog call site or as a module-level constant.

    Static scan rather than import: importing every pipeline to read a constant
    would execute module-level code for the side effect of a string.
    """
    names = set()
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    for fn in sorted(os.listdir(pkg_dir)):
        if not fn.endswith(".py"):
            continue
        try:
            with open(os.path.join(pkg_dir, fn), encoding="utf-8") as fh:
                src = fh.read()
        except OSError:
            continue
        for pattern in _PIPELINE_NAME_PATTERNS:
            names.update(pattern.findall(src))
    return names


def validate_pipeline_names(db: Session) -> dict:
    """
    Compare every pipeline name in CHECKS against the names the pipelines
    declare in source, and against the names update_logs has seen.

      declared + seen      -> known, covered
      declared + not seen  -> pending. Correct configuration, no run yet.
      not declared         -> unknown. A real configuration error: nothing in
                              this package will ever write that name.

    Returns {"unknown": [...], "pending": [...], "unchecked": [...], ...}.
    """
    seen = {r[0] for r in db.query(UpdateLog.pipeline_name).distinct().all()}
    declared = declared_pipeline_names()
    configured = {n for c in CHECKS for n in c.get("pipelines", [])}

    missing = configured - seen
    pending = sorted(missing & declared)
    unknown = sorted(missing - declared)
    # Names the database records that no check covers.
    unchecked = sorted(seen - configured)

    if unknown:
        logger.error(
            "FRESHNESS CONFIG ERROR \u2014 CHECKS names %d pipeline(s) that no "
            "pipeline declares: %s. Declared names are: %s",
            len(unknown), ", ".join(unknown), ", ".join(sorted(declared)),
        )
    if unchecked:
        logger.info(
            "Pipelines running but not covered by any freshness check: %s",
            ", ".join(unchecked),
        )
    if pending:
        logger.info(
            "Configured pipelines declared but not yet run: %s",
            ", ".join(pending),
        )

    return {
        "unknown": unknown,
        "pending": pending,
        "unchecked": unchecked,
        "stale_suppressions": [],
        "declared": sorted(declared),
        "known": sorted(seen),
    }


def calibrate(db: Session) -> str:
    """
    Report observed age per group against the live database and propose a
    threshold, so thresholds are set from data rather than guessed a second
    time. Proposal is observed age x2, rounded up to a round number — wide
    enough not to alarm on healthy data, tight enough to catch a dead source.
    """
    now = datetime.utcnow()
    lines = ["Observed freshness — set thresholds from these, not from theory", ""]
    for check in CHECKS:
        latest = _latest_dates_by_pattern(db, check["patterns"])
        if not latest:
            lines.append(f"  {check['label']:<34} NO DATA — cannot calibrate")
            continue
        newest = max(latest.values())
        oldest_code = min(latest, key=lambda c: latest[c])
        age = (now - newest).days
        oldest_age = (now - latest[oldest_code]).days
        proposed = max(5, ((age * 2) // 5 + 1) * 5)
        flag = "  <-- CURRENT LIMIT TOO TIGHT" if age > check["max_age_days"] else ""
        lines.append(
            f"  {check['label']:<34} age={age:>4}d  laggard={oldest_age:>4}d "
            f"({oldest_code})  limit={check['max_age_days']:>4}d  "
            f"proposed={proposed:>4}d{flag}"
        )
    return "\n".join(lines)


def _classify(age_days, max_age_days):
    if age_days is None:
        return "unknown"
    if age_days <= max_age_days:
        return "ok"
    if age_days <= max_age_days * 2:
        return "stale"
    return "critical"


def get_freshness_report(db: Session) -> dict:
    """Build the report. Read-only — safe to call from an API route."""
    now = datetime.utcnow()
    config = validate_pipeline_names(db)
    sources = []

    for check in CHECKS:
        latest_by_code = _latest_dates_by_pattern(db, check["patterns"])

        if latest_by_code:
            newest = max(latest_by_code.values())
            age_days = (now - newest).days
            # the single laggard within the group is often the real story
            oldest_code = min(latest_by_code, key=lambda c: latest_by_code[c])
            oldest_date = latest_by_code[oldest_code]
            oldest_age = (now - oldest_date).days
        else:
            newest = age_days = None
            oldest_code = oldest_date = oldest_age = None

        status = _classify(age_days, check["max_age_days"])

        pipelines = _last_success(db, check.get("pipelines", []))

        # D-0046: an anomaly raises an otherwise-OK source to `anomaly`. It
        # never lowers a worse status - stale data with an odd jump is still
        # stale, and the more serious finding wins.
        anomalies = []
        for info in pipelines.values():
            anomalies.extend(_anomalies_from(info))
        if anomalies and status == "ok":
            status = "anomaly"
        pipeline_view = {
            name: {
                "last_run": info["completed_at"].isoformat(),
                "status": info["status"],
                "hours_ago": round(
                    (now - info["completed_at"]).total_seconds() / 3600, 1
                ),
            }
            for name, info in pipelines.items()
        }

        sources.append({
            "key": check["key"],
            "label": check["label"],
            "status": status,
            "latest_date": newest.date().isoformat() if newest else None,
            "age_days": age_days,
            "max_age_days": check["max_age_days"],
            "metric_count": len(latest_by_code),
            "laggard": (
                {"code": oldest_code,
                 "date": oldest_date.date().isoformat(),
                 "age_days": oldest_age}
                if oldest_code and oldest_age != age_days else None
            ),
            "pipelines": pipeline_view,
            "anomalies": anomalies,
            "note": check.get("note"),
        })

    counts = {"ok": 0, "anomaly": 0, "stale": 0, "critical": 0, "unknown": 0}
    for s in sources:
        counts[s["status"]] += 1

    # A misconfigured check must never read as a healthy system.
    if config["unknown"]:
        overall = "config_error"
    elif counts["critical"]:
        overall = "critical"
    elif counts["stale"]:
        overall = "stale"
    elif counts["unknown"]:
        overall = "unknown"
    elif counts["anomaly"]:
        # Below stale on purpose. A stale source is definitely wrong; an
        # anomalous one is plausibly correct and worth a look. Ranking it
        # higher would make every genuine market move outrank real staleness.
        overall = "anomaly"
    else:
        overall = "ok"

    return {
        "overall": overall,
        "counts": counts,
        "config": config,
        "checked_at": now.isoformat(),
        "sources": sorted(
            sources,
            key=lambda s: ({"critical": 0, "stale": 1, "unknown": 2, "anomaly": 3, "ok": 4}[s["status"]],
                           -(s["age_days"] or 0)),
        ),
    }


def format_report_text(report: dict) -> str:
    """Plain-text rendering for email / webhook bodies and console output."""
    icon = {"ok": "OK      ", "anomaly": "ANOMALY ",
            "stale": "STALE   ", "critical": "CRITICAL",
            "unknown": "UNKNOWN ", "config_error": "CONFIG  "}
    lines = [
        f"Sentinel data freshness — {report['overall'].upper()}",
        f"Checked {report['checked_at']}Z",
        "",
    ]
    for s in report["sources"]:
        age = f"{s['age_days']}d" if s["age_days"] is not None else "no data"
        lines.append(
            f"  [{icon[s['status']]}] {s['label']:<34} "
            f"latest={s['latest_date'] or '—':<12} age={age:<9} "
            f"limit={s['max_age_days']}d"
        )
        if s["laggard"]:
            lines.append(
                f"               laggard: {s['laggard']['code']} "
                f"@ {s['laggard']['date']} ({s['laggard']['age_days']}d)"
            )
        if s["status"] != "ok" and s.get("note"):
            lines.append(f"               note: {s['note']}")
    return "\n".join(lines)


def _notify(report: dict) -> None:
    """POST the report to JARVIS (or any webhook). No-op if unset."""
    url = os.getenv("JARVIS_WEBHOOK_URL")
    if not url:
        return
    try:
        import requests
        requests.post(
            url,
            json={
                "source": "sentinel",
                "kind": "data_freshness",
                "severity": report["overall"],
                "summary": (
                    f"{report['counts']['critical']} critical, "
                    f"{report['counts']['stale']} stale"
                ),
                "text": format_report_text(report),
                "report": report,
            },
            timeout=15,
        )
        logger.info("Freshness alert sent to JARVIS webhook")
    except Exception as e:
        logger.error("Freshness webhook failed: %s", e)


def run_freshness_check(db: Session, notify: bool = True) -> dict:
    """
    Scheduler entry point. Signature matches the other pipelines.
    Writes an update_logs row so the watchdog is itself auditable.
    """
    start_time = datetime.utcnow()

    try:
        report = get_freshness_report(db)
    except Exception as e:
        msg = str(e)[:ERROR_FIELD_LIMIT]
        logger.error("Freshness check failed: %s", msg)
        db.add(UpdateLog(
            pipeline_name=PIPELINE_NAME, status="failed",
            records_inserted=0, records_updated=0, error_message=msg,
            started_at=start_time, completed_at=datetime.utcnow(),
        ))
        db.commit()
        return {"status": "failed", "error": msg}

    problems = [
        f"{s['label']} {s['age_days']}d (limit {s['max_age_days']}d)"
        for s in report["sources"] if s["status"] in ("critical", "stale", "unknown")
    ]

    status = "success" if report["overall"] == "ok" else "partial"
    err_text = ("; ".join(problems))[:ERROR_FIELD_LIMIT] if problems else None

    db.add(UpdateLog(
        pipeline_name=PIPELINE_NAME, status=status,
        records_inserted=0, records_updated=0, error_message=err_text,
        started_at=start_time, completed_at=datetime.utcnow(),
    ))
    db.commit()

    logger.info("Freshness: %s — %s", report["overall"], report["counts"])
    if problems:
        logger.warning("Stale sources: %s", "; ".join(problems))
        if notify:
            _notify(report)

    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from database.connection import get_session

    import sys

    db = get_session()
    try:
        if "--calibrate" in sys.argv:
            print(calibrate(db))
        elif "--validate" in sys.argv:
            cfg = validate_pipeline_names(db)
            print("unknown (CONFIG ERROR):", cfg["unknown"] or "none")
            print("running but unchecked :", cfg["unchecked"] or "none")
        else:
            print(format_report_text(run_freshness_check(db, notify=False)))
    finally:
        db.close()
