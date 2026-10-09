"""
Auction demand metrics, computed at read time.
=============================================
z-scores of the recomputed bid-to-cover and the primary dealer share against
the trailing window of the same term (D-0099), the term labels the panel
filters on (D-0103), and the staleness rule (D-0101).

Read time rather than stored: ~6,300 rows, and a stored z-score is stale the
moment a result is revised. The recomputed bid-to-cover is the input, not the
reported one, so the derivation is ours and auditable (§2).
"""
import bisect
import datetime
import statistics

WINDOW_N = 26           # D-0099
MIN_OBSERVATIONS = 8    # D-0099
STALE_BUSINESS_DAYS = 3  # D-0101

# Panel label -> term group (D-0103). Charted in v1, in display order.
CHARTED_TERMS = {
    "4W": "4-Week",
    "8W": "8-Week",
    "13W": "13-Week",
    "17W": "17-Week",
    "26W": "26-Week",
    "52W": "52-Week",
    "2Y": "2-Year",
    "5Y": "5-Year",
    "10Y": "10-Year",
    "30Y": "30-Year",
}
# D-0105. Filterable through the API and windowed, but not charted in v1.
FAMILY_TERMS = {
    "TIPS5Y": "TIPS 5-Year",
    "TIPS10Y": "TIPS 10-Year",
    "TIPS20Y": "TIPS 20-Year",
    "TIPS30Y": "TIPS 30-Year",
    "FRN2Y": "FRN 2-Year",
}
FILTER_TERMS = {**CHARTED_TERMS, **FAMILY_TERMS}
TERM_BY_GROUP = {group: label for label, group in FILTER_TERMS.items()}


def window_stats(window):
    """(mean, sd, used) of the trailing values, NULLs skipped. mean and sd are
    None below MIN_OBSERVATIONS: a band on three points is not a band."""
    used = [float(v) for v in window if v is not None]
    if len(used) < MIN_OBSERVATIONS:
        return None, None, len(used)
    return statistics.fmean(used), statistics.stdev(used), len(used)


def zscore(window, value):
    """(z, used, reason). `window` is the trailing values, NULLs included."""
    mean, sd, used = window_stats(window)
    if value is None:
        return None, used, "value_missing"
    if mean is None:
        return None, used, "insufficient_history"
    if sd == 0:
        return None, used, "zero_variance"
    return (float(value) - mean) / sd, used, None


def attach_zscores(rows):
    """Copies of `rows` with b2c_z / dealer_z, their window sizes and reasons.

    Rows need term_group, auction_date, cusip, b2c_recomputed and
    primary_dealer_share. Windows are per term group, ordered by auction date,
    and never include the auction being scored. Each row also carries its
    bid-to-cover window's mean and sd, which is the band the panel draws: one
    window rule, here, rather than a second copy in JavaScript (F-0047).
    """
    by_group = {}
    for r in rows:
        by_group.setdefault(r.get("term_group"), []).append(r)

    scored = {}
    for group, members in by_group.items():
        members = sorted(members, key=lambda r: (r["auction_date"], r["cusip"]))
        for i, r in enumerate(members):
            out = dict(r)
            out["b2c_window_mean"] = out["b2c_window_sd"] = None
            if group is None:
                for prefix in ("b2c", "dealer"):
                    out[f"{prefix}_z"] = None
                    out[f"{prefix}_z_window"] = 0
                    out[f"{prefix}_z_reason"] = "no_term_family"
            else:
                before = members[max(0, i - WINDOW_N):i]
                mean, sd, _ = window_stats([m["b2c_recomputed"] for m in before])
                out["b2c_window_mean"], out["b2c_window_sd"] = mean, sd
                for prefix, field in (("b2c", "b2c_recomputed"),
                                      ("dealer", "primary_dealer_share")):
                    z, used, reason = zscore([m[field] for m in before], r[field])
                    out[f"{prefix}_z"] = z
                    out[f"{prefix}_z_window"] = used
                    out[f"{prefix}_z_reason"] = reason
            out["demand_signal"], out["demand_signal_reason"] = demand_signal(
                r.get("b2c_check"), out["b2c_z"], out["dealer_z"]
            )
            scored[id(r)] = out
    return [scored[id(r)] for r in rows]


def business_days_since(data_as_of: datetime.date, today: datetime.date) -> int:
    """Weekdays after `data_as_of`, up to and including `today`."""
    days, d = 0, data_as_of
    while d < today:
        d += datetime.timedelta(days=1)
        if d.weekday() < 5:
            days += 1
    return days


