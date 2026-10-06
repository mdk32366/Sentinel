"""D-0093: short-lived, read-only proof access past Basic Auth (dormant by default).

G1-G13 pin api/proof_access.py and its hook in main.py; G14 pins
tools/proof_access.py. Every token is generated at runtime with
secrets.token_urlsafe(32); this file holds no literal token or hash (G11).
"Over HTTPS" means sending Fly-Forwarded-Proto: https, which is what Fly's
proxy sets (D4).
"""
import ast
import base64
import contextlib
import hashlib
import hmac
import importlib.util
import io
import logging
import os
import re
import secrets
import stat
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import httpx

import api.routes
import tests.test_frontend_auth as frontend_auth
from api import proof_access
from config import settings
from main import app

REPO = Path(__file__).resolve().parents[1]
HTTPS = {"Fly-Forwarded-Proto": "https"}
FORM = {"Content-Type": "application/x-www-form-urlencoded"}
COOKIE = "sentinel_proof"


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _basic(username: str, password: str) -> str:
    raw = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    return f"Basic {raw}"


def _helper_mint(password: str, sha: str, expires_raw: str, exp_unix=None, version="v1", key=None) -> str:
    """An independent implementation of the D3 cookie, so the formula is pinned."""
    if exp_unix is None:
        exp_unix = int(datetime.fromisoformat(expires_raw).timestamp())
    if key is None:
        key = hmac.new(
            password.encode(),
            b"sentinel-proof-cookie|v1|" + sha.encode() + b"|" + expires_raw.encode(),
            hashlib.sha256,
        ).digest()
    mac = hmac.new(key, f"{version}.{exp_unix}".encode(), hashlib.sha256).hexdigest()
    return f"{version}.{exp_unix}.{mac}"


def _cookie_from(response: httpx.Response) -> str:
    header = response.headers.get("set-cookie", "")
    first = header.split(";", 1)[0]
    name, _, value = first.partition("=")
    if name.strip() != COOKIE:
        raise AssertionError("no sentinel_proof Set-Cookie")
    return value


async def _send(method: str, path: str, headers=None, content=None, json=None) -> httpx.Response:
    # A fresh client per request: no cookie jar carries state between calls,
    # so every cookie a test sends is one it chose to send.
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, headers=headers or {}, content=content, json=json)


def _with_cookie(value: str, extra=None) -> dict:
    headers = {"Cookie": f"{COOKIE}={value}"}
    headers.update(extra or {})
    return headers


class ProofBase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        proof_access._reset_lockout()
        self.addCleanup(proof_access._reset_lockout)
        # Start every test dormant, whatever the environment holds.
        self._patch("sentinel_proof_token_sha256", "")
        self._patch("sentinel_proof_expires_at", "")

    def _patch(self, field: str, value: str):
        patcher = mock.patch.object(settings, field, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _arm(self, token=None, ttl=timedelta(hours=1)):
        token = token or _new_token()
        expires_raw = _iso(_utcnow() + ttl)
        self._patch("sentinel_proof_token_sha256", _sha(token))
        self._patch("sentinel_proof_expires_at", expires_raw)
        return token, expires_raw

    def _freeze(self, at: datetime):
        patcher = mock.patch.object(proof_access, "_now", return_value=at)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def _sign_in(self, token: str) -> httpx.Response:
        return await _send("POST", "/__proof", headers={**HTTPS, **FORM}, content=f"token={token}")

    async def _grant(self, token: str) -> str:
        response = await self._sign_in(token)
        self.assertEqual(response.status_code, 303, response.text)
        return _cookie_from(response)

    def assertChallenge(self, response):
        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.headers.get("www-authenticate", "").lower().startswith("basic"))

    def assertNoChallenge(self, response):
        self.assertNotIn("www-authenticate", {k.lower() for k in response.headers.keys()})

    def assertDormant(self, response):
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("form", response.text.lower())
        self.assertNotIn("token", response.text.lower())
        self.assertNoChallenge(response)


