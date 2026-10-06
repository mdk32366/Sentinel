"""Classify HTTP/network fetch failures for UpdateLog storage (D-0094).

A blocked source and a temporary outage used to write the same ``failed``
row. The watchdog then ignored every failed row, so six nights of Cloudflare
403s still looked fine. This module puts a machine-readable prefix on the
error string so the watchdog can tell them apart — without a schema change.
"""
from __future__ import annotations

import json
import re
import socket
import urllib.error
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse

# Cloudflare challenge / block markers searched in the first 4 KB of body.
# The body itself is never logged (D-0094 G9 / redaction).
_CF_BODY_MARKERS = (
    "Sorry, you have been blocked",
    "Attention Required",
    "cf-error-details",
    "Just a moment",
)

_HOST_RE = re.compile(r"https?://([^/\s?#]+)", re.I)
_QUERY_RE = re.compile(r"\?[^\\s]*")


class ClassifiedFetchError(Exception):
    """Raised in place of a raw HTTPError once classified, so the body is
    not re-read (and emptied) by a second classify call."""

    def __init__(self, failure: "FetchFailure", cause: BaseException):
        self.failure = failure
        self.cause = cause
        super().__init__(str(cause))


@dataclass(frozen=True)
class FetchFailure:
    kind: str  # blocked | rate_limited | transient | parse | unknown
    http_status: Optional[int] = None
    cloudflare: bool = False
    detail: str = ""
    host: Optional[str] = None


def _redact(text: str) -> str:
    """Drop query strings so an apikey= never reaches UpdateLog or logs."""
    if not text:
        return text
    return _QUERY_RE.sub("", str(text))


def _host_of(url_or_text: Optional[str]) -> Optional[str]:
    if not url_or_text:
        return None
    text = str(url_or_text)
    try:
        parsed = urlparse(text if "://" in text else f"https://{text}")
        if parsed.hostname:
            return parsed.hostname
    except Exception:
        pass
    m = _HOST_RE.search(text)
    return m.group(1) if m else None


def _read_http_body(exc: urllib.error.HTTPError, limit: int = 4096) -> bytes:
    try:
        return exc.read(limit) or b""
    except Exception:
        return b""


def _is_cloudflare(exc: urllib.error.HTTPError, body: bytes) -> bool:
    headers = getattr(exc, "headers", None) or {}
    # email.message.Message / HTTPMessage is case-insensitive
    try:
        mitigated = (headers.get("cf-mitigated") or "").lower()
    except Exception:
        mitigated = ""
    if mitigated == "challenge":
        return True
    try:
        server = (headers.get("server") or "").lower()
    except Exception:
        server = ""
    if "cloudflare" not in server:
        return False
    try:
        text = body.decode("utf-8", errors="replace")
    except Exception:
        text = ""
    return any(marker in text for marker in _CF_BODY_MARKERS)


