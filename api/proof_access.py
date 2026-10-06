"""D-0093: short-lived, read-only proof access past Basic Auth (dormant by default).

Chrome's native Basic Auth dialog is browser chrome, not DOM, so no form-fill
tool can reach it and the live click proofs stall at it. This module adds a
real DOM sign-in page at ``/__proof`` that trades a one-time proof token for a
signed cookie, and that cookie admits GET and HEAD only.

Dormant unless BOTH Fly secrets are set and the expiry is inside a 24h window:

    SENTINEL_PROOF_TOKEN_SHA256  lowercase hex SHA-256 of the plaintext token
    SENTINEL_PROOF_EXPIRES_AT    ISO-8601 with an explicit offset

Dormant means ``/__proof`` is a 404, the cookie is ignored, and Basic Auth
behaves exactly as it did before D-0093. Only the hash is ever stored; the
plaintext token lives on Matt's clipboard (``tools/proof_access.py arm``).

Never log, echo or return the token, its hash, the cookie value, the request
body or the Authorization header.
"""
import hashlib
import hmac
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from starlette.responses import HTMLResponse, PlainTextResponse, Response

from config import settings

logger = logging.getLogger("sentinel.proof")

PROOF_PATH = "/__proof"
COOKIE_NAME = "sentinel_proof"
COOKIE_VERSION = "v1"
READ_METHODS = frozenset({"GET", "HEAD"})
MAX_WINDOW = timedelta(hours=24)
MAX_BODY_BYTES = 4096
LOCK_AFTER = 5

_HEX64 = re.compile(r"[0-9a-f]{64}")
_IP_CHARS = re.compile(r"[^0-9A-Fa-f.:]")
_REGION_CHARS = re.compile(r"[^0-9a-z]")

# D5: one machine, one process (fly.toml), so an in-process counter is
# coherent. Any `fly secrets import`/`unset` restarts the process and resets it.
_failures = 0


def _now() -> datetime:
    """The one clock this module reads. Tests patch it."""
    return datetime.now(timezone.utc)


def _reset_lockout() -> None:
    """Test hook: a fresh process starts at zero failures."""
    global _failures
    _failures = 0


def _locked() -> bool:
    return _failures >= LOCK_AFTER


def _parse_expires(raw: str) -> Optional[datetime]:
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None  # a naive timestamp is ambiguous, so it never arms
    return parsed.astimezone(timezone.utc)


def _arming() -> Optional[Tuple[str, datetime]]:
    """(stored hash, expiry) when the secrets describe a live window, else None.

    The server cannot know when a secret was set, so the 24h cap is enforced as
    "never more than 24h ahead of now".
    """
    armed_sha256 = settings.sentinel_proof_token_sha256 or ""
    if not _HEX64.fullmatch(armed_sha256):
        return None
    expires = _parse_expires(settings.sentinel_proof_expires_at or "")
    if expires is None:
        return None
    now = _now()
    if not now < expires:
        return None
    if expires - now > MAX_WINDOW:
        return None
    return armed_sha256, expires


def is_armed() -> bool:
    """True when the sign-in page is open: a live window and no lockout."""
    if _arming() is None:
        return False
    return not _locked()


def _cookie_mac(armed_sha256: str, expires_raw: str, exp_unix: int) -> str:
    # D3: the key mixes in the Basic Auth password, so the stored hash alone
    # cannot mint a cookie, and changing either proof secret or the password
    # invalidates every cookie already issued.
    key = hmac.new(
        settings.auth_password.encode(),
        b"sentinel-proof-cookie|v1|" + armed_sha256.encode() + b"|" + expires_raw.encode(),
        hashlib.sha256,
    ).digest()
    return hmac.new(key, f"{COOKIE_VERSION}.{exp_unix}".encode(), hashlib.sha256).hexdigest()


def mint_cookie() -> Optional[str]:
    """The cookie value for the current arming, or None when dormant."""
    state = _arming()
    if state is None:
        return None
    armed_sha256, expires = state
    exp_unix = int(expires.timestamp())
    mac_hex = _cookie_mac(armed_sha256, settings.sentinel_proof_expires_at, exp_unix)
    return f"{COOKIE_VERSION}.{exp_unix}.{mac_hex}"


def cookie_ok(request: Request) -> bool:
    """A valid cookie for the CURRENT arming. Survives the lockout (D5)."""
    try:
        state = _arming()
        if state is None:
            return False
        raw = request.cookies.get(COOKIE_NAME)
        if not raw:
            return False
        parts = raw.split(".")
        if len(parts) != 3:
            return False
        version, exp_text, presented_mac = parts
        if version != COOKIE_VERSION:
            return False
        armed_sha256, expires = state
        exp_unix = int(exp_text)
        if exp_unix != int(expires.timestamp()):
            return False  # minted under an earlier arming
        if not _now().timestamp() < exp_unix:
            return False
        expected_mac = _cookie_mac(armed_sha256, settings.sentinel_proof_expires_at, exp_unix)
        return hmac.compare_digest(presented_mac, expected_mac)
    except Exception:
        return False


def _where(request: Request) -> str:
    ip = _IP_CHARS.sub("", request.headers.get("fly-client-ip", ""))[:45] or "-"
    region = _REGION_CHARS.sub("", request.headers.get("fly-region", ""))[:8] or "-"
    return f"ip={ip} region={region}"


