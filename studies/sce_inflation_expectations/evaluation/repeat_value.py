"""Information in two cached generations, distinct from population diversity."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.stats import pearsonr

from .metrics import quantile


def report(source, out):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists():
        raise ValueError('Fresh output required')
    cases = json.loads(source.read_text())
    lookup = {(r['month'], r['agent_id'], r['repeat']): r for r in cases}
    if len(lookup) != len(cases):
        raise ValueError('Duplicate person-month-repeat')
    months = sorted({r['month'] for r in cases})
    arms = sorted(cases[0]['arms'])
    results = {}
    for arm in arms:
        cells = []
        for month in months:
            pairs = [(r, lookup.get((month, r['agent_id'], 2))) for r in cases
                     if r['month'] == month and r['repeat'] == 1]
            pairs = [(a, b) for a, b in pairs if b is not None
                     and a['real'].get('q9_mean') is not None
                     and all(z['arms'][arm].get('mean') is not None
                             and np.isfinite(z['arms'][arm]['mean']) for z in (a, b))]
            if len(pairs) < 2:
                continue
            x = np.array([[a['arms'][arm]['mean'], b['arms'][arm]['mean']] for a, b in pairs])
            w = np.array([a['design_survey_weight'] for a, b in pairs], float)
            if not np.isfinite(w).all() or (w <= 0).any():
                raise ValueError('Finite positive design weights required')
            w /= w.sum()
            within = float(w@((x[:, 0]-x[:, 1])**2)/2)
            z = x.mean(axis=1)
            between_means = float(w@((z-w@z)**2))
            stable = between_means-within/2
            raw = [(a['arms'][arm].get('raw_q9_bins', a['arms'][arm].get('q9_bins')),
                    b['arms'][arm].get('raw_q9_bins', b['arms'][arm].get('q9_bins'))) for a, b in pairs]
            valid_raw = [i for i, (a, b) in enumerate(raw) if a is not None and b is not None]
            same = [i for i in valid_raw if np.allclose(raw[i][0], raw[i][1], atol=1e-6, rtol=0)]
            cells.append({'month': month, 'people': len(pairs),
                          'mean_absolute_repeat_gap_pp': float(w@abs(x[:, 0]-x[:, 1])),
                          'person_pearson_equal_weight': float(pearsonr(x[:, 0], x[:, 1]).statistic)
                          if np.ptp(x[:, 0]) > 0 and np.ptp(x[:, 1]) > 0 else None,
                          'raw_q9_same_share': float(w[same].sum()/w[valid_raw].sum()) if valid_raw else None,
                          'monthly_median_repeat_gap_pp': abs(quantile(x[:, 0], w, .5)-quantile(x[:, 1], w, .5)),
                          'within_person_generation_variance_pp2': within,
                          'noise_adjusted_between_variance_pp2': stable,
                          'generation_noise_fraction': within/(stable+within) if stable+within > 0 else None})
        if not cells:
            continue
        keys = [k for k in cells[0] if k not in ('month', 'people')]
        results[arm] = {'monthly': cells, 'equal_month_means':
                       {k: float(np.mean([r[k] for r in cells if r[k] is not None]))
                        if any(r[k] is not None for r in cells) else None for k in keys}}
    if not results:
        raise ValueError('No valid paired generations')
    result = {'status': 'cached_two_generation_information_diagnostic',
              'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'new_api_calls': 0, 'source': str(source),
              'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'implementation_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'compared_repeats': [1, 2], 'arms': results,
              'limits': ['Only cached generations1/2; conditional on these people, prompts and months.',
                         'Pearson uses equal people within month; gaps/variance use design weights, months equally weighted.',
                         'Variance subtraction is descriptive; two repeats do not establish a precise random-effects model.',
                         'LLM repeat noise is not stable human heterogeneity or additional real respondents.',
                         'Results for Qwen or DeepSeek do not establish the variance of an untested V3.2 route.']}
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    return result
