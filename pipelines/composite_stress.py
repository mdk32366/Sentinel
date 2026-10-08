"""
Composite Sovereign Stress Scorer
------------------------------------
Seven-dimension scoring system:

  DIMENSION 1 — Treasury (0-50 pts)
    MoM decline magnitude:    0-30 pts (scaled)
    Consecutive months:       0-20 pts (4 pts each, cap 5 months)

  DIMENSION 2 — Gold Reserves (0-40 pts)
    QoQ decline magnitude:    0-20 pts (scaled)
    Consecutive quarters:     0-20 pts (4 pts each, cap 5 quarters)

  DIMENSION 3 — Monetary / M2 (0-35 pts)
    >15% YoY M2 growth:       10 pts
    >30% YoY M2 growth:       20 pts
    >50% YoY M2 growth:       35 pts

  DIMENSION 4 — Sovereign Spread (RETIRED from scoring, D-0066)
    Measured and displayed, worth 0 pts. It scored a country more than 50bps
    ABOVE the US 10Y and held yields only for the fourteen developed markets
    in SOVEREIGN_YIELD_CODES, every one of which trades BELOW the US:
    AUS -22.5bps, GBR -25.1, NOR -95.4, FRA -124.0, ITA -125.4, CAN -156.5.
    Across all 48 scored countries it awarded 0 points to 0 countries. It
    could only fire for emerging markets and held no yield data for any.
    F-0079.
    Spread >50bps vs US 10Y:   5 pts  (mild risk premium)
    Spread >100bps vs US 10Y: 10 pts  (elevated)
    Spread >200bps vs US 10Y: 15 pts  (significant stress)
    Spread widening >30bps in 3M: +5 pts (trend component)

  DIMENSION 5 — Petrodollar / Oil Pressure (0-20 pts)  ← NEW
    Only fires for oil-dependent economies.
    Brent down >10% over 3M:  5 pts  (mild revenue pressure)
    Brent down >20% over 3M: 10 pts  (significant)
    Brent down >30% over 3M: 20 pts  (severe — forced seller risk)
    Convergence bonus: +5 pts if oil falling AND country selling treasuries
    simultaneously (confirms petrodollar recycling breakdown)

    Oil-dependent nations: Gulf states, Russia/CIS oil exporters,
    Nigeria, Algeria, Libya, Angola, Mexico, Colombia, Ecuador,
    Venezuela, Norway, Kazakhstan, Azerbaijan.

  DIMENSION 6 — Non-dollar reserves / TRESEG (score multiplier)
    Reserves-ex-gold trend. REBUILDING (>5% YoY) applies a 1.2x boost
    for countries that have exited Treasuries; DEPLETING (<-5% YoY)
    flags distress. Mainly significant when a country holds zero US
    Treasuries (active de-dollarization into an alternative system).

  DIMENSION 7 — Sovereign CDS (0-20 pts)  ← NEW
    Market-priced default risk from 5Y/10Y CDS spreads.
    5Y >100bps:  5 pts  (mild credit risk premium)
    5Y >250bps: 10 pts  (elevated)
    5Y >500bps: 15 pts  (significant distress)
    5Y widening >20% over 3M:       +5 pts (trend component)
    Inverted term structure (10Y<5Y): +3 pts (acute distress)
    Degrades gracefully to zero where CDS coverage is absent.

MULTIPLIERS (applied to raw sum):
  Cross-asset (selling both T + gold):    1.5x
  Divergence (selling gold into rising):  2.0x

TIERS:
  WATCH:    score < 25
  ELEVATED: 25 ≤ score < 50
  STRESSED: 50 ≤ score < 75
  CRISIS:   score ≥ 75
"""

import logging
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import json

# F-0074: the CDS admissibility rule lives with the CDS pipeline, so the
# scorer and the API cannot drift into judging the same rows differently.
from pipelines.cds_fetcher import (
    MAX_CDS_AGE_DAYS,
    MAX_PLAUSIBLE_CDS_BPS,
    admit_cds_quote,
)
from database.models import (
    Metric, TimeSeries, Country, CompositeSnapshot, UpdateLog,
)

logger = logging.getLogger(__name__)


# ORDER-03 D2 / F-0023. Each dimension helper used to re-resolve its metric by
# code, once per country per dimension, against a table of 79 rows that does
# not change during a request. One query replaces roughly 250.
#
# Cached on the Session, not module-level: a module-level dict would outlive
# the session that produced the ORM instances and hand detached objects to the
# next request.
def _metrics_by_code(db: Session) -> dict:
    cache = getattr(db, "_sentinel_metric_cache", None)
    if cache is None:
        cache = {m.code: m for m in db.query(Metric).all()}
        db._sentinel_metric_cache = cache
    return cache

# FRED codes for 10Y government bond yields (OECD monthly series)
SOVEREIGN_YIELD_CODES = {
    "JPN": "IRLTLT01JPM156N",
    "DEU": "IRLTLT01DEM156N",
    "ITA": "IRLTLT01ITM156N",
    "FRA": "IRLTLT01FRM156N",
    "ESP": "IRLTLT01ESM156N",
    "GBR": "IRLTLT01GBM156N",
    "AUS": "IRLTLT01AUM156N",
    "CAN": "IRLTLT01CAM156N",
    "NLD": "IRLTLT01NLM156N",
    "NOR": "IRLTLT01NOM156N",
    "SWE": "IRLTLT01SEM156N",
    "CHE": "IRLTLT01CHM156N",
    "BEL": "IRLTLT01BEM156N",
    "KOR": "IRLTLT01KRM156N",
}

# Countries whose external reserve dynamics are significantly driven by
# oil/gas export revenues. When Brent falls, these countries experience
# reduced petrodollar recycling — meaning less USD flowing back into
# Treasuries, and potential forced selling to cover fiscal gaps.
OIL_DEPENDENT_COUNTRIES = {
    # Gulf / Middle East
    "SAU", "ARE", "KWT", "QAT", "IRQ", "OMN", "BHR",
    # Russia / CIS
    "RUS", "KAZ", "AZE",
    # Africa
    "NGA", "AGO", "DZA", "LBY",
    # Latin America
    "VEN", "ECU", "COL", "MEX",
    # Europe/Other
    "NOR",
}


def get_us_10y_yield(db: Session) -> float | None:
    """Get latest US 10Y yield from DB."""
    metric = _metrics_by_code(db).get("DGS10")
    if not metric:
        return None
    latest = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == None,
    ).order_by(TimeSeries.date.desc()).first()
    return float(latest.value) if latest else None


def get_brent_trend(db: Session, months: int = 3) -> dict:
    """
    Get Brent crude price trend over the past N months.
    Uses DCOILBRENTEU (daily) from FRED.
    Falls back to WTI (DCOILWTICO) if Brent not available.
    Returns: {latest_price, start_price, change_pct, falling}
    """
    for code in ("DCOILBRENTEU", "DCOILWTICO"):
        metric = _metrics_by_code(db).get(code)
        if not metric:
            continue

        cutoff = datetime.utcnow() - timedelta(days=months * 31)
        history = db.query(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id == None,
            TimeSeries.date >= cutoff,
        ).order_by(TimeSeries.date.asc()).all()

        if len(history) < 10:
            continue

        latest = float(history[-1].value)
        start = float(history[0].value)
        change_pct = (latest - start) / start * 100 if start else None

        return {
            "source": code,
            "latest_price": round(latest, 2),
            "start_price": round(start, 2),
            "change_pct": round(change_pct, 1) if change_pct is not None else None,
            "falling": change_pct < -10 if change_pct is not None else None,
            "change_3m_pct": round(change_pct, 1) if change_pct is not None else None,
        }

    return {
        "source": None,
        "latest_price": None,
        "start_price": None,
        "change_pct": None,
        "falling": None,
        "change_3m_pct": None,
    }


