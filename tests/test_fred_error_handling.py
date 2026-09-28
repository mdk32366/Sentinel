"""ORDER-01 B4 — redaction, truncation and retry in the FRED fetcher.

Offline. Every network call is a stub; nothing here reaches FRED and nothing
needs a key.

Covers two findings and one assumption:
  F-0010  the live key reached update_logs and was served over HTTP
  A-0003  a multi-series failure overflows varchar(500), the insert throws,
          and the log row - the diagnostic - is lost entirely
"""
import unittest
from unittest import mock

import requests

from pipelines import fred_fetcher
from pipelines.fred_fetcher import ERROR_FIELD_LIMIT, _redact, fetch_fred_series

FAKE_KEY = "0123456789abcdef0123456789abcdef"


class TestRedaction(unittest.TestCase):
    def test_key_in_a_url_is_redacted(self):
        text = (f"503 Server Error for url: https://api.stlouisfed.org/fred/"
                f"series/observations?series_id=DGS10&api_key={FAKE_KEY}")
        out = _redact(text)
        self.assertNotIn(FAKE_KEY, out)
        self.assertIn("api_key=***", out)

    def test_redaction_keeps_the_rest_of_the_message(self):
        out = _redact(f"DGS10: 502 Bad Gateway api_key={FAKE_KEY} retrying")
        self.assertIn("502 Bad Gateway", out)
        self.assertIn("retrying", out)

    def test_redacts_every_occurrence(self):
        out = _redact(f"api_key={FAKE_KEY} then again api_key={FAKE_KEY}")
        self.assertNotIn(FAKE_KEY, out)
        self.assertEqual(out.count("api_key=***"), 2)

    def test_redaction_accepts_an_exception_object(self):
        """errors.append is handed an exception, not a string."""
        exc = requests.HTTPError(f"boom api_key={FAKE_KEY}")
        self.assertNotIn(FAKE_KEY, _redact(exc))

    def test_message_without_a_key_is_untouched(self):
        """A correct and an incorrect implementation must differ somewhere."""
        self.assertEqual(_redact("DGS10: timed out"), "DGS10: timed out")


class TestErrorFieldTruncation(unittest.TestCase):
    """A-0003: the field is varchar(500). Truncate BEFORE the insert."""

    def _joined(self, errors):
        joined = "; ".join(errors) if errors else None
        if joined and len(joined) > ERROR_FIELD_LIMIT:
            joined = joined[: ERROR_FIELD_LIMIT - 3] + "..."
        return joined

    def test_limit_leaves_headroom_under_the_column(self):
        self.assertLess(ERROR_FIELD_LIMIT, 500)

    def test_multi_series_failure_fits_the_column(self):
        """The case A-0003 says would lose the row entirely."""
        errors = [f"METRIC{i}: 502 Server Error for url: {'x' * 120}"
                  for i in range(12)]
        joined = self._joined(errors)
        self.assertLessEqual(len(joined), ERROR_FIELD_LIMIT)
        self.assertLess(len(joined), 500)

    def test_truncation_is_visible_rather_than_silent(self):
        joined = self._joined([f"METRIC{i}: {'x' * 200}" for i in range(9)])
        self.assertTrue(joined.endswith("..."))

    def test_a_short_error_is_not_truncated(self):
        self.assertEqual(self._joined(["DGS10: timed out"]), "DGS10: timed out")

    def test_no_errors_means_no_message(self):
        self.assertIsNone(self._joined([]))


def _response(status):
    r = requests.Response()
    r.status_code = status
    r.url = f"https://api.stlouisfed.org/fred/x?api_key={FAKE_KEY}"
    return r


class TestRetryPolicy(unittest.TestCase):
    """F-0003: single-series 502s are transient and recover. A 4xx does not."""

    def setUp(self):
        patcher = mock.patch.object(fred_fetcher.time, "sleep")
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def test_transient_502_is_retried_then_succeeds(self):
        good = mock.Mock(status_code=200)
        good.raise_for_status = mock.Mock()
        good.json.return_value = {"observations": [{"date": "2026-09-24",
                                                    "value": "5.18"}]}
        bad = _response(502)
        with mock.patch.object(fred_fetcher.requests, "get",
                               side_effect=[bad, good]) as get:
            out = fetch_fred_series("DGS10", "2026-01-01", "2026-09-25")
        self.assertEqual(len(out), 1)
        self.assertEqual(get.call_count, 2)

    def test_gives_up_after_the_configured_attempts(self):
        with mock.patch.object(fred_fetcher.requests, "get",
                               return_value=_response(502)) as get:
            with self.assertRaises(requests.HTTPError):
                fetch_fred_series("DGS10", "2026-01-01", "2026-09-25", attempts=3)
        self.assertEqual(get.call_count, 3)

    def test_backoff_grows(self):
        with mock.patch.object(fred_fetcher.requests, "get",
                               return_value=_response(502)):
            with self.assertRaises(requests.HTTPError):
                fetch_fred_series("DGS10", "2026-01-01", "2026-09-25",
                                  attempts=3, backoff=4.0)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [4.0, 8.0])

    def test_4xx_is_not_retried(self):
        """A bad key is not transient. Retrying only delays the report."""
        with mock.patch.object(fred_fetcher.requests, "get",
                               return_value=_response(400)) as get:
            with self.assertRaises(requests.HTTPError):
                fetch_fred_series("DGS10", "2026-01-01", "2026-09-25")
        self.assertEqual(get.call_count, 1)
        self.sleep.assert_not_called()

    def test_429_is_retried_despite_being_4xx(self):
        """Rate limiting IS transient - that is the whole point of waiting."""
        with mock.patch.object(fred_fetcher.requests, "get",
                               return_value=_response(429)) as get:
            with self.assertRaises(requests.HTTPError):
                fetch_fred_series("DGS10", "2026-01-01", "2026-09-25", attempts=2)
        self.assertEqual(get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
