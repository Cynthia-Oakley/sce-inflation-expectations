"""Evaluation-only demographic grid selection using existing SCE answers.

No provider, simulator or Q9 fitting imports. Outcomes never become P/E.
"""
from __future__ import annotations

from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
import hashlib
import json
import math

import numpy as np
import pandas as pd
from scipy.linalg import solve

from ..population_stratification import allocate_core

ROOT = Path(__file__).resolve().parents[3]
PROTOCOL = Path(__file__).with_name('grid_dimension_protocol_20261023.json')
CACHE = ROOT/'outputs/sce_population_associations_20261015_v1/analysis_frame_private.parquet'
FEATURES = {
    'education': ['high_school', 'some_college', 'college'],
    'numeracy': ['High', 'Low'],
    'income': ['under_50k', '50k_100k', 'over_100k'],
    'age': ['under_40', '40_60', 'over_60'],
    'employment': ['attached', 'unemployed', 'retired', 'other_not_working'],
    'gender': ['Male', 'Female'],
    'housing': ['owner', 'renter', 'other'],
    'region': ['Northeast', 'Midwest', 'South', 'West'],
}
LABELS = {'education': '学历', 'numeracy': '数理能力', 'income': '收入', 'age': '年龄',
          'employment': '就业四类', 'gender': '性别', 'housing': '住房', 'region': '地区'}