def get_petrodollar_score(iso: str, brent: dict, selling_tic: bool) -> dict:
    """
    Compute petrodollar stress score for a given country.
    Only fires for oil-dependent economies.

    The signal: oil revenue is the primary source of USD for these countries.
    When Brent falls, their ability to recycle petrodollars into US Treasuries
    weakens. Combined with active treasury selling, this confirms a revenue
    stress dynamic rather than strategic repositioning.
    """
    if iso not in OIL_DEPENDENT_COUNTRIES:
        return {"score": 0, "oil_dependent": False, "oil_signal": None}

    change_pct = brent.get("change_pct")
    if change_pct is None:
        return {"score": 0, "oil_dependent": True, "oil_signal": "no price data"}

    score = 0
    signal = None

    if change_pct <= -30:
        score = 20
        signal = f"Brent {change_pct:.1f}% (3M) — severe revenue shock"
    elif change_pct <= -20:
        score = 10
        signal = f"Brent {change_pct:.1f}% (3M) — significant revenue pressure"
    elif change_pct <= -10:
        score = 5
        signal = f"Brent {change_pct:.1f}% (3M) — mild revenue pressure"

    # Convergence bonus: oil falling AND selling treasuries simultaneously
    # This is the clearest petrodollar recycling breakdown signal
    if score > 0 and selling_tic:
        score += 5
        signal += " + treasury selling (petrodollar recycling breakdown)"

    return {
        "score": min(score, 20),
        "oil_dependent": True,
        "oil_signal": signal,
    }


def get_sovereign_spread(db: Session, iso: str, us_10y: float | None) -> dict:
    """
    Get sovereign bond yield spread vs US 10Y for a given country.
    Returns: {spread_bps, widening_bps, score}
    """
    if us_10y is None or iso not in SOVEREIGN_YIELD_CODES:
        return {"spread_bps": None, "widening_bps": None, "score": 0}

    fred_code = SOVEREIGN_YIELD_CODES[iso]
    metric = _metrics_by_code(db).get(fred_code)
    if not metric:
        return {"spread_bps": None, "widening_bps": None, "score": 0}

    cutoff_3m = datetime.utcnow() - timedelta(days=120)
    history = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == None,
        TimeSeries.date >= cutoff_3m,
    ).order_by(TimeSeries.date.asc()).all()

    if not history:
        return {"spread_bps": None, "widening_bps": None, "score": 0}

    latest_yield = float(history[-1].value)
    spread_bps = (latest_yield - us_10y) * 100

    widening_bps = None
    if len(history) >= 2:
        old_yield = float(history[0].value)
        old_spread = (old_yield - us_10y) * 100
        widening_bps = spread_bps - old_spread

    score = 0
    if spread_bps > 200:
        score = 15
    elif spread_bps > 100:
        score = 10
    elif spread_bps > 50:
        score = 5

    if widening_bps is not None and widening_bps > 30:
        score += 5

    return {
        "spread_bps": round(spread_bps, 1),
        "widening_bps": round(widening_bps, 1) if widening_bps is not None else None,
        "score": min(score, 20),
    }


# D-0065: the 5Y level at which CDS starts contributing.
#
# It was 100bps, which is an ordinary emerging-market spread rather than a
# stress signal. Brazil printed 129.6 and South Africa 130.9 - unremarkable
# for those sovereigns - and Brazil was ranked WATCH on a composite score of
# 5.0 that came ENTIRELY from that band. Meanwhile India at 87.7 and Mexico
# at 91.0 sat just below it. A threshold separating 91 from 130 is not
# separating calm from stressed; it is separating two ordinary spreads.
#
# At 200 the band fires for Turkey (248) and Egypt (307) and nobody else on
# the current board.
#
# NOTE: this leaves a narrow 200-250 window worth 5 points before the 250
# band takes over at 10. The ladder is compressed at the bottom as a result.
# Recorded rather than silently re-spaced, because re-spacing the upper bands
# is a separate judgement nobody has made.
CDS_ELEVATED_BPS = 200.0

# D-0067: the upper rungs, re-spaced so the ladder is proportional.
#
# D-0065 raised the floor to 200 and left 200/250/500, which gave 5 points
# across a 50bps window and the next 5 across 250bps - steeply sensitive at
# the bottom and flat above it. 200/350/600 spaces them at 150 and 250.
#
# Consequence, stated because it is not cosmetic: Egypt prints 307.3 and
# moves from the second rung to the first, 10 points to 5. Its composite sits
# at exactly 50.0, the STRESSED floor, so it drops to ELEVATED. That is the
# ladder doing what it was re-spaced to do - 307bps is elevated, not
# significant, once "significant" means 350 - but it is a tier change on a
# real country, not a rounding difference.
CDS_SIGNIFICANT_BPS = 350.0
CDS_DISTRESS_BPS = 600.0


# ── DIMENSION 7: Sovereign CDS ────────────────────────────────────────────────
# CDS metrics are stored with country_id=None; the country is encoded in the
# metric CODE (e.g. "FRANCE_CDS_5Y"), using country NAMES. The scorer keys on
# ISO codes, so we map ISO -> the CDS code prefix used by the fetcher.
# (Codes are the clean, post-migration form: no doubled tenor suffix.)
CDS_NAME_BY_ISO = {
    "FRA": "FRANCE", "DEU": "GERMANY", "GRC": "GREECE", "ITA": "ITALY",
    "ESP": "SPAIN", "CHE": "SWITZERLAND", "RUS": "RUSSIA", "TUR": "TURKEY",
    "SAU": "SAUDI_ARABIA", "EGY": "EGYPT", "CHN": "CHINA", "JPN": "JAPAN",
    "KOR": "SOUTH_KOREA", "IND": "INDIA", "IDN": "INDONESIA", "USA": "UNITED_STATES",
    "CAN": "CANADA", "MEX": "MEXICO", "BRA": "BRAZIL", "AUS": "AUSTRALIA",
    "ZAF": "SOUTH_AFRICA",
    # D-0064
    "AUT": "AUSTRIA",
    "BEL": "BELGIUM",
    "DNK": "DENMARK",
    "FIN": "FINLAND",
    "IRL": "IRELAND",
    "ISR": "ISRAEL",
    "NLD": "NETHERLANDS",
    "PRT": "PORTUGAL",
    "SWE": "SWEDEN",
    "GBR": "UNITED_KINGDOM",
}

# D-0091 / F-0106: the inverse, derived rather than written out, so there is
# one map and no second copy to drift (F-0062 / D-0061). `/cds/all` uses it to
# hand the UI an ISO-3166 key beside the CDS namespace token, because the
# country card is keyed by ISO3 and the token ("RUSSIA") opens an empty one.
ISO_BY_CDS_NAME = {v: k for k, v in CDS_NAME_BY_ISO.items()}


