"""CDS 5Y parser: conventional/par spread from WGB structured fields, not the coupon."""
import unittest
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base, Metric, TimeSeries
from pipelines.cds_fetcher import (
    CDS_SOURCE,
    CdsQuote,
    board_looks_like_coupon_collapse,
    cds_instrument_codes,
    get_cds_coverage,
    latest_cds_observation,
    pair_cds_tenors,
    parse_wgb_cds_payload,
    parse_wgb_cds_table,
    run_cds_fetch,
)


FIXTURES = Path(__file__).parent / "fixtures" / "cds"
WGB_BOARD = FIXTURES / "wgb_5y_board.html"
INVESTING_TRAP = FIXTURES / "investing_germany_coupon_trap.html"


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _quotes_by_name(quotes):
    return {q.country: q for q in quotes}


class TestWgbCdsParser(unittest.TestCase):
    def test_extracts_conventional_spread_not_coupon(self):
        html = WGB_BOARD.read_text(encoding="utf-8")
        quotes = parse_wgb_cds_table(html)
        by_name = _quotes_by_name(quotes)

        self.assertIn("Germany", by_name)
        de = by_name["Germany"]
        self.assertEqual(de.spread_bps, Decimal("6.99"))
        self.assertNotEqual(de.spread_bps, Decimal("500"))
        self.assertEqual(de.as_of, date(2026, 9, 1))
        self.assertEqual(de.source, CDS_SOURCE)

        # Page text also contains the ISDA 500 coupon; the 5Y column must win.
        self.assertIn("500", html)
        self.assertTrue(any(q.spread_bps == Decimal("6.99") for q in quotes))
        self.assertFalse(any(q.country == "Germany" and q.spread_bps == Decimal("500") for q in quotes))

    def test_values_under_50_bps_are_accepted(self):
        html = WGB_BOARD.read_text(encoding="utf-8")
        quotes = parse_wgb_cds_table(html)
        by_name = _quotes_by_name(quotes)
        self.assertLess(by_name["Germany"].spread_bps, Decimal("50"))
        self.assertLess(by_name["Switzerland"].spread_bps, Decimal("50"))
        self.assertEqual(by_name["Switzerland"].spread_bps, Decimal("7.00"))
        self.assertEqual(by_name["Spain"].spread_bps, Decimal("16.07"))

    def test_ig_europe_ranks_below_periphery_none_at_500(self):
        quotes = parse_wgb_cds_table(WGB_BOARD.read_text(encoding="utf-8"))
        by_name = _quotes_by_name(quotes)
        six = ["Germany", "Switzerland", "France", "Italy", "Greece", "Spain"]
        for name in six:
            self.assertIn(name, by_name)
            self.assertNotEqual(by_name[name].spread_bps, Decimal("500"))
        self.assertLess(by_name["Germany"].spread_bps, by_name["France"].spread_bps)
        self.assertLess(by_name["Switzerland"].spread_bps, by_name["Italy"].spread_bps)
        self.assertLess(by_name["Germany"].spread_bps, by_name["Greece"].spread_bps)

    def test_does_not_blanket_reject_near_500_distressed_print(self):
        quotes = parse_wgb_cds_table(WGB_BOARD.read_text(encoding="utf-8"))
        by_name = _quotes_by_name(quotes)
        self.assertEqual(by_name["Hypothetical Distressed"].spread_bps, Decimal("497.50"))

    def test_json_envelope(self):
        html = WGB_BOARD.read_text(encoding="utf-8")
        quotes = parse_wgb_cds_payload({"success": True, "table": html, "chart": "<div>500</div>"})
        self.assertGreaterEqual(len(quotes), 6)
        self.assertEqual(_quotes_by_name(quotes)["France"].spread_bps, Decimal("32.73"))

    def test_investing_coupon_trap_html_is_not_read_as_500(self):
        """Whole-page regex with a 50–3000 floor would return 500 from this HTML.

        Our parser only reads a WGB 5Y column; this Investing.com-shaped page
        has no such column, so it must not invent a 500 spread.
        """
        html = INVESTING_TRAP.read_text(encoding="utf-8")
        self.assertIn("6.99", html)
        self.assertIn("500", html)
        quotes = parse_wgb_cds_table(html)
        self.assertEqual(quotes, [])
        self.assertFalse(any(q.spread_bps == Decimal("500") for q in quotes))


class TestCouponCollapseGuard(unittest.TestCase):
    def test_flat_500_board_is_rejected(self):
        quotes = [
            CdsQuote(country=name, spread_bps=Decimal("500"), as_of=date(2026, 9, 1))
            for name in ("Germany", "France", "Italy", "Spain", "Switzerland", "Greece")
        ]
        self.assertTrue(board_looks_like_coupon_collapse(quotes))

    def test_differentiated_board_is_not_collapse(self):
        html = WGB_BOARD.read_text(encoding="utf-8")
        quotes = parse_wgb_cds_table(html)
        self.assertFalse(board_looks_like_coupon_collapse(quotes))


