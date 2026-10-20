"""Calm/drastic month regimes from the archived full-sample truth series.

The regime lookup is built from the per-month weighted median of Q9_mean in
``outputs/sce_age_reporting_audit_20261012_v1/reference_private.parquet``
(NaN means excluded). A month is drastic when the absolute change of the
weighted median versus the previous month in that series is >= 0.2pp. The
parquet is a continuous monthly series, so chained deltas are well defined;
batch months are a non-contiguous subset and inherit labels from this series.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

EXPECTED_SHA256 = ('86414d573d053b72ef20906dcc448ee9476f1679'
                   'f86833144babd17bd433dc1b')
DEFAULT_PARQUET = Path(__file__).resolve().parents[3] / 'outputs' / (
    'sce_age_reporting_audit_20261012_v1/reference_private.parquet')
DRASTIC_THRESHOLD_PP = 0.2


def build_regime_lookup(monthly_medians, threshold_pp=DRASTIC_THRESHOLD_PP):
    """Pure lookup builder; monthly_medians maps YYYYMM -> weighted median pp."""
    months = sorted(monthly_medians)
    lookup = {}
    previous = None
    for month in months:
        median = monthly_medians[month]
        if previous is None:
            delta, regime = None, 'series_start'
        else:
            delta = abs(median - previous)
            regime = 'drastic' if delta >= threshold_pp else 'calm'
        lookup[month] = {'median_pp': float(median), 'abs_delta_pp': delta,
                         'regime': regime}
        previous = median
    return lookup


def load_regime_lookup(parquet_path=DEFAULT_PARQUET,
                       expected_sha256=EXPECTED_SHA256,
                       threshold_pp=DRASTIC_THRESHOLD_PP):
    parquet_path = Path(parquet_path)
    digest = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ValueError(
            'reference_private.parquet sha256 mismatch: got %s, expected %s; '
            'refusing to build regime lookup on an unverified source' % (digest, expected_sha256))
    frame = pd.read_parquet(parquet_path)
    frame = frame[np.isfinite(frame['Q9_mean']) & (frame['weight'] > 0)]
    medians = {}
    for month, group in frame.groupby('date'):
        order = np.argsort(group['Q9_mean'].values, kind='stable')
        x = group['Q9_mean'].values[order]
        w = group['weight'].values[order]
        index = np.searchsorted(np.cumsum(w), 0.5 * w.sum(), side='left')
        medians[int(month)] = float(x[min(index, len(x) - 1)])
    return build_regime_lookup(medians, threshold_pp)