def _latest_and_prior(db: Session, code: str, days_back: int = 90):
    """Return (latest_value, prior_value_or_None, as_of_date_or_None).

    'prior' is the earliest observation within the lookback window, used to
    measure recent widening. Returns (None, None, None) if the metric or data
    is absent, so a missing country simply scores zero on this dimension.

    F-0074: the as-of date is returned because the caller cannot otherwise
    tell a current quote from a stale one. `get_cds_score` read only the
    value, so legacy rows written by a previous scraper - every 10Y series and
    Saudi Arabia's 5Y, all frozen at 2026-07-16 - kept scoring months after
    the fetcher had been fixed to stop producing them. Fixing the writer does
    not fix the reader.
    """
    metric = _metrics_by_code(db).get(code)
    if not metric:
        return None, None, None

    cutoff = datetime.utcnow() - timedelta(days=days_back)
    history = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == None,
        TimeSeries.date >= cutoff,
    ).order_by(TimeSeries.date.asc()).all()

    if not history:
        # No data in the window — fall back to the single latest point, if any.
        latest_row = db.query(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id == None,
        ).order_by(TimeSeries.date.desc()).first()
        if not latest_row:
            return None, None, None
        return float(latest_row.value), None, latest_row.date

    latest = float(history[-1].value)
    prior = float(history[0].value) if len(history) >= 2 else None
    return latest, prior, history[-1].date


def get_cds_score(db: Session, iso: str) -> dict:
    """
    Dimension 7 — Sovereign CDS (0-20 pts).

    CDS is the most direct market-priced measure of sovereign default risk
    in the dataset. Scored as a level band on the 5Y spread plus a widening
    kicker, mirroring the sovereign-spread dimension. An inverted term
    structure (10Y < 5Y) — the near term priced as riskier than the far term —
    is a recognized acute-distress signal and adds a small amount.

        Absolute 5Y level (D-0065 raised the floor, D-0067 re-spaced):
            >200 bps:   5 pts   (elevated)
            >350 bps:  10 pts   (significant)
            >600 bps:  15 pts   (distress)
        Widening (5Y up >20% over ~90d):      +5 pts

    D-0062: the term-structure component is GONE. It scored an inverted curve
    (10Y < 5Y) at +3, and the source has no 10Y to invert - the WGB board
    publishes Country, rating, 5Y, Var 1m, Var 6m, implied PD and date, and
    the string "10Y" does not occur in its payload at all. The only inversions
    it ever produced were a frozen July placeholder subtracted from a current
    5Y (F-0074).

    A scoring branch that cannot be reached is not conservative, it is
    decoration that reads as rigour.

    Thresholds are intentionally conservative and additive to the existing
    tier math (no re-normalization). Returns zero cleanly when a country has
    no CDS coverage, so partial coverage never drops a country from scoring.
    """
    name = CDS_NAME_BY_ISO.get(iso)
    if not name:
        return {"cds_5y": None, "cds_10y": None, "term_spread": None,
                "widening_pct": None, "score": 0, "signal": None,
                "coverage": "not on the board"}

    cds_5y, prior_5y, as_of_5y = _latest_and_prior(db, f"{name}_CDS_5Y", days_back=90)
    cds_10y, _, as_of_10y = _latest_and_prior(db, f"{name}_CDS_10Y", days_back=90)

    # F-0074. A quote is admitted only if it is current AND expressible as a
    # running spread. Each tenor is judged on its own: the 10Y board stopped
    # publishing in July 2026 while the 5Y board did not, and pairing a July
    # 10Y against a September 5Y produced "term structure inversions" that
    # were an artefact of the gap.
    rejected_5y = admit_cds_quote(cds_5y, as_of_5y)
    rejected_10y = admit_cds_quote(cds_10y, as_of_10y)
    if rejected_5y:
        cds_5y, prior_5y = None, None
    if rejected_10y:
        cds_10y = None

    if cds_5y is None:
        return {"cds_5y": None, "cds_10y": cds_10y, "term_spread": None,
                "widening_pct": None, "score": 0, "signal": None,
                "coverage": rejected_5y or "no coverage"}

    # Level band on 5Y
    score = 0
    if cds_5y > CDS_DISTRESS_BPS:
        score = 15
    elif cds_5y > CDS_SIGNIFICANT_BPS:
        score = 10
    elif cds_5y > CDS_ELEVATED_BPS:
        score = 5

    # Widening kicker: recent 5Y move relative to the start of the window
    widening_pct = None
    if prior_5y and prior_5y > 0:
        widening_pct = (cds_5y - prior_5y) / prior_5y * 100
        if widening_pct > 20:
            score += 5

    # D-0062: no 10Y from this source, so no term structure and no inversion
    # kicker. Kept as an explicit None rather than deleted from the payload,
    # because the API contract still carries the field and a reader needs to
    # see that it is absent by design rather than missing by accident.
    term_spread = None
    inverted = False

    # Human-readable signal for the active-signals list / UI
    signal = None
    if score > 0:
        parts = [f"5Y CDS {cds_5y:.0f}bps"]
        if widening_pct is not None and widening_pct > 20:
            parts.append(f"widening +{widening_pct:.0f}% (3M)")
        if inverted:
            parts.append(f"inverted term structure ({term_spread:.0f}bps)")
        signal = " · ".join(parts)

    return {
        "cds_5y": round(cds_5y, 1),
        "cds_10y": round(cds_10y, 1) if cds_10y is not None else None,
        "term_spread": round(term_spread, 1) if term_spread is not None else None,
        "widening_pct": round(widening_pct, 1) if widening_pct is not None else None,
        "score": min(score, 20),
        "signal": signal,
        # Why the 10Y is absent when it is, so the UI can distinguish "no
        # paired 10Y on this board" from "we dropped it as unusable".
        "coverage": "quoted",
        "coverage_10y": rejected_10y,
    }


def get_spot_gold_trend(db: Session, months: int = 3) -> dict:
    """Get recent spot gold price trend."""
    gold_metric = _metrics_by_code(db).get("GOLD_SPOT_USD")
    if not gold_metric:
        return {"latest_price": None, "trend_3m_pct": None, "rising": None}

    cutoff = datetime.utcnow() - timedelta(days=months * 31)
    history = db.query(TimeSeries).filter(
        TimeSeries.metric_id == gold_metric.id,
        TimeSeries.country_id == None,
        TimeSeries.date >= cutoff,
    ).order_by(TimeSeries.date.asc()).all()

    if len(history) < 2:
        return {"latest_price": None, "trend_3m_pct": None, "rising": None}

    latest = float(history[-1].value)
    start = float(history[0].value)
    trend_3m_pct = (latest - start) / start * 100 if start else None

    return {
        "latest_price": round(latest, 2),
        "trend_3m_pct": round(trend_3m_pct, 2) if trend_3m_pct is not None else None,
        "rising": trend_3m_pct > 2 if trend_3m_pct is not None else None,
    }


