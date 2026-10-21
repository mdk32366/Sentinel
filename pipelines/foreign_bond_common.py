"""Shared plumbing for the Foreign Bonds fetchers (Sentinel D-0111, vault:D-0057).

Three official, free sources feed the FOREIGN-BONDS tab:

    Bundesbank  pipelines/bundesbank_yields.py  -> FB_DE_{02,05,07,10,30}Y  (FIT)
    BoE         pipelines/boe_yields.py         -> FB_GB_{02,05,07,10,30}Y  (FIT)
    MOF Japan   pipelines/mof_jgb.py            -> FB_JP_{02,05,07,10,30}Y  (CMT)

France has no free official daily source (D-0111 option A): its row is the
existing monthly FRED/OECD ``IRLTLT01FRM156N``, read-only, and the other four
French cells are NO SOURCE.

Display only. None of these codes is read by ``stress_score_v2.py`` or
``composite_stress.py``; the ``FB_`` prefix and the ``foreign_bond`` category
were chosen so no existing LIKE pattern (``IRLTLT01%``, ``%\\_CDS\\_%``)
matches them, and ``tests/test_foreign_bonds.py`` pins that.

Fail-closed, all or nothing per run:
  - transport: timeout 30 s, 3 attempts, backoff 4 s x 2^(n-1), no retry on a
    4xx except 429, every failure classified by ``fetch_failure`` (D-0094) so
    a Cloudflare block is ``FETCH_BLOCKED``, not a silent ``failed``;
  - parse: a missing column, an unparseable date or a value outside
    [-2.0, 15.0] % raises ``SchemaDrift``; blank / ``-`` cells are skipped,
    never read as zero;
  - write: nothing is written unless the whole source parsed; one transaction;
    ``fred_fetcher.upsert_observations`` (F-0073 ON CONFLICT) does the write;
  - a run that would write 0 rows is ``failed``, never ``success``.
"""
from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Callable, Iterable, Optional

from sqlalchemy.orm import Session

from database.models import UpdateLog
from pipelines.fetch_failure import (
    ClassifiedFetchError,
    FetchFailure,
    classify_fetch_error,
    format_failure,
)
from pipelines.fred_fetcher import (
    ERROR_FIELD_LIMIT,
    _redact,
    ensure_metric,
    upsert_observations,
)

logger = logging.getLogger(__name__)

CATEGORY = "foreign_bond"
TENORS = (2, 5, 7, 10, 30)
PLAUSIBLE_PCT = (-2.0, 15.0)
QUANT = Decimal("0.00000001")  # TimeSeries.value is Numeric(20, 8)

TIMEOUT_S = 30
ATTEMPTS = 3
BACKOFF_S = 4.0
USER_AGENT = "Sentinel/2.0 (sovereign stress monitor; foreign bonds D-0111)"


class SchemaDrift(ValueError):
    """The source answered, but not in the shape this parser was written for.

    A ValueError so ``fetch_failure`` classifies it as ``parse``.
    """


class EmptyResponse(ValueError):
    """A 200 that carried no observations (Bundesbank header-only body).

    Transient on the wire - the fetcher retries it - and ``failed`` once the
    attempts run out. Never a success with 0 rows.
    """


def code_for(country: str, tenor: int) -> str:
    return f"FB_{country}_{tenor:02d}Y"


def all_codes(country: str) -> list:
    return [code_for(country, t) for t in TENORS]