def is_stale(data_as_of: datetime.date, today: datetime.date) -> bool:
    return business_days_since(data_as_of, today) > STALE_BUSINESS_DAYS


# ── D-0107: when weak demand is flagged ─────────────────────────────────────
#
# Weak demand at an auction is two things at once: little cover, and dealers
# left holding the issue because end investors did not take it. One without
# the other is common - either test alone at 2 sd fired 7 to 7.5 times a year
# across the ten charted terms, 2008-2026 - so the alert needs both:
#
#   alert   b2c_z <= -2.0 AND dealer_z >= +2.0      1.9 a year
#   watch   b2c_z <= -2.5 OR  dealer_z >= +2.5      3.0 a year (alert first)
#
# Strong demand is never flagged: the signal is one-sided by design. A row
# whose two bid-to-cover paths disagree (b2c_check != ok) is not scored at all,
# because its z-score rests on a figure that is itself in question (§2).
ALERT_B2C_Z = -2.0
ALERT_DEALER_Z = 2.0
WATCH_B2C_Z = -2.5
WATCH_DEALER_Z = 2.5


def demand_signal(b2c_check, b2c_z, dealer_z):
    """(signal, reason): signal is "alert", "watch" or None (D-0107).

    `reason` explains a row that could not be scored; None when it was."""
    if b2c_check != "ok":
        return None, f"b2c_check_{b2c_check}"
    if b2c_z is None or dealer_z is None:
        return None, "not_scored"
    if b2c_z <= ALERT_B2C_Z and dealer_z >= ALERT_DEALER_Z:
        return "alert", None
    if b2c_z <= WATCH_B2C_Z or dealer_z >= WATCH_DEALER_Z:
        return "watch", None
    return None, None


# ── D-0108: the signal leaderboard ──────────────────────────────────────────

def weakness(b2c_z, dealer_z):
    """How far both z-scores went the weak way: -(b2c z) + (dealer z).

    The two quantities D-0107 already tests, added, so the ranking cannot
    disagree with the alert about what "weak" means. None if either is missing.
    """
    if b2c_z is None or dealer_z is None:
        return None
    return round(-b2c_z + dealer_z, 2)


def signal_board(rows, since):
    """Every flagged auction in a charted term since `since` (ISO date, or
    None for all history): alerts first, then weakest first, then newest.

    `rows` are scored rows (attach_zscores output, with `term`). Returns
    counts, a per-term tally in display order, and the ranked signals.
    """
    flagged = [
        dict(r, weakness=weakness(r.get("b2c_z"), r.get("dealer_z")))
        for r in rows
        if r.get("term") in CHARTED_TERMS
        and r.get("demand_signal")
        and (since is None or str(r["auction_date"]) >= since)
    ]
    flagged.sort(key=lambda r: str(r["auction_date"]), reverse=True)
    flagged.sort(key=lambda r: (
        0 if r["demand_signal"] == "alert" else 1,
        -(r["weakness"] if r["weakness"] is not None else float("-inf")),
    ))

    by_term = []
    for term in CHARTED_TERMS:
        mine = [r for r in flagged if r["term"] == term]
        by_term.append({
            "term": term,
            "alerts": sum(r["demand_signal"] == "alert" for r in mine),
            "watches": sum(r["demand_signal"] == "watch" for r in mine),
            "last_signal_date": max((str(r["auction_date"]) for r in mine), default=None),
        })

    return {
        "counts": {
            "alert": sum(r["demand_signal"] == "alert" for r in flagged),
            "watch": sum(r["demand_signal"] == "watch" for r in flagged),
        },
        "by_term": by_term,
        "signals": flagged,
    }


# ── D-0109: the number of signals is the signal ─────────────────────────────
#
# One weak auction is noise; a run of them is a regime. The trailing 12-month
# count of D-0107 alerts and watches across the ten charted terms, banded
# against its own history. Measured over 209 month-ends, 2009-06 to 2026-10:
# median 4, 80th percentile 8, 95th percentile 10, maximum 14.
FREQUENCY_WINDOW_DAYS = 365
FREQUENCY_ELEVATED = 8   # top 20% of month-ends
FREQUENCY_HIGH = 11      # top 3%: only the 2019 repo-stress peak and 2026


def frequency_band(count):
    if count >= FREQUENCY_HIGH:
        return "high"
    if count >= FREQUENCY_ELEVATED:
        return "elevated"
    return "normal"