def compute_composite_stress(db: Session) -> dict:
    """
    Compute five-dimension composite stress scores for all countries.
    Returns structured dict with tiers and summary.
    """
    tic_metric = _metrics_by_code(db).get("TIC_UST_HOLDINGS")
    gold_metric = _metrics_by_code(db).get("GOLD_RESERVES")
    m2_metric = _metrics_by_code(db).get("BROAD_MONEY_GROWTH")

    if not tic_metric:
        return {"error": "No TIC data loaded"}

    tic_latest = db.query(func.max(TimeSeries.date)).filter(
        TimeSeries.metric_id == tic_metric.id).scalar()
    if not tic_latest:
        return {"error": "No TIC data points"}

    gold_latest = None
    if gold_metric:
        gold_latest = db.query(func.max(TimeSeries.date)).filter(
            TimeSeries.metric_id == gold_metric.id).scalar()

    spot = get_spot_gold_trend(db, months=3)
    spot_rising = spot.get("rising")
    us_10y = get_us_10y_yield(db)

    # Fetch Brent trend once — applies to all oil-dependent countries
    brent = get_brent_trend(db, months=3)

    # D-0084. The bill book, and the denominator for the size weight. Both are
    # read once rather than per country.
    st_metric = db.query(Metric).filter_by(code="TIC_UST_ST_HOLDINGS").first()
    net_metric_d1 = db.query(Metric).filter_by(code="TIC_UST_NET_SALES").first()
    val_metric_d1 = db.query(Metric).filter_by(code="TIC_UST_LT_VALUATION").first()
    global_total = None
    gt_metric = db.query(Metric).filter_by(code="TIC_GRAND_TOTAL").first()
    if gt_metric is not None:
        gt_row = db.query(TimeSeries).filter(
            TimeSeries.metric_id == gt_metric.id,
            TimeSeries.country_id.is_(None),
        ).order_by(TimeSeries.date.desc()).first()
        global_total = float(gt_row.value) if gt_row else None

    results = []
    # NOTE: Exclude USA from scoring — it's the issuer of Treasuries, not a holder.
    # TIC (Treasury International Capital) data tracks *foreign* holdings only.
    # The US having "zero holdings" is expected and not a stress signal.
    for country in db.query(Country).filter(Country.iso_code != "USA").all():
        iso = country.iso_code

        # ── DIMENSION 1: Treasury ──────────────────────────────────────────
        # D-0084 widened this from 185 days. The magnitude term is now a
        # three-month change, which needs four monthly observations, and the
        # persistence term counts up to five consecutive declines.
        tic_hist = db.query(TimeSeries).filter(
            TimeSeries.metric_id == tic_metric.id,
            TimeSeries.country_id == country.id,
            TimeSeries.date >= tic_latest - timedelta(days=200),
        ).order_by(TimeSeries.date.asc()).all()

        tic_mom = 0
        tic_consec = 0
        tic_score = 0
        selling_tic = False
        # D-0084. Set here so a country that never reaches the scoring branch
        # still carries the fields; an absent key would be filtered to a default
        # by response_model and read as a real value (F-0079).
        mag_detail = {
            "tic_3m_pct": None, "tic_st_drawdown_pct": None,
            "tic_magnitude_basis": "none", "tic_price_driven": False,
        }

        # F-0097. `tic_hist` above is windowed and answers "is there current
        # data". This answers "what did they last actually report", at any age.
        # The two are different questions and conflating them is the defect.
        tic_last_bn, tic_last_date = last_reported_holding(
            db, tic_metric.id, country.id
        )
        # D-0106: an exit needs a position to exit from.
        tic_peak_bn = peak_reported_holding(db, tic_metric.id, country.id)
        tic_state = classify_tic_state(bool(tic_hist), tic_last_bn, tic_peak_bn)
        no_tic_holdings = tic_state == EXITED

        if len(tic_hist) >= 2:
            tic_prev = float(tic_hist[-2].value)
            if tic_prev > 0:
                tic_mom = (float(tic_hist[-1].value) - tic_prev) / tic_prev * 100
                for i in range(len(tic_hist) - 1, 0, -1):
                    if float(tic_hist[i].value) < float(tic_hist[i-1].value):
                        tic_consec += 1
                    else:
                        break
                # D-0084. The magnitude term, replacing
                # `min(30, abs(tic_mom) * 3)`. A three-month lens over the
                # total position OR the bill book, whichever is worse, with the
                # total suppressed where the fall was price rather than selling
                # and the result weighted by the country's share of all foreign
                # holdings. F-0099 and A-0021 are why; the function carries the
                # derivation of every constant.
                st_series = _series_values(
                    db, st_metric, country.id, tic_latest, days=200
                )
                net_3m = _sum_recent(
                    db, net_metric_d1, country.id, tic_latest, months=3
                )
                val_3m = _sum_recent(
                    db, val_metric_d1, country.id, tic_latest, months=3
                )
                tot_series = [float(r.value) for r in tic_hist]

                magnitude, mag_detail = treasury_magnitude(
                    tot_series, st_series, net_3m, val_3m, global_total
                )
                tic_score += magnitude
                tic_score += min(20, tic_consec * 4)
                selling_tic = (
                    magnitude > 0 or tic_mom < -0.5 or tic_consec >= 2
                )
        elif no_tic_holdings:
            # Completed Treasury liquidation — most severe de-dollarization signal.
            # Assign a strong tic_score based on gold holdings as confirmation.
            # We don't know MoM since they've already exited, so we score on posture.
            tic_score = 0  # Will be set after gold is known
            tic_mom = None
            tic_consec = 0
        else:
            # F-0097. below_threshold or no_data. Unknown is not zero and it is
            # not calm either: this dimension simply cannot speak, and it says
            # so rather than awarding points in either direction.
            tic_mom = None
            tic_consec = 0

        # ── DIMENSION 2: Gold Reserves ─────────────────────────────────────
        gold_score = 0
        gold_mom = None
        gold_consec = 0
        gold_tonnes = None
        selling_gold = False
        gold_stale = False

        if gold_metric and gold_latest:
            gold_rows = db.query(TimeSeries).filter(
                TimeSeries.metric_id == gold_metric.id,
                TimeSeries.country_id == country.id,
                TimeSeries.date >= gold_latest - timedelta(days=GOLD_WINDOW_DAYS),
            ).order_by(TimeSeries.date.asc()).all()

            # F-0094. This dimension counts "consecutive quarters" and used to
            # count consecutive ROWS. Those were the same thing only because
            # the World Gold Council CSV is quarterly - the label was true by
            # accident of the source.
            #
            # D-0076 adds a MONTHLY feed (IMF IRFCL) to the same series. Left
            # alone, three consecutive monthly dips would have scored as three
            # consecutive quarters: 12 points for a quarter of movement, and
            # every country's gold score inflated the day the better source
            # landed. Fixing the source would have corrupted the score.
            #
            # So the series is resampled to one observation per calendar
            # quarter - the last reading in each - and "consecutive quarters"
            # now means what it says whatever cadence the rows arrive at.
            gold_hist = _last_per_quarter(gold_rows)

            # A-0017. Too old to describe current behaviour. The TONNAGE is
            # still reported - "Venezuela last reported 161t in 2018" is worth
            # seeing - but it cannot earn points, exactly as F-0092 ruled for
            # broad money.
            gold_stale = bool(
                gold_hist
                and (tic_latest or gold_latest)
                and (gold_latest - gold_hist[-1].date).days > MAX_GOLD_DATA_AGE_DAYS
            )

            if gold_hist and gold_stale:
                # Reported, not scored.
                gold_tonnes = float(gold_hist[-1].value)

            if gold_hist and not gold_stale:
                gold_tonnes = float(gold_hist[-1].value)
                if len(gold_hist) >= 2:
                    gold_prev = float(gold_hist[-2].value)
                    if gold_prev > 0:
                        gold_mom = (gold_tonnes - gold_prev) / gold_prev * 100
                        for i in range(len(gold_hist) - 1, 0, -1):
                            if float(gold_hist[i].value) < float(gold_hist[i-1].value):
                                gold_consec += 1
                            else:
                                break
                        if gold_mom < 0:
                            gold_score += min(20, abs(gold_mom) * 2)
                        gold_score += min(20, gold_consec * 4)
                        selling_gold = gold_mom < -0.5 or gold_consec >= 2

        # ── DIMENSION 3: Monetary / M2 ─────────────────────────────────────
        # If EXITED and has meaningful gold, now assign tic_score
        if no_tic_holdings and gold_tonnes and gold_tonnes >= 50:
            tic_score = 30  # Base: completed liquidation confirmed by gold holdings
            if gold_tonnes >= 500:
                tic_score = 40  # Large gold holder — structural de-dollarization
            if gold_tonnes >= 1000:
                tic_score = 50  # Major gold power — maximum posture score
        monetary_score = 0
        m2_growth_pct = None
        m2_year = None
        m2_stale = False

        if m2_metric:
            m2_row = db.query(TimeSeries).filter(
                TimeSeries.metric_id == m2_metric.id,
                TimeSeries.country_id == country.id,
            ).order_by(TimeSeries.date.desc()).first()

            if m2_row:
                m2_growth_pct = float(m2_row.value)
                m2_year = m2_row.date.year

                # F-0092. This used to score whatever the newest row was,
                # however old. Countries drop out of World Bank reporting and
                # never come back: Canada's newest broad money figure is
                # **2008**, Switzerland's 2016, Saudi Arabia's 2017, Russia's
                # 2020. Canada's is 14.9% - a tenth of a point under the 15%
                # first rung, which is the only reason an eighteen-year-old
                # number was not earning points.
                #
                # Russia's was: 16.7% from 2020, worth 10 points, presented
                # beside Turkey's 2025 figure with nothing marking the
                # difference. The source-level watchdog cannot see this - the
                # SOURCE is current, because 2025 data exists for the countries
                # that still report. The staleness is per country, which is the
                # `laggard` idea the watchdog already applies to
                # reserves_ex_gold, one level down.
                #
                # Money supply growth from 2008 says nothing about debasement
                # in 2026. The figure is still reported, because "Canada last
                # reported in 2008" is a fact worth seeing, but it cannot earn
                # points.
                m2_stale = m2_year < datetime.utcnow().year - MAX_M2_DATA_AGE_YEARS

                if not m2_stale:
                    if m2_growth_pct > 50:
                        monetary_score = 35
                    elif m2_growth_pct > 30:
                        monetary_score = 20
                    elif m2_growth_pct > 15:
                        monetary_score = 10

        # ── DIMENSION 4: Sovereign Spread ──────────────────────────────────
        # D-0066: still MEASURED, no longer SCORED. The spread itself is
        # worth showing - Japan sitting 300bps below the US 10Y is a real
        # fact about the world - but it cannot earn points.
        spread_data = get_sovereign_spread(db, iso, us_10y)
        spread_bps = spread_data["spread_bps"]
        spread_widening = spread_data["widening_bps"]

        # ── DIMENSION 5: Petrodollar / Oil Pressure ────────────────────────
        selling_tic = (tic_mom is not None and (tic_mom < -0.5 or tic_consec >= 2))
        petro_data = get_petrodollar_score(iso, brent, selling_tic)
        petro_score = petro_data["score"]
        oil_dependent = petro_data["oil_dependent"]
        oil_signal = petro_data["oil_signal"]

        # ── DIMENSION 7: Sovereign CDS ─────────────────────────────────────
        cds_data = get_cds_score(db, iso)
        cds_score = cds_data["score"]

        # ── MULTIPLIERS ────────────────────────────────────────────────────
        cross_asset = selling_tic and selling_gold
        # EXITED + selling gold = structurally equivalent to cross-asset stress
        exited_cross = no_tic_holdings and selling_gold and (gold_tonnes or 0) >= 50
        divergence = (cross_asset or exited_cross) and spot_rising

        if divergence:
            multiplier = 2.0
        elif cross_asset or exited_cross:
            multiplier = 1.5
        else:
            multiplier = 1.0

        # D-0066: spread_score is gone from the sum. See the note on
        # DIMENSION 4 above - it could not fire for any country.
        raw_score = tic_score + gold_score + monetary_score + petro_score + cds_score
        composite_score = raw_score * multiplier

        # Don't skip EXITED countries even if raw score is low —
        # tic_score will be set after signals block if no_tic_holdings
        if composite_score == 0 and not no_tic_holdings:
            continue

        if composite_score >= 75:
            tier = "CRISIS"
        elif composite_score >= 50:
            tier = "STRESSED"
        elif composite_score >= 25:
            tier = "ELEVATED"
        else:
            tier = "WATCH"

        # ── ACTIVE SIGNALS ─────────────────────────────────────────────────
        signals = []
        if no_tic_holdings and gold_tonnes and gold_tonnes >= 50:
            signals.append(f"🚨 EXITED: Zero US Treasuries · {gold_tonnes:.0f}t gold")
        elif tic_state == BELOW_THRESHOLD:
            # F-0097. This used to read "EXITED: Zero US Treasuries" for
            # Germany, holding $103.1bn. Naming the last reported figure and its
            # date is the whole difference between a fact and a fabrication.
            signals.append(describe(tic_state, tic_last_bn, tic_last_date))
        elif tic_state in (NO_DATA, NEVER_HELD):
            signals.append(describe(tic_state, tic_last_bn, tic_last_date, tic_peak_bn))
        if exited_cross:
            signals.append("⚠ EXITED + gold selling — maximum de-dollarization stress")
        if selling_tic and tic_consec >= 3:
            signals.append(f"T-bills: {tic_consec}mo consecutive ↓")
        elif selling_tic:
            signals.append(f"T-bills: {tic_mom:+.1f}% MoM")
        if selling_gold:
            signals.append(f"Gold selling: {gold_mom:+.1f}% QoQ" if gold_mom else "Gold declining")
        if m2_growth_pct and m2_growth_pct > 15:
            # Named as not scored when it is not scored. A signal that reads
            # identically whether or not it contributed is how a reader adds up
            # the narrative and gets a different number from the score.
            suffix = " - too old to score" if m2_stale else ""
            signals.append(f"M2 growth: {m2_growth_pct:.0f}% YoY ({m2_year}){suffix}")
        if spread_bps and spread_bps > 50:
            signals.append(f"Spread: +{spread_bps:.0f}bps vs US")
        if spread_widening and spread_widening > 30:
            signals.append(f"Spread widening: +{spread_widening:.0f}bps (3M)")
        if oil_signal:
            signals.append(f"🛢 {oil_signal}")
        if cds_data["signal"]:
            signals.append(f"⚑ {cds_data['signal']}")
        if divergence:
            signals.append("⚡ DIVERGENCE: selling gold into rising price")
        elif cross_asset:
            signals.append("⚠ Cross-asset: selling T-bills + gold")

        # Skip countries with no signals at all
        if not signals and composite_score == 0:
            continue

        # ── DIMENSION 6: Non-dollar reserve trend (TRESEG) ────────────────
        treseg = get_treseg_signal(db, iso, no_tic_holdings)

        # Boost score if exited TIC AND rebuilding non-gold reserves
        # (active de-dollarization into alternative system)
        if no_tic_holdings and treseg["signal"] == "REBUILDING":
            signals.append(f"⚡ Non-$ reserves rebuilding: +{treseg['trend_pct']}% YoY (de-dollarization)")
            composite_score = min(composite_score * 1.2, 150)  # 20% boost, capped at 150
        elif no_tic_holdings and treseg["signal"] == "DEPLETING":
            signals.append(f"⚠ Non-$ reserves depleting: {treseg['trend_pct']}% YoY (distress)")

        results.append({
            "country_iso": iso,
            "country_name": country.name,
            "region": country.region,
            # Treasury
            "tic_holdings_bn": round(float(tic_hist[-1].value), 2) if tic_hist else 0,
            "tic_mom_pct": round(tic_mom, 2) if tic_mom is not None else None,
            "tic_consecutive_months": tic_consec,
            "tic_score": round(tic_score, 1),
            "no_tic_holdings": no_tic_holdings,
            # Gold
            "gold_tonnes": round(gold_tonnes, 1) if gold_tonnes else None,
            "gold_mom_pct": round(gold_mom, 2) if gold_mom is not None else None,
            "gold_consecutive_quarters": gold_consec,
            "gold_score": round(gold_score, 1),
            # Monetary
            "m2_growth_pct": round(m2_growth_pct, 1) if m2_growth_pct is not None else None,
            "m2_year": m2_year,
            "m2_stale": m2_stale,
            **treasury_flows(db, country.id, tic_latest),
            **mag_detail,
            "gold_stale": gold_stale,
            **(lambda avail: {
                "available_points": avail,
                "score_pct_of_available": (
                    round(raw_score / avail * 100, 1) if avail else None
                ),
            })(available_points(
                tic_state, gold_tonnes, gold_stale, m2_stale, m2_year,
                cds_data.get("coverage"),
            )),
            "tic_state": tic_state,
            "tic_last_reported_bn": round(tic_last_bn, 1) if tic_last_bn is not None else None,
            "tic_last_reported_date": tic_last_date.date().isoformat() if tic_last_date else None,
            "monetary_score": round(monetary_score, 1),
            # Spread
            "spread_bps": spread_bps,
            "spread_widening_bps": spread_widening,
            # Petrodollar
            "oil_dependent": oil_dependent,
            "oil_signal": oil_signal,
            "brent_3m_pct": brent.get("change_3m_pct"),
            "brent_price": brent.get("latest_price"),
            "petro_score": round(petro_score, 1),
            # Sovereign CDS (Dimension 7)
            "cds_5y": cds_data["cds_5y"],
            "cds_10y": cds_data["cds_10y"],
            "cds_term_spread": cds_data["term_spread"],
            "cds_widening_pct": cds_data["widening_pct"],
            "cds_score": round(cds_score, 1),
            # F-0074: why there is no number, when there is no number. The UI
            # otherwise cannot tell "nobody quotes this country" from "the
            # quote we had was months old and we refused it".
            "cds_coverage": cds_data.get("coverage"),
            "cds_coverage_10y": cds_data.get("coverage_10y"),
            # Non-dollar reserves (TRESEG)
            "treseg_signal": treseg["signal"],
            "treseg_trend_pct": treseg["trend_pct"],
            "treseg_latest_bn": treseg["latest_bn"],
            # Multipliers & totals
            "multiplier": multiplier,
            "raw_score": round(raw_score, 1),
            "composite_score": round(composite_score, 1),
            "tier": tier,
            # Flags
            "selling_treasuries": selling_tic,
            "selling_gold": selling_gold,
            "cross_asset": cross_asset,
            "divergence": divergence,
            "active_signals": signals,
            # Context
            "spot_gold_price": spot.get("latest_price"),
            "spot_gold_rising": spot_rising,
            "as_of": tic_latest.strftime("%Y-%m"),
        })

    results.sort(key=lambda x: x["composite_score"], reverse=True)

    crisis = [r for r in results if r["tier"] == "CRISIS"]
    stressed = [r for r in results if r["tier"] == "STRESSED"]
    elevated = [r for r in results if r["tier"] == "ELEVATED"]
    watch = [r for r in results if r["tier"] == "WATCH"]

    return {
        "crisis": crisis,
        "stressed": stressed,
        "elevated": elevated,
        "watch": watch,
        "summary": {
            "crisis": len(crisis),
            "stressed": len(stressed),
            "elevated": len(elevated),
            "watch": len(watch),
            "total": len(results),
            "highest_risk": results[0] if results else None,
            "us_10y_yield": us_10y,
            "brent_price": brent.get("latest_price"),
            "brent_3m_pct": brent.get("change_3m_pct"),
            "brent_source": brent.get("source"),
            "countries_with_spread_data": len([r for r in results if r["spread_bps"] is not None]),
            "countries_with_cds_data": len([r for r in results if r["cds_5y"] is not None]),
            "oil_dependent_countries": len([r for r in results if r["oil_dependent"]]),
            # D-0079 / A-0019 option 2. A SYSTEM-LEVEL series, reported once.
            # SLT Table 5 folds every holder outside its twenty into one "All
            # Other" row, so the non-reporters' combined position is knowable
            # even though no individual position is. It is in `summary` rather
            # than on each country precisely so it cannot be read as a finding
            # about one - that would be F-0097 again, a number nobody observed
            # asserted about a named sovereign.
            "all_other": all_other_signal(db),
            # D-0080. The other cut of the same total: what CENTRAL BANKS are
            # doing, across every holder rather than only the unnamed ones.
            # System-level for the same reason - it describes a group.
            "foreign_official": foreign_official_signal(db),
        },
        "as_of": tic_latest.strftime("%Y-%m") if tic_latest else None,
    }


