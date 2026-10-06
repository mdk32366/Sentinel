"""D-0093: arm, disarm and check Sentinel's short-lived read-only proof access.

Run on the laptop where flyctl is logged in. Standard library only.

    python tools/proof_access.py arm [--ttl 4h] [--app sentinel-holy-rain-4562]
    python tools/proof_access.py status [--url https://sentinel-holy-rain-4562.fly.dev]
    python tools/proof_access.py disarm [--app ...] [--url ...]

arm      generates a fresh token, pipes its SHA-256 and an expiry into
         `fly secrets import` over stdin (nothing in argv or shell history),
         and puts the plaintext token on the clipboard. If no clipboard tool
         exists it writes the token to a 0600 temp file and prints only the
         path. It never prints the token or the hash.
status   GET /__proof: 200 = armed, 404 = dormant. Sends no token.
disarm   `fly secrets unset` both secrets, then waits until /__proof is 404
         and / is 401 + WWW-Authenticate: Basic. Prints PASS or FAIL.

Never run `fly secrets ... --stage`: the machine must restart to pick the
secrets up (and to drop them).
"""
import argparse
import hashlib
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

DEFAULT_APP = "sentinel-holy-rain-4562"
DEFAULT_URL = "https://sentinel-holy-rain-4562.fly.dev"
DEFAULT_TTL = "4h"
MAX_TTL = timedelta(hours=24)
HASH_KEY = "SENTINEL_PROOF_TOKEN_SHA256"
EXPIRY_KEY = "SENTINEL_PROOF_EXPIRES_AT"
POLL_INTERVAL = 5
DEFAULT_TIMEOUT = 300

_CLIPBOARDS = (
    ["pbcopy"],
    ["clip"],
    ["wl-copy"],
    ["xclip", "-selection", "clipboard"],
    ["xsel", "--clipboard", "--input"],
)


def _run(argv, stdin_text=None):
    """Run a command; returns (returncode, stdout, stderr)."""
    done = subprocess.run(argv, input=stdin_text, capture_output=True, text=True)
    return done.returncode, done.stdout, done.stderr