class G1DormantDefault(ProofBase):
    async def test_both_empty_is_a_404_for_get_and_post(self):
        self.assertDormant(await _send("GET", "/__proof", headers=HTTPS))
        self.assertDormant(await self._sign_in(_new_token()))

    async def test_a_well_formed_cookie_is_ignored_while_dormant(self):
        other = _new_token()
        cookie = _helper_mint(settings.auth_password, _sha(other), _iso(_utcnow() + timedelta(hours=1)))
        self.assertChallenge(await _send("GET", "/", headers=_with_cookie(cookie)))

    async def test_one_secret_alone_is_still_dormant(self):
        self._patch("sentinel_proof_token_sha256", _sha(_new_token()))
        self.assertDormant(await _send("GET", "/__proof", headers=HTTPS))
        self._patch("sentinel_proof_token_sha256", "")
        self._patch("sentinel_proof_expires_at", _iso(_utcnow() + timedelta(hours=1)))
        self.assertDormant(await _send("GET", "/__proof", headers=HTTPS))
        self.assertFalse(proof_access.is_armed())


class G2MalformedOrOutOfWindow(ProofBase):
    async def _state(self, sha: str, expires_raw: str) -> int:
        self._patch("sentinel_proof_token_sha256", sha)
        self._patch("sentinel_proof_expires_at", expires_raw)
        return (await _send("GET", "/__proof", headers=HTTPS)).status_code

    async def test_a_malformed_hash_is_dormant(self):
        good = _sha(_new_token())
        later = _iso(_utcnow() + timedelta(hours=1))
        for bad in (good[:63], good.upper(), "g" + good[1:], good + "0", ""):
            with self.subTest(length=len(bad)):
                self.assertEqual(await self._state(bad, later), 404)

    async def test_a_bad_or_out_of_window_expiry_is_dormant(self):
        base = _utcnow()
        self._freeze(base)
        sha = _sha(_new_token())
        cases = {
            "unparseable": "tomorrow",
            "naive": (base + timedelta(hours=1)).replace(tzinfo=None).isoformat(),
            "past": _iso(base - timedelta(seconds=1)),
            "now": _iso(base),
            "over 24h": _iso(base + timedelta(hours=24, seconds=1)),
            "a week out": _iso(base + timedelta(days=7)),
        }
        for label, expires_raw in cases.items():
            with self.subTest(label):
                self.assertEqual(await self._state(sha, expires_raw), 404)

    async def test_inside_the_window_is_armed(self):
        base = _utcnow()
        self._freeze(base)
        sha = _sha(_new_token())
        self.assertEqual(await self._state(sha, _iso(base + timedelta(hours=23, minutes=59))), 200)
        self.assertEqual(await self._state(sha, _iso(base + timedelta(hours=24))), 200)
        offset = (base + timedelta(hours=2)).astimezone(timezone(timedelta(hours=-7))).isoformat()
        self.assertEqual(await self._state(sha, offset), 200)


class G3Expiry(ProofBase):
    async def test_the_cookie_and_the_page_die_at_expiry(self):
        token, expires_raw = self._arm()
        cookie = await self._grant(token)
        self.assertEqual((await _send("GET", "/", headers=_with_cookie(cookie))).status_code, 200)

        self._freeze(datetime.fromisoformat(expires_raw) + timedelta(seconds=1))
        self.assertChallenge(await _send("GET", "/", headers=_with_cookie(cookie)))
        self.assertDormant(await _send("GET", "/__proof", headers=HTTPS))


class G4WrongTokenAndLockout(ProofBase):
    async def test_a_wrong_token_is_403_with_no_cookie(self):
        self._arm()
        wrong = _new_token()
        response = await self._sign_in(wrong)
        self.assertEqual(response.status_code, 403)
        self.assertIn("Not accepted", response.text)
        self.assertIn("<form", response.text)
        self.assertNotIn("set-cookie", {k.lower() for k in response.headers.keys()})
        self.assertNotIn(wrong, response.text)
        self.assertNoChallenge(response)

    async def test_five_failures_lock_out_even_the_right_token(self):
        token, _ = self._arm()
        early = await self._grant(token)
        with self.assertLogs("sentinel.proof", "INFO") as logs:
            for _ in range(5):
                self.assertEqual((await self._sign_in(_new_token())).status_code, 403)
            locked = await self._sign_in(token)
        self.assertEqual(locked.status_code, 404)
        self.assertNotIn("set-cookie", {k.lower() for k in locked.headers.keys()})
        self.assertTrue(any("proof: locked" in line for line in logs.output), logs.output)
        self.assertTrue(any("proof: rejected (5/5)" in line for line in logs.output), logs.output)
        self.assertEqual((await _send("GET", "/__proof", headers=HTTPS)).status_code, 404)
        # D5: a tripwire, not a kill switch - a cookie issued before the trip still reads.
        self.assertEqual((await _send("GET", "/", headers=_with_cookie(early))).status_code, 200)

    async def test_an_oversized_body_is_a_failure_not_a_500(self):
        token, _ = self._arm()
        response = await _send("POST", "/__proof", headers={**HTTPS, **FORM},
                               content=f"token={token}&pad=" + "a" * 5000)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(proof_access._failures, 1)

    async def test_a_missing_or_doubled_field_is_403_not_422(self):
        token, _ = self._arm()
        for body in ("other=x", "", f"token={token}&token={token}", "token="):
            with self.subTest(fields=body.count("=")):
                response = await _send("POST", "/__proof", headers={**HTTPS, **FORM}, content=body)
                self.assertEqual(response.status_code, 403)
                self.assertNotIn(token, response.text)


