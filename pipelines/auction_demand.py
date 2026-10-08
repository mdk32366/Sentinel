"""Read-time auction demand metrics (D-0099, D-0101, D-0103). STUB — tests first."""
WINDOW_N = None
MIN_OBSERVATIONS = None
STALE_BUSINESS_DAYS = None
CHARTED_TERMS = {}


def attach_zscores(rows):
    out = []
    for r in rows:
        out.append(dict(r, b2c_z=0.0, b2c_z_window=0, b2c_z_reason=None,
                        dealer_z=0.0, dealer_z_window=0, dealer_z_reason=None))
    return out


def is_stale(data_as_of, today) -> bool:
    return None
