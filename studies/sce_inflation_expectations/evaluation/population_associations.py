"""Evaluation-only relationships of observed characteristics to SCE answers.

All person-level artifacts remain in ignored outputs. No API/provider imports.
"""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import chi2, t
import statsmodels.api as sm
from statsmodels.stats.sandwich_covariance import cov_cluster
from statsmodels.stats.multitest import multipletests

from population_field_inventory import read_rows

ROOT = Path(__file__).resolve().parents[3]
REFERENCE = ROOT/'outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet'
PROTOCOL = ROOT/'studies/sce_inflation_expectations/evaluation/population_association_protocol_20261015.json'
SOURCES = [('data/raw/sce_p_sources/micro_2017_2019.xlsx', 201701, 201912),
           ('data/raw/sce_audit_20260928/micro_2020_2024.xlsx', 202001, 202412),
           ('data/raw/sce_baselines_latest_20261007/micro_latest.xlsx', 202501, 202510)]
ENTRY_CODES = {'Q36': (1, 9), 'QRA1': (1, 7), 'QRA2': (1, 7), 'Q46': (1, 5),
               'QNUM8': (1, 3), 'QNUM9': (1, 2)}
QUIZ = {'QNUM1': 150., 'QNUM2': 242., 'QNUM3': 10., 'QNUM5': 100., 'QNUM6': 5.}
BASE = {'age_group': ['40 to 60', 'Under 40', 'Over 60'],
        'income_group': ['50k to 100k', 'Under 50k', 'Over 100k'],
        'gender': ['Male', 'Female'], 'region': ['Northeast', 'Midwest', 'South', 'West'],
        'employment': ['employed', 'unemployed', 'on_leave', 'disabled', 'retired', 'student', 'homemaker', 'other'],
        'numeracy': ['High', 'Low']}
FACTORS = {'education_fine': [5, 1, 2, 3, 4, 6, 7, 8, 9],
           'financial_change': [3, 1, 2, 4, 5], 'financial_risk': [4, 1, 2, 3, 5, 6, 7],
           'general_risk': [4, 1, 2, 3, 5, 6, 7]}
OUTCOMES = ['Q8v2part2', 'Q9_mean', 'Q9_iqr', 'zero_deflation_pct']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def clean_code(series, low, high):
    v = pd.to_numeric(series, errors='coerce')
    return v.where(v.between(low, high) & v.mod(1).eq(0))


def attach_history(raw):
    f = raw.sort_values(['userid', 'date']).copy()
    for key, (low, high) in ENTRY_CODES.items():
        f[key] = clean_code(f[key], low, high)
        f[key+'_source_month'] = f.date.where(f[key].notna())
        f[[key, key+'_source_month']] = f.groupby('userid', sort=False)[[key, key+'_source_month']].ffill()
        known = f[key].notna()
        assert (f.loc[known, key+'_source_month'] <= f.loc[known, 'date']).all()
    # Score single items from their actual entry answer, never make a blank an
    # incorrect answer and never assign missing raw answers from the High tag.
    for key, correct in QUIZ.items():
        values = pd.to_numeric(f[key], errors='coerce')
        f['correct_'+key] = values.eq(correct).astype(float).where(values.notna())
        f['correct_'+key] = f.groupby('userid', sort=False)['correct_'+key].ffill()
    f['correct_QNUM8'] = f.QNUM8.eq(3).astype(float).where(f.QNUM8.notna())
    f['correct_QNUM9'] = f.QNUM9.eq(2).astype(float).where(f.QNUM9.notna())
    # Current subjective financial state stays current; missing Q1 is NOT filled.
    f['financial_change'] = clean_code(f.Q1, 1, 5)
    return f