class TestPairCdsTenors(unittest.TestCase):
    def test_blanks_10y_when_as_of_differs(self):
        obs5 = {"value": 6.99, "date": date(2026, 9, 1), "source": CDS_SOURCE}
        obs10 = {"value": 500.0, "date": date(2026, 8, 1), "source": CDS_SOURCE}
        cds5, cds10, term = pair_cds_tenors(obs5, obs10)
        self.assertEqual(cds5, 6.99)
        self.assertIsNone(cds10)
        self.assertIsNone(term)

    def test_blanks_10y_when_source_differs(self):
        obs5 = {"value": 6.99, "date": date(2026, 9, 1), "source": CDS_SOURCE}
        obs10 = {"value": 12.0, "date": date(2026, 9, 1), "source": "Investing.com"}
        cds5, cds10, term = pair_cds_tenors(obs5, obs10)
        self.assertEqual(cds5, 6.99)
        self.assertIsNone(cds10)
        self.assertIsNone(term)

    def test_pairs_when_source_and_as_of_match(self):
        obs5 = {"value": 30.87, "date": date(2026, 9, 1), "source": CDS_SOURCE}
        obs10 = {"value": 40.1, "date": date(2026, 9, 1), "source": CDS_SOURCE}
        cds5, cds10, term = pair_cds_tenors(obs5, obs10)
        self.assertEqual(cds5, 30.87)
        self.assertEqual(cds10, 40.1)
        self.assertEqual(term, 9.2)


class TestRunCdsFetchFromFixtureBoard(unittest.TestCase):
    def test_fixture_board_writes_real_5y_not_coupon(self):
        db = _session()
        html = WGB_BOARD.read_text(encoding="utf-8")
        try:
            with patch(
                "pipelines.cds_fetcher.fetch_wgb_cds_board",
                return_value={"success": True, "table": html},
            ):
                result = run_cds_fetch(db)

            self.assertEqual(result["source"], CDS_SOURCE)
            self.assertEqual(result["as_of"], "2026-09-01")
            self.assertGreater(result["ok"], 0)
            self.assertEqual(result["status"], "partial")  # Saudi Arabia etc. not on fixture
            self.assertIn("SAUDI_ARABIA_CDS_5Y", ";".join(result["errors"]))

            de = latest_cds_observation(db, "GERMANY_CDS_5Y")
            ch = latest_cds_observation(db, "SWITZERLAND_CDS_5Y")
            fr = latest_cds_observation(db, "FRANCE_CDS_5Y")
            self.assertIsNotNone(de)
            self.assertEqual(de["value"], 6.99)
            self.assertEqual(de["date"], date(2026, 9, 1))
            self.assertEqual(de["source"], CDS_SOURCE)
            self.assertEqual(ch["value"], 7.0)
            self.assertEqual(fr["value"], 32.73)
            self.assertLess(de["value"], fr["value"])
            self.assertNotEqual(de["value"], 500)

            metric = db.query(Metric).filter_by(code="GERMANY_CDS_5Y").one()
            self.assertEqual(metric.source, CDS_SOURCE)
            self.assertIn("not the ISDA", metric.description)

            coverage = get_cds_coverage(db)
            self.assertGreater(coverage["with_data"], 0)
            self.assertEqual(coverage["last_pipeline"]["status"], "partial")
        finally:
            db.close()

    def test_all_none_when_board_empty(self):
        db = _session()
        try:
            with patch(
                "pipelines.cds_fetcher.fetch_wgb_cds_board",
                return_value={"success": True, "table": "<table></table>"},
            ):
                result = run_cds_fetch(db)
            self.assertEqual(result["ok"], 0)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(len(cds_instrument_codes()), result["attempted"])
        finally:
            db.close()

    def test_refuses_coupon_collapse_board(self):
        db = _session()
        rows = []
        for name in ("Germany", "France", "Italy", "Spain", "Switzerland", "Greece"):
            rows.append(
                f'<tr><td></td><td sorttable_customkey="{name}">{name}</td>'
                f'<td>AAA</td><td sorttable_customkey="500">500</td>'
                f'<td></td><td></td><td></td>'
                f'<td sorttable_customkey="2026-09-01">1 Sep</td></tr>'
            )
        html = (
            "<table><thead><tr><th></th><th>Country</th><th>S&P</th>"
            "<th>5Y CDS</th><th>Var 1m</th><th>Var 6m</th><th>PD</th>"
            "<th>Date</th></tr></thead><tbody>"
            + "".join(rows)
            + "</tbody></table>"
        )
        try:
            with patch(
                "pipelines.cds_fetcher.fetch_wgb_cds_board",
                return_value={"success": True, "table": html},
            ):
                result = run_cds_fetch(db)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["ok"], 0)
            self.assertTrue(any("coupon-collapse" in e for e in result["errors"]))
            self.assertIsNone(latest_cds_observation(db, "GERMANY_CDS_5Y"))
        finally:
            db.close()


class TestLatestObservationHelper(unittest.TestCase):
    def test_returns_source_and_as_of(self):
        db = _session()
        try:
            metric = Metric(
                code="GERMANY_CDS_5Y",
                name="Germany 5Y CDS",
                category="sovereign_cds",
                unit="bps",
                source=CDS_SOURCE,
            )
            db.add(metric)
            db.flush()
            db.add(TimeSeries(
                metric_id=metric.id,
                country_id=None,
                date=datetime(2026, 9, 1),
                value=Decimal("6.99"),
            ))
            db.commit()
            obs = latest_cds_observation(db, "GERMANY_CDS_5Y")
            self.assertEqual(obs["value"], 6.99)
            self.assertEqual(obs["date"], date(2026, 9, 1))
            self.assertEqual(obs["source"], CDS_SOURCE)
            self.assertIsNone(latest_cds_observation(db, "NO_SUCH_CDS_5Y"))
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