class G5Grant(ProofBase):
    async def test_the_right_token_sets_a_strict_cookie(self):
        token, expires_raw = self._arm()
        response = await self._sign_in(token)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers.get("location"), "/")
        set_cookie = response.headers.get("set-cookie", "")
        for attribute in ("HttpOnly", "Secure", "SameSite=Strict", "Path=/"):
            self.assertIn(attribute, set_cookie)
        self.assertNotIn("Domain", set_cookie)
        max_age = int(re.search(r"Max-Age=(\d+)", set_cookie).group(1))
        to_expiry = (datetime.fromisoformat(expires_raw) - datetime.now(timezone.utc)).total_seconds()
        self.assertGreater(max_age, 0)
        self.assertLessEqual(max_age, to_expiry + 1)
        self.assertNoChallenge(response)

    async def test_the_cookie_alone_reads_the_spa_and_the_api(self):
        token, _ = self._arm()
        cookie = await self._grant(token)
        page = await _send("GET", "/", headers=_with_cookie(cookie))
        self.assertEqual(page.status_code, 200)
        self.assertIn('id="root"', page.text)
        self.assertEqual((await _send("HEAD", "/", headers=_with_cookie(cookie))).status_code, 200)
        api_read = await _send("GET", "/api/analyze/providers", headers=_with_cookie(cookie))
        self.assertNotIn(api_read.status_code, (401, 403))


class G6ReadOnly(ProofBase):
    async def test_every_write_with_the_cookie_alone_is_403_without_a_challenge(self):
        token, _ = self._arm()
        cookie = await self._grant(token)
        providers = mock.MagicMock()
        with mock.patch.object(api.routes, "run_cds_fetch") as cds_spy, \
                mock.patch.object(api.routes, "get_session") as session_spy, \
                mock.patch.object(api.routes, "BRIEF_PROVIDERS", providers):
            writes = [
                ("POST", "/api/cds/fetch", None),
                ("POST", "/api/analyze/country", {"country": "USA"}),
                ("PUT", "/api/stats", None),
                ("DELETE", "/api/stats", None),
                ("PATCH", "/api/stats", None),
            ]
            for method, path, body in writes:
                with self.subTest(method=method, path=path):
                    response = await _send(method, path, headers=_with_cookie(cookie), json=body)
                    self.assertNoChallenge(response)
                    self.assertEqual(response.status_code, 403)
                    self.assertEqual(response.text, "Proof access is read-only")
        cds_spy.assert_not_called()
        session_spy.assert_not_called()
        providers.get.assert_not_called()

    async def test_basic_still_governs_writes_when_the_cookie_is_present(self):
        token, _ = self._arm()
        cookie = await self._grant(token)
        headers = _with_cookie(cookie, {"Authorization": _basic(settings.auth_username, settings.auth_password)})
        response = await _send("POST", "/api/__no_such_route__", headers=headers)
        self.assertNotIn(response.status_code, (401, 403))