def build_frame(out):
    previous_receipt = json.loads((REFERENCE.parent/'summary.json').read_text())
    assert sha(REFERENCE) == previous_receipt['private_frame_sha256'], 'Reference cache changed'
    registry = json.loads((ROOT/'data/evaluation/sce_baselines_latest_20261007/micro_reference_sources.json').read_text())
    records = []; hashes = {str(REFERENCE.relative_to(ROOT)): sha(REFERENCE)}
    keep = ['date', 'userid', 'Q1', *ENTRY_CODES, *QUIZ]
    for relative, start, end in SOURCES:
        path = ROOT/relative
        hashes[relative] = sha(path)
        assert hashes[relative] == registry['sources'][relative], 'Workbook changed'
        n = 0
        for row in read_rows(path):
            month = int(row['date'])
            if start <= month <= end:
                records.append({k: row.get(k) for k in keep}); n += 1
        print('Read public traits', start, end, n, flush=True)
    raw = pd.DataFrame(records)
    raw[['date', 'userid']] = raw[['date', 'userid']].astype('int64')
    assert not raw.duplicated(['userid', 'date']).any()
    f = attach_history(raw)
    reference = pd.read_parquet(REFERENCE)
    assert set(map(tuple, f[['userid', 'date']].to_numpy())) == set(map(tuple, reference[['userid', 'date']].to_numpy()))
    extras = [*ENTRY_CODES, 'financial_change', *['correct_'+k for k in [*QUIZ, 'QNUM8', 'QNUM9']]]
    f = reference.merge(f[['userid', 'date', *extras]], on=['userid', 'date'], validate='one_to_one')
    f = f.rename(columns={'Q36': 'education_fine', 'QRA1': 'financial_risk', 'QRA2': 'general_risk',
        'Q46': 'financial_role', '_AGE_CAT': 'age_group', '_HH_INC_CAT': 'income_group',
        '_NUM_CAT': 'numeracy', '_REGION_CAT': 'region'})
    bins = f[[f'Q9_bin{i}' for i in range(1, 11)]].to_numpy(float)
    legal = np.isfinite(bins).all(axis=1) & (bins >= 0).all(axis=1) & (bins <= 100).all(axis=1) & (np.abs(bins.sum(axis=1)-100) <= 1e-6)
    f['zero_deflation_pct'] = np.where(legal, (bins[:, 5:].sum(axis=1) == 0).astype(float)*100, np.nan)
    f = f.sort_values(['userid', 'date']).reset_index(drop=True)
    f.to_parquet(out/'analysis_frame_private.parquet', index=False)
    return f, hashes


def design(frame, specs):
    names, columns, blocks = [], [], {}
    for field, levels in specs.items():
        present = [level for level in levels if frame[field].eq(level).any()]
        if len(present) < 2:
            continue
        blocks[field] = []
        for level in present[1:]:
            blocks[field].append(len(names)); names.append(f'{field}={level}')
            columns.append(frame[field].eq(level).to_numpy(float))
    return np.column_stack(columns), names, blocks


def month_residual(values, weights, months):
    v = np.asarray(values, float)
    if v.ndim == 1:
        v = v[:, None]
    _, index = np.unique(months, return_inverse=True)
    mass = np.bincount(index, weights=weights)
    means = np.column_stack([np.bincount(index, weights=weights*v[:, j])/mass for j in range(v.shape[1])])
    return v-means[index]


def fit_month_model(y, x, weight, months, persons):
    y, x, w = np.asarray(y, float), np.asarray(x, float), np.asarray(weight, float)
    _, index = np.unique(months, return_inverse=True)
    w = w/np.bincount(index, weights=w)[index]*(len(w)/len(np.unique(months)))
    yy = month_residual(y, w, months).ravel(); xx = month_residual(x, w, months)
    n, p = xx.shape; m = len(np.unique(months)); g = len(np.unique(persons))
    if np.linalg.matrix_rank(xx) != p or g < 2 or n <= p+m:
        raise ValueError('Unidentified or undersupported model')
    fit = sm.WLS(yy, xx, weights=w).fit()
    covariance = cov_cluster(fit, persons, use_correction=False)*g/(g-1)*(n-1)/(n-p-m)
    return {'coef': fit.params, 'cov': covariance, 'critical': float(t.ppf(.975, g-1)),
        'rows': n, 'persons': g, 'months': m, 'R2_within_month': float(1-np.sum(w*fit.resid**2)/np.sum(w*yy**2))}


