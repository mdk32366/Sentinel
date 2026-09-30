"""
What a country's absence from the TIC table actually means
----------------------------------------------------------
`F-0097`. SLT Table 5 is the **MAJOR** Foreign Holders table. It names exactly
20 countries and folds every other holder into a single "All Other" row.
Falling off that list means dropping below the reporting threshold. It does not
mean going to zero.

Two separate places computed `len(tic_hist) == 0` against a 185-day window and
read the result as "holds zero US Treasuries" - `composite_stress.py` for
dimension 1 (30-50 points, the largest dimension) and `gold_fetcher.py` for the
CROSS-ASSET surface (50-90 points plus multipliers). Measured against
production, 32 of 49 scored countries were on that path and **not one had ever
reported zero**: Germany's last reported holding was $103.1bn, Mexico's $85.4bn,
Italy's $62.1bn. Fifteen more had no TIC row at all and were each given 30
points for a liquidation never recorded.

One classifier, imported by both, because `F-0047` is the standing example of
two implementations of one idea drifting apart and the endpoint serving the
wrong one's output.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from database.models import TimeSeries

logger = logging.getLogger(__name__)

# A last reported holding below this counts as a genuine exit. Not exactly 0.0
# because Table 5 rounds to 0.1bn, so a real wind-down lands at 0.0-0.9 rather
# than on zero. The smallest positive last-reported holding observed in
# production was Finland at $11.2bn, so there is an order of magnitude of
# clearance either side.
TIC_EXIT_THRESHOLD_BN = 1.0

# The four states. Only `EXITED` earns the gold-confirmed posture score.
REPORTED = "reported"
EXITED = "exited"
BELOW_THRESHOLD = "below_threshold"
NO_DATA = "no_data"


def classify_tic_state(has_current_rows: bool, last_reported_bn: float | None) -> str:
    """The rule, as both callers apply it.

    `has_current_rows` is whether the country appears in the *current* release
    window. `last_reported_bn` is its newest reported value at any age - the
    two answer different questions, and conflating them is the defect.

      reported         current data exists; score the trend.
      exited           last reported holding is ~zero. A real completed
                       liquidation, and the only state that earns the posture
                       score.
      below_threshold  last reported holding was positive but the country is no
                       longer among Table 5's 20 named holders, so it sits
                       inside "All Other". Its current position is unknown, and
                       zero is not a safe guess in either direction.
      no_data          never appeared in the table at all.
    """
    if has_current_rows:
        return REPORTED
    if last_reported_bn is None:
        return NO_DATA
    if last_reported_bn < TIC_EXIT_THRESHOLD_BN:
        return EXITED
    return BELOW_THRESHOLD


def last_reported_holding(db: Session, metric_id: int, country_id: int):
    """`(value_bn, date)` for the country's newest TIC row at any age.

    Deliberately unwindowed. Every caller already has a windowed query for "is
    there current data"; this is the other half of the question, and the reason
    it is a named function is that fetching it inside the window was the bug.
    """
    row = (
        db.query(TimeSeries)
        .filter(
            TimeSeries.metric_id == metric_id,
            TimeSeries.country_id == country_id,
        )
        .order_by(TimeSeries.date.desc())
        .first()
    )
    if row is None:
        return None, None
    return float(row.value), row.date


def describe(state: str, last_bn: float | None, last_date: datetime | None) -> str:
    """One line a reader can act on, naming the figure behind the verdict.

    The old signal read "EXITED: Zero US Treasuries" for Germany while Germany
    held $103.1bn. Naming the last reported figure and its date is the whole
    difference between a fact and a fabrication.
    """
    if state == EXITED:
        return "Exited: last reported holding was zero"
    if state == BELOW_THRESHOLD:
        when = f" ({last_date:%b %Y})" if last_date else ""
        return f"Below TIC reporting threshold — last reported ${last_bn:,.1f}bn{when}"
    if state == NO_DATA:
        return "No TIC data — never among the reported holders"
    return "Reported in the current TIC release"
