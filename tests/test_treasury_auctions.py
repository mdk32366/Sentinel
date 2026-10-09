"""ORDER auction-demand §8a — Treasury auction demand, backend.

Offline against `tests/fixtures/auctions/`, verbatim records from Fiscal Data's
`auctions_query` captured 2026-10-08 (`D-0098`). The one live check, §8a-10,
is skipped unless `SENTINEL_LIVE_TESTS=1`. Principle 5: a test that needs the
real world is a different kind of check, and the gate must not depend on a
third party being up.

The load-bearing rule is §2: Treasury's bid-to-cover excludes SOMA, the API's
totals include it, and a ratio computed on the totals is well-formed,
plausible and wrong (2.62 for a bill whose true figure is 2.76).
"""
import datetime
import json
import os
import unittest
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database.connection import get_db
from database.models import Base, TreasuryAuction, UpdateLog
from pipelines import auction_demand as demand
from pipelines import treasury_auctions as auctions

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "auctions" / "auctions_query_2026-10-08.json"
)
RECORDS = json.loads(FIXTURE.read_text(encoding="utf-8"))["data"]

AMOUNT_FIELDS = (
    "offering_amt", "total_tendered", "total_accepted", "soma_tendered",
    "soma_accepted", "comp_tendered", "comp_accepted", "noncomp_accepted",
    "fima_noncomp_tendered", "fima_noncomp_accepted",
    "primary_dealer_tendered", "primary_dealer_accepted",
    "direct_bidder_tendered", "direct_bidder_accepted",
    "indirect_bidder_tendered", "indirect_bidder_accepted",
)


def record(cusip, auction_date):
    return next(
        r for r in RECORDS if r["cusip"] == cusip and r["auction_date"] == auction_date
    )


GOLDEN = record("912797VH7", "2026-06-15")


def session():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def as_dict(row):
    skip = {"id", "ingested_at", "updated_at"}
    return {c.name: getattr(row, c.name) for c in row.__table__.columns if c.name not in skip}


class GoldenFixture(unittest.TestCase):
    """§8a-1. Worked from Treasury's own release for the 26-week bill."""

    def setUp(self):
        self.row = auctions.parse_record(GOLDEN)

    def test_recomputed_bid_to_cover(self):
        self.assertAlmostEqual(float(self.row["b2c_recomputed"]), 2.7573, delta=1e-4)

    def test_reported_bid_to_cover_and_check(self):
        self.assertEqual(self.row["b2c_reported"], Decimal("2.76"))
        self.assertEqual(self.row["b2c_check"], "ok")

    def test_bidder_shares(self):
        self.assertAlmostEqual(float(self.row["primary_dealer_share"]), 0.23327, delta=1e-5)
        self.assertAlmostEqual(float(self.row["direct_bidder_share"]), 0.06565, delta=1e-5)
        self.assertAlmostEqual(float(self.row["indirect_bidder_share"]), 0.70108, delta=1e-5)

    def test_shares_sum_to_one(self):
        total = sum(
            self.row[k] for k in
            ("primary_dealer_share", "direct_bidder_share", "indirect_bidder_share")
        )
        self.assertAlmostEqual(float(total), 1.0, delta=1e-6)
        self.assertEqual(self.row["shares_check"], "ok")

    def test_the_a0025_identity_holds(self):
        # total - SOMA == competitive + non-competitive + FIMA, tendered side.
        self.assertEqual(self.row["identity_check"], "ok")


class SomaTrap(unittest.TestCase):
    """§8a-2. SOMA inclusion is caught by name."""

    def test_recomputed_bid_to_cover_is_not_the_soma_inclusive_ratio(self):
        row = auctions.parse_record(GOLDEN)
        self.assertIsNotNone(row["b2c_recomputed"])
        soma_inclusive = Decimal(GOLDEN["total_tendered"]) / Decimal(GOLDEN["total_accepted"])
        self.assertAlmostEqual(float(soma_inclusive), 2.62, delta=0.005)
        self.assertNotAlmostEqual(float(row["b2c_recomputed"]), 2.62, delta=0.05)
        self.assertGreater(float(row["b2c_recomputed"]), 2.7)

    def test_a_reported_value_that_includes_soma_is_a_mismatch_not_a_rounding(self):
        tampered = dict(GOLDEN, bid_to_cover_ratio="2.620000")
        row = auctions.parse_record(tampered)
        self.assertEqual(row["b2c_check"], "mismatch")
        # Both stored; neither silently chosen.
        self.assertEqual(row["b2c_reported"], Decimal("2.62"))
        self.assertAlmostEqual(float(row["b2c_recomputed"]), 2.7573, delta=1e-4)