# ── TRESEG country mapping ────────────────────────────────────────────────────
TRESEG_MAP = {
    "CHN": "TRESEGCNM052N",
    "JPN": "TRESEGJPM052N",
    "RUS": "TRESEGRUM052N",
    "IND": "TRESEGINM052N",
    "TUR": "TRESEGTRM052N",
    "DEU": "TRESEGDEM052N",
    "FRA": "TRESEGFRM052N",
    "GBR": "TRESEGGBM052N",
    "SAU": "TRESEGSAM052N",
    "BRA": "TRESEGBRM052N",
    "USA": "TRESEGUSM052N",
    "IDN": "TRESEGIDM052N",
}


# ── DIMENSION 1 MAGNITUDE (D-0084) ──────────────────────────────────────────
#
# Replaces `min(30, abs(month-on-month %) * 3)`, which had three defects
# measured in F-0099 and A-0021:
#
#   1. It read a single month, and a liquidation spread over a quarter is
#      invisible in any one of them. Japan's bill sales were May and June; by
#      July it was buying back.
#   2. It read the TOTAL position, so a move confined to the bill book - where
#      a sovereign raises dollars first - was diluted to nothing. Japan sold
#      **54% of its short-term book** in two months while its total moved 8%.
#   3. It scaled by the proportion of a country's own position, so $1bn of
#      selling was worth 0.27 points to Japan and 90.91 to Uruguay.
#
# Every constant below was fitted against the real 13-month Table 3 history
# rather than chosen, and the before/after across all 60 countries is in
# `docs/decisions.md` under D-0084.

