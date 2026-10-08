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


def zscore(window, value):
    """(z, used, reason). `window` is the trailing values, NULLs included."""
    used = [float(v) for v in window if v is not None]
    if value is None:
        return None, len(used), "value_missing"
    if len(used) < MIN_OBSERVATIONS:
        return None, len(used), "insufficient_history"
    sd = statistics.stdev(used)
    if sd == 0:
        return None, len(used), "zero_variance"
    return (float(value) - statistics.fmean(used)) / sd, len(used), None


def attach_zscores(rows):
    """Copies of `rows` with b2c_z / dealer_z, their window sizes and reasons.

    Rows need term_group, auction_date, cusip, b2c_recomputed and
    primary_dealer_share. Windows are per term group, ordered by auction date,
    and never include the auction being scored.
    """
    by_group = {}
    for r in rows:
        by_group.setdefault(r.get("term_group"), []).append(r)

    scored = {}
    for group, members in by_group.items():
        members = sorted(members, key=lambda r: (r["auction_date"], r["cusip"]))
        for i, r in enumerate(members):
            out = dict(r)
            if group is None:
                for prefix in ("b2c", "dealer"):
                    out[f"{prefix}_z"] = None
                    out[f"{prefix}_z_window"] = 0
                    out[f"{prefix}_z_reason"] = "no_term_family"
            else:
                before = members[max(0, i - WINDOW_N):i]
                for prefix, field in (("b2c", "b2c_recomputed"),
                                      ("dealer", "primary_dealer_share")):
                    z, used, reason = zscore([m[field] for m in before], r[field])
                    out[f"{prefix}_z"] = z
                    out[f"{prefix}_z_window"] = used
                    out[f"{prefix}_z_reason"] = reason
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