def contrast(model, vector):
    v = np.asarray(vector, float); estimate = float(v@model['coef'])
    se = float(np.sqrt(max(0, v@model['cov']@v)))
    return {'estimate': estimate, 'se_person_cluster': se,
        'ci95': [estimate-model['critical']*se, estimate+model['critical']*se]}


def pack_model(model, names, blocks):
    results = {'rows': model['rows'], 'persons': model['persons'], 'months': model['months'],
        'R2_within_month': model['R2_within_month'], 'joint': {}, 'contrasts': {}}
    for factor, positions in blocks.items():
        b = model['coef'][positions]; cov = model['cov'][np.ix_(positions, positions)]
        stat = float(b@np.linalg.solve(cov, b))
        results['joint'][factor] = {'chi2': stat, 'df': len(positions), 'p': float(chi2.sf(stat, len(positions)))}
    definitions = {'education_fine': {'education_fine=2': 1},
        'financial_change': {'financial_change=2': 1},
        'financial_risk': {f'financial_risk={i}': w for i, w in [(1, -.5), (2, -.5), (6, .5), (7, .5)]},
        'general_risk': {f'general_risk={i}': w for i, w in [(1, -.5), (2, -.5), (6, .5), (7, .5)]},
        'financial_role': {'financial_role=5': 1, 'financial_role=1': -1}}
    for key in [*QUIZ, 'QNUM8', 'QNUM9']:
        definitions['correct_'+key] = {'correct_'+key+'=1': 1}
    for factor, definition in definitions.items():
        if all(name in names for name in definition):
            v = np.array([definition.get(name, 0.) for name in names])
            results['contrasts'][factor] = contrast(model, v)
    # All per-level coefficients are retained, not just convenient contrasts.
    results['coefficients'] = {name: contrast(model, np.eye(len(names))[i]) for i, name in enumerate(names)}
    return results


def eligible(frame, fields, outcome):
    mask = np.isfinite(frame.weight) & frame.weight.gt(0) & np.isfinite(frame[outcome])
    for field, levels in fields.items():
        mask &= frame[field].isin(levels)
    if outcome == 'Q9_iqr':
        mask &= frame[outcome].ge(0)
    return frame.loc[mask].copy()


def wquantile(x, w, q):
    order = np.argsort(x); values = np.asarray(x)[order]; weights = np.asarray(w)[order]
    return float(values[min(np.searchsorted(weights.cumsum(), q*weights.sum()), len(values)-1)])


def distribution_summaries(frame):
    result = {}
    for field, levels in FACTORS.items():
        output = {}
        for level in levels:
            group = frame.loc[frame[field].eq(level) & np.isfinite(frame.weight) & frame.weight.gt(0)]
            monthly = []; bin_curves = []
            for month, rows in group.groupby('date'):
                row = {'month': int(month), 'rows': len(rows)}
                for target in ['Q8v2part2', 'Q9_mean', 'Q9_iqr']:
                    valid = rows.loc[np.isfinite(rows[target])]
                    if len(valid) >= 10:
                        x, w = valid[target].to_numpy(float), valid.weight.to_numpy(float)
                        row[target+'_median'] = wquantile(x, w, .5)
                        if target == 'Q9_mean':
                            row['cross_person_IQR'] = wquantile(x, w, .75)-wquantile(x, w, .25)
                valid = rows.loc[np.isfinite(rows.zero_deflation_pct)]
                if len(valid) >= 10:
                    row['zero_deflation_pct'] = float(np.average(valid.zero_deflation_pct, weights=valid.weight))
                    curve = np.average(valid[[f'Q9_bin{i}' for i in range(1, 11)]], axis=0, weights=valid.weight)
                    bin_curves.append(curve)
                monthly.append(row)
            keys = ['Q8v2part2_median', 'Q9_mean_median', 'Q9_iqr_median', 'cross_person_IQR', 'zero_deflation_pct']
            output[str(level)] = {'rows': len(group), 'persons': int(group.userid.nunique()),
                'equal_month': {key: {'value': float(np.mean([r[key] for r in monthly if key in r])),
                    'months': sum(key in r for r in monthly)} for key in keys if any(key in r for r in monthly)},
                'average_probability_by_bin': np.mean(bin_curves, axis=0).tolist() if bin_curves else None,
                'monthly': monthly}
        result[field] = output
    return result


