"""Frozen project Q9 scorer (the project's single approximate density metric).

Dispatch (preregistered in docs/SCORER_HOLDOUT_PLAN_20261003.md, selected on the
2020-04 / 2021-10 / 2022-12 holdout, outputs/scorer_holdout_20261003T023026Z_77ebb305):

- Every answer is first scored by the ORIGINAL scorer (sce_q9.score_q9), which is
  not modified.
- If the ten bins are valid (each 0-100, sum 100 within 1e-6) AND at least three
  bins are positive, the result is replaced by the holdout-selected candidate:
  beta_fit_kernel.fit(..., variant="relaxed_tail_skip_zero", tail_start=20.0),
  with prob_deflation from the fitted beta CDF.
- All other families (uniform / two-bin triangle / invalid) stay byte-identical
  to the original scorer.

2026-10-03 kernel migration (review docs/CORE_NORMAL_REVIEW_20261003.md sec. 4):
the fit kernel was moved verbatim from scripts/diagnose_sce_beta.py into this
directory as beta_fit_kernel.py, so the study is self-contained when copied out
of the repository. The algorithm and all parameters are unchanged; equivalence
on all 3,741 sealed holdout rows was verified with zero per-field difference.
Pinned-hash record of the migration:
  scripts/diagnose_sce_beta.py (old source, unchanged, still pinned for the
      record): b45a29345f432288fe3b0b18e8c39066998bf19a803a0e7c661dc2a193987e57
  studies/sce_inflation_expectations/scoring/beta_fit_kernel.py (new source):
      1db41474fa927b6a207b7bc8d0dd0fdfe5d3b2bc359620fced0c54b9d66b05bb

Per D039 this one algorithm scores BOTH the real SCE questionnaires and the
simulated ones; the approximation and its difference from the official headline
are reported alongside. The pinned source hashes below are the freeze record;
provenance() lets any run report exactly which code produced its scores.
"""

from __future__ import annotations

import hashlib
import math
import sys
from pathlib import Path
from typing import Sequence

import numpy as np
from scipy.special import betainc

_HERE = Path(__file__).resolve()
sys.path.insert(0, str(_HERE.parent))
from sce_q9 import DensityScore, score_q9  # noqa: E402
from beta_fit_kernel import fit as beta_fit  # noqa: E402

FROZEN_VARIANT = "relaxed_tail_skip_zero"
FROZEN_TAIL_START = 20.0
HOLDOUT_RUN_ID = "20261003T023026Z_77ebb305"
# 2026-10-03 kernel migration: the fit source moved from
# scripts/diagnose_sce_beta.py (b45a29345f432288fe3b0b18e8c39066998bf19a803a0e
# 7c661dc2a193987e57) to scoring/beta_fit_kernel.py (below). Algorithm unchanged.
PINNED_SHA256 = {
    "studies/sce_inflation_expectations/scoring/sce_q9.py":
        "24bccc6581201003840b1c2c7d21cf4f0749ec937c47075e24b398fb03489c09",
    "studies/sce_inflation_expectations/scoring/beta_fit_kernel.py":
        "1db41474fa927b6a207b7bc8d0dd0fdfe5d3b2bc359620fced0c54b9d66b05bb",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def provenance() -> dict:
    """Freeze record: pinned sources, live hashes, variant and holdout evidence."""
    live = {
        "studies/sce_inflation_expectations/scoring/sce_q9.py": _sha256(
            _HERE.parent / "sce_q9.py"),
        "studies/sce_inflation_expectations/scoring/beta_fit_kernel.py": _sha256(
            _HERE.parent / "beta_fit_kernel.py"),
    }
    return {
        "scorer": "sce_q9_frozen",
        "variant": FROZEN_VARIANT,
        "tail_start": FROZEN_TAIL_START,
        "holdout_run_id": HOLDOUT_RUN_ID,
        "pinned_sha256": PINNED_SHA256,
        "live_sha256": live,
        "live_matches_pinned": live == PINNED_SHA256,
        "kernel_migration": {
            "migrated_at": "2026-10-03",
            "old_source": "scripts/diagnose_sce_beta.py",
            "old_source_sha256":
                "b45a29345f432288fe3b0b18e8c39066998bf19a803a0e7c661dc2a193987e57",
            "new_source": "studies/sce_inflation_expectations/scoring/beta_fit_kernel.py",
            "algorithm_unchanged": True,
            "equivalence_check": "3,741 sealed holdout rows recomputed; zero per-field difference",
        },
        "approximation_notice": (
            "Research approximation of the Armantier et al. (2017) Appendix C "
            "generalized-beta fit, selected on a preregistered holdout; not the "
            "official FRBNY implementation. The same algorithm scores real and "
            "simulated questionnaires; differences from official headline values "
            "are reported separately."),
    }


def _valid_bins(bins: Sequence[float]) -> bool:
    return (len(bins) == 10
            and all(isinstance(v, (int, float)) and math.isfinite(v) and 0 <= v <= 100
                    for v in bins)
            and abs(sum(bins) - 100) <= 1e-6)


def score_q9_frozen(bins: Sequence[float]) -> DensityScore:
    """Score one ten-bin Q9 answer with the frozen project algorithm."""
    base = score_q9(bins)
    if not (_valid_bins(bins) and sum(v > 0 for v in bins) >= 3):
        return base
    try:
        fit = beta_fit(list(bins), FROZEN_VARIANT,
                       tail_start=FROZEN_TAIL_START)
    except Exception:
        # Explicit, countable failure (the holdout saw zero of these); never
        # silently fall back to another algorithm.
        return DensityScore("candidate_exception", "generalized_beta",
                            None, None, None, None, None, None, None)
    a, b, left, right = fit["params"]
    cdf = lambda x: float(betainc(a, b, np.clip((x - left) / (right - left), 0, 1)))
    return DensityScore(
        "ok", "generalized_beta", fit["mean"],
        fit["quartiles"][0], fit["quartiles"][1], fit["quartiles"][2],
        fit["iqr"], cdf(0.0), fit["loss"],
    )