async def read_only_gate(request: Request, call_next):
    """D2 step 4: the cookie admits reads; any write is a 403 with no challenge.

    A 401 here would carry WWW-Authenticate and pop the native dialog
    mid-proof. 403 tells the truth: known, but read-only.
    """
    if request.method in READ_METHODS:
        return await call_next(request)
    logger.info("proof: write-refused %s %s %s", request.method, request.url.path, _where(request))
    return PlainTextResponse("Proof access is read-only", status_code=403)


# ── /__proof ─────────────────────────────────────────────────────────────────

_PAGE_HEADERS = {
    "Cache-Control": "no-store",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; "
        "form-action 'self'; frame-ancestors 'none'"
    ),
    "X-Frame-Options": "DENY",
}

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="robots" content="noindex, nofollow">
<title>Sentinel proof access</title>
<style>
body {{ font-family: system-ui, sans-serif; background: #0b0f14; color: #d8dee9; margin: 4rem auto; max-width: 22rem; }}
label, input, button {{ display: block; margin: 0.5rem 0; font-size: 1rem; }}
input {{ width: 100%; padding: 0.4rem; }}
.note {{ color: #f0b45a; }}
</style>
</head>
<body>
<h1>Sentinel proof access</h1>
{note}<form method="post" action="/__proof">
  <label for="token">Proof token</label>
  <input id="token" name="token" type="password" autocomplete="off" required>
  <button type="submit">Enter</button>
</form>
</body>
</html>
"""


def _page(status_code: int, note: str = "") -> HTMLResponse:
    note_html = f'<p class="note">{note}</p>\n' if note else ""
    return HTMLResponse(_PAGE.format(note=note_html), status_code=status_code, headers=dict(_PAGE_HEADERS))


def _not_found() -> PlainTextResponse:
    return PlainTextResponse("Not Found", status_code=404, headers={"Cache-Control": "no-store"})


def _https(request: Request) -> bool:
    # D4: Fly sets Fly-Forwarded-Proto and a client cannot override it, unlike
    # X-Forwarded-Proto. request.url.scheme is "http" behind Fly (no
    # --proxy-headers), and force_https is false, so check it here.
    return request.headers.get("fly-forwarded-proto") == "https"


def _gate(request: Request) -> bool:
    """True when /__proof may answer. Logs why when it may not."""
    if not _https(request):
        logger.info("proof: dormant-hit (not https) %s", _where(request))
        return False
    if not is_armed():
        if _arming() is not None:
            logger.info("proof: locked %s", _where(request))
        else:
            logger.info("proof: dormant-hit %s", _where(request))
        return False
    return True


async def _read_capped_body(request: Request) -> Optional[bytes]:
    """At most MAX_BODY_BYTES, or None when the body is larger."""
    declared = request.headers.get("content-length")
    if declared is not None:
        try:
            if int(declared) > MAX_BODY_BYTES:
                return None
        except ValueError:
            return None
    chunks = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_BODY_BYTES:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


def _submitted_token(body: Optional[bytes]) -> Optional[str]:
    if body is None:
        return None
    try:
        fields = parse_qs(body.decode("utf-8"), keep_blank_values=True, max_num_fields=8)
    except (UnicodeDecodeError, ValueError):
        return None
    values = fields.get("token") or []
    if len(values) != 1 or not values[0]:
        return None
    return values[0]


def _reject(request: Request) -> HTMLResponse:
    global _failures
    _failures += 1
    logger.info("proof: rejected (%d/%d) %s", min(_failures, LOCK_AFTER), LOCK_AFTER, _where(request))
    if _locked():
        logger.info("proof: locked %s", _where(request))
    return _page(403, "Not accepted.")


async def _sign_in(request: Request) -> Response:
    # Never a pydantic/Form parameter: FastAPI's 422 body echoes the input.
    state = _arming()
    if state is None:
        return _not_found()
    armed_sha256, expires = state
    submitted = _submitted_token(await _read_capped_body(request))
    if submitted is None:
        return _reject(request)
    presented_sha256 = hashlib.sha256(submitted.encode()).hexdigest()
    if not hmac.compare_digest(presented_sha256, armed_sha256):
        return _reject(request)
    value = mint_cookie()
    max_age = int((expires - _now()).total_seconds())
    if value is None or max_age < 1:
        return _not_found()
    logger.info("proof: granted %s", _where(request))
    response = Response(status_code=303, headers={"Location": "/", "Cache-Control": "no-store"})
    response.headers["Set-Cookie"] = (
        f"{COOKIE_NAME}={value}; Path=/; Max-Age={max_age}; HttpOnly; Secure; SameSite=Strict"
    )
    return response


router = APIRouter()


@router.api_route(
    PROOF_PATH,
    methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    include_in_schema=False,
)
async def proof_sign_in(request: Request) -> Response:
    """GET shows the DOM form, POST trades the token for the cookie.

    Every other method, and every request while dormant, locked or not over
    HTTPS, is a plain 404. No response here ever carries WWW-Authenticate.
    """
    if not _gate(request):
        return _not_found()
    if request.method in READ_METHODS:
        return _page(200)
    if request.method == "POST":
        return await _sign_in(request)
    return _not_found()