class TwoPathAgreement(unittest.TestCase):
    """§8a-3. Over the full fixture: every row with both values is ok or an
    explicit mismatch, and nothing is ok with a delta over 0.01."""

    def test_every_comparable_row_is_ok_or_mismatch(self):
        rows = [r for r in map(auctions.parse_record, RECORDS) if r is not None]
        self.assertGreater(len(rows), 40)
        comparable = [
            r for r in rows
            if r["b2c_reported"] is not None and r["b2c_recomputed"] is not None
        ]
        self.assertGreater(len(comparable), 40)
        for r in comparable:
            self.assertIn(r["b2c_check"], ("ok", "mismatch"), r["cusip"])
            if r["b2c_check"] == "ok":
                delta = abs(r["b2c_recomputed"] - r["b2c_reported"])
                self.assertLessEqual(delta, Decimal("0.01"), r["cusip"])

    def test_a_mismatch_is_surfaced_in_the_ingest_summary_and_the_log(self):
        db = session()
        tampered = dict(GOLDEN, bid_to_cover_ratio="2.620000")
        result = auctions.run_treasury_auctions_fetch(db, fetch=lambda start: [tampered])
        self.assertEqual(len(result["mismatches"]), 1)
        self.assertIn("912797VH7", result["mismatches"][0])
        log = db.query(UpdateLog).filter_by(pipeline_name=auctions.PIPELINE_NAME).one()
        self.assertIn("912797VH7", log.error_message or "")
        stored = db.query(TreasuryAuction).one()
        self.assertEqual(stored.b2c_check, "mismatch")


class Units(unittest.TestCase):
    """§8a-4. The source is whole dollars (D-0098); nothing is rescaled."""

    def test_a_known_release_parses_to_exact_dollars(self):
        row = auctions.parse_record(GOLDEN)
        self.assertEqual(row["offering_amt"], Decimal("77000000000"))
        self.assertEqual(row["total_tendered"], Decimal("218768419200"))
        self.assertEqual(row["total_accepted"], Decimal("83455419200"))
        self.assertEqual(row["soma_accepted"], Decimal("6455051600"))
        # The §2 subtotal, excluding SOMA, exactly.
        self.assertEqual(row["total_tendered"] - row["soma_tendered"], Decimal("212313367600"))
        self.assertEqual(row["total_accepted"] - row["soma_accepted"], Decimal("77000367600"))


class Nulls(unittest.TestCase):
    """§8a-5 and §3. Absent is a category, never a zero."""

    PRE_SOMA = ("912795C58", "2008-01-02")

    def test_every_null_encoding_parses_to_null_with_a_reason(self):
        for encoding in ("null", "", None):
            rec = dict(GOLDEN, soma_tendered=encoding)
            if encoding is None:
                del rec["soma_tendered"]
            row = auctions.parse_record(rec)
            self.assertIsNone(row["soma_tendered"], repr(encoding))
            self.assertIn("soma_tendered", row["null_reasons"], repr(encoding))

    def test_no_missing_amount_parses_to_zero(self):
        checked = 0
        for rec in RECORDS:
            row = auctions.parse_record(rec)
            if row is None:
                continue
            for field in AMOUNT_FIELDS:
                if rec[field] == "null":
                    checked += 1
                    self.assertIsNone(row[field], f"{rec['cusip']} {field}")
                    self.assertIn(field, row["null_reasons"])
        self.assertGreater(checked, 20)

    def test_missing_soma_makes_the_recompute_unverifiable_not_zero_soma(self):
        row = auctions.parse_record(record(*self.PRE_SOMA))
        self.assertIsNone(row["b2c_recomputed"])
        self.assertEqual(row["null_reasons"]["b2c_recomputed"], "soma_not_reported")
        self.assertEqual(row["b2c_check"], "unverifiable")
        self.assertEqual(row["identity_check"], "unverifiable")

    def test_a_share_with_a_missing_input_is_null(self):
        row = auctions.parse_record(record(*self.PRE_SOMA))
        for share in ("primary_dealer_share", "direct_bidder_share", "indirect_bidder_share"):
            self.assertIsNone(row[share])
            self.assertEqual(row["null_reasons"][share], "input_missing")
        self.assertEqual(row["shares_check"], "unverifiable")

    def test_a_share_gap_is_stored_and_flagged_not_forced(self):
        # F-0112 / D-0104.
        row = auctions.parse_record(record("912795L66", "2009-01-26"))
        self.assertEqual(row["shares_check"], "gap")
        self.assertEqual(row["bidder_gap"], Decimal("10000000"))
        total = row["primary_dealer_share"] + row["direct_bidder_share"] + row["indirect_bidder_share"]
        self.assertAlmostEqual(float(total), 0.99962, delta=1e-5)

    def test_an_announced_auction_with_no_results_is_pending_not_stored(self):
        pending = [r for r in RECORDS if r["auction_date"] == "2026-10-13"]
        self.assertEqual(len(pending), 3)
        for rec in pending:
            self.assertIsNone(auctions.parse_record(rec))
        result = auctions.ingest_records(session(), pending)
        self.assertEqual(result["pending"], 3)
        self.assertEqual(result["inserted"], 0)


