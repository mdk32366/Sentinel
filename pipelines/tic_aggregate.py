"""
The TIC "All Other" aggregate
-----------------------------
`D-0079` / `A-0019` option 2.

SLT Table 5 names twenty holders and folds every other foreign holder into one
**"All Other"** row. `F-0097` established that a country absent from the table is
inside that row rather than at zero, and `D-0078` put that on the screen as a
gap. This closes the other half: the row itself is published, so the
non-reporters' **combined** position is knowable even though no individual
position is.

**What this must never do.** Attribute an aggregate move to an individual
country. All Other covers roughly a hundred holders including sovereign wealth
funds, private institutions and the 28 scored countries outside the table; a
-1% move says *someone* reduced, and turning that into 28 country-level findings
would be `F-0097` in a new costume - a number nobody observed, asserted about a
named sovereign. So this is a **system-level** series, reported once, and
`tests/test_tic_all_other.py` asserts no country's score can move because of it.

**Why the share matters more than the level.** All Other rising could mean the
non-reporters bought, or simply that total foreign holdings grew. The share of
Grand Total separates those, which is why both rows are captured.
"""

import logging
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import Metric, TimeSeries

logger = logging.getLogger(__name__)

ALL_OTHER_CODE = "TIC_ALL_OTHER"
GRAND_TOTAL_CODE = "TIC_GRAND_TOTAL"
FOREIGN_OFFICIAL_CODE = "TIC_FOREIGN_OFFICIAL"
FOREIGN_OFFICIAL_BILLS_CODE = "TIC_FOREIGN_OFFICIAL_BILLS"
FOREIGN_OFFICIAL_BONDS_CODE = "TIC_FOREIGN_OFFICIAL_BONDS"

# A move in the share of total beyond this is worth naming. Chosen from the
# observed series: over the thirteen months to 2026-07 the share moved within
# 19.3%-20.1%, so a 3-month swing of half a point is outside ordinary drift
# without being a once-a-decade event.
#
# Deliberately a share threshold, not a level threshold. The level moved +2.74%
# over twelve months while the share fell - total foreign holdings grew faster -
# and a level-based rule would have called that accumulation.
SHARE_MOVE_PCT_POINTS = 0.5


def _series(db: Session, code: str) -> list:
    metric = db.query(Metric).filter_by(code=code).first()
    if not metric:
        return []
    return (
        db.query(TimeSeries)
        .filter(TimeSeries.metric_id == metric.id,
                TimeSeries.country_id.is_(None))
        .order_by(TimeSeries.date.asc())
        .all()
    )


def _pct(new, old):
    if old in (None, 0) or new is None:
        return None
    return round((float(new) - float(old)) / float(old) * 100, 2)


def all_other_signal(db: Session) -> dict | None:
    """The aggregate's level, share and direction. `None` if not yet imported.

    Every figure is derived from observations; nothing here is attributed to a
    country.
    """
    rows = _series(db, ALL_OTHER_CODE)
    if not rows:
        return None

    totals = {r.date: float(r.value) for r in _series(db, GRAND_TOTAL_CODE)}
    latest = rows[-1]
    level = float(latest.value)

    def share_at(row):
        total = totals.get(row.date)
        return None if not total else round(float(row.value) / total * 100, 2)

    share = share_at(latest)
    share_3m = share_at(rows[-4]) if len(rows) >= 4 else None

    # Consecutive monthly declines in the LEVEL, counted back from the newest.
    consec = 0
    for i in range(len(rows) - 1, 0, -1):
        if float(rows[i].value) < float(rows[i - 1].value):
            consec += 1
        else:
            break

    share_move = (
        round(share - share_3m, 2) if share is not None and share_3m is not None
        else None
    )

    return {
        "as_of": latest.date.date().isoformat(),
        "level_bn": round(level, 1),
        "share_pct": share,
        "mom_pct": _pct(level, rows[-2].value) if len(rows) >= 2 else None,
        "three_month_pct": _pct(level, rows[-4].value) if len(rows) >= 4 else None,
        # D-0088: rows[-13]. Correct today only because All Other is still the
        # 13-month Table 5 series; it would have gone wrong the moment that
        # deepened, exactly as Foreign Official did.
        "twelve_month_pct": _pct(level, rows[-13].value) if len(rows) >= 13 else None,
        "share_move_3m_points": share_move,
        "consecutive_declines": consec,
        "points": len(rows),
        # A verdict about the AGGREGATE, never about a member of it.
        "notable": bool(
            share_move is not None and abs(share_move) >= SHARE_MOVE_PCT_POINTS
        ),
        "note": (
            "Combined holdings of every foreign holder too small to be named in "
            "SLT Table 5 — roughly a hundred holders, including the 28 scored "
            "countries outside the table. A move here says something happened "
            "among them; it does not say who, and it is not attributed to any "
            "country (A-0019 option 2)."
        ),
    }


# ── Foreign Official (D-0080, recalibrated by D-0088) ───────────────────────
#
# A SUBSET of Grand Total, never additive with All Other: it spans every holder.
# Where All Other answers "what are the countries we cannot see doing", this
# answers "what are CENTRAL BANKS doing" - the question this application exists
# to ask.
#
# `A-0020` asked whether the first rule was calibrated on enough history. It was
# not, and the answer inverted the finding.
#
# `D-0080` used the thirteen months SLT Table 5 carries and flagged a
# "sustained decline" on 9 falls in 12 with a 1.0pp cumulative move. Against the
# **79 months** Table 3 carries (`D-0081`), 9 falls is the **median** window and
# that rule fires on **70% of windows**. It was decoration (`D-0024`) - a light
# that has been on for most of six years.
#
# Worse, it was pointing the wrong way. The current 12-month move of -1.86pp
# sits at the **84th percentile**: 56 of 67 windows were more negative. The
# present period is among the SLOWEST declines in the series, and the flag said
# something was happening.
#
# So notability is now measured against this series' own distribution rather
# than against a threshold chosen from a short window. The worst decile fires
# about a tenth of the time by construction, which is what a signal should do.
FO_WORST_DECILE_PP = -5.10   # p10 of 67 rolling 12-month share moves
FO_MEDIAN_MOVE_PP = -3.23    # the median, for context on the surface