class G7NoTokenMaterialLeaks(ProofBase):
    async def test_no_response_or_log_line_carries_the_token_the_hash_or_the_cookie(self):
        token, expires_raw = self._arm()
        sha = _sha(token)
        responses = []
        with self.assertLogs("sentinel.proof", "INFO") as proof_logs, self.assertLogs(level="INFO") as root_logs:
            logging.getLogger("tests.proof").info("G7 flow start")
            responses.append(await _send("GET", "/__proof", headers=HTTPS))
            responses.append(await self._sign_in(_new_token()))
            granted = await self._sign_in(token)
            responses.append(granted)
            cookie = _cookie_from(granted)
            responses.append(await _send("GET", "/", headers=_with_cookie(cookie)))
            responses.append(await _send("HEAD", "/", headers=_with_cookie(cookie)))
            responses.append(await _send("GET", "/api/analyze/providers", headers=_with_cookie(cookie)))
            with mock.patch.object(api.routes, "run_cds_fetch"):
                responses.append(await _send("POST", "/api/cds/fetch", headers=_with_cookie(cookie)))
            responses.append(await _send("DELETE", "/api/stats", headers=_with_cookie(cookie)))
            responses.append(await _send("POST", "/__proof", headers={**HTTPS, **FORM},
                                         content=f"token={token}&pad=" + "a" * 5000))
            self._freeze(datetime.fromisoformat(expires_raw) + timedelta(seconds=1))
            responses.append(await _send("GET", "/", headers=_with_cookie(cookie)))
            responses.append(await _send("GET", "/__proof", headers=HTTPS))

        self.assertTrue(cookie)
        for response in responses:
            body = response.content.decode("latin-1")
            for needle in (token, sha):
                self.assertNotIn(needle, body)
                for name, value in response.headers.items():
                    self.assertNotIn(needle, value, f"{name} leaks token material")
        messages = [r.getMessage() for r in proof_logs.records + root_logs.records]
        self.assertTrue(any("proof: granted" in m for m in messages), messages)
        self.assertTrue(any("proof: write-refused" in m for m in messages), messages)
        for message in messages:
            for needle in (token, sha, cookie):
                self.assertNotIn(needle, message)


class G8ConstantTimeCompare(ProofBase):
    async def test_both_the_token_and_the_cookie_go_through_compare_digest(self):
        token, _ = self._arm()
        with mock.patch.object(proof_access.hmac, "compare_digest", wraps=hmac.compare_digest) as spy:
            cookie = await self._grant(token)
            self.assertEqual((await _send("GET", "/", headers=_with_cookie(cookie))).status_code, 200)
        self.assertGreaterEqual(spy.call_count, 2)

    def test_no_plain_equality_on_secret_material(self):
        pattern = re.compile(r"(digest|mac|token|sha256)\w*\s*[!=]=|[!=]=\s*\w*(digest|mac|token|sha256)")
        source = (REPO / "api" / "proof_access.py").read_text(encoding="utf-8")
        offenders = [line.strip() for line in source.splitlines() if pattern.search(line)]
        self.assertEqual(offenders, [])


class G9HttpsOnly(ProofBase):
    async def test_without_fly_forwarded_proto_https_it_is_404_even_with_the_right_token(self):
        token, _ = self._arm()
        for headers in ({}, {"Fly-Forwarded-Proto": "http"}, {"X-Forwarded-Proto": "https"}):
            with self.subTest(headers=headers):
                self.assertDormant(await _send("GET", "/__proof", headers=headers))
                response = await _send("POST", "/__proof", headers={**headers, **FORM}, content=f"token={token}")
                self.assertDormant(response)
                self.assertNotIn("set-cookie", {k.lower() for k in response.headers.keys()})
        self.assertEqual(proof_access._failures, 0)


class G10BasicAuthUnchanged(unittest.TestCase):
    def _run_frontend_auth(self) -> unittest.TestResult:
        suite = unittest.TestLoader().loadTestsFromTestCase(frontend_auth.FrontendAuthTests)
        result = unittest.TestResult()
        suite.run(result)
        return result

    def test_the_six_frontend_auth_tests_pass_dormant_and_armed(self):
        token = _new_token()
        dormant = {"sentinel_proof_token_sha256": "", "sentinel_proof_expires_at": ""}
        armed = {"sentinel_proof_token_sha256": _sha(token),
                 "sentinel_proof_expires_at": _iso(_utcnow() + timedelta(hours=1))}
        for label, values in (("dormant", dormant), ("armed", armed)):
            with self.subTest(label), \
                    mock.patch.object(settings, "sentinel_proof_token_sha256", values["sentinel_proof_token_sha256"]), \
                    mock.patch.object(settings, "sentinel_proof_expires_at", values["sentinel_proof_expires_at"]):
                result = self._run_frontend_auth()
                self.assertEqual(result.testsRun, 6)
                self.assertTrue(result.wasSuccessful(), result.failures + result.errors)

    def test_credentials_ok_and_the_401_are_untouched(self):
        source = (REPO / "main.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        functions = {n.name: n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        credentials = ast.get_source_segment(source, functions["_credentials_ok"])
        self.assertEqual(credentials.count("secrets.compare_digest("), 2)
        self.assertNotIn("proof", credentials)
        middleware = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "BasicAuthMiddleware"][0]
        dispatch = ast.get_source_segment(source, middleware)
        self.assertIn('"Unauthorized"', dispatch)
        self.assertIn("status.HTTP_401_UNAUTHORIZED", dispatch)
        self.assertIn('headers={"WWW-Authenticate": "Basic"}', dispatch)