# A 20% fall in the total position over three months earns the full magnitude.
# Observed range across 60 countries: South Africa -19.7% is the worst.
TOT_PCT_PER_POINT = 1.5

# A 50% drawdown in the bill book - "the majority", the user's threshold - earns
# the full magnitude. Japan -48%, Norway -49%, Thailand -39%.
ST_PCT_PER_POINT = 0.6

# Below this a bill book is rolling, not being liquidated.
ST_MIN_DRAWDOWN_PCT = 15.0

# A $0.2bn book halving is noise, not a liquidation.
ST_MIN_BOOK_BN = 1.0

# The size weight. 1.0x for a country holding nothing, rising to 1.5x at a 10%
# share of all foreign holdings - Japan is 11.9% and so is capped at 1.5x.
#
# Deliberately gentle and deliberately capped. Proportion still leads: the user's
# judgement is that the percentage move matters more than the dollar size, and a
# weight large enough to let Japan outrank a small country on dollars alone would
# invert that. This modifies; it does not drive.
SIZE_WEIGHT_MAX = 1.5
SIZE_WEIGHT_FULL_SHARE_PCT = 10.0

MAGNITUDE_CAP = 30.0


def _pct_change(new, old):
    return None if not old else (new - old) / old * 100


def treasury_magnitude(tot_series, st_series, net_3m, val_3m, global_total):
    """Dimension 1's magnitude term, and why it landed where it did.

    Returns `(points, detail)`. `detail` names the basis so the surface can say
    what the score was built from rather than presenting a bare number.
    """
    detail = {
        "tic_3m_pct": None, "tic_st_drawdown_pct": None,
        "tic_magnitude_basis": "none", "tic_price_driven": False,
    }
    if len(tot_series) < 4:
        return 0.0, detail

    tot_3m = _pct_change(tot_series[-1], tot_series[-4])
    detail["tic_3m_pct"] = round(tot_3m, 2) if tot_3m is not None else None

    # A-0021 option 2, accepted on the condition that it makes the picture more
    # reliable. Measured: of 31 countries whose position fell over three months,
    # 19 fell for reasons other than selling, and five of those were net BUYERS
    # - Sweden, Hong Kong, Italy, Brazil, Australia. Japan, China, Germany and
    # France are all kept, their declines being 84-93% transactions.
    #
    # Two ways a fall is not selling: the country bought on net anyway, or the
    # valuation swing was larger than the transactions.
    price_driven = net_3m is None or net_3m >= 0 or abs(val_3m or 0) > abs(net_3m)
    detail["tic_price_driven"] = bool(price_driven)

    mag_total = 0.0
    if tot_3m is not None and tot_3m < 0 and not price_driven:
        mag_total = min(MAGNITUDE_CAP, abs(tot_3m) * TOT_PCT_PER_POINT)

    # The bill book. Not suppressed for price, because bills are short enough
    # that valuation barely moves them - a drawdown here is a quantity change,
    # which is what makes it the cleaner distress signal.
    mag_st = 0.0
    if len(st_series) >= 4 and max(st_series[-4:]) >= ST_MIN_BOOK_BN:
        peak = max(st_series[-4:])
        drawdown = _pct_change(st_series[-1], peak)
        # Gated twice. A bill book shrinking while the TOTAL position grows is a
        # rotation into duration (Finland: total +19.5%, bills -30.8%), and a net
        # buyer did not raise dollars (Brazil +$1.3bn, Hong Kong +$5.2bn).
        if (drawdown is not None and drawdown <= -ST_MIN_DRAWDOWN_PCT
                and tot_3m is not None and tot_3m <= 0
                and net_3m is not None and net_3m < 0):
            detail["tic_st_drawdown_pct"] = round(drawdown, 1)
            mag_st = min(MAGNITUDE_CAP, abs(drawdown) * ST_PCT_PER_POINT)

    raw = max(mag_total, mag_st)
    if raw <= 0:
        return 0.0, detail

    share = (tot_series[-1] / global_total * 100) if global_total else 0.0
    weight = 1 + min(1.0, share / SIZE_WEIGHT_FULL_SHARE_PCT) * (SIZE_WEIGHT_MAX - 1)

    detail["tic_magnitude_basis"] = (
        "short-term liquidation" if mag_st > mag_total else "total position"
    )
    return min(MAGNITUDE_CAP, raw * weight), detail