def classify_fetch_error(exc: BaseException, url: Optional[str] = None) -> FetchFailure:
    """Map an exception to a FetchFailure kind.

    Table (D-0094 Spec A1):
      401/403/451 / other 4xx except 408/429 → blocked
      Cloudflare challenge/block (incl. 503) → blocked, cloudflare=True
      429 → rate_limited
      5xx non-CF, timeout, DNS, conn refused → transient
      ValueError / JSONDecodeError → parse
      else → unknown
    """
    host = _host_of(url)

    if isinstance(exc, urllib.error.HTTPError):
        body = _read_http_body(exc)
        cf = _is_cloudflare(exc, body)
        code = int(exc.code)
        host = host or _host_of(getattr(exc, "url", None)) or _host_of(url)
        if cf:
            return FetchFailure(
                kind="blocked", http_status=code, cloudflare=True,
                detail=_redact(f"http={code} cf=1"), host=host,
            )
        if code == 429:
            return FetchFailure(
                kind="rate_limited", http_status=code, cloudflare=False,
                detail=_redact(f"http={code}"), host=host,
            )
        if code in (401, 403, 451) or (400 <= code < 500 and code not in (408, 429)):
            return FetchFailure(
                kind="blocked", http_status=code, cloudflare=False,
                detail=_redact(f"http={code}"), host=host,
            )
        if 500 <= code < 600:
            return FetchFailure(
                kind="transient", http_status=code, cloudflare=False,
                detail=_redact(f"http={code}"), host=host,
            )
        return FetchFailure(
            kind="unknown", http_status=code, cloudflare=False,
            detail=_redact(f"http={code}"), host=host,
        )

    if isinstance(exc, (TimeoutError, socket.timeout)):
        return FetchFailure(
            kind="transient", detail="net=timeout", host=host,
        )

    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", exc)
        if isinstance(reason, socket.gaierror):
            return FetchFailure(kind="transient", detail="net=dns", host=host)
        if isinstance(reason, (ConnectionRefusedError, ConnectionResetError)):
            return FetchFailure(kind="transient", detail="net=conn", host=host)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return FetchFailure(kind="transient", detail="net=timeout", host=host)
        # URLError wrapping HTTP-ish text
        text = _redact(str(reason))
        return FetchFailure(kind="transient", detail=f"net=url {text}"[:80], host=host)

    if isinstance(exc, (ValueError, json.JSONDecodeError)):
        return FetchFailure(
            kind="parse", detail=_redact(str(exc))[:120], host=host,
        )

    return FetchFailure(
        kind="unknown", detail=_redact(str(exc))[:120], host=host,
    )


_KIND_TO_PREFIX = {
    "blocked": "FETCH_BLOCKED",
    "rate_limited": "FETCH_RATE_LIMITED",
    "transient": "FETCH_TRANSIENT",
    "parse": "FETCH_PARSE",
    "unknown": "FETCH_UNKNOWN",
}


def format_failure(failure: FetchFailure, human: str) -> str:
    """Machine-readable prefix + human tail, fitting String(500)."""
    token = _KIND_TO_PREFIX.get(failure.kind, "FETCH_UNKNOWN")
    parts = [token]
    if failure.detail:
        # detail already holds http= / net= / cf=
        # avoid duplicating http= if detail starts with it
        parts.append(failure.detail)
    elif failure.http_status is not None:
        parts.append(f"http={failure.http_status}")
        if failure.cloudflare:
            parts.append("cf=1")
    if failure.host:
        parts.append(f"host={failure.host}")
    prefix = " ".join(parts)
    tail = _redact(human or "")
    combined = f"{prefix} | {tail}" if tail else prefix
    if len(combined) > 480:
        combined = combined[:477] + "..."
    return combined


_PREFIX_RE = re.compile(
    r"^(FETCH_BLOCKED|FETCH_RATE_LIMITED|FETCH_TRANSIENT|FETCH_PARSE|FETCH_UNKNOWN)\b"
)
_PREFIX_TO_KIND = {v: k for k, v in _KIND_TO_PREFIX.items()}


def parse_failure_prefix(text: Optional[str]) -> Optional[str]:
    """Return the kind token, or None for legacy unprefixed rows."""
    if not text:
        return None
    m = _PREFIX_RE.match(text.strip())
    if not m:
        return None
    return _PREFIX_TO_KIND.get(m.group(1))


def parse_failure_fields(text: Optional[str]) -> dict:
    """Extract kind / http_status / cloudflare from a stored error_message."""
    kind = parse_failure_prefix(text)
    if kind is None:
        return {"kind": None, "http_status": None, "cloudflare": False}
    http_status = None
    cloudflare = False
    if text:
        m = re.search(r"\bhttp=(\d{3})\b", text)
        if m:
            http_status = int(m.group(1))
        if re.search(r"\bcf=1\b", text):
            cloudflare = True
    return {"kind": kind, "http_status": http_status, "cloudflare": cloudflare}