class TermGroups(unittest.TestCase):
    """D-0103. FRNs and TIPS are filed as Notes; reopenings carry odd terms."""

    def group(self, cusip, auction_date):
        return auctions.parse_record(record(cusip, auction_date))["term_group"]

    def test_a_bill_groups_by_its_own_term_even_when_reopened(self):
        self.assertEqual(self.group("912797VH7", "2026-09-14"), "13-Week")

    def test_a_coupon_reopening_groups_by_its_original_term(self):
        self.assertEqual(self.group("912828JR2", "2009-01-08"), "10-Year")

    def test_tips_and_frns_are_their_own_families(self):
        # D-0105. Filed by original term, apart from the nominal window.
        self.assertEqual(self.group("912828WK2", "2014-01-29"), "FRN 2-Year")
        self.assertEqual(self.group("912828HN3", "2008-01-10"), "TIPS 10-Year")

    def test_the_families_are_never_charted(self):
        charted = set(demand.CHARTED_TERMS.values())
        for cusip, day in (("912828WK2", "2014-01-29"), ("912828HN3", "2008-01-10")):
            self.assertNotIn(self.group(cusip, day), charted)
        self.assertIsNone(self.group("912795D81", "2008-02-13"))  # CMB: no family


class Idempotence(unittest.TestCase):
    """§8a-6. Re-running a full ingest changes nothing."""

    def test_ingesting_twice_yields_identical_rows(self):
        db = session()
        first = auctions.ingest_records(db, RECORDS)
        snapshot = sorted(
            (as_dict(r) for r in db.query(TreasuryAuction).all()),
            key=lambda d: (d["cusip"], d["auction_date"]),
        )
        second = auctions.ingest_records(db, RECORDS)
        again = sorted(
            (as_dict(r) for r in db.query(TreasuryAuction).all()),
            key=lambda d: (d["cusip"], d["auction_date"]),
        )
        self.assertEqual(first["inserted"], len(RECORDS) - 3)
        self.assertEqual(second["inserted"], 0)
        self.assertEqual(second["updated"], 0)
        self.assertEqual(len(again), len(snapshot))
        self.assertEqual(again, snapshot)


class Rederivation(unittest.TestCase):
    """D-0105. A change to how a row is derived must reach rows already
    stored, even though the source record itself has not changed."""

    def test_a_row_from_an_older_parser_is_rewritten(self):
        db = session()
        auctions.ingest_records(db, [GOLDEN])
        row = db.query(TreasuryAuction).one()
        row.term_group = "stale"
        row.parser_version = getattr(auctions, "PARSER_VERSION", 1) - 1
        db.commit()
        result = auctions.ingest_records(db, [GOLDEN])
        self.assertEqual(result["updated"], 1)
        self.assertEqual(db.query(TreasuryAuction).one().term_group, "26-Week")

    def test_a_current_row_is_left_alone(self):
        db = session()
        auctions.ingest_records(db, [GOLDEN])
        self.assertEqual(auctions.ingest_records(db, [GOLDEN])["unchanged"], 1)


