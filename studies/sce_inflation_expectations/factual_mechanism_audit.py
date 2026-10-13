"""Offline aggregate diagnostics for observed priors and CE recorded purchase days.

No simulation provider, API client, credentials or runtime inputs are loaded.
SCE outcomes remain evaluation-only. Diary day counts are external proxies.
"""
from collections import defaultdict
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .diary_experience import CATEGORY_NAMES, VALID_DAY_FLAGS


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wquantile(x, w, q=.5):
    x, w = np.asarray(x, float), np.asarray(w, float)
    valid = np.isfinite(x) & np.isfinite(w) & (w > 0)
    x, w = x[valid], w[valid]
    if not len(x):
        return None
    idx = np.argsort(x, kind='stable')
    x, w = x[idx], w[idx]
    return float(x[min(np.searchsorted(w.cumsum(), q*w.sum()), len(x)-1)])


def correlation(x, y, w):
    x, y, w = np.asarray(x, float), np.asarray(y, float), np.asarray(w, float)
    x, y = x-np.average(x, weights=w), y-np.average(y, weights=w)
    den = np.sqrt(np.average(x*x, weights=w)*np.average(y*y, weights=w))
    return None if den == 0 else float(np.average(x*y, weights=w)/den)


def adjacent_pairs(frame):
    """Exact calendar adjacency; never treat a missing interview as t-1."""
    if frame.duplicated(['userid', 'date']).any():
        raise ValueError('duplicate respondent-month')
    f = frame.sort_values(['userid', 'date']).copy()
    f['mi'] = f.date.floordiv(100)*12+f.date.mod(100)
    names = ['date', 'mi', 'Q9_mean', 'Q9_iqr', 'weight']
    prev = f.groupby('userid', sort=False)[names].shift(1).add_prefix('previous_')
    f = pd.concat([f, prev], axis=1)
    return f[f.mi-f.previous_mi == 1].copy()


