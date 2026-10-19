"""Rank cached observed trait blocks by descriptive within-month linear fit.

No LLM, scorer, raw workbook scan, causal claims, or simulation input changes.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.linalg import lstsq

from population_associations import BASE, FACTORS, design, eligible, month_residual

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT/'outputs/sce_population_associations_20261015_v1'
PERIODS = {'2020_2022': (202001, 202212), '2023_2025_10': (202301, 202510)}


def importance(y, x, w, months, blocks):
    """Keep support fixed; add/remove every categorical block as a whole."""
    y, x, w = np.asarray(y, float), np.asarray(x, float), np.asarray(w, float)
    _, idx = np.unique(months, return_inverse=True)
    w = w / np.bincount(idx, weights=w)[idx]
    yy = month_residual(y, w, months).ravel()
    xx = month_residual(x, w, months)
    root = np.sqrt(w); yw = yy*root; xw = xx*root[:, None]
    tss = float(yw@yw)
    if not tss > 0:
        raise ValueError('Positive within-month variation required')

    def r2(cols):
        cols = list(cols)
        if not cols:
            return 0.0
        z = xw[:, cols]
        beta, _, _, _ = lstsq(z, yw, lapack_driver='gelsy')
        residual = yw-z@beta
        return 1-float(residual@residual)/tss

    allcols = list(range(x.shape[1])); full = r2(allcols)
    rows = []
    for block, cols in blocks.items():
        drop = full-r2([j for j in allcols if j not in cols])
        if drop < -1e-10:
            raise ValueError('Nested linear fit cannot worsen')
        rows.append({'factor': block, 'dummy_count': len(cols),
                     'drop_from_full_r2_points': 100*max(0, drop),
                     'alone_r2_points': 100*r2(cols)})
    return {'r2_within_month': full,
            'ranked_factors': sorted(rows, key=lambda v: -v['drop_from_full_r2_points'])}


def run(out):
    if out.exists():
        raise ValueError('Fresh output required')
    frame_path = CACHE/'analysis_frame_private.parquet'
    old = json.loads((CACHE/'summary.json').read_text())
    f = pd.read_parquet(frame_path); specs = {**BASE, **FACTORS}; periods = {}
    for period, (start, end) in PERIODS.items():
        sub = f.loc[f.date.between(start, end)]
        models = {}
        for outcome in ['Q9_mean', 'Q9_iqr']:
            data = eligible(sub, specs, outcome)
            x, _, blocks = design(data, specs)
            result = importance(data[outcome], x, data.weight.to_numpy(), data.date, blocks)
            expected = old['periods'][period]['models'][outcome]
            delta = abs(result['r2_within_month']-expected['R2_within_month'])
            if len(data) != expected['rows'] or delta > 1e-10:
                raise ValueError('Cached source-model reconciliation failed')
            models[outcome] = {**result, 'n_person_months': len(data),
                'n_persons': int(data.userid.nunique()), 'n_months': int(data.date.nunique()),
                'existing_full_r2_difference': delta}
        periods[period] = models
    result = {'status': 'descriptive_cached_trait_priority_not_causal_or_validation',
        'completed_at_utc': datetime.now(timezone.utc).isoformat(), 'new_llm_calls': 0,
        'q9_refits': 0, 'variables': list(specs), 'periods': periods,
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [frame_path, CACHE/'summary.json', Path(__file__)]},
        'method': 'Survey-weighted month fixed effects; equal monthly weight. Remove whole factor on identical complete cases; R2 loss is within-month R2 percentage points. Alone fit also controls month.',
        'limits': ['Ten available trait blocks, not an inventory of every SCE field.',
            'No historical answer or Simulation predictor included; Q1 is a current subjective condition.',
            'In-sample descriptive linear fit, not causal influence, out-of-sample ranking or statistical significance.',
            'Unique increments overlap and are not additive; correlated traits share information.',
            'No adjustment for number of factor levels in this descriptive R2 ranking.',
            'Official supplied Q9 mean and individual density IQR; these are not monthly headline medians or cross-person IQR.',
            'Previously inspected periods; outcome noise, nonlinearities and unmeasured traits remain.']}
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return result