class Reopenings(unittest.TestCase):
    """§8a-7. Same CUSIP, different dates, two rows."""

    def test_the_golden_cusip_and_its_reopening_are_two_rows(self):
        db = session()
        auctions.ingest_records(db, RECORDS)
        rows = db.query(TreasuryAuction).filter_by(cusip="912797VH7").all()
        self.assertEqual(
            sorted(r.auction_date for r in rows),
            [datetime.date(2026, 6, 15), datetime.date(2026, 9, 14)],
        )


def series(group, values, start=datetime.date(2020, 1, 6)):
    return [
        {
            "term_group": group,
            "auction_date": start + datetime.timedelta(weeks=i),
            "cusip": f"{group[:2]}{i:07d}",
            "b2c_recomputed": None if v is None else Decimal(str(v)),
            "primary_dealer_share": None if v is None else Decimal(str(v)) / 10,
        }
        for i, v in enumerate(values)
    ]


class ZScoreWindow(unittest.TestCase):
    """§8a-8 and D-0099."""

    def test_the_rulings_are_the_ones_logged(self):
        self.assertEqual(demand.WINDOW_N, 26)
        self.assertEqual(demand.MIN_OBSERVATIONS, 8)

    def test_fewer_than_the_minimum_is_null_insufficient_history(self):
        rows = demand.attach_zscores(series("13-Week", [2.0, 2.5] * 4 + [3.0]))
        eighth, ninth = rows[7], rows[8]
        self.assertIsNone(eighth["b2c_z"])
        self.assertEqual(eighth["b2c_z_reason"], "insufficient_history")
        self.assertEqual(eighth["b2c_z_window"], 7)
        self.assertIsNotNone(ninth["b2c_z"])
        self.assertEqual(ninth["b2c_z_window"], 8)

    def test_the_window_is_the_previous_26_and_excludes_the_auction_itself(self):
        values = [9.0] * 4 + [2.0, 3.0] * 13 + [2.5]
        rows = demand.attach_zscores(series("13-Week", values))
        last = rows[-1]
        self.assertEqual(last["b2c_z_window"], 26)
        # Mean of the 26 before it is 2.5, so the 9.0s fell outside the window.
        self.assertAlmostEqual(last["b2c_z"], 0.0, places=9)
        # The band the panel draws is this window, from here, not recomputed
        # in JavaScript (one window rule, not two: F-0047).
        mean, sd = last.get("b2c_window_mean"), last.get("b2c_window_sd")
        self.assertIsInstance(mean, float, "no window mean on the row")
        self.assertIsInstance(sd, float, "no window sd on the row")
        self.assertAlmostEqual(mean, 2.5, places=9)
        self.assertAlmostEqual(sd, 0.5099019513592785, places=9)

    def test_a_window_too_short_to_score_has_no_band(self):
        rows = demand.attach_zscores(series("13-Week", [2.0, 2.5, 3.0]))
        self.assertIsNone(rows[-1].get("b2c_window_mean", "absent"))
        self.assertIsNone(rows[-1].get("b2c_window_sd", "absent"))

    def test_nulls_are_skipped_and_the_window_reports_what_it_used(self):
        values = [2.0, None, 2.5, None, 3.0, 2.0, 2.5, 3.0, 2.0, 2.5, 3.0]
        last = demand.attach_zscores(series("13-Week", values))[-1]
        self.assertEqual(last["b2c_z_window"], 8)
        self.assertIsNotNone(last["b2c_z"])

    def test_a_26_week_bill_never_enters_a_13_week_window(self):
        thirteen = series("13-Week", [2.0, 2.5] * 5)
        twenty_six = series("26-Week", [50.0] * 10, start=datetime.date(2020, 1, 7))
        rows = demand.attach_zscores(thirteen + twenty_six)
        last_13 = [r for r in rows if r["term_group"] == "13-Week"][-1]
        self.assertEqual(last_13["b2c_z_window"], 9)
        self.assertLess(abs(last_13["b2c_z"]), 2)
        last_26 = [r for r in rows if r["term_group"] == "26-Week"][-1]
        self.assertIsNone(last_26["b2c_z"])
        self.assertEqual(last_26["b2c_z_reason"], "zero_variance")

    def test_the_dealer_share_z_uses_the_same_window(self):
        rows = demand.attach_zscores(series("13-Week", [2.0, 2.5] * 5))
        self.assertEqual(rows[-1]["dealer_z_window"], 9)
        self.assertEqual(rows[-1]["dealer_z_window"], rows[-1]["b2c_z_window"])
        self.assertIsNotNone(rows[-1]["dealer_z"])

    def test_a_row_with_no_term_family_gets_no_zscore(self):
        # Only cash-management bills have no family (D-0105).
        rows = demand.attach_zscores(series("13-Week", [2.0] * 3) + [dict(
            term_group=None, auction_date=datetime.date(2020, 3, 1), cusip="CMB",
            b2c_recomputed=Decimal("3"), primary_dealer_share=Decimal("0.3"),
        )])
        cmb = rows[-1]
        self.assertIsNone(cmb["b2c_z"])
        self.assertEqual(cmb["b2c_z_reason"], "no_term_family")


