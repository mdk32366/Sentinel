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