def adjacent_differences(frame, target, specs):
    f = frame.sort_values(['userid', 'date']).copy()
    lag = f.groupby('userid', sort=False).shift()
    mi = f.date//100*12+f.date%100
    previous_mi = lag.date//100*12+lag.date%100
    valid = mi.sub(previous_mi).eq(1) & np.isfinite(f[target]) & np.isfinite(lag[target])
    for field, levels in specs.items():
        valid &= f[field].isin(levels) & lag[field].isin(levels)
    valid &= np.isfinite(f.weight) & f.weight.gt(0)
    rows = f.loc[valid].copy(); previous = lag.loc[valid]
    columns, names = [], []
    for field, levels in specs.items():
        for level in levels[1:]:
            x = rows[field].eq(level).to_numpy(float)-previous[field].eq(level).to_numpy(float)
            if np.any(x):
                columns.append(x); names.append(f'{field}={level}')
    return rows, rows[target].to_numpy()-previous[target].to_numpy(), np.column_stack(columns), names


def run(out, cache=None):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    out.mkdir(parents=True)
    protocol = json.loads(PROTOCOL.read_text())
    if cache is None:
        frame, hashes = build_frame(out)
        dump(out/'frame_sources.json', hashes)
    else:
        cache = Path(cache).resolve()
        hashes = json.loads((cache.parent/'frame_sources.json').read_text())
        frame = pd.read_parquet(cache)
        hashes[str(cache.relative_to(ROOT))] = sha(cache)
        frame.to_parquet(out/'analysis_frame_private.parquet', index=False)
        dump(out/'frame_sources.json', hashes)
    all_specs = {**FACTORS, **BASE}
    results = {}
    for period, (start, end) in protocol['periods'].items():
        current = frame.loc[frame.date.between(start, end)].copy()
        print('Fit period', period, len(current), flush=True)
        block = {'rows': len(current), 'persons': int(current.userid.nunique()), 'models': {},
                 'distributions': distribution_summaries(current), 'secondary': {}, 'first_differences': {}}
        for outcome in OUTCOMES:
            data = eligible(current, all_specs, outcome)
            x, names, groups = design(data, all_specs)
            model = fit_month_model(data[outcome], x, data.weight, data.date, data.userid)
            block['models'][outcome] = pack_model(model, names, groups)
            print('Primary', outcome, len(data), flush=True)
            if outcome == 'Q8v2part2':
                clipped = fit_month_model(data[outcome].clip(-100, 100), x, data.weight, data.date, data.userid)
                block['Q8_tail_sensitivity'] = pack_model(clipped, names, groups)
                block['Q8_tail_sensitivity']['capped_rows'] = int(data[outcome].abs().gt(100).sum())
        tests = [(outcome, factor) for outcome in OUTCOMES for factor in FACTORS]
        p = [block['models'][y]['joint'][f]['p'] for y, f in tests]
        for (y, f), q in zip(tests, multipletests(p, method='fdr_bh')[1]):
            block['models'][y]['joint'][f]['BH_q_primary_16'] = float(q)
        # Increment of the detailed quiz response pattern, beyond High/Low.
        quiz_specs = {**all_specs, **{'correct_'+k: [0, 1] for k in [*QUIZ, 'QNUM8', 'QNUM9']}}
        for outcome in ['Q9_mean', 'Q9_iqr', 'zero_deflation_pct']:
            data = eligible(current, quiz_specs, outcome)
            x, names, groups = design(data, quiz_specs)
            base_x, _, _ = design(data, all_specs)
            detailed = fit_month_model(data[outcome], x, data.weight, data.date, data.userid)
            base = fit_month_model(data[outcome], base_x, data.weight, data.date, data.userid)
            packed = pack_model(detailed, names, groups)
            positions = [i for i, name in enumerate(names) if name.startswith('correct_')]
            b = detailed['coef'][positions]; covariance = detailed['cov'][np.ix_(positions, positions)]
            stat = float(b@np.linalg.solve(covariance, b))
            packed['seven_items_joint'] = {'chi2': stat, 'df': len(positions), 'p': float(chi2.sf(stat, len(positions)))}
            packed['same_sample_base_R2'] = base['R2_within_month']
            packed['incremental_R2'] = detailed['R2_within_month']-base['R2_within_month']
            block['secondary']['quiz_'+outcome] = packed
            role_specs = {**all_specs, 'financial_role': [3, 1, 2, 4, 5]}
            data = eligible(current, role_specs, outcome)
            x, names, groups = design(data, role_specs)
            block['secondary']['role_'+outcome] = pack_model(fit_month_model(data[outcome], x, data.weight, data.date, data.userid), names, groups)
        # Same-person changes: static unobserved personal intercepts cancel.
        delta_specs = {'financial_change': FACTORS['financial_change'],
                       'income_group': BASE['income_group'], 'employment': BASE['employment']}
        for outcome in ['Q8v2part2', 'Q9_mean', 'Q9_iqr']:
            rows, dy, x, names = adjacent_differences(frame.loc[frame.date.le(end)], outcome, delta_specs)
            select = rows.date.ge(start).to_numpy(); rows = rows.loc[select]; dy = dy[select]; x = x[select]
            active = np.ptp(x, axis=0)>0; x = x[:, active]; names = [n for n, keep in zip(names, active) if keep]
            groups = {'financial_change': [i for i, n in enumerate(names) if n.startswith('financial_change=')]}
            block['first_differences'][outcome] = pack_model(fit_month_model(dy, x, rows.weight, rows.date, rows.userid), names, groups)
        results[period] = block
    summary = {'status': 'completed_observational_analysis_not_causal_or_simulation', 'new_api_calls': 0,
        'protocol': protocol, 'periods': results, 'source_sha256': {**hashes, str(PROTOCOL.relative_to(ROOT)): sha(PROTOCOL),
            str(Path(__file__).relative_to(ROOT)): sha(Path(__file__)),
            'studies/sce_inflation_expectations/evaluation/population_field_inventory.py': sha(ROOT/'studies/sce_inflation_expectations/evaluation/population_field_inventory.py')},
        'analysis_frame_sha256': sha(out/'analysis_frame_private.parquet'),
        'limits': ['No causal identification: current Q1 and inflation beliefs may influence one another.',
            'Month FE, observed controls and person clustering do not resolve every omitted variable or shared residual shock.',
            'Risk, education and financial role are observed entry traits carried only forward; not experimentally assigned behaviour.',
            'First differences cancel stable person effects but not time-varying confounders or survey measurement error.',
            'Adjacent forecasts have rolling overlapping 12-month horizons; revisions are not fixed-target Bayesian updates.',
            'Conditional regression coefficients refer to means; descriptive group medians/IQR are separate objects.',
            'Descriptive distributions are not population-standardized for all controls. Secondary models are exploratory.',
            'No simulation inputs changed, no observed current target values exported to a provider.']}
    dump(out/'summary.json', summary)
    print('Completed zero-API population associations', flush=True)
    return summary