class DemandSignal(unittest.TestCase):
    """D-0107. Weak demand is low cover AND dealers left holding the issue.

    Measured over 4,557 scored auctions in the ten charted terms, 2008-2026:
    the alert (both) fired 1.9 times a year, the watch (either, stronger, and
    not an alert) 3.0.
    Either test alone at 2 sd fired 7 to 7.5 times a year."""

    def test_the_rulings_are_the_ones_logged(self):
        self.assertEqual(demand.ALERT_B2C_Z, -2.0)
        self.assertEqual(demand.ALERT_DEALER_Z, 2.0)
        self.assertEqual(demand.WATCH_B2C_Z, -2.5)
        self.assertEqual(demand.WATCH_DEALER_Z, 2.5)

    def test_both_together_is_an_alert_inclusive_at_the_line(self):
        self.assertEqual(demand.demand_signal("ok", -2.0, 2.0), ("alert", None))
        self.assertEqual(demand.demand_signal("ok", -3.2, 3.8), ("alert", None))

    def test_either_alone_past_the_wider_line_is_a_watch(self):
        self.assertEqual(demand.demand_signal("ok", -2.5, 0.0), ("watch", None))
        self.assertEqual(demand.demand_signal("ok", 0.0, 2.5), ("watch", None))

    def test_one_side_at_two_sd_is_nothing(self):
        self.assertEqual(demand.demand_signal("ok", -2.29, 0.46), (None, None))
        self.assertEqual(demand.demand_signal("ok", -1.94, 2.14), (None, None))

    def test_strong_demand_is_never_flagged(self):
        self.assertEqual(demand.demand_signal("ok", 3.5, -3.5), (None, None))

    def test_a_row_whose_paths_disagree_is_not_scored(self):
        self.assertEqual(
            demand.demand_signal("mismatch", -3.0, 3.0), (None, "b2c_check_mismatch")
        )

    def test_a_missing_z_is_not_scored(self):
        self.assertEqual(demand.demand_signal("ok", None, 3.0), (None, "not_scored"))
        self.assertEqual(demand.demand_signal("ok", -3.0, None), (None, "not_scored"))

    def test_every_scored_row_carries_its_signal(self):
        rows = series("13-Week", [2.6, 2.5, 2.7, 2.4, 2.6, 2.5, 2.7, 2.4, 2.6, 1.0])
        for r in rows:
            r["b2c_check"] = "ok"
        last = demand.attach_zscores(rows)[-1]
        self.assertEqual(last.get("demand_signal"), "watch")  # cover collapsed
        self.assertIn("demand_signal_reason", last)


def flagged(term, group, day, signal, b2c_z, dealer_z):
    return {
        "term": term, "term_group": group, "auction_date": day, "cusip": f"{term}{day}",
        "demand_signal": signal, "b2c_z": b2c_z, "dealer_z": dealer_z,
    }


BOARD_ROWS = [
    flagged("26W", "26-Week", "2026-03-16", "alert", -2.40, 2.46),
    flagged("26W", "26-Week", "2025-12-29", "alert", -3.01, 4.76),
    flagged("8W", "8-Week", "2026-07-23", "alert", -3.19, 3.80),
    flagged("17W", "17-Week", "2026-06-24", "watch", -3.11, 0.61),
    flagged("2Y", "2-Year", "2026-03-24", "watch", -1.86, 4.19),
    flagged("4W", "4-Week", "2026-10-08", None, -2.29, 0.46),            # not flagged
    flagged("30Y", "30-Year", "2011-08-11", "alert", -2.60, 3.27),       # outside a 1y window
    {"term": None, "term_group": "TIPS 10-Year", "auction_date": "2026-05-01",
     "cusip": "TIPS", "demand_signal": "alert", "b2c_z": -3.0, "dealer_z": 3.0},  # not charted
]