def _copy_to_clipboard(text):
    """Put text on the OS clipboard. Returns the tool used, or None."""
    for argv in _CLIPBOARDS:
        exe = shutil.which(argv[0])
        if not exe:
            continue
        try:
            done = subprocess.run([exe] + argv[1:], input=text, text=True, capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            continue
        if done.returncode == 0:
            return argv[0]
    return None


def _write_private_file(text):
    fd, path = tempfile.mkstemp(prefix="sentinel-proof-", suffix=".txt")
    try:
        os.chmod(path, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
    except Exception:
        os.remove(path)
        raise
    return path


def _http_get(url):
    """(status, headers) for a GET, or (None, {}) when unreachable."""
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": "sentinel-proof-access/1"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers or {})
    except (urllib.error.URLError, OSError):
        return None, {}


def _sleep(seconds):
    time.sleep(seconds)


def _fly():
    return shutil.which("fly") or shutil.which("flyctl") or "fly"


def _parse_ttl(raw):
    match = re.fullmatch(r"(\d+)([hm])", (raw or "").strip())
    if not match:
        return None
    amount = int(match.group(1))
    ttl = timedelta(hours=amount) if match.group(2) == "h" else timedelta(minutes=amount)
    if ttl <= timedelta(0) or ttl > MAX_TTL:
        return None
    return ttl


def _pacific(when):
    try:
        from zoneinfo import ZoneInfo
        return when.astimezone(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d %H:%M %Z")
    except Exception:
        local = when.astimezone()
        return local.strftime("%Y-%m-%d %H:%M ") + (local.tzname() or "local")


def _redact(text, *secret_values):
    for value in secret_values:
        if value:
            text = text.replace(value, "[redacted]")
    return text


def _header(headers, name):
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return ""


def cmd_arm(args):
    ttl = _parse_ttl(args.ttl)
    if ttl is None:
        print(f"refused: --ttl must look like 4h or 90m, above zero and at most 24h (got {args.ttl!r})",
              file=sys.stderr)
        return 2
    token = secrets.token_urlsafe(32)
    token_sha256 = hashlib.sha256(token.encode()).hexdigest()
    expires = (datetime.now(timezone.utc) + ttl).replace(microsecond=0)
    expires_raw = expires.strftime("%Y-%m-%dT%H:%M:%SZ")

    stdin_text = f"{HASH_KEY}={token_sha256}\n{EXPIRY_KEY}={expires_raw}\n"
    code, out, err = _run([_fly(), "secrets", "import", "-a", args.app], stdin_text=stdin_text)
    if code != 0:
        detail = _redact((err or out or "").strip(), token, token_sha256)
        print(f"FAIL: fly secrets import exited {code}: {detail}", file=sys.stderr)
        return 1

    print(f"armed until {expires_raw} (UTC) / {_pacific(expires)}")
    where = _copy_to_clipboard(token)
    if where:
        print(f"The proof token is on your clipboard ({where}). Paste it only into the Secure Form.")
    else:
        path = _write_private_file(token)
        print(f"No clipboard tool found. The proof token is in this 0600 file: {path}")
        print("Delete that file once the token has been pasted.")
    print("Fly restarts the machine; wait for it, then run: python tools/proof_access.py status")
    print("Teardown when the proofs are done: python tools/proof_access.py disarm")
    return 0


def _poll(url, accept, timeout):
    attempts = max(1, int(timeout // POLL_INTERVAL))
    last = None
    for attempt in range(attempts):
        status, headers = _http_get(url)
        last = status
        if accept(status, headers):
            return True, status
        if attempt + 1 < attempts:
            _sleep(POLL_INTERVAL)
    return False, last


def _secrets_still_set(app):
    """True/False from `fly secrets list`, or None when it cannot be read.

    The listing carries names and digests; only the names are looked at, and
    none of its output is ever printed.
    """
    code, out, _ = _run([_fly(), "secrets", "list", "-a", app])
    if code != 0:
        return None
    return HASH_KEY in out or EXPIRY_KEY in out


def cmd_disarm(args):
    base = args.url.rstrip("/")
    code, _, _ = _run([_fly(), "secrets", "unset", HASH_KEY, EXPIRY_KEY, "-a", args.app])
    if code != 0:
        # A locked page is also a 404 and / is a 401 either way, so the live
        # checks below cannot tell "disarmed" from "unset failed while locked"
        # (old cookies would still read). Only the secret list can.
        still_set = _secrets_still_set(args.app)
        if still_set is None:
            print(f"FAIL: fly secrets unset exited {code} and fly secrets list could not be read")
            return 1
        if still_set:
            print(f"FAIL: fly secrets unset exited {code} and a proof secret is still listed")
            return 1
        print(f"note: fly secrets unset exited {code}, but neither proof secret is listed", file=sys.stderr)

    page_ok, page_status = _poll(f"{base}/__proof", lambda s, h: s == 404, args.timeout)
    if not page_ok:
        print(f"FAIL: {base}/__proof still answers {page_status}, not 404")
        return 1
    root_ok, root_status = _poll(
        f"{base}/",
        lambda s, h: s == 401 and _header(h, "WWW-Authenticate").lower().startswith("basic"),
        args.timeout,
    )
    if not root_ok:
        print(f"FAIL: {base}/ answers {root_status}, not 401 + WWW-Authenticate: Basic")
        return 1
    stamp = datetime.now(timezone.utc).replace(microsecond=0)
    print(f"PASS: /__proof is 404 and / is 401 + Basic. Disarmed at "
          f"{stamp.strftime('%Y-%m-%dT%H:%M:%SZ')} (UTC) / {_pacific(stamp)}")
    print("Clear the clipboard if the token is still on it.")
    return 0


def cmd_status(args):
    url = f"{args.url.rstrip('/')}/__proof"
    status, _ = _http_get(url)
    if status == 200:
        print(f"armed: {url} answers 200")
    elif status == 404:
        print(f"dormant: {url} answers 404")
    else:
        print(f"unknown: {url} answers {status}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="D-0093 proof access: arm, disarm, status.")
    sub = parser.add_subparsers(dest="command", required=True)

    arm = sub.add_parser("arm", help="generate a token and arm for --ttl (default 4h, max 24h)")
    arm.add_argument("--ttl", default=DEFAULT_TTL, help="e.g. 4h or 90m; at most 24h (default 4h)")
    arm.add_argument("--app", default=DEFAULT_APP)
    arm.set_defaults(func=cmd_arm)

    disarm = sub.add_parser("disarm", help="unset both secrets and verify the app is back to Basic only")
    disarm.add_argument("--app", default=DEFAULT_APP)
    disarm.add_argument("--url", default=DEFAULT_URL)
    disarm.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="seconds per check (default 300)")
    disarm.set_defaults(func=cmd_disarm)

    status = sub.add_parser("status", help="armed (200) or dormant (404); sends no token")
    status.add_argument("--url", default=DEFAULT_URL)
    status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