class G10ArmedWithoutCredentials(ProofBase):
    async def test_armed_but_neither_basic_nor_cookie_is_still_a_challenge(self):
        self._arm()
        self.assertChallenge(await _send("GET", "/"))
        self.assertChallenge(await _send("GET", "/api/stats"))
        self.assertChallenge(await _send("GET", "/", headers=_with_cookie("v1.0.nope")))


# ── G11 ──────────────────────────────────────────────────────────────────────

_HASH_KEY = "SENTINEL_PROOF_" + "TOKEN_SHA256"
_EXPIRY_KEY = "SENTINEL_PROOF_" + "EXPIRES_AT"
_HASH_ASSIGNED = re.compile(_HASH_KEY + r"\s*[=:]\s*[\"']?[0-9a-f]{64}", re.IGNORECASE)
_EXPIRY_ASSIGNED = re.compile(_EXPIRY_KEY + r"\s*[=:]\s*[\"']?\d{4}-", re.IGNORECASE)
_HEX64_LITERAL = re.compile(r"(?<![0-9A-Fa-f])[0-9A-Fa-f]{64}(?![0-9A-Fa-f])")
_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
_SKIP_PATHS = {("api", "static"), ("ui", "dist")}
_HEX_GUARDED = {"api/proof_access.py", "tools/proof_access.py", "config.py", ".env.template",
                "tests/test_proof_access.py"}


def _secret_violations(relpath: str, text: str) -> list:
    found = []
    if _HASH_ASSIGNED.search(text):
        found.append(f"{relpath}: proof hash value")
    if not relpath.startswith("tests/") and _EXPIRY_ASSIGNED.search(text):
        found.append(f"{relpath}: proof expiry value")
    if relpath == "fly.toml" and "SENTINEL_PROOF_" in text:
        found.append("fly.toml: SENTINEL_PROOF_ key (secrets only, never [env])")
    if relpath in _HEX_GUARDED and _HEX64_LITERAL.search(text):
        found.append(f"{relpath}: 64-hex literal")
    return found


class G11NoPlaintextSecretInTheTree(unittest.TestCase):
    def test_the_scanner_catches_each_shape(self):
        sha = _sha(_new_token())
        when = _iso(_utcnow())
        self.assertTrue(_secret_violations("docs/x.md", f"{_HASH_KEY}={sha}"))
        self.assertTrue(_secret_violations("docs/x.md", f"{_EXPIRY_KEY}: '{when}'"))
        self.assertFalse(_secret_violations("tests/test_x.py", f"{_EXPIRY_KEY}={when}"))
        self.assertTrue(_secret_violations("fly.toml", f"[env]\n  {_EXPIRY_KEY} = ''"))
        self.assertTrue(_secret_violations("config.py", f'x = "{sha}"'))
        self.assertFalse(_secret_violations("config.py", "x = 1"))

    def test_no_plaintext_proof_secret_anywhere_in_the_repo(self):
        found = []
        for root, dirs, files in os.walk(REPO):
            rel_root = Path(root).relative_to(REPO)
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and (rel_root / d).parts not in _SKIP_PATHS]
            for name in files:
                path = Path(root) / name
                try:
                    if path.stat().st_size > 5_000_000:
                        continue
                    data = path.read_bytes()
                except OSError:
                    continue
                if b"\0" in data:
                    continue
                found += _secret_violations((rel_root / name).as_posix(), data.decode("utf-8", "ignore"))
        self.assertEqual(found, [])