def _series_values(db, metric, country_id, latest, days):
    """Ascending values for one metric and country inside a window."""
    if metric is None or latest is None:
        return []
    rows = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == country_id,
        TimeSeries.date >= latest - timedelta(days=days),
    ).order_by(TimeSeries.date.asc()).all()
    return [float(r.value) for r in rows]


def _sum_recent(db, metric, country_id, latest, months):
    """Sum of the last `months` observations, or None when there are none."""
    vals = _series_values(db, metric, country_id, latest, days=months * 32)
    return sum(vals[-months:]) if vals else None


def treasury_flows(db: Session, country_id: int, tic_latest) -> dict:
    """Where a country's change in Treasury holdings came from.

    `D-0083` / `A-0021`. Dimension 1 scores the change in HOLDINGS, which moves
    with transactions and with price. Japan's July 2026: holdings -$12.7bn, net
    transactions **+$0.9bn**, long-term valuation -$12.1bn. A net buyer, scored
    as a seller.

    Read-only; it scores nothing. `A-0021` records why switching the input is
    not a one-line change: across 3,192 country-months the position change and
    the published flows disagree by more than 10% of the move **65% of the
    time**, and France's July 2026 carries a -$28.9bn residual that neither
    transactions nor valuation explain.
    """
    net_metric = db.query(Metric).filter_by(code="TIC_UST_NET_SALES").first()
    val_metric = db.query(Metric).filter_by(code="TIC_UST_LT_VALUATION").first()
    if not net_metric or not tic_latest:
        return {}

    since = tic_latest - timedelta(days=95)

    def window(metric):
        if metric is None:
            return []
        return db.query(TimeSeries).filter(
            TimeSeries.metric_id == metric.id,
            TimeSeries.country_id == country_id,
            TimeSeries.date >= since,
        ).order_by(TimeSeries.date.asc()).all()

    nets = window(net_metric)
    if not nets:
        return {}
    vals = window(val_metric)

    latest_net = float(nets[-1].value) if nets[-1].date == tic_latest else None
    latest_val = next((float(v.value) for v in vals if v.date == tic_latest), None)

    return {
        "tic_net_1m_bn": round(latest_net, 1) if latest_net is not None else None,
        "tic_valuation_1m_bn": round(latest_val, 1) if latest_val is not None else None,
        "tic_net_3m_bn": round(sum(float(n.value) for n in nets[-3:]), 1),
        "tic_flow_months": len(nets[-3:]),
    }


def get_treseg_signal(db: Session, iso: str, no_tic: bool) -> dict:
    """
    Get total reserves ex-gold trend for a country.
    Returns signal: REBUILDING / DEPLETING / STABLE / NO_DATA
    Analytically significant mainly when no_tic=True (exited Treasuries).
    """
    fred_code = TRESEG_MAP.get(iso)
    if not fred_code:
        return {"signal": "NO_DATA", "trend_pct": None, "latest_bn": None}

    metric = _metrics_by_code(db).get(fred_code)
    if not metric:
        return {"signal": "NO_DATA", "trend_pct": None, "latest_bn": None}

    history = db.query(TimeSeries).filter(
        TimeSeries.metric_id == metric.id,
        TimeSeries.country_id == None,
    ).order_by(TimeSeries.date.desc()).limit(13).all()

    if len(history) < 2:
        return {"signal": "NO_DATA", "trend_pct": None, "latest_bn": None}

    latest = float(history[0].value)
    prior = float(history[min(12, len(history)-1)].value)

    if prior == 0:
        return {"signal": "NO_DATA", "trend_pct": None, "latest_bn": round(latest/1000, 1)}

    trend_pct = (latest - prior) / prior * 100

    if trend_pct > 5:
        signal = "REBUILDING"
    elif trend_pct < -5:
        signal = "DEPLETING"
    else:
        signal = "STABLE"

    return {
        "signal": signal,
        "trend_pct": round(trend_pct, 1),
        "latest_bn": round(latest / 1000, 1),
    }

