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

        Absolute 5Y level:
            >200 bps:   5 pts   (elevated - D-0065, was >100)
            >250 bps:  10 pts   (significant)
            >500 bps:  15 pts   (distress)
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
    if cds_5y > 500:
        score = 15
    elif cds_5y > 250:
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

    results = []
    # NOTE: Exclude USA from scoring — it's the issuer of Treasuries, not a holder.
    # TIC (Treasury International Capital) data tracks *foreign* holdings only.
    # The US having "zero holdings" is expected and not a stress signal.
    for country in db.query(Country).filter(Country.iso_code != "USA").all():
        iso = country.iso_code

        # ── DIMENSION 1: Treasury ──────────────────────────────────────────
        tic_hist = db.query(TimeSeries).filter(
            TimeSeries.metric_id == tic_metric.id,
            TimeSeries.country_id == country.id,
            TimeSeries.date >= tic_latest - timedelta(days=185),
        ).order_by(TimeSeries.date.asc()).all()

        tic_mom = 0
        tic_consec = 0
        tic_score = 0
        selling_tic = False
        no_tic_holdings = len(tic_hist) == 0

        if len(tic_hist) >= 2:
            tic_prev = float(tic_hist[-2].value)
            if tic_prev > 0:
                tic_mom = (float(tic_hist[-1].value) - tic_prev) / tic_prev * 100
                for i in range(len(tic_hist) - 1, 0, -1):
                    if float(tic_hist[i].value) < float(tic_hist[i-1].value):
                        tic_consec += 1
                    else:
                        break
                if tic_mom < 0:
                    tic_score += min(30, abs(tic_mom) * 3)
                tic_score += min(20, tic_consec * 4)
                selling_tic = tic_mom < -0.5 or tic_consec >= 2
        elif no_tic_holdings:
            # Completed Treasury liquidation — most severe de-dollarization signal.
            # Assign a strong tic_score based on gold holdings as confirmation.
            # We don't know MoM since they've already exited, so we score on posture.
            tic_score = 0  # Will be set after gold is known
            tic_mom = None
            tic_consec = 0

        # ── DIMENSION 2: Gold Reserves ─────────────────────────────────────
        gold_score = 0
        gold_mom = None
        gold_consec = 0
        gold_tonnes = None
        selling_gold = False

        if gold_metric and gold_latest:
            gold_hist = db.query(TimeSeries).filter(
                TimeSeries.metric_id == gold_metric.id,
                TimeSeries.country_id == country.id,
                TimeSeries.date >= gold_latest - timedelta(days=400),
            ).order_by(TimeSeries.date.asc()).all()

            if gold_hist:
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

        if m2_metric:
            m2_row = db.query(TimeSeries).filter(
                TimeSeries.metric_id == m2_metric.id,
                TimeSeries.country_id == country.id,
            ).order_by(TimeSeries.date.desc()).first()

            if m2_row:
                m2_growth_pct = float(m2_row.value)
                m2_year = m2_row.date.year
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
        if exited_cross:
            signals.append("⚠ EXITED + gold selling — maximum de-dollarization stress")
        if selling_tic and tic_consec >= 3:
            signals.append(f"T-bills: {tic_consec}mo consecutive ↓")
        elif selling_tic:
            signals.append(f"T-bills: {tic_mom:+.1f}% MoM")
        if selling_gold:
            signals.append(f"Gold selling: {gold_mom:+.1f}% QoQ" if gold_mom else "Gold declining")
        if m2_growth_pct and m2_growth_pct > 15:
            signals.append(f"M2 growth: {m2_growth_pct:.0f}% YoY ({m2_year})")
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