class G12ForgeryAndRotation(ProofBase):
    async def _reads(self, cookie: str) -> int:
        return (await _send("GET", "/", headers=_with_cookie(cookie))).status_code

    async def test_the_helper_cookie_for_the_current_arming_is_accepted(self):
        token, expires_raw = self._arm()
        self.assertEqual(await self._reads(_helper_mint(settings.auth_password, _sha(token), expires_raw)), 200)

    async def test_a_cookie_keyed_from_the_hash_alone_is_rejected(self):
        token, expires_raw = self._arm()
        sha = _sha(token)
        hash_keyed = hmac.new(sha.encode(), b"sentinel-proof-cookie|v1|" + sha.encode() + b"|"
                              + expires_raw.encode(), hashlib.sha256).digest()
        for key in (hash_keyed, sha.encode(), bytes.fromhex(sha)):
            with self.subTest(key_len=len(key)):
                self.assertEqual(await self._reads(_helper_mint("", sha, expires_raw, key=key)), 401)

    async def test_a_cookie_for_another_expiry_is_rejected(self):
        token, expires_raw = self._arm()
        exp_unix = int(datetime.fromisoformat(expires_raw).timestamp())
        for other in (exp_unix - 1, exp_unix + 60):
            with self.subTest(delta=other - exp_unix):
                forged = _helper_mint(settings.auth_password, _sha(token), expires_raw, exp_unix=other)
                self.assertEqual(await self._reads(forged), 401)

    async def test_rearming_with_a_new_token_rejects_the_old_cookie(self):
        token_a, _ = self._arm()
        cookie = await self._grant(token_a)
        self._patch("sentinel_proof_token_sha256", _sha(_new_token()))
        self.assertEqual(await self._reads(cookie), 401)

    async def test_changing_the_basic_password_rejects_the_old_cookie(self):
        token, _ = self._arm()
        cookie = await self._grant(token)
        self._patch("auth_password", _new_token())
        self.assertEqual(await self._reads(cookie), 401)

    async def test_wrong_version_or_shape_is_rejected(self):
        token, expires_raw = self._arm()
        good = _helper_mint(settings.auth_password, _sha(token), expires_raw)
        v2 = _helper_mint(settings.auth_password, _sha(token), expires_raw, version="v2")
        _, exp_text, mac = good.split(".")
        for bad in (v2, f"v1.{exp_text}", f"{exp_text}.{mac}", good + ".x", "v1..", ""):
            with self.subTest(parts=bad.count(".") + 1):
                self.assertEqual(await self._reads(bad), 401)


class G13SignInPageContract(ProofBase):
    async def test_the_armed_page_is_a_dom_form_with_safe_headers(self):
        self._arm()
        response = await _send("GET", "/__proof", headers=HTTPS)
        self.assertEqual(response.status_code, 200)
        for needle in ("<form", 'method="post"', 'action="/__proof"', 'type="password"', 'name="token"'):
            self.assertIn(needle, response.text)
        self.assertEqual(response.headers.get("cache-control"), "no-store")
        self.assertEqual(response.headers.get("referrer-policy"), "no-referrer")
        self.assertIn("frame-ancestors 'none'", response.headers.get("content-security-policy", ""))
        self.assertEqual(response.headers.get("x-frame-options"), "DENY")
        self.assertNoChallenge(response)


# ── G14: tools/proof_access.py ──────────────────────────────────────────────