def audit_prior(frame):
    f = frame.copy()
    for k in ['date', 'userid', 'weight', 'Q9_mean', 'Q9_iqr']:
        f[k] = pd.to_numeric(f[k], errors='coerce')
    if f[['date', 'userid']].isna().any().any():
        raise ValueError('invalid panel key')
    f['date'] = f.date.astype(int)
    pairs = adjacent_pairs(f)
    valid = pairs[np.isfinite(pairs.Q9_mean) & np.isfinite(pairs.previous_Q9_mean)
                  & np.isfinite(pairs.weight) & (pairs.weight > 0)].copy()
    monthly = []
    for month, now in f.groupby('date', sort=True):
        allpairs = pairs[pairs.date == month]
        p = valid[valid.date == month]
        rec = {'month': int(month), 'wave_n': len(now), 'adjacent_same_person_n': len(allpairs),
               'adjacent_coverage_fraction': len(allpairs)/len(now), 'valid_q9_pairs_n': len(p)}
        if len(p):
            w = p.weight.to_numpy(float)
            delta = p.Q9_mean-p.previous_Q9_mean
            common = wquantile(p.previous_Q9_mean, w)
            rec.update({'own_previous_mae_pp': float(np.average(abs(delta), weights=w)),
                        'own_previous_median_absolute_change_pp': wquantile(abs(delta), w),
                        'common_previous_panel_median_mae_pp': float(np.average(abs(p.Q9_mean-common), weights=w)),
                        'q9_pair_correlation': correlation(p.previous_Q9_mean, p.Q9_mean, w),
                        'q9_unweighted_spearman': float(p.previous_Q9_mean.corr(p.Q9_mean, method='spearman')),
                        'share_absolute_change_at_most_0_5pp': float(np.average(abs(delta) <= .5, weights=w)),
                        'prior_q9_iqr_pp': wquantile(p.previous_Q9_mean,w,.75)-wquantile(p.previous_Q9_mean,w,.25),
                        'current_q9_iqr_pp': wquantile(p.Q9_mean,w,.75)-wquantile(p.Q9_mean,w,.25)})
        monthly.append(rec)
    # Normalize weights within each month, so months have equal aggregate mass.
    if not len(valid):
        return {'monthly': monthly, 'valid_pairs': 0}
    valid['mw'] = valid.weight / valid.groupby('date').weight.transform('sum')
    x, y = valid.previous_Q9_mean.copy(), valid.Q9_mean.copy()
    for month, p in valid.groupby('date'):
        x.loc[p.index] -= np.average(p.previous_Q9_mean, weights=p.weight)
        y.loc[p.index] -= np.average(p.Q9_mean, weights=p.weight)
    uncertainty = valid[np.isfinite(valid.Q9_iqr) & np.isfinite(valid.previous_Q9_iqr)]
    yearly = {}
    for year, p in valid.groupby(valid.date.floordiv(100)):
        rows = [r for r in monthly if r['month']//100 == year and r['valid_q9_pairs_n']]
        yearly[str(int(year))] = {
            'pairs': len(p), 'months': len(rows),
            'own_previous_mae_pp_month_equal': float(np.mean([r['own_previous_mae_pp'] for r in rows])),
            'common_prior_mae_pp_month_equal': float(np.mean([r['common_previous_panel_median_mae_pp'] for r in rows]))}
    return {'rows': len(f), 'months': int(f.date.nunique()),
            'unique_respondents': int(f.userid.nunique()),
            'adjacent_pairs': len(pairs), 'valid_q9_pairs': len(valid),
            'monthly': monthly, 'yearly': yearly,
            'within_month_centered_q9_correlation': correlation(x, y, valid.mw),
            'mean_monthly_unweighted_spearman': float(np.mean([r['q9_unweighted_spearman'] for r in monthly if r.get('q9_unweighted_spearman') is not None])),
            'uncertainty_pair_correlation': correlation(uncertainty.previous_Q9_iqr, uncertainty.Q9_iqr, uncertainty.mw),
            'interpretation': 'Descriptive A-line repeated-person diagnostic, not a causal effect or PIT B forecast. Previous/current rolling 12-month windows overlap 11 months. Prior-only benchmarks condition on returning valid respondents and current evaluation weights.'}


def category_days(rows, category_map, known_ucc):
    """Count distinct valid days, retaining missing support per category."""
    out = {k: {'days': set(), 'positive_records': 0, 'missing_day_records': 0,
               'invalid_cost_records': 0} for k in CATEGORY_NAMES}
    for row in rows:
        if str(row.get('PUB_FLAG') or '').strip() != '2':
            continue
        code = str(row.get('UCC') or '').strip().zfill(6)
        k = category_map.get(code, 'other_known_ucc' if code in known_ucc else 'unknown_ucc')
        try:
            cost = Decimal(str(row.get('COST') or '').strip())
            if not cost.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            out[k]['invalid_cost_records'] += 1
            continue
        if cost <= 0:
            continue
        out[k]['positive_records'] += 1
        try:
            raw = Decimal(str(row.get('EXPNSQDY') or '').strip())
            if not raw.is_finite() or raw != int(raw) or not 1 <= raw <= 7:
                raise ValueError
            if str(row.get('EXPN_QDY') or '').strip() not in VALID_DAY_FLAGS:
                raise ValueError
            out[k]['days'].add(int(raw))
        except (InvalidOperation, ValueError, OverflowError):
            out[k]['missing_day_records'] += 1
    for item in out.values():
        item['day_codes'] = sorted(item.pop('days'))
        item['recorded_days_7d'] = len(item['day_codes'])
        item['status'] = ('no_published_positive_records' if not item['positive_records']
                          else 'partial_day_support' if item['missing_day_records'] or item['invalid_cost_records']
                          else 'complete_recorded_day_support')
        # Zero recorded days does not assert the household never bought the category.
    return out


def audit_diary(old_rows, expd, category_map, known_ucc):
    by_id = defaultdict(list)
    for row in expd:
        by_id[str(row['NEWID']).strip()].append(row)
    summary, output = {}, []
    # Registry computed once; same key formula as original preparation.
    from .diary_experience import _hash_key
    lookup = {_hash_key('week|Q4', uid): rows for uid, rows in by_id.items()}
    for old in old_rows:
        details = lookup.get(old['diary_week_key_sha256'], [])
        groups = category_days(details, category_map, known_ucc)
        union = sorted(set().union(*(set(x['day_codes']) for x in groups.values())))
        expected = old['purchase_day_support']['valid_day_codes_1_to_7']
        if union != expected:
            raise ValueError('category day union disagrees with prior validated overall day set')
        output.append({'diary_cu_pair_key_sha256': old['diary_cu_pair_key_sha256'],
                       'diary_week_key_sha256': old['diary_week_key_sha256'],
                       'week': old['diary_week_number'], 'weight': float(old['sampling_weight_FINLWT21']),
                       'demographics': old['consumer_unit_demographics_raw'], 'categories': groups})
    pairs = defaultdict(dict)
    for row in output:
        pairs[row['diary_cu_pair_key_sha256']][row['week']] = row
    for k in CATEGORY_NAMES:
        positive = [r for r in output if r['categories'][k]['positive_records']]
        complete = [r for r in positive if r['categories'][k]['status'] == 'complete_recorded_day_support']
        both = [(v[1]['categories'][k], v[2]['categories'][k]) for v in pairs.values()
                if 1 in v and 2 in v and all(v[t]['categories'][k]['status'] == 'complete_recorded_day_support' for t in [1,2])]
        summary[k] = {'positive_record_week_n': len(positive), 'complete_day_week_n': len(complete),
                      'partial_day_week_n': len(positive)-len(complete),
                      'no_positive_record_week_n': len(output)-len(positive),
                      'weighted_median_days_given_complete_positive_records': wquantile(
                          [r['categories'][k]['recorded_days_7d'] for r in complete], [r['weight'] for r in complete]),
                      'same_cu_two_complete_positive_weeks_n': len(both),
                      'two_week_median_absolute_day_difference': float(np.median([abs(a['recorded_days_7d']-b['recorded_days_7d']) for a,b in both])) if both else None}
    return output, {'household_weeks': len(output), 'unique_cu_pairs': len(pairs),
                    'overall_day_set_reconciliation_passed': len(output), 'categories': summary,
                    'interpretation': 'Recorded days with positive published costs, conditional on support; not transaction counts, attention, or annual frequency. Weekly zeros are censored exposure observations, not stable nonconsumer labels. Current corrected 2020Q4 file is A-only unless a historical B version is independently established.'}