class SignalBoard(unittest.TestCase):
    """D-0108. The leaderboard: every flagged auction in a window, worst first."""

    def board(self, since="2025-10-08"):
        return demand.signal_board(BOARD_ROWS, since)

    def test_weakness_is_both_z_scores_in_the_weak_direction(self):
        self.assertAlmostEqual(demand.weakness(-2.40, 2.46), 4.86)
        self.assertIsNone(demand.weakness(None, 2.0))

    def test_alerts_rank_above_watches_then_by_weakness(self):
        order = [(r["term"], r["auction_date"]) for r in self.board()["signals"]]
        self.assertEqual(order, [
            ("26W", "2025-12-29"),   # alert, weakness 7.77
            ("8W", "2026-07-23"),    # alert, 6.99
            ("26W", "2026-03-16"),   # alert, 4.86
            ("2Y", "2026-03-24"),    # watch, 6.05
            ("17W", "2026-06-24"),   # watch, 3.72
        ])

    def test_each_row_carries_its_weakness(self):
        signals = self.board()["signals"]
        self.assertTrue(signals, "the board is empty")
        top = signals[0]
        self.assertAlmostEqual(top["weakness"], 7.77)

    def test_the_window_and_the_charted_terms_bound_it(self):
        terms = {r["term"] for r in self.board()["signals"]}
        self.assertNotIn("30Y", terms)          # 2011, before the window
        self.assertNotIn(None, terms)           # TIPS: a family, not charted
        everything = demand.signal_board(BOARD_ROWS, None)["signals"]
        self.assertIn("30Y", {r["term"] for r in everything})

    def test_counts_and_the_per_term_tally(self):
        b = self.board()
        self.assertEqual(b["counts"], {"alert": 3, "watch": 2})
        tally = {t["term"]: t for t in b["by_term"]}
        self.assertEqual(tally["26W"]["alerts"], 2)
        self.assertEqual(tally["26W"]["last_signal_date"], "2026-03-16")
        self.assertEqual(tally["2Y"]["watches"], 1)
        # Every charted term appears, flagged or not, in display order.
        self.assertEqual([t["term"] for t in b["by_term"]], list(demand.CHARTED_TERMS))
        self.assertEqual(tally["4W"]["alerts"] + tally["4W"]["watches"], 0)


class SignalBoardEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from api.routes import router

        db = session()
        auctions.ingest_records(db, RECORDS)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: db
        cls.client = TestClient(app)

    def test_the_contract(self):
        r = self.client.get("/api/auctions/signals?days=365")
        self.assertEqual(r.status_code, 200, r.text[:200])
        body = r.json()
        for key in ("data_as_of", "days", "since", "counts", "by_term", "signals"):
            self.assertIn(key, body)
        self.assertEqual(body["days"], 365)
        self.assertEqual(body["since"], "2025-09-14")   # 365 days before data_as_of

    def test_all_history_has_no_since(self):
        r = self.client.get("/api/auctions/signals?days=0")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["since"])

    def test_an_unoffered_window_is_refused(self):
        self.assertEqual(self.client.get("/api/auctions/signals?days=17").status_code, 400)


class Staleness(unittest.TestCase):
    """D-0101. More than 3 business days old is stale."""

    def test_business_days_not_calendar_days(self):
        friday = datetime.date(2026, 10, 2)
        self.assertEqual(demand.STALE_BUSINESS_DAYS, 3)
        self.assertFalse(demand.is_stale(friday, datetime.date(2026, 10, 7)))  # Wed: 3
        self.assertTrue(demand.is_stale(friday, datetime.date(2026, 10, 8)))   # Thu: 4


