"""D-0114 shadow: old (D-0066) vs new (D-0114) dimension 4 and composite, per country.

READ-ONLY. The scorer is run twice on the same session, once with
FB_DIM4_CODES emptied (exactly master's behaviour: dimension 4 measured, 0
points) and once as shipped. On PostgreSQL the session is opened with
default_transaction_read_only=on and rolled back; nothing is written.

    DATABASE_URL=postgresql://... python scripts/d0114_shadow.py --out /workspace/d0114-shadow.md
    python scripts/d0114_shadow.py --fixture          # offline, tests/d0114_fixture.py

Trinity's merge gate: France must not move the wrong way, and every non-FB
row must show zero delta. The table states the second explicitly.
"""
import argparse
import os
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipelines import composite_stress as cs  # noqa: E402



def rows_of(result):
    out = {}
    for key, val in result.items():
        if isinstance(val, list):
            for r in val:
                if isinstance(r, dict) and "country_iso" in r:
                    out[r["country_iso"]] = r
    return out


def run_both(db):
    with mock.patch.object(cs, "FB_DIM4_CODES", {}):
        old = rows_of(cs.compute_composite_stress(db))
    new = rows_of(cs.compute_composite_stress(db))
    return old, new


def fmt(v, nd=1):
    if v is None:
        return "—"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def table(old, new, label):
    lines = [f"# D-0114 shadow — {label}", "",
             "| country | old dim4 | new dim4 | old composite | new composite | Δ composite | source used | spread bp | spread pctile | flags |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    non_fb_moved = []
    for iso in sorted(set(old) | set(new)):
        o, n = old.get(iso, {}), new.get(iso, {})
        oc, nc = o.get("composite_score", 0.0 if not o else None), n.get("composite_score", 0.0 if not n else None)
        delta = (nc or 0) - (oc or 0)
        if iso not in cs.FB_DIM4_CODES and (o != n):
            non_fb_moved.append(iso)
        lines.append("| " + " | ".join([
            iso, "0 (retired)", fmt(n.get("dim4_score", 0)), fmt(oc), fmt(nc), f"{delta:+.1f}",
            n.get("dim4_source") or "—", fmt(n.get("dim4_spread_bp")),
            fmt(n.get("dim4_spread_pctile")), ", ".join(n.get("dim4_flags") or []) or "—",
        ]) + " |")
    lines += ["", f"Countries compared: {len(set(old) | set(new))}. FB countries: "
              + ", ".join(sorted(i for i in cs.FB_DIM4_CODES if i in new)) + "."]
    if non_fb_moved:
        lines.append(f"**NON-FB ROWS MOVED: {', '.join(non_fb_moved)} — gate FAILS.**")
    else:
        lines.append("**Non-FB rows show zero delta:** every non-FB country's full payload "
                     "(not just its score) is identical old vs new.")
    fra = new.get("FRA")
    if fra is not None:
        d = (fra.get("composite_score") or 0) - (old.get("FRA", {}).get("composite_score") or 0)
        lines.append(f"France: composite {d:+.1f} (dim 4 can only add, so never lower).")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", action="store_true")
    ap.add_argument("--out")
    a = ap.parse_args()
    if a.fixture:
        sys.path.insert(0, str(ROOT / "tests"))
        import d0114_fixture as fx
        from datetime import datetime as _dt

        class _Frozen(_dt):
            @classmethod
            def utcnow(cls):
                return cls(2026, 10, 22, 12, 0, 0)

            @classmethod
            def now(cls, tz=None):
                return cls(2026, 10, 22, 12, 0, 0)

        db = fx.build()
        with mock.patch.object(cs, "datetime", _Frozen):
            old, new = run_both(db)
        label = "OFFLINE FIXTURE (tests/d0114_fixture.py), not PROD"
    else:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        url = os.environ["DATABASE_URL"]
        kw = {"connect_args": {"options": "-c default_transaction_read_only=on"}} if url.startswith("postgres") else {}
        db = sessionmaker(bind=create_engine(url, **kw))()
        try:
            old, new = run_both(db)
        finally:
            db.rollback()
            db.close()
        label = "PROD (read-only)"
    text = table(old, new, label)
    if a.out:
        Path(a.out).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
