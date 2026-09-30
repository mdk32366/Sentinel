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
        "twelve_month_pct": _pct(level, rows[0].value) if len(rows) >= 13 else None,
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


# ── Foreign Official (D-0080) ───────────────────────────────────────────────
#
# A SUBSET of Grand Total, never additive with All Other: it spans every
# holder, named and unnamed. Where All Other answers "what are the countries we
# cannot see doing", this answers "what are CENTRAL BANKS doing" - which is the
# question this application exists to ask.
#
# `SHARE_MOVE_PCT_POINTS = 0.5`, derived for All Other, is NOT reused here. This
# series is far more volatile in share terms: against the thirteen months to
# 2026-07, 0.5pp over three months fires on **7 of 10 windows**. Inheriting a
# threshold across two series that happen to share a unit is exactly F-0089 and
# F-0091 - a number carried from where it was derived to where it was not.
#
# Nor is a magnitude threshold used at all. The observed 3-month moves run
# -1.21 to +0.55 with no gap between ordinary and notable: 0.75pp fires on 4 of
# 10, 1.0pp on 2, 1.25pp on none. There is no value that separates signal from
# noise, so none is invented.
#
# The robust signal is PERSISTENCE. Over the same window the share fell in 9 of
# 12 monthly steps for a cumulative -1.87pp. One noisy month cannot produce
# that, and it is computable from the history that exists.
FO_SUSTAINED_MIN_FALLS = 8      # of the last 12 monthly steps
FO_SUSTAINED_MIN_MOVE_PP = 1.0  # cumulative 12-month share move

# Calibrated on ONE thirteen-month window, which is all Table 5 carries. Stated
# rather than marked PROVISIONAL and forgotten, which is what happened to the
# gold tolerance for months (D-0076). Re-derive when a second year exists: the
# question is whether 9-of-12 falls is ordinary for this series or is the
# de-dollarization it currently appears to be.
FO_CALIBRATION_MONTHS = 13


def foreign_official_signal(db: Session) -> dict | None:
    """Central-bank holdings, their share, their duration mix, and the private side.

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

    # Persistence over the last twelve monthly steps.
    steps = [shares[i][1] - shares[i - 1][1] for i in range(1, len(shares))][-12:]
    falls = sum(1 for v in steps if v < 0)
    move_12m = (
        round(shares[-1][1] - shares[-13][1], 2) if len(shares) >= 13 else None
    )

    # The private side is derived, not stored: Grand Total minus official. A
    # stored copy would be a second thing to keep in step with two others.
    private = round(total - level, 1) if total else None

    b, n = bills.get(latest.date), bonds.get(latest.date)
    reconciles = (
        None if b is None or n is None else abs((b + n) - level) <= 0.5
    )
    bills_share = round(b / level * 100, 2) if b is not None and level else None
    bills_share_12m = None
    if len(rows) >= 13:
        old = rows[-13]
        ob, ol = bills.get(old.date), float(old.value)
        if ob is not None and ol:
            bills_share_12m = round(bills_share - (ob / ol * 100), 2)

    sustained = bool(
        move_12m is not None
        and falls >= FO_SUSTAINED_MIN_FALLS
        and abs(move_12m) >= FO_SUSTAINED_MIN_MOVE_PP
    )

    return {
        "as_of": latest.date.date().isoformat(),
        "level_bn": round(level, 1),
        "share_pct": share,
        "private_bn": private,
        "private_share_pct": round(private / total * 100, 2) if private and total else None,
        "mom_pct": _pct(level, rows[-2].value) if len(rows) >= 2 else None,
        "three_month_pct": _pct(level, rows[-4].value) if len(rows) >= 4 else None,
        "twelve_month_pct": _pct(level, rows[0].value) if len(rows) >= 13 else None,
        "share_move_12m_points": move_12m,
        "falls_of_last_12": falls,
        "bills_bn": b,
        "bonds_bn": n,
        "bills_share_of_official_pct": bills_share,
        "bills_share_move_12m_points": bills_share_12m,
        # Table 5 publishes the components; they must sum to the headline. A
        # free integrity check on every run rather than a trusted parse.
        "components_reconcile": reconciles,
        "points": len(rows),
        "sustained": sustained,
        "calibration_months": FO_CALIBRATION_MONTHS,
        "note": (
            "US Treasuries held by foreign official institutions - central banks "
            "and sovereign funds - across every holder, named and unnamed. A "
            "subset of the Grand Total, not a part of All Other and never added "
            "to it. Like All Other it describes a group, not any one country."
        ),
    }