class ApiContracts(unittest.TestCase):
    """§8a-9. Documented fields, data_as_of, null reasons, filtering."""

    @classmethod
    def setUpClass(cls):
        from api.routes import router

        cls.db = session()
        auctions.ingest_records(cls.db, RECORDS)
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[get_db] = lambda: cls.db
        cls.client = TestClient(app)

    def get(self, path):
        r = self.client.get(path)
        self.assertEqual(r.status_code, 200, f"{path}: {r.text[:200]}")
        return r.json()

    def test_list_is_newest_first_with_data_as_of(self):
        body = self.get("/api/auctions")
        self.assertEqual(body["data_as_of"], "2026-09-14")
        dates = [a["auction_date"] for a in body["auctions"]]
        self.assertEqual(dates, sorted(dates, reverse=True))
        self.assertEqual(len(dates), len(RECORDS) - 3)

    def test_list_rows_carry_metrics_and_null_reasons(self):
        row = next(a for a in self.get("/api/auctions")["auctions"] if a["cusip"] == "912795C58")
        for field in ("b2c_reported", "b2c_recomputed", "b2c_check", "b2c_z",
                      "b2c_z_window", "b2c_z_reason", "primary_dealer_share",
                      "direct_bidder_share", "indirect_bidder_share", "dealer_z",
                      "dealer_z_window", "allocation_pct", "shares_check",
                      "term", "term_group", "null_reasons"):
            self.assertIn(field, row)
        self.assertIsNone(row["b2c_recomputed"])
        self.assertEqual(row["null_reasons"]["b2c_recomputed"], "soma_not_reported")

    def test_list_filters_by_term_type_and_date(self):
        rows = self.get("/api/auctions?term=26W")["auctions"]
        self.assertTrue(rows)
        self.assertEqual({r["term_group"] for r in rows}, {"26-Week"})
        notes = self.get("/api/auctions?type=Note")["auctions"]
        self.assertEqual({r["security_type"] for r in notes}, {"Note"})
        june = self.get("/api/auctions?from=2026-06-10&to=2026-06-15")["auctions"]
        self.assertTrue(june)
        self.assertTrue(all("2026-06-10" <= r["auction_date"] <= "2026-06-15" for r in june))

    def test_list_filters_to_a_tips_or_frn_family(self):
        rows = self.get("/api/auctions?term=FRN2Y")["auctions"]
        self.assertTrue(rows)
        self.assertEqual({r["term_group"] for r in rows}, {"FRN 2-Year"})
        self.assertEqual({r["term"] for r in rows}, {"FRN2Y"})

    def test_summary_is_latest_per_charted_term(self):
        body = self.get("/api/auctions/summary")
        self.assertEqual(body["data_as_of"], "2026-09-14")
        by_term = {t["term"]: t for t in body["terms"]}
        self.assertEqual(by_term["13W"]["auction_date"], "2026-09-14")
        self.assertEqual(by_term["26W"]["auction_date"], "2026-06-29")
        for t in body["terms"]:
            for field in ("b2c_z", "b2c_z_window", "dealer_z", "dealer_z_window", "b2c_check"):
                self.assertIn(field, t)
        self.assertTrue(set(by_term) <= set(demand.CHARTED_TERMS))

    def test_one_auction_has_the_bidder_breakdown_and_soma_marked_excluded(self):
        body = self.get("/api/auctions/912797VH7/2026-06-15")
        self.assertEqual(body["data_as_of"], "2026-09-14")
        a = body["auction"]
        self.assertEqual(a["bidders"]["primary_dealer"]["accepted"], 17490500000)
        self.assertAlmostEqual(a["bidders"]["indirect"]["share"], 0.70108, delta=1e-5)
        self.assertEqual(a["soma"]["accepted"], 6455051600)
        self.assertTrue(a["soma"]["excluded_from_b2c"])

    def test_an_unknown_auction_is_404(self):
        r = self.client.get("/api/auctions/XXXXXXXXX/2026-06-15")
        self.assertEqual(r.status_code, 404)
        # Ours, not the router's "Not Found" for a path that does not exist.
        self.assertIn("XXXXXXXXX", r.json()["detail"])