def _load_tool():
    spec = importlib.util.spec_from_file_location("proof_access_tool", REPO / "tools" / "proof_access.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class G14ToolNeverPrintsSecrets(unittest.TestCase):
    def setUp(self):
        self.tool = _load_tool()
        self.calls = []
        self.clipboard = []

    def _fake_run(self, argv, stdin_text=None):
        self.calls.append((list(argv), stdin_text))
        return 0, "", ""

    def _fake_clipboard(self, text):
        self.clipboard.append(text)
        return "pbcopy"

    def _main(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = self.tool.main(argv)
            except SystemExit as exit_:
                code = exit_.code
        return code, out.getvalue(), err.getvalue()

    def test_arm_pipes_both_secrets_over_stdin_and_prints_neither(self):
        with mock.patch.object(self.tool, "_run", side_effect=self._fake_run), \
                mock.patch.object(self.tool, "_copy_to_clipboard", side_effect=self._fake_clipboard):
            code, out, err = self._main(["arm", "--ttl", "4h"])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(len(self.clipboard), 1)
        token = self.clipboard[0]
        sha = _sha(token)
        self.assertGreaterEqual(len(token), 40)
        for needle in (token, sha):
            self.assertNotIn(needle, out)
            self.assertNotIn(needle, err)
        self.assertIn("armed until", out)
        imports = [c for c in self.calls if "import" in c[0]]
        self.assertEqual(len(imports), 1)
        argv, stdin_text = imports[0]
        self.assertIn("secrets", argv)
        self.assertIn("sentinel-holy-rain-4562", argv)
        for needle in (token, sha):
            self.assertFalse(any(needle in part for part in argv), "secret in argv")
        self.assertIn(_HASH_KEY + "=" + sha, stdin_text)
        self.assertIn(_EXPIRY_KEY + "=", stdin_text)
        self.assertNotIn(token, stdin_text)
        expires_raw = re.search(_EXPIRY_KEY + r"=(\S+)", stdin_text).group(1)
        ahead = datetime.fromisoformat(expires_raw) - datetime.now(timezone.utc)
        self.assertTrue(timedelta(hours=3, minutes=58) < ahead <= timedelta(hours=4), ahead)

    def test_without_a_clipboard_the_token_goes_to_a_private_file_and_only_the_path_prints(self):
        with mock.patch.object(self.tool, "_run", side_effect=self._fake_run), \
                mock.patch.object(self.tool, "_copy_to_clipboard", return_value=None):
            code, out, err = self._main(["arm"])
        self.assertEqual(code, 0, out + err)
        stdin_text = self.calls[0][1]
        sha = re.search(_HASH_KEY + r"=(\S+)", stdin_text).group(1)
        paths = [p for p in re.findall(r"\S+", out) if "sentinel-proof-" in p and os.path.isfile(p)]
        self.assertEqual(len(paths), 1, out)
        try:
            token = Path(paths[0]).read_text(encoding="utf-8").strip()
            self.assertEqual(_sha(token), sha)
            self.assertNotIn(token, out + err)
            self.assertNotIn(sha, out + err)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(os.stat(paths[0]).st_mode), 0o600)
        finally:
            os.remove(paths[0])

    def test_a_ttl_over_24h_is_refused_before_fly_runs(self):
        with mock.patch.object(self.tool, "_run", side_effect=self._fake_run), \
                mock.patch.object(self.tool, "_copy_to_clipboard", side_effect=self._fake_clipboard):
            for ttl in ("25h", "1441m", "0h", "4d", "soon"):
                with self.subTest(ttl=ttl):
                    code, _, _ = self._main(["arm", "--ttl", ttl])
                    self.assertNotEqual(code, 0)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.clipboard, [])

    def test_disarm_fails_while_the_page_still_answers_200(self):
        with mock.patch.object(self.tool, "_run", side_effect=self._fake_run), \
                mock.patch.object(self.tool, "_http_get", return_value=(200, {})), \
                mock.patch.object(self.tool, "_sleep"):
            code, out, err = self._main(["disarm", "--timeout", "20"])
        self.assertNotEqual(code, 0)
        self.assertIn("FAIL", out + err)
        self.assertNotIn("PASS", out + err)
        unset = self.calls[0][0]
        self.assertIn("unset", unset)
        self.assertIn(_HASH_KEY, unset)
        self.assertIn(_EXPIRY_KEY, unset)

    def test_disarm_passes_on_404_then_401_basic(self):
        def fake_get(url):
            if url.endswith("/__proof"):
                return 404, {}
            return 401, {"WWW-Authenticate": "Basic"}

        with mock.patch.object(self.tool, "_run", side_effect=self._fake_run), \
                mock.patch.object(self.tool, "_http_get", side_effect=fake_get), \
                mock.patch.object(self.tool, "_sleep"):
            code, out, err = self._main(["disarm"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("PASS", out)

    def test_status_reports_without_sending_a_token(self):
        for status_code, word in ((200, "armed"), (404, "dormant")):
            with mock.patch.object(self.tool, "_http_get", return_value=(status_code, {})) as getter:
                code, out, _ = self._main(["status"])
            self.assertEqual(code, 0)
            self.assertIn(word, out)
            self.assertEqual(len(getter.call_args.args), 1)


if __name__ == "__main__":
    unittest.main()
