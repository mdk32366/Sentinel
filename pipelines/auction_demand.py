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


# D-0108. STUB - tests first.
def weakness(b2c_z, dealer_z):
    return 0.0


def signal_board(rows, since):
    return {"counts": {}, "by_term": [], "signals": []}