class ResponseModelsDeclareWhatIsSent(unittest.TestCase):
    """F-0101: a response_model is a filter. A key the producer sends and the
    model does not declare vanishes from the response with no error."""

    def test_every_row_key_is_declared_and_every_declared_key_is_sent(self):
        from api import schemas
        from api.routes import _scored_auctions

        db = session()
        auctions.ingest_records(db, RECORDS)
        scored, _, _ = _scored_auctions(db)
        sent = set(scored[0])
        declared = set(schemas.AuctionRow.model_fields)
        self.assertEqual(sorted(sent - declared), [], "stripped from the response")
        self.assertEqual(sorted(declared - sent), [], "declared but never sent")

    def test_the_detail_adds_only_declared_keys(self):
        from api import schemas

        body = ApiContracts.client.get("/api/auctions/912797VH7/2026-06-15").json()
        declared = set(schemas.AuctionDetail.model_fields)
        self.assertEqual(sorted(set(body["auction"]) - declared), [])
        for key in ("bidders", "soma", "comp_tendered", "noncomp_accepted"):
            self.assertIn(key, body["auction"])


class ThePanelUsesTheSameRulings(unittest.TestCase):
    """D-0101 and D-0103 live in Python and in ui/src/lib/auctions.js. A JS
    test cannot read the Python, so the comparison is made from here."""

    JS = Path(__file__).resolve().parents[1] / "ui" / "src" / "lib" / "auctions.js"

    def js(self):
        return self.JS.read_text(encoding="utf-8")

    def test_the_charted_terms_match(self):
        import re
        m = re.search(r"export const CHARTED_TERMS = \[([^\]]*)\]", self.js())
        self.assertIsNotNone(m, "CHARTED_TERMS not found in auctions.js")
        self.assertEqual(re.findall(r'"([^"]+)"', m.group(1)), list(demand.CHARTED_TERMS))

    def test_the_stale_threshold_matches(self):
        import re
        m = re.search(r"export const STALE_BUSINESS_DAYS = (\w+);", self.js())
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1), str(demand.STALE_BUSINESS_DAYS))


class Scheduling(unittest.TestCase):
    """§5. Piggybacks on the existing scheduler, daily."""

    def test_the_pipeline_is_declared_as_scheduled(self):
        from pipelines import scheduler as sched
        self.assertIn(auctions.PIPELINE_NAME, sched.SCHEDULED_PIPELINES)

    def test_the_watchdog_ages_auctions_from_their_own_table(self):
        # SCHEDULED_PIPELINES and the watchdog's CHECKS must name the same
        # pipelines (F-0091), and F-0110 is what a scheduled feed with no CHECK
        # costs: a silent drop that leaves every surface green.
        from pipelines.freshness_watchdog import get_freshness_report
        db = session()
        auctions.ingest_records(db, [GOLDEN])
        report = get_freshness_report(db)
        src = next((s for s in report["sources"] if s["key"] == "treasury_auctions"), None)
        self.assertIsNotNone(src, "no freshness CHECK for treasury auctions")
        self.assertEqual(src["latest_date"], "2026-06-15")
        self.assertEqual(src["status"], "critical")  # months old against a 5-day bound

    def test_the_first_run_backfills_from_the_ruled_start(self):
        asked = []
        auctions.run_treasury_auctions_fetch(session(), fetch=lambda start: asked.append(start) or [])
        self.assertEqual(asked, [datetime.date(2008, 1, 1)])

    def test_a_later_run_rereads_a_trailing_month_not_history(self):
        db = session()
        auctions.ingest_records(db, [GOLDEN])
        asked = []
        auctions.run_treasury_auctions_fetch(db, fetch=lambda start: asked.append(start) or [])
        self.assertEqual(asked, [datetime.date(2026, 5, 16)])


@unittest.skipUnless(
    os.environ.get("SENTINEL_LIVE_TESTS") == "1",
    "live source check; set SENTINEL_LIVE_TESTS=1 (integration, not unit)",
)
class LiveSourceIntegration(unittest.TestCase):
    """§8a-10. The API record for the golden bill matches Treasury's release."""

    def test_the_api_matches_the_press_release(self):
        live = auctions.fetch_records(datetime.date(2026, 6, 15), cusip="912797VH7")
        rec = next(r for r in live if r["auction_date"] == "2026-06-15")
        row = auctions.parse_record(rec)
        self.assertEqual(row["total_tendered"] - row["soma_tendered"], Decimal("212313367600"))
        self.assertEqual(row["total_accepted"] - row["soma_accepted"], Decimal("77000367600"))
        self.assertEqual(row["soma_tendered"], Decimal("6455051600"))
        self.assertEqual(row["b2c_reported"], Decimal("2.76"))
        self.assertEqual(row["b2c_check"], "ok")


if __name__ == "__main__":
    unittest.main()
