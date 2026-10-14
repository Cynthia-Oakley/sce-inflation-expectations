"""Shared data access for the belief-dynamics line.

Only the audited private reference parquet is read. Its sha256 is asserted
on every load. No network, no credentials, no other private inputs.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from ..factual_mechanism_audit import adjacent_pairs, wquantile, correlation  # noqa: F401  (re-exported)

REPO_ROOT = Path(__file__).resolve().parents[3]
REFERENCE_PARQUET = REPO_ROOT / "outputs" / "sce_age_reporting_audit_20261012_v1" / "reference_private.parquet"
REFERENCE_SHA256 = "86414d573d053b72ef20906dcc448ee9476f1679f86833144babd17bd433dc1b"

Q9_BIN_COLUMNS = [f"Q9_bin{i}" for i in range(1, 11)]

# Acceptance gate from docs/literature/sce/factual_mechanisms_20261013/summary_public.json
EXPECTED_ADJACENT_PAIRS = 106351
EXPECTED_VALID_Q9_PAIRS = 103630

VALID_PAIR_DEFINITION = (
    "Strict calendar-adjacent respondent-month pairs (a skipped interview is never t-1; "
    "reference implementation: studies/sce_inflation_expectations/factual_mechanism_audit.py "
    "adjacent_pairs), both waves' official Q9_mean finite, both waves' ten Q9 bins legal "
    "(each 0-100, sum 100 within 1e-6), and current-wave weight > 0. The 517 bin-legal "
    "pairs whose official Q9_mean is not published are excluded so the valid set matches "
    "the preregistered 103,630-pair reconciliation target."
)
WEIGHT_SCOPE_NOTE = (
    "SCE sampling weights are valid only for the current-wave cross-section; the previous "
    "wave's weight is not used. Month-equal aggregation gives every calendar month equal "
    "weight regardless of sample size or total weight."
)
OVERLAP_NOTE = (
    "Adjacent 12-month inflation-forecast windows overlap 11 months, so adjacent-wave "
    "correlations and update statistics contain mechanical overlap component; they are "
    "descriptive persistence/ordering facts, not causal update rates."
)


def sha256_path(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_reference_frame() -> pd.DataFrame:
    """Load the audited private micro cache, asserting the pinned sha256."""
    digest = sha256_path(REFERENCE_PARQUET)
    if digest != REFERENCE_SHA256:
        raise AssertionError(
            f"reference_private.parquet sha256 mismatch: {digest} != {REFERENCE_SHA256}")
    return pd.read_parquet(REFERENCE_PARQUET)


def month_index(date: int) -> int:
    """YYYYMM -> absolute month index."""
    return date // 100 * 12 + date % 100


def previous_calendar_month(date: int) -> int:
    y, m = divmod(int(date), 100)
    if m == 1:
        return (y - 1) * 100 + 12
    return y * 100 + (m - 1)


def legal_bins_mask(frame: pd.DataFrame) -> pd.Series:
    """Row-wise legality of the ten Q9 bins: finite, 0-100, sum 100 +/- 1e-6."""
    b = frame[Q9_BIN_COLUMNS].to_numpy(float)
    ok = (np.isfinite(b).all(axis=1) & (b >= 0).all(axis=1) & (b <= 100).all(axis=1)
          & (np.abs(b.sum(axis=1) - 100.0) <= 1e-6))
    return pd.Series(ok, index=frame.index)


def build_pairs(frame: pd.DataFrame) -> pd.DataFrame:
    """All strict calendar-adjacent pairs with legality flags for both waves.

    `frame` must already have numeric date/userid/weight/Q9_mean/Q9_iqr.
    """
    f = frame.copy()
    f["_bin_ok"] = legal_bins_mask(f)
    pairs = adjacent_pairs(f)
    meta = f.set_index(["userid", "date"])
    cur_idx = list(zip(pairs["userid"], pairs["date"]))
    prev_idx = list(zip(pairs["userid"], pairs["previous_date"]))
    pairs["cur_bin_ok"] = meta["_bin_ok"].loc[cur_idx].to_numpy()
    pairs["prev_bin_ok"] = meta["_bin_ok"].loc[prev_idx].to_numpy()
    pairs["cur_mean_ok"] = np.isfinite(pairs["Q9_mean"])
    pairs["prev_mean_ok"] = np.isfinite(pairs["previous_Q9_mean"])
    return pairs


def build_valid_pairs(frame: pd.DataFrame) -> pd.DataFrame:
    """The preregistered valid pair set (both waves legal, weight > 0)."""
    pairs = build_pairs(frame)
    valid = pairs[pairs["cur_bin_ok"] & pairs["prev_bin_ok"]
                  & pairs["cur_mean_ok"] & pairs["prev_mean_ok"]
                  & np.isfinite(pairs["weight"]) & (pairs["weight"] > 0)].copy()
    return valid


def add_month_equal_weight(valid: pd.DataFrame) -> pd.DataFrame:
    """Weight normalized within month so months carry equal aggregate mass."""
    valid = valid.copy()
    valid["month_weight"] = valid["weight"] / valid.groupby("date")["weight"].transform("sum")
    return valid
