"""D-0094 G1 / G9 — classify_fetch_error and redaction."""
import json
import socket
import unittest
import urllib.error
from email.message import Message
from io import BytesIO
from unittest.mock import MagicMock

from pipelines.fetch_failure import (
    classify_fetch_error,
    format_failure,
    parse_failure_fields,
    parse_failure_prefix,
    _redact,
)


def _http(code, body=b"", headers=None, url="https://prices.lbma.org.uk/json/gold_pm.json"):
    hdrs = Message()
    for k, v in (headers or {}).items():
        hdrs[k] = v
    return urllib.error.HTTPError(url, code, "err", hdrs, BytesIO(body))


class TestClassifier(unittest.TestCase):
    def test_4xx_blocked(self):
        for code in (401, 403, 451, 404):
            f = classify_fetch_error(_http(code))
            self.assertEqual(f.kind, "blocked", code)
            self.assertEqual(f.http_status, code)

    def test_cloudflare_503_challenge_header(self):
        f = classify_fetch_error(_http(
            503, body=b"ok", headers={"cf-mitigated": "challenge", "server": "cloudflare"},
        ))
        self.assertEqual(f.kind, "blocked")
        self.assertTrue(f.cloudflare)

    def test_cloudflare_body_blocked(self):
        body = b"<html>Sorry, you have been blocked</html>"
        f = classify_fetch_error(_http(
            403, body=body, headers={"server": "cloudflare"},
        ))
        self.assertEqual(f.kind, "blocked")
        self.assertTrue(f.cloudflare)

    def test_cloudflare_attention_required(self):
        f = classify_fetch_error(_http(
            403, body=b"Attention Required! cf-error-details",
            headers={"server": "cloudflare"},
        ))
        self.assertTrue(f.cloudflare)

    def test_429_rate_limited(self):
        f = classify_fetch_error(_http(429))
        self.assertEqual(f.kind, "rate_limited")

    def test_5xx_transient(self):
        for code in (500, 502, 503, 504):
            f = classify_fetch_error(_http(code, body=b"upstream", headers={"server": "nginx"}))
            self.assertEqual(f.kind, "transient", code)
            self.assertFalse(f.cloudflare)

    def test_dns_transient(self):
        exc = urllib.error.URLError(socket.gaierror(8, "name or service not known"))
        f = classify_fetch_error(exc, url="https://api.gold-api.com/price/XAU")
        self.assertEqual(f.kind, "transient")
        self.assertIn("dns", f.detail)

    def test_timeout_transient(self):
        f = classify_fetch_error(TimeoutError("timed out"))
        self.assertEqual(f.kind, "transient")
        self.assertIn("timeout", f.detail)

    def test_value_error_parse(self):
        f = classify_fetch_error(ValueError("stale_upstream"))
        self.assertEqual(f.kind, "parse")

    def test_4xx_vs_5xx_differ(self):
        b = classify_fetch_error(_http(403))
        t = classify_fetch_error(_http(503, headers={"server": "nginx"}))
        self.assertNotEqual(b.kind, t.kind)
        bp = format_failure(b, "GOLD_SPOT_USD: HTTP Error 403")
        tp = format_failure(t, "GOLD_SPOT_USD: HTTP Error 503")
        self.assertTrue(bp.startswith("FETCH_BLOCKED"))
        self.assertTrue(tp.startswith("FETCH_TRANSIENT"))
        self.assertNotEqual(bp.split()[0], tp.split()[0])


class TestPrefixRoundTrip(unittest.TestCase):
    def test_parse_prefix(self):
        self.assertEqual(
            parse_failure_prefix(
                "FETCH_BLOCKED http=403 cf=1 host=prices.lbma.org.uk | GOLD"
            ),
            "blocked",
        )
        self.assertIsNone(parse_failure_prefix("GOLD_SPOT_USD: HTTP Error 403"))
        self.assertIsNone(parse_failure_prefix(None))

    def test_fields(self):
        f = parse_failure_fields(
            "FETCH_BLOCKED http=403 cf=1 host=prices.lbma.org.uk | x"
        )
        self.assertEqual(f["kind"], "blocked")
        self.assertEqual(f["http_status"], 403)
        self.assertTrue(f["cloudflare"])


class TestRedaction(unittest.TestCase):
    def test_query_string_dropped(self):
        text = "https://host/path?apikey=SECRET123&x=1"
        self.assertNotIn("SECRET123", _redact(text))
        self.assertNotIn("apikey=", _redact(text))

    def test_stored_message_has_host_only(self):
        exc = ValueError("boom at https://host/path?apikey=SECRET123")
        f = classify_fetch_error(exc, url="https://host/path?apikey=SECRET123")
        msg = format_failure(f, str(exc))
        self.assertNotIn("SECRET123", msg)
        self.assertIn("host=host", msg)


if __name__ == "__main__":
    unittest.main()