def _day(value):
    return value if isinstance(value, datetime.date) else datetime.date.fromisoformat(str(value)[:10])


def _month_end(year, month):
    nxt = datetime.date(year + (month == 12), month % 12 + 1, 1)
    return nxt - datetime.timedelta(days=1)


def signal_frequency(rows, as_of):
    """The trailing 12-month signal count at `as_of`, its band, its monthly
    history, and whether it beats every month-end before this window began.

    `rows` are scored rows (with `term`). History starts one full window
    after the first auction that could be scored, so every point counts a
    whole year."""
    as_of = _day(as_of)
    charted = [r for r in rows if r.get("term") in CHARTED_TERMS]
    scorable = [_day(r["auction_date"]) for r in charted
                if r.get("b2c_z") is not None and r.get("dealer_z") is not None]
    flagged = sorted((_day(r["auction_date"]), r["demand_signal"])
                     for r in charted if r.get("demand_signal"))
    days = [d for d, _ in flagged]
    window = datetime.timedelta(days=FREQUENCY_WINDOW_DAYS)

    def count_at(end):
        return bisect.bisect_right(days, end) - bisect.bisect_right(days, end - window)

    current = [s for d, s in flagged if as_of - window < d <= as_of]
    history = []
    if scorable:
        start = min(scorable) + window
        y, m = start.year, start.month
        while (y, m) <= (as_of.year, as_of.month):
            end = min(_month_end(y, m), as_of)
            history.append({"month": f"{y}-{m:02d}", "count": count_at(end), "end": end})
            m += 1
            if m == 13:
                y, m = y + 1, 1
    earlier = [h["count"] for h in history if h["end"] <= as_of - window]
    max_before = max(earlier) if earlier else None
    count = len(current)
    return {
        "count": count,
        "alerts": current.count("alert"),
        "watches": current.count("watch"),
        "band": frequency_band(count),
        "window_days": FREQUENCY_WINDOW_DAYS,
        "elevated_at": FREQUENCY_ELEVATED,
        "high_at": FREQUENCY_HIGH,
        "max_before": max_before,
        "record": max_before is not None and count > max_before,
        "history": [{"month": h["month"], "count": h["count"]} for h in history],
    }


# ── D-0110: the slow drift the 26-auction window cannot see ─────────────────
#
# Each auction is scored against the 26 before it, so a decline that takes
# years becomes the baseline and never trips D-0107. This compares each
# term's 52-week median cover with its own 5-year median. At 85% or less -
# about the 10th percentile of that ratio's history - the term is drifting.
# Historically it flagged the 2015-2018 slide in bill cover as QE ended.
DRIFT_RATIO = 0.85
DRIFT_RECENT_DAYS = 364
DRIFT_BASELINE_DAYS = 5 * 365
DRIFT_MIN_RECENT = 6


def cover_drift(rows):
    """Per charted term, in display order: the 52-week and 5-year median of
    Treasury's reported bid-to-cover at its latest auction, their ratio, and
    whether it is drifting. A term without the history gets no ratio."""
    by_term = {}
    for r in rows:
        if r.get("term") in CHARTED_TERMS and r.get("b2c_reported") is not None:
            by_term.setdefault(r["term"], []).append((_day(r["auction_date"]), float(r["b2c_reported"])))
    out = []
    for term in CHARTED_TERMS:
        series = sorted(by_term.get(term, []))
        row = {"term": term, "ratio": None, "median_52w": None, "median_5y": None,
               "drifting": False, "reason": None}
        if not series:
            row["reason"] = "no_auctions"
            out.append(row)
            continue
        last = series[-1][0]
        if series[0][0] > last - datetime.timedelta(days=DRIFT_BASELINE_DAYS):
            row["reason"] = "insufficient_history"
            out.append(row)
            continue
        recent = [b for d, b in series if d > last - datetime.timedelta(days=DRIFT_RECENT_DAYS)]
        base = [b for d, b in series if d > last - datetime.timedelta(days=DRIFT_BASELINE_DAYS)]
        if len(recent) < DRIFT_MIN_RECENT:
            row["reason"] = "insufficient_recent"
            out.append(row)
            continue
        m52, m5 = statistics.median(recent), statistics.median(base)
        ratio = m52 / m5
        row.update(median_52w=m52, median_5y=m5, ratio=ratio, drifting=ratio <= DRIFT_RATIO)
        out.append(row)
    return out
