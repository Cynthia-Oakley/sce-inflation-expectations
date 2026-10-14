"""Pure generalized-beta fit kernel for the frozen Q9 scorer.

Migrated verbatim on 2026-10-03 from scripts/diagnose_sce_beta.py (Codex's
diagnostic script) so that studies/sce_inflation_expectations/ is self-contained
and can be copied out of the repository without import failures. The fitting
code below is byte-for-byte the implementation the frozen scorer uses:
fit(bins, variant="relaxed_tail_skip_zero", tail_start=20.0). No diagnostic
data loading (xlsx/file readers, argparse, caches) is included; only the
numeric kernel and its EDGES constant were moved. Parameters, optimizer
settings, bounds and defaults are unchanged; the algorithm is unchanged.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares, brentq
from scipy.special import betainc

EDGES = np.array([-np.inf, -12, -8, -4, -2, 0, 2, 4, 8, 12, np.inf])


def fit(bins, variant="base", tail_start=20.0):
    p = np.asarray(bins, dtype=float)[::-1] / 100
    occupied = np.flatnonzero(p > 0)
    lo, hi = int(occupied[0]), int(occupied[-1])
    left_open, right_open = lo == 0, hi == 9
    edges = EDGES[lo + 1:hi + 1]
    cdf = np.cumsum(p)[lo:hi]
    # Diagnostics, not claims about the official procedure.
    mask = np.ones(len(edges), dtype=bool)
    if variant in ("skip_zero_cdf", "skip_zero_1001", "relaxed_tail_skip_zero"):
        mask = p[lo:hi] > 0
    relaxed_tail = variant.startswith("relaxed_tail")
    min_shape = .05 if variant == "relax_shape" else (
        1.001 if relaxed_tail or variant in ("shape_1001", "skip_zero_1001") else 1.0)
    max_shape = 2000.0 if variant == "cap_2000" else 200.0
    lower = [min_shape, min_shape] + ([-38.] if left_open else []) + ([12.000001] if right_open else [])
    upper = [max_shape, max_shape] + ([-12.000001] if left_open else []) + ([38.] if right_open else [])
    if relaxed_tail:
        if left_open: upper[2] = 12.0 if right_open else EDGES[hi+1] - 1e-6
        if right_open: lower[2 + int(left_open)] = -12.0 if left_open else EDGES[lo] + 1e-6

    def unpack(v):
        l = v[2] if left_open else EDGES[lo]
        r = v[2 + int(left_open)] if right_open else EDGES[hi + 1]
        return v[0], v[1], l, r

    def residual(v):
        a, b, l, r = unpack(v)
        if l >= r:
            return np.full(int(sum(mask)), 10.0 + l-r)
        pred = betainc(a, b, np.clip((edges - l) / (r - l), 0, 1))
        if variant == "bin_mass":
            return np.diff(np.r_[0., pred, 1.]) - p[lo:hi + 1]
        return (pred - cdf)[mask]

    starts = [(1.1, 1.1), (2., 2.), (5., 5.)]
    candidates = []
    for a, b in starts:
        init = [a, b] + ([-tail_start] if left_open else []) + ([tail_start] if right_open else [])
        res = least_squares(residual, init, bounds=(lower, upper),
                            ftol=1e-11, xtol=1e-11, gtol=1e-11, max_nfev=1200)
        candidates.append(res)
    best = min(candidates, key=lambda z: float(z.fun @ z.fun))
    a, b, l, r = unpack(best.x)
    # scipy 1.17.1 betaincinv is inaccurate at some shapes extremely near 1.
    # Invert the CDF independently; this does not affect the mean or fitting.
    q = np.array([l + (r-l)*brentq(lambda z: betainc(a,b,z)-p,0,1,xtol=1e-13)
                  for p in (.25,.5,.75)])
    return {"mean": float(l + (r-l)*a/(a+b)), "iqr": float(q[2]-q[0]),
            "quartiles": q.tolist(), "params": [float(v) for v in (a,b,l,r)],
            "loss": float(best.fun @ best.fun), "success": bool(best.success),
            "rank": int(np.linalg.matrix_rank(best.jac)), "n_parameters": len(best.x),
            "n_residuals": len(best.fun), "nfev": best.nfev,
            "shape_at_cap": bool(max(a,b) > max_shape - .001)}