# ─────────────────────────────────────────────────────────────────────────────
# ORDER-03 D3 — persist, so the endpoint is a read
# ─────────────────────────────────────────────────────────────────────────────

# F-0094. Six quarters of history, so the documented five-consecutive-quarter
# cap is reachable. It was 400 days, which holds at most five quarterly rows and
# therefore at most FOUR consecutive declines - 16 of the 20 available points,
# with the last 4 unreachable for every country. The same shape as F-0089 and
# F-0091: a threshold nobody re-derived after the arithmetic changed around it.
GOLD_WINDOW_DAYS = 600

# A-0017. Dimension 2 will not score a country whose newest gold reading is
# older than this.
#
# The per-country age report (A-0017's own diagnostic) found 33 of 98 countries
# beyond the laggard threshold and a maximum of **3,104 days** - Venezuela's
# newest reading is from 2018. Ghana was scoring **24 of 40 points** on a
# 364-day-old figure, which is dimension 2's version of F-0092: a number too old
# to describe current behaviour, scored as though it described it.
#
# 200 days, because the series has two cadences. IMF IRFCL is monthly and lands
# 28-55 days behind (D-0076); the World Gold Council backfill for the ~24
# countries IRFCL does not carry is quarterly and can legitimately be ~150 days
# old. A cutoff tight enough for the monthly feed would exclude quarterly
# reporters who are perfectly current, which is F-0089's mistake. 200 admits
# both and excludes 35 countries, exactly one of which currently scores.
#
# The other dimensions did not need one, which the same report established:
# dimension 1 is protected by its own 200-day `tic_hist` window (a country
# outside it gets neither magnitude nor persistence), dimension 3 has
# MAX_M2_DATA_AGE_YEARS (F-0092) and dimension 7 admits a quote only within
# MAX_CDS_AGE_DAYS.
MAX_GOLD_DATA_AGE_DAYS = 200

# ── D-0089 (A-0019 option 4): score out of what can actually speak ─────────
#
# The raw maximum is 165, and no country is measured on all of it. Germany's
# Treasury dimension cannot speak (`F-0097`), Ghana's gold reading is a year old
# (`A-0017`), Canada's broad money is from 2008 (`F-0092`). A score of 8.0 built
# from two dimensions and a score of 42.0 built from five are not comparable,
# and `D-0078` disclosed that without fixing it.
#
# **The rescaling this option proposed is NOT implemented, and the measurement
# is why.** Dividing the raw score by the available points and multiplying back
# to 165 makes Malta - 28 points of gold and nothing else - read **77.0, a
# CRISIS**, outranking Japan's 42.0 measured on the full model. Ghana and
# Mongolia reach STRESSED the same way. Less evidence would produce a higher
# score, which is strictly worse than the incomparability it set out to fix and
# is the same shape as `F-0097`: a number asserted where an observation is
# missing.
#
# What is implemented is the part that survives: the DENOMINATOR, and the rate.
# Malta reads 46.7% of 60 available points and Japan 25.5% of 165. Those are
# comparable and neither is inflated. Tiers stay on the absolute score, so
# nothing silently rescores.
DIMENSION_MAX = {
    "tic_score": 50,
    "gold_score": 40,
    "monetary_score": 35,
    "petro_score": 20,
    "cds_score": 20,
}


def available_points(tic_state, gold_tonnes, gold_stale, m2_stale, m2_year,
                     cds_coverage):
    """How much of the 165-point model can speak about this country.

    Mirrors `ui/src/lib/coverage.js`, which renders the same judgement. The two
    are separate because one runs in Python and one in the browser; the tests
    assert they agree on the dimensions and the maxima.
    """
    total = DIMENSION_MAX["petro_score"]  # oil price is global; always computable
    if tic_state not in ("below_threshold", "no_data"):
        total += DIMENSION_MAX["tic_score"]
    if gold_tonnes is not None and not gold_stale:
        total += DIMENSION_MAX["gold_score"]
    if m2_year is not None and not m2_stale:
        total += DIMENSION_MAX["monetary_score"]
    if cds_coverage == "quoted":
        total += DIMENSION_MAX["cds_score"]
    return total


def _last_per_quarter(rows):
    """One row per calendar quarter - the last reading in each.

    `F-0094`. Dimension 2 scores consecutive QUARTERLY declines. Feeding it
    monthly rows without collapsing them would count three monthly dips as
    three quarters. Keyed on (year, quarter) and relying on the caller's
    ascending date order, so the survivor is the latest reading in its quarter.
    """
    by_quarter = {}
    for row in rows:
        by_quarter[(row.date.year, (row.date.month - 1) // 3)] = row
    return [by_quarter[k] for k in sorted(by_quarter)]


# F-0092. Dimension 3 will not score a country whose newest broad money
# figure is older than this. The World Bank publishes year Y around the middle
# of Y+1, so in 2026 the newest available year is 2025 and a cutoff of 3 admits
# 2023, 2024 and 2025 - one full missed release of slack, and no more.
MAX_M2_DATA_AGE_YEARS = 3

# F-0097. One classifier, shared with gold_fetcher.py, because F-0047 is the
# standing example of two implementations of one idea drifting apart.
from pipelines.tic_aggregate import (  # noqa: E402
    all_other_signal, foreign_official_signal,
)
from pipelines.tic_state import (  # noqa: E402
    BELOW_THRESHOLD, EXITED, NEVER_HELD, NO_DATA,
    classify_tic_state, describe, last_reported_holding, peak_reported_holding,
)

PIPELINE_NAME = "Composite_Snapshot"


def persist_composite_snapshot(db: Session) -> dict:
    """Compute the composite score once and store the result.

    Called by the scheduler. The endpoint then serves what this wrote, instead
    of recomputing ~230 queries on every click of the COMPOSITE tab.
    """
    started = datetime.utcnow()
    try:
        result = compute_composite_stress(db)
        if "error" in result:
            raise RuntimeError(result["error"])

        countries = sum(
            len(result.get(tier, []))
            for tier in ("crisis", "stressed", "elevated", "watch")
        )
        snapshot = CompositeSnapshot(
            computed_at=started,
            country_count=countries,
            payload=json.dumps(result, default=str),
        )
        db.add(snapshot)
        db.add(UpdateLog(
            pipeline_name=PIPELINE_NAME,
            status="success",
            records_inserted=1,
            records_updated=0,
            error_message=None,
            started_at=started,
            completed_at=datetime.utcnow(),
        ))
        db.commit()
        return {"status": "success", "countries": countries,
                "computed_at": started.isoformat()}
    except Exception as exc:
        db.rollback()
        db.add(UpdateLog(
            pipeline_name=PIPELINE_NAME,
            status="failed",
            records_inserted=0,
            records_updated=0,
            error_message=str(exc)[:480],
            started_at=started,
            completed_at=datetime.utcnow(),
        ))
        db.commit()
        raise


def latest_composite_snapshot(db: Session):
    """Most recent stored result, or None if the job has never run."""
    return (
        db.query(CompositeSnapshot)
        .order_by(CompositeSnapshot.computed_at.desc())
        .first()
    )