THRESHOLDS = np.array([-5., 0., 2., 4., 6., 8., 10., 15., 20.])
DOMAIN_NAMES = ['level', 'uncertainty', 'reporting', 'distribution']
HOUSING_SOURCES = [
    ('data/raw/sce_p_sources/micro_2017_2019.xlsx', 201701, 201912),
    ('data/raw/sce_audit_20260928/micro_2020_2024.xlsx', 202001, 202412),
    ('data/raw/sce_micro_refresh_20261021/micro_latest.xlsx', 202501, 202510),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def ess(w):
    w = np.asarray(w, float)
    return float(w.sum()**2/(w@w)) if len(w) and w.sum() > 0 else 0.


def equal_month_weights(frame):
    w = frame.weight.to_numpy(float)
    _, m = np.unique(frame.date.to_numpy(), return_inverse=True)
    return w/np.bincount(m, weights=w)[m]


def residualize(a, w, months):
    a = np.asarray(a, float)
    if a.ndim == 1:
        a = a[:, None]
    _, m = np.unique(months, return_inverse=True)
    mass = np.bincount(m, weights=w)
    mean = np.column_stack([np.bincount(m, weights=w*a[:, j])/mass for j in range(a.shape[1])])
    return a-mean[m]


def weighted_cramers_v(a, b, w):
    _, i = np.unique(a, return_inverse=True)
    _, j = np.unique(b, return_inverse=True)
    table = np.zeros((i.max()+1, j.max()+1))
    np.add.at(table, (i, j), w)
    p = table/table.sum()
    expected = p.sum(1)[:, None]*p.sum(0)[None, :]
    df = min(len(p)-1, p.shape[1]-1)
    return float(np.sqrt(np.sum((p-expected)**2/expected)/df)) if df > 0 else 0.


def encode(frame, *, include_attachment=False):
    columns, blocks = [], {}
    for name, levels in FEATURES.items():
        blocks[name] = []
        for level in levels[1:]:
            blocks[name].append(len(columns))
            columns.append(frame[name].eq(level).to_numpy(float))
    if include_attachment:
        blocks['attachment'] = [len(columns)]
        columns.append(frame.attachment.eq('not_attached').to_numpy(float))
    return np.column_stack(columns), blocks


def associations(frame):
    keys = list(FEATURES)
    w = equal_month_weights(frame)
    vs = [[weighted_cramers_v(frame[a].to_numpy(), frame[b].to_numpy(), w)
           for b in keys] for a in keys]
    x, blocks = encode(frame)
    xr = residualize(x, w, frame.date.to_numpy())
    gram = xr.T@(w[:, None]*xr)
    scale = np.sqrt(np.diag(gram))
    r = gram/scale[:, None]/scale[None, :]
    sign, ld = np.linalg.slogdet(r)
    gvif = {}
    for name, col in blocks.items():
        other = [j for j in range(x.shape[1]) if j not in col]
        s1, d1 = np.linalg.slogdet(r[np.ix_(col, col)])
        s2, d2 = np.linalg.slogdet(r[np.ix_(other, other)])
        if min(sign, s1, s2) <= 0:
            raise ValueError('Singular block correlation; inspect encoding instead of hiding it')
        gvif[name] = {'df': len(col), 'gvif': float(np.exp(d1+d2-ld)),
                      'adjusted_gvif': float(np.exp((d1+d2-ld)/(2*len(col))))}
    # MCA is correspondence analysis of a complete indicator matrix, not PCA
    # of arbitrary category numbers. It describes X only.
    z = np.column_stack([frame[name].eq(level).to_numpy(float)
                         for name, levels in FEATURES.items() for level in levels])
    wn = w/w.sum(); mass = wn@z
    standardized = (z-mass)*np.sqrt(wn[:, None]/(len(keys)*mass))
    eigen, vec = np.linalg.eigh(standardized.T@standardized)
    order = np.argsort(eigen)[::-1]; eigen = np.maximum(eigen[order], 0); vec = vec[:, order]
    pos = eigen > 1e-10; eigen, vec = eigen[pos], vec[:, pos]
    contrib = {}; start = 0
    for name, levels in FEATURES.items():
        contrib[name] = (vec[start:start+len(levels), :6]**2).sum(0).tolist()
        start += len(levels)
    return {'variables': keys, 'weighted_cramers_v': vs, 'within_month_block_gvif': gvif,
            'mca': {'eigenvalues': eigen.tolist(), 'raw_inertia_fraction': (eigen/eigen.sum()).tolist(),
                    'variable_contribution_first_six_axes': contrib,
                    'interpretation': 'Raw categorical MCA inertia of X, not variance explained in survey answers.'}}


def housing_at_or_before(frame):
    raw, hashes = [], {}
    for relative, start, end in HOUSING_SOURCES:
        path = ROOT/relative
        df = pd.read_excel(path, skiprows=1, usecols=['date', 'userid', 'Q43'])
        df = df.loc[df.date.between(start, end)].copy()
        raw.append(df); hashes[relative] = sha(path)
    r = pd.concat(raw, ignore_index=True).sort_values(['userid', 'date'])
    if r.duplicated(['userid', 'date']).any():
        raise ValueError('Duplicate housing-source row')
    r.Q43 = pd.to_numeric(r.Q43, errors='coerce').where(r.Q43.isin([1, 2, 3]))
    r['housing_source_month'] = r.date.where(r.Q43.notna())
    r[['Q43', 'housing_source_month']] = r.groupby('userid')[['Q43', 'housing_source_month']].ffill()
    f = frame.merge(r[['userid', 'date', 'Q43', 'housing_source_month']], on=['userid', 'date'],
                    how='left', validate='one_to_one')
    known = f.Q43.notna()
    if not (f.loc[known, 'housing_source_month'] <= f.loc[known, 'date']).all():
        raise ValueError('Future housing answer leaked backward')
    f['housing'] = f.Q43.map({1: 'owner', 2: 'renter', 3: 'other'})
    return f, hashes


def load_frame():
    f, hashes = housing_at_or_before(pd.read_parquet(CACHE))
    f = f.loc[f.date.between(201901, 202510)].copy()
    f['education'] = f._EDU_CAT.map({'High School': 'high_school', 'Some College': 'some_college', 'College': 'college'})
    f['income'] = f.income_group.map({'Under 50k': 'under_50k', '50k to 100k': '50k_100k', 'Over 100k': 'over_100k'})
    f['age'] = f.age_group.map({'Under 40': 'under_40', '40 to 60': '40_60', 'Over 60': 'over_60'})
    f['employment_original'] = f.employment
    f['employment'] = f.employment.map({'employed': 'attached', 'on_leave': 'attached',
        'unemployed': 'unemployed', 'retired': 'retired', 'disabled': 'other_not_working',
        'student': 'other_not_working', 'homemaker': 'other_not_working', 'other': 'other_not_working'})
    f['attachment'] = f.employment.map({'attached': 'attached', 'unemployed': 'not_attached',
        'retired': 'not_attached', 'other_not_working': 'not_attached'})
    f['newcomer'] = f.tenure.eq(1)
    f = f.sort_values(['date', 'userid']).reset_index(drop=True)
    if f.duplicated(['userid', 'date']).any():
        raise ValueError('Duplicate respondent-month')
    hashes[str(CACHE.relative_to(ROOT))] = sha(CACHE)
    return f, hashes


def candidates(blocks):
    keys = list(FEATURES)
    rows = []
    for n in [3, 4]:
        for fields in combinations(keys, n):
            rows.append({'name': '+'.join(fields), 'fields': list(fields), 'role': 'candidate',
                         'cartesian_cells': math.prod(len(FEATURES[k]) for k in fields),
                         'columns': [j for k in fields for j in blocks[k]]})
    rows.append({'name': 'all_eight_additive', 'fields': keys, 'role': 'reference',
                 'cartesian_cells': None, 'columns': [j for k in keys for j in blocks[k]]})
    rows.append({'name': 'education_x_attachment_6', 'fields': ['education', 'attachment'],
                 'role': 'benchmark', 'cartesian_cells': 6,
                 'columns': blocks['education']+blocks['attachment']})
    for key in keys:
        fields = [k for k in keys if k != key]
        rows.append({'name': 'without_'+key, 'fields': fields, 'role': 'ablation',
                     'cartesian_cells': None, 'columns': [j for k in fields for j in blocks[k]]})
    return rows


def response_matrix(f):
    return np.column_stack([f.Q9_mean.to_numpy(float), f.Q9_iqr.to_numpy(float),
        f.zero_deflation_pct.to_numpy(float)/100,
        (f.Q9_mean.to_numpy(float)[:, None] <= THRESHOLDS).astype(float)])


def fit_subsets(x, y, w, months, models):
    xr, yr = residualize(x, w, months), residualize(y, w, months)
    sd = np.sqrt(np.sum(w[:, None]*xr*xr, axis=0)/w.sum())
    if np.any(sd < 1e-10):
        raise ValueError('A categorical contrast is absent in training')
    xr = xr/sd
    gram, rhs = xr.T@(w[:, None]*xr), xr.T@(w[:, None]*yr)
    result = []
    for model in models:
        col = model['columns']
        g = gram[np.ix_(col, col)] + np.eye(len(col))*(1e-6*w.sum())
        b = solve(g, rhs[col], assume_a='pos')/sd[col, None]
        result.append(b)
    return result


def domain_losses(y, prediction, w, months):
    """Remove common month level in scoring, never supply it to predictors.

    All compared models receive the same outcome-independent x and masks.
    These scores concern relative within-month response structure only.
    """
    yr = residualize(y, w, months); pr = residualize(prediction, w, months)
    unique, m = np.unique(months, return_inverse=True)
    se = np.column_stack([np.bincount(m, weights=w*(yr[:, j]-pr[:, j])**2) for j in range(y.shape[1])])
    ss = np.column_stack([np.bincount(m, weights=w*yr[:, j]**2) for j in range(y.shape[1])])
    if np.any(ss[:, :3] <= 0):
        raise ValueError('A month has no outcome variation')
    first = se[:, :3]/ss[:, :3]
    delta = np.gradient(THRESHOLDS)
    cdf = (se[:, 3:]@delta)/(ss[:, 3:]@delta)
    return unique, np.column_stack([first, cdf])


def evaluate_models(data, models, *, cv=False, fit_data=None):
    x, _ = encode(data, include_attachment=True); y = response_matrix(data)
    w = equal_month_weights(data); dates = data.date.to_numpy()
    if cv:
        predictions = [np.empty_like(y) for _ in models]
        folds = np.array([int.from_bytes(hashlib.sha256(f'20261023:{int(u)}'.encode()).digest()[:8], 'big') % 4
                          for u in data.userid])
        for fold in range(4):
            train, test = folds != fold, folds == fold
            if set(data.userid[train]) & set(data.userid[test]):
                raise AssertionError('Respondent crossed CV fold')
            print('  person fold', fold, 'train', int(train.sum()), 'test', int(test.sum()), flush=True)
            wt = equal_month_weights(data.loc[train])
            betas = fit_subsets(x[train], y[train], wt, dates[train], models)
            for model, beta, pred in zip(models, betas, predictions):
                pred[test] = x[test][:, model['columns']]@beta
    else:
        if set(data.userid) & set(fit_data.userid):
            raise ValueError('Temporal check contains development respondent')
        xt, _ = encode(fit_data, include_attachment=True)
        betas = fit_subsets(xt, response_matrix(fit_data), equal_month_weights(fit_data), fit_data.date.to_numpy(), models)
        predictions = [x[:, model['columns']]@beta for model, beta in zip(models, betas)]
    results = {}
    for model, prediction in zip(models, predictions):
        months, loss = domain_losses(y, prediction, w, dates)
        results[model['name']] = {'domain_gain': dict(zip(DOMAIN_NAMES, (1-loss.mean(0)).tolist())),
            'composite_gain': float(1-loss.mean()), 'monthly_domain_losses': loss.tolist(),
            'months': [int(m) for m in months]}
    return results


def grid_support(frame, fields, budgets=(192, 256, 384, 512)):
    """Full-frame support, no answer screen; projections are not actual draws."""
    monthly = []
    for month, rows in frame.groupby('date', sort=True):
        valid = np.isfinite(rows.weight) & rows.weight.gt(0)
        r = rows.loc[valid]
        known = np.column_stack([r[k].isin(FEATURES[k]) if k != 'attachment' else r[k].notna() for k in fields]).all(1)
        labels = np.zeros(len(r), dtype=int)
        for field in fields:
            levels = FEATURES[field] if field != 'attachment' else ['attached', 'not_attached']
            code = pd.Categorical(r[field], categories=levels).codes
            labels = labels*len(levels)+np.maximum(code, 0)
        labels = np.where(known, labels+1, 0)
        rw = r.weight.to_numpy(float); entrant = r.newcomer.to_numpy(float)
        nn = np.bincount(labels); ww = np.bincount(labels, weights=rw)
        ww2 = np.bincount(labels, weights=rw*rw)
        en = np.bincount(labels, weights=entrant); ew = np.bincount(labels, weights=rw*entrant)
        counts, mass, neff, newcomer = {}, {}, {}, {}
        for i in np.flatnonzero(nn):
            cell = 'unknown' if i == 0 else str(i)
            counts[cell] = int(nn[i]); mass[cell] = float(ww[i]); neff[cell] = float(ww[i]**2/ww2[i])
            newcomer[cell] = {'n': int(en[i]), 'weight': float(ew[i])}
        total = sum(mass.values())
        supported = sum(mass[k] for k in counts if k != 'unknown' and counts[k] >= 20 and neff[k] >= 10)/total
        new_mass = sum(v['weight'] for v in newcomer.values())
        new_supported = sum(v['weight'] for k, v in newcomer.items() if k != 'unknown' and v['n'] >= 10)/new_mass if new_mass else None
        projections = {}
        for budget in budgets:
            try:
                alloc = allocate_core(counts, mass, min(budget, len(r)), minimum=3)
                good = sum(mass[k] for k in counts if k != 'unknown' and alloc[k]*neff[k]/counts[k] >= 10)/total
                projections[str(budget)] = {'feasible_floor_3': True, 'projected_mass_ess_ge_10': good}
            except ValueError:
                projections[str(budget)] = {'feasible_floor_3': False, 'projected_mass_ess_ge_10': None}
        monthly.append({'month': int(month), 'nonempty_cells': len(counts),
            'unknown_weight_fraction': mass.get('unknown', 0)/total,
            'frame_supported_mass': supported, 'newcomer_mass_in_cells_n_ge_10': new_supported,
            'core_projection': projections})
    def summary(rows):
        return {'months': len(rows), 'mean_frame_supported_mass': float(np.mean([r['frame_supported_mass'] for r in rows])),
                'minimum_frame_supported_mass': float(min(r['frame_supported_mass'] for r in rows)),
                'mean_newcomer_mass_in_cells_n_ge_10': float(np.mean([r['newcomer_mass_in_cells_n_ge_10'] for r in rows if r['newcomer_mass_in_cells_n_ge_10'] is not None])),
                'max_nonempty_cells': max(r['nonempty_cells'] for r in rows),
                'core_projection': {str(b): {'feasible_months': sum(r['core_projection'][str(b)]['feasible_floor_3'] for r in rows),
                    'mean_projected_mass_ess_ge_10': float(np.mean([r['core_projection'][str(b)]['projected_mass_ess_ge_10'] or 0 for r in rows]))} for b in budgets}}
    return {'development': summary([r for r in monthly if r['month'] <= 202212]),
            'all_months': summary(monthly), 'monthly': monthly}


def bootstrap_indices(n, *, seed=20261023, draws=300, block_size=6):
    rng = np.random.default_rng(seed)
    blocks = [np.arange(i, min(n, i+block_size)) for i in range(0, n, block_size)]
    return [np.concatenate([blocks[i] for i in rng.integers(len(blocks), size=len(blocks))])[:n]
            for _ in range(draws)]


def select_development(models, cv, support):
    valid = [m for m in models if m['role'] == 'candidate' and
             support[m['name']]['development']['mean_frame_supported_mass'] >= .9]
    if not valid:
        return {'recommended': None, 'reason': 'No candidate passes the predeclared frame-support screen'}
    best = max(valid, key=lambda m: cv[m['name']]['composite_gain'])
    losses = np.asarray(cv[best['name']]['monthly_domain_losses']).mean(1)
    indices = bootstrap_indices(len(losses))
    se = float(np.std([losses[i].mean() for i in indices], ddof=1))
    cutoff = cv[best['name']]['composite_gain']-se
    one_se = [m for m in valid if cv[m['name']]['composite_gain'] >= cutoff]
    winner = min(one_se, key=lambda m: (m['cartesian_cells'], len(m['fields']), -cv[m['name']]['composite_gain'], m['name']))
    ranked = sorted(valid, key=lambda m: -cv[m['name']]['composite_gain'])
    return {'recommended': winner['name'], 'best_predictive': best['name'], 'best_bootstrap_se': se,
            'one_se_cutoff': cutoff, 'one_se_candidates': [m['name'] for m in one_se],
            'ranked_top_ten': [m['name'] for m in ranked[:10]],
            'screen_passed': len(valid), 'screen_total': sum(m['role'] == 'candidate' for m in models),
            'rule': 'Development only. Among frame-supported three/four-dimensional candidates within one block-bootstrap SE of best, choose the fewest Cartesian cells.'}


def run(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('A fresh ignored outputs directory is required')
    out.mkdir(parents=True)
    protocol = json.loads(PROTOCOL.read_text())
    dump(out/'protocol.json', protocol)
    print('Loading existing frame and own-at-or-before housing', flush=True)
    frame, sources = load_frame()
    missing = {k: {'n_missing': int((~frame[k].isin(levels)).sum())} for k, levels in FEATURES.items()}
    known = np.column_stack([frame[k].isin(levels) for k, levels in FEATURES.items()]).all(1)
    bins = frame[[f'Q9_bin{i}' for i in range(1, 11)]].to_numpy(float)
    legal = np.isfinite(bins).all(1) & (bins >= 0).all(1) & (bins <= 100).all(1) & (np.abs(bins.sum(1)-100) <= 1e-6)
    mask = known & np.isfinite(frame.weight) & frame.weight.gt(0) & legal & np.isfinite(frame.Q9_mean) & np.isfinite(frame.Q9_iqr) & frame.Q9_iqr.ge(0) & np.isfinite(frame.zero_deflation_pct)
    data = frame.loc[mask].copy()
    data.to_parquet(out/'analysis_frame_private.parquet', index=False)
    train = data.loc[data.date.le(202212)].copy()
    x, blocks = encode(train, include_attachment=True); models = candidates(blocks)
    print('Development common support', len(train), 'persons', train.userid.nunique(), flush=True)
    assoc = {'development': associations(train)}
    dev = evaluate_models(train, models, cv=True)
    print('Auditing full-frame cell support; answers are not used', flush=True)
    supports = {m['name']: grid_support(frame, m['fields']) for m in models if m['role'] == 'candidate'}
    old_support = grid_support(frame, ['education', 'attachment'])
    selection = select_development(models, dev, supports)
    dump(out/'development_selection_frozen_before_temporal.json', selection)
    print('Frozen development recommendation', selection['recommended'], flush=True)
    checks, exclusions = {}, {}
    for name, (start, end) in protocol['temporal_checks'].items():
        original = data.loc[data.date.between(start, end)]
        sub = original.loc[~original.userid.isin(train.userid)].copy()
        exclusions[name] = {'rows_before_identity_exclusion': len(original), 'rows_after': len(sub),
                            'excluded_rows': len(original)-len(sub), 'persons': int(sub.userid.nunique()),
                            'months': int(sub.date.nunique())}
        print('Temporal check', name, exclusions[name], flush=True)
        checks[name] = evaluate_models(sub, models, fit_data=train)
        assoc[name] = associations(sub)
    full = dev['all_eight_additive']
    indices = bootstrap_indices(len(full['months']))
    loco = {}
    for k in FEATURES:
        delta = np.asarray(dev['without_'+k]['monthly_domain_losses'])-np.asarray(full['monthly_domain_losses'])
        boots = np.array([delta[i].mean(0) for i in indices])
        loco[k] = {'development_domain_loss_increase': dict(zip(DOMAIN_NAMES, delta.mean(0).tolist())),
                   'ci95_block_bootstrap': dict(zip(DOMAIN_NAMES, np.quantile(boots, [.025, .975], axis=0).T.tolist())),
                   'temporal_domain_loss_increase': {n: {d: checks[n]['all_eight_additive']['domain_gain'][d]-checks[n]['without_'+k]['domain_gain'][d] for d in DOMAIN_NAMES} for n in checks}}
    rows = []
    for m in models:
        row = {k: v for k, v in m.items() if k != 'columns'}
        row['development_cv'] = dev[m['name']]
        row['temporal_checks'] = {k: v[m['name']] for k, v in checks.items()}
        if m['role'] == 'candidate':
            row['support'] = supports[m['name']]
        rows.append(row)
    result = {'status': 'development_grid_recommendation_not_frozen_simulation_design',
        'completed_at_utc': datetime.now(timezone.utc).isoformat(),
        'new_api_calls': 0, 'q9_refits': 0, 'protocol': protocol,
        'source_sha256': {**sources, str(PROTOCOL.relative_to(ROOT)): sha(PROTOCOL), str(Path(__file__).relative_to(ROOT)): sha(__file__)},
        'coverage': {'all_frame_person_months': len(frame), 'all_frame_persons': int(frame.userid.nunique()),
            'model_common_person_months': len(data), 'model_common_persons': int(data.userid.nunique()),
            'missing_by_feature': missing, 'development_rows': len(train), 'temporal_exclusions': exclusions},
        'associations': assoc, 'conditional_information': loco, 'selection': selection,
        'candidates': rows, 'old_six_grid_support': old_support,
        'score_interpretation': '1 - normalized residual loss within month; 0=no demographic improvement. Not absolute level forecasting, national MAE, causal effects or LLM gains.',
        'next_required': ['Shortlisted joint-cell nonlinear held-out check', 'Independent newcomer support and pooling',
                          'Core/Normal joint-answer model and new sampling-weight contract', 'User review before adopting a grid or final Core count']}
    dump(out/'summary.json', result)
    print('Saved', out/'summary.json', flush=True)
    return result
