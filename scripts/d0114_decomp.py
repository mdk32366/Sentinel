"""D-0114 decomposition: per-dimension composite for named countries, old vs new.

READ-ONLY, same path as d0114_shadow.py (read-only session, rolled back).
    python scripts/d0114_decomp.py DEU GBR            # DATABASE_URL from env
    python scripts/d0114_decomp.py --fixture DEU GBR
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import d0114_shadow as sh  # noqa: E402

DIMS = ["tic_score", "gold_score", "monetary_score", "petro_score", "cds_score", "dim4_score"]
EXTRA = ["dim4_level_score", "dim4_spread_score", "dim4_source", "multiplier", "cross_asset",
         "divergence", "selling_treasuries", "selling_gold", "no_tic_holdings", "spot_gold_rising",
         "treseg_signal", "raw_score", "composite_score", "tier"]


def decompose(old, new, isos):
    out = []
    for iso in isos:
        o, n = old.get(iso, {}), new.get(iso, {})
        out += [f"## {iso}", "", "| field | old | new |", "|---|---|---|"]
        for k in DIMS + EXTRA:
            out.append(f"| {k} | {o.get(k, 0 if k == 'dim4_score' else None)} | {n.get(k)} |")
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("isos", nargs="+")
    a = ap.parse_args()
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    url = os.environ["DATABASE_URL"]
    kw = {"connect_args": {"options": "-c default_transaction_read_only=on"}} if url.startswith("postgres") else {}
    db = sessionmaker(bind=create_engine(url, **kw))()
    try:
        old, new = sh.run_both(db)
    finally:
        db.rollback()
        db.close()
    print(decompose(old, new, a.isos))


if __name__ == "__main__":
    main()