def to_value(raw, where: str) -> Optional[Decimal]:
    """A cell -> Decimal %, None for a blank / '-' cell, SchemaDrift otherwise."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        value = Decimal(repr(float(raw)))
    else:
        text = str(raw).strip()
        if text in ("", "-", ".", "NaN", "nan"):
            return None
        try:
            value = Decimal(text)
        except InvalidOperation as exc:
            raise SchemaDrift(f"{where}: value {text!r} is not a number") from exc
    if not value.is_finite():
        raise SchemaDrift(f"{where}: value {raw!r} is not finite")
    lo, hi = PLAUSIBLE_PCT
    if not (Decimal(str(lo)) <= value <= Decimal(str(hi))):
        raise SchemaDrift(
            f"{where}: value {value} outside the plausible range [{lo}, {hi}] %"
        )
    return value.quantize(QUANT)


def _urlopen(url: str, headers: Optional[dict] = None):
    hdrs = {"User-Agent": USER_AGENT}
    hdrs.update(headers or {})
    request = urllib.request.Request(url, headers=hdrs)
    return urllib.request.urlopen(request, timeout=TIMEOUT_S)


def fetch_bytes(
    url: str,
    headers: Optional[dict] = None,
    is_empty: Optional[Callable[[bytes], bool]] = None,
    attempts: int = ATTEMPTS,
    backoff: float = BACKOFF_S,
    sleep: Callable[[float], None] = time.sleep,
    opener: Callable = None,
) -> bytes:
    """GET with retries. ``is_empty(body)`` True -> retried like a 5xx.

    Blocked (Cloudflare or a non-429 4xx) is raised at once, classified.
    """
    opener = opener or _urlopen
    last_error: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            with opener(url, headers) as response:
                body = response.read()
            if is_empty is not None and is_empty(body):
                last_error = EmptyResponse(
                    f"{_redact(url)}: 200 with no observations (header only)"
                )
            else:
                return body
        except urllib.error.HTTPError as exc:
            failure = classify_fetch_error(exc, url=url)
            wrapped = ClassifiedFetchError(failure, exc)
            if failure.kind == "blocked" or (
                failure.http_status is not None
                and 400 <= failure.http_status < 500
                and failure.http_status != 429
            ):
                raise wrapped from exc
            last_error = wrapped
        except ClassifiedFetchError:
            raise
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = ClassifiedFetchError(classify_fetch_error(exc, url=url), exc)

        if attempt < attempts:
            wait = backoff * (2 ** (attempt - 1))
            logger.warning(
                "%s attempt %d/%d failed (%s); retrying in %.0fs",
                _redact(url), attempt, attempts, _redact(str(last_error)), wait,
            )
            sleep(wait)

    raise last_error


def failure_of(exc: BaseException, url: Optional[str]) -> FetchFailure:
    if isinstance(exc, ClassifiedFetchError):
        return exc.failure
    if isinstance(exc, EmptyResponse):
        return FetchFailure(kind="transient", detail="empty=header_only",
                            host=classify_fetch_error(exc, url=url).host)
    return classify_fetch_error(exc, url=url)


def _truncate(text: Optional[str]) -> Optional[str]:
    if text and len(text) > ERROR_FIELD_LIMIT:
        return text[: ERROR_FIELD_LIMIT - 3] + "..."
    return text


def write_run(
    db: Session,
    pipeline_name: str,
    metrics: Iterable[dict],
    produce: Callable[[], list],
    url_for_errors: str,
) -> dict:
    """Fetch+parse via ``produce()``, then write everything or nothing.

    ``produce`` returns ``[(code, datetime, Decimal), ...]``. One UpdateLog row
    per run. Returns the ``run_fred_fetch`` shape plus ``latest_date``.
    """
    started = datetime.utcnow()
    inserted = updated = 0
    errors: list = []
    latest = None
    status = "failed"
    metrics = list(metrics)

    try:
        rows = produce()
        if not rows:
            raise EmptyResponse(f"{pipeline_name}: parsed 0 observations")
        by_code: dict = {}
        for code, when, value in rows:
            by_code.setdefault(code, []).append((when, value))
        known = {m["code"] for m in metrics}
        stray = sorted(set(by_code) - known)
        if stray:
            raise SchemaDrift(f"{pipeline_name}: unexpected codes {stray}")
        # Metric rows first: ensure_metric commits, so it must never run
        # between two observation writes or it would commit half a source.
        ids = {m["code"]: ensure_metric(db, m).id for m in metrics}
        try:
            for m in metrics:
                points = by_code.get(m["code"], [])
                if not points:
                    continue
                i, u = upsert_observations(db, ids[m["code"]], points)
                inserted += i
                updated += u
            db.commit()
        except Exception:
            db.rollback()
            raise
        latest = max(when for _, when, _ in rows)
        status = "success"
    except Exception as exc:
        db.rollback()
        failure = failure_of(exc, url_for_errors)
        msg = _truncate(format_failure(failure, _redact(f"{pipeline_name}: {exc}")))
        errors.append(msg)
        level = logging.ERROR
        logger.log(level, "%s failed: %s", pipeline_name, msg)
        inserted = updated = 0
        status = "failed"

    db.add(UpdateLog(
        pipeline_name=pipeline_name,
        status=status,
        records_inserted=inserted,
        records_updated=updated,
        error_message=_truncate("; ".join(errors)) if errors else None,
        started_at=started,
        completed_at=datetime.utcnow(),
    ))
    db.commit()
    return {
        "status": status,
        "inserted": inserted,
        "updated": updated,
        "errors": errors,
        "latest_date": latest.date().isoformat() if latest else None,
    }