# The real finding is structural and much larger than any 12-month window:
# official share 59.34% -> 40.80% since 2020-01 while private holdings rose
# 91.6%. Reported as a trend rather than an alarm, because a six-year drift is
# not an event.
FO_TREND_START = "2020-01"


def foreign_official_signal(db: Session) -> dict | None:
    """Central-bank holdings, their share, their duration mix, and the trend.

    System-level like `all_other_signal`. Foreign Official spans ALL holders, so
    it is not about the non-reporters and must not be read as a refinement of
    All Other - the two are different cuts of the same Grand Total.
    """
    rows = _series(db, FOREIGN_OFFICIAL_CODE)
    if not rows:
        return None

    totals = {r.date: float(r.value) for r in _series(db, GRAND_TOTAL_CODE)}
    bills = {r.date: float(r.value) for r in _series(db, FOREIGN_OFFICIAL_BILLS_CODE)}
    bonds = {r.date: float(r.value) for r in _series(db, FOREIGN_OFFICIAL_BONDS_CODE)}

    latest = rows[-1]
    level = float(latest.value)
    total = totals.get(latest.date)

    def share_at(row):
        t = totals.get(row.date)
        return None if not t else round(float(row.value) / t * 100, 2)

    share = share_at(latest)
    shares = [(r.date, share_at(r)) for r in rows]
    shares = [(d, v) for d, v in shares if v is not None]

    steps = [shares[i][1] - shares[i - 1][1] for i in range(1, len(shares))][-12:]
    falls = sum(1 for v in steps if v < 0)
    move_12m = (
        round(shares[-1][1] - shares[-13][1], 2) if len(shares) >= 13 else None
    )

    # D-0088. Where this window sits in the series' own history, rather than
    # against a number chosen from a short one.
    window_moves = sorted(
        shares[i][1] - shares[i - 12][1] for i in range(12, len(shares))
    )
    percentile = None
    if move_12m is not None and len(window_moves) >= 24:
        below = sum(1 for v in window_moves if v < move_12m)
        percentile = round(below / len(window_moves) * 100)

    # The structural trend: the finding a 12-month window cannot show.
    trend = None
    if len(shares) >= 60:
        trend = {
            "from": shares[0][0].date().isoformat(),
            "from_share_pct": shares[0][1],
            "to_share_pct": shares[-1][1],
            "share_change_pp": round(shares[-1][1] - shares[0][1], 2),
            "level_change_pct": _pct(level, rows[0].value),
            "months": len(shares),
        }

    private = round(total - level, 1) if total else None
    b, n = bills.get(latest.date), bonds.get(latest.date)
    reconciles = None if b is None or n is None else abs((b + n) - level) <= 0.5
    bills_share = round(b / level * 100, 2) if b is not None and level else None
    bills_share_12m = None
    if len(rows) >= 13:
        old = rows[-13]
        ob, ol = bills.get(old.date), float(old.value)
        if ob is not None and ol:
            bills_share_12m = round(bills_share - (ob / ol * 100), 2)

    # Fires about a tenth of the time by construction, on this series' own
    # worst decile - not on a threshold that was true of thirteen months.
    unusual = bool(move_12m is not None and move_12m <= FO_WORST_DECILE_PP)

    return {
        "as_of": latest.date.date().isoformat(),
        "level_bn": round(level, 1),
        "share_pct": share,
        "private_bn": private,
        "private_share_pct": round(private / total * 100, 2) if private and total else None,
        "mom_pct": _pct(level, rows[-2].value) if len(rows) >= 2 else None,
        "three_month_pct": _pct(level, rows[-4].value) if len(rows) >= 4 else None,
        # D-0088: rows[-13], not rows[0]. This said rows[0] and was correct
        # only while the series was exactly thirteen months long (Table 5). With
        # Table 3's 79 months it silently became a six-and-a-half-year change
        # labelled "twelve month" - -9.51% instead of the true -2.92%.
        "twelve_month_pct": _pct(level, rows[-13].value) if len(rows) >= 13 else None,
        "share_move_12m_points": move_12m,
        "share_move_percentile": percentile,
        "median_move_12m_points": FO_MEDIAN_MOVE_PP,
        "falls_of_last_12": falls,
        "trend": trend,
        "bills_bn": b,
        "bonds_bn": n,
        "bills_share_of_official_pct": bills_share,
        "bills_share_move_12m_points": bills_share_12m,
        "components_reconcile": reconciles,
        "points": len(rows),
        "unusual": unusual,
        # D-0088 retired `sustained`: 9 falls in 12 is the median window, so it
        # was true for most of six years. Kept as False rather than removed so
        # an older cached snapshot does not render a missing key as absent data.
        "sustained": False,
        "note": (
            "US Treasuries held by foreign official institutions - central banks "
            "and sovereign funds - across every holder, named and unnamed. A "
            "subset of the Grand Total, not a part of All Other and never added "
            "to it. Like All Other it describes a group, not any one country."
        ),
    }
