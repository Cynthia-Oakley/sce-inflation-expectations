"""Past-only prediction of observed answer stability, not causal inattention.

Uses existing public-microdata cache, followed by frozen trajectory evaluation.
No network, new Q9 fits, current-answer features, or default runtime changes.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import expit

from .response_gap import MONTHS, prepare_pairs
from .history_forward import metric_cells

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT/'outputs/sce_population_associations_20261015_v1'
TRAJECTORY = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1'
YEARS = tuple(range(2020, 2026))
RIDGE = .01
NUMERIC = ('prior_center', 'prior_iqr', 'prior_change', 'prior_abs_change',
           'prior_active_bins', 'prior_grid5', 'prior_zero_deflation',
           'history_count', 'history_mean', 'history_sd', 'transition_count',
           'past_stable_rate', 'past_exact_rate')
P_COLUMNS = ('age_group', 'numeracy', '_EDU_CAT', 'income_group', 'region', 'employment')
STATE_COLUMNS = ('financial_change', 'financial_risk', 'general_risk', 'financial_role')
METHODS = ('population_rate', 'personal_rate', 'history', 'history_P', 'history_P_state')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def signed_log(x):
    return np.sign(x)*np.log1p(np.abs(x))


def build_features(frame):
    """Every feature at month t is a function of this person's records before t."""
    d = frame.sort_values(['userid', 'date'], kind='stable').reset_index(drop=True).copy()
    if d.duplicated(['userid', 'date']).any():
        raise ValueError('Duplicate person-month')
    g = d.groupby('userid', sort=False)
    prior = g['Q9_mean'].shift(1)
    prior_iqr = g['Q9_iqr'].shift(1)
    previous_mi = g['mi'].shift(1)
    adjacent = (d['mi']-previous_mi == 1) & d['panel_status'].eq('adjacent_returner')
    eligible = adjacent & np.isfinite(d['Q9_mean']) & np.isfinite(prior)
    delta = d['Q9_mean']-prior
    label = pd.Series(np.where(eligible, (delta.abs() <= .5).astype(float), np.nan))
    bins = d[[f'Q9_bin{i}' for i in range(1, 11)]].to_numpy(float)
    valid_bins = np.isfinite(bins).all(1) & (bins >= 0).all(1) & (bins <= 100).all(1) & (np.abs(bins.sum(1)-100) <= 1e-6)
    previous_bins = g[[f'Q9_bin{i}' for i in range(1, 11)]].shift(1).to_numpy(float)
    previous_valid_bins = np.isfinite(previous_bins).all(1) & (previous_bins >= 0).all(1) & (previous_bins <= 100).all(1) & (np.abs(previous_bins.sum(1)-100) <= 1e-6)
    exact = pd.Series(np.where(adjacent & valid_bins & previous_valid_bins,
                              np.isclose(bins, previous_bins, atol=1e-8, rtol=0).all(1).astype(float), np.nan))
    ids = d['userid']

    def history_sum(series):
        values = series.fillna(0.)
        return values.groupby(ids, sort=False).cumsum()-values

    def lag(series):
        return series.groupby(ids, sort=False).shift(1)

    center = d['Q9_mean'].where(np.isfinite(d['Q9_mean']))
    n = history_sum(center.notna().astype(float))
    hmean = history_sum(center)/n.replace(0, np.nan)
    hvar = (history_sum(center*center)/n.replace(0, np.nan)-hmean*hmean).clip(lower=0)
    transitions = history_sum(label.notna().astype(float))
    exact_count = history_sum(exact.notna().astype(float))
    previous_change = lag(delta.where(eligible))
    features = pd.DataFrame({
        'userid': ids, 'month': d['date'], 'year': d['date']//100,
        'weight': d['weight'], 'eligible_label': eligible,
        'label_stable': label, 'label_exact': exact,
        'prior_center': signed_log(prior), 'prior_iqr': np.log1p(prior_iqr.clip(lower=0)),
        'prior_change': signed_log(previous_change),
        'prior_abs_change': np.log1p(previous_change.abs()),
        'prior_active_bins': np.where(previous_valid_bins, (previous_bins > 0).sum(1), np.nan),
        'prior_grid5': np.where(previous_valid_bins, np.isclose(previous_bins/5, np.round(previous_bins/5), atol=1e-8).all(1).astype(float), np.nan),
        'prior_zero_deflation': np.where(previous_valid_bins, (previous_bins[:, 5:].sum(1) == 0).astype(float), np.nan),
        'history_count': np.log1p(n), 'history_mean': signed_log(hmean),
        'history_sd': np.log1p(np.sqrt(hvar)), 'transition_count': np.log1p(transitions),
        'past_stable_rate': history_sum(label)/transitions.replace(0, np.nan),
        'past_exact_rate': history_sum(exact)/exact_count.replace(0, np.nan),
        'past_stable_count': history_sum(label), 'past_transition_n': transitions,
        'official_current_center': d['Q9_mean'], 'official_prior_center': prior,
    })
    for column in P_COLUMNS+STATE_COLUMNS:
        features['past_'+column] = g[column].shift(1)
    return features


def month_weights(rows):
    weights = rows['weight'].to_numpy(float)
    sums = rows.groupby('month')['weight'].transform('sum').to_numpy(float)
    if not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError('Positive finite survey weights required')
    return weights/sums/rows['month'].nunique()


def category(series):
    return series.astype('string').fillna('__MISSING__').astype(str)


class Encoder:
    def __init__(self, train, weights, categories):
        self.categories = tuple('past_'+c for c in categories)
        values = train[list(NUMERIC)].to_numpy(float)
        self.mean = np.array([np.average(values[np.isfinite(values[:, j]), j],
                                        weights=weights[np.isfinite(values[:, j])])
                              if np.isfinite(values[:, j]).any() else 0. for j in range(values.shape[1])])
        filled = np.where(np.isfinite(values), values, self.mean)
        self.scale = np.sqrt(np.average((filled-self.mean)**2, weights=weights, axis=0))
        self.scale[self.scale < 1e-8] = 1.
        self.levels = {c: sorted(set(category(train[c]))) for c in self.categories}
        self.names = ['intercept']+list(NUMERIC)+[c+'_missing' for c in NUMERIC]
        self.names += [c+'='+level for c in self.categories for level in self.levels[c]]

    def transform(self, rows):
        values = rows[list(NUMERIC)].to_numpy(float)
        missing = ~np.isfinite(values)
        columns = [np.ones((len(rows), 1)), (np.where(missing, self.mean, values)-self.mean)/self.scale,
                   missing.astype(float)]
        for c in self.categories:
            v = category(rows[c]).to_numpy()
            columns.append(np.column_stack([v == level for level in self.levels[c]]).astype(float))
        return np.concatenate(columns, axis=1)


def fit_logistic(x, y, weights, ridge=RIDGE):
    """Weighted mean Bernoulli loss with fixed L2; intercept not penalized."""
    weights = np.asarray(weights, float); weights /= weights.sum()
    rate = np.clip(np.dot(weights, y), 1e-6, 1-1e-6)
    initial = np.zeros(x.shape[1]); initial[0] = np.log(rate/(1-rate))
    penalty = np.ones(x.shape[1]); penalty[0] = 0.

    def objective(b):
        z = x@b
        loss = np.dot(weights, np.logaddexp(0, z)-y*z)+.5*ridge*np.dot(penalty*b, b)
        gradient = x.T@(weights*(expit(z)-y))+ridge*penalty*b
        return float(loss), gradient

    result = minimize(objective, initial, jac=True, method='L-BFGS-B',
                      options={'maxiter': 300, 'gtol': 1e-7, 'ftol': 1e-12})
    if not result.success:
        raise RuntimeError('Logistic solver did not converge: '+str(result.message))
    return result.x, {'converged': True, 'iterations': int(result.nit), 'penalized_loss': float(result.fun)}


def auc(y, p, weights):
    order = np.argsort(p, kind='stable'); y, p, w = y[order], p[order], weights[order]
    starts = np.r_[0, np.flatnonzero(np.diff(p))+1]
    positive = np.add.reduceat(w*y, starts); negative = np.add.reduceat(w*(1-y), starts)
    denominator = positive.sum()*negative.sum()
    return float(np.dot(positive, np.cumsum(negative)-.5*negative)/denominator) if denominator > 0 else None


def probability_metrics(rows, p, y_column='label_stable'):
    valid = np.isfinite(rows[y_column].to_numpy(float))
    d = rows.loc[valid].reset_index(drop=True); p = np.asarray(p)[valid]
    w = month_weights(d); y = d[y_column].to_numpy(float); p = np.clip(p, 1e-8, 1-1e-8)
    calibration = []
    bin_index = np.minimum((p*10).astype(int), 9)
    for index in range(10):
        lo = index/10
        keep = bin_index == index
        if keep.sum() >= 10:
            calibration.append({'probability_bin': [round(float(lo), 1), round(float(lo+.1), 1)],
                                'n': int(keep.sum()), 'predicted': float(np.average(p[keep], weights=w[keep])),
                                'observed': float(np.average(y[keep], weights=w[keep]))})
    return {'n_person_months': len(d), 'n_months': int(d['month'].nunique()),
            'observed_rate': float(np.dot(w, y)), 'predicted_rate': float(np.dot(w, p)),
            'brier': float(np.dot(w, (p-y)**2)),
            'log_loss': float(-np.dot(w, y*np.log(p)+(1-y)*np.log1p(-p))),
            'weighted_auc': auc(y, p, w), 'calibration': calibration}


def run(out):
    begin = perf_counter(); out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Use a new ignored output directory')
    receipt = json.loads((CACHE/'summary.json').read_text())
    datafile = CACHE/'analysis_frame_private.parquet'
    if sha(datafile) != receipt['analysis_frame_sha256']:
        raise ValueError('Cached population frame changed')
    source = pd.read_parquet(datafile)
    frame = build_features(source); prepared = perf_counter()
    tested, folds = [], []
    for year in YEARS:
        train = frame.loc[(frame['year'] < year) & frame['eligible_label'] & np.isfinite(frame['weight']) & (frame['weight'] > 0)].copy()
        test = frame.loc[frame['year'] == year].copy()
        assert train['month'].max() < test['month'].min()
        w = month_weights(train); y = train['label_stable'].to_numpy(float)
        rate = float(np.dot(w, y))
        prediction = test[['userid', 'month', 'weight', 'eligible_label', 'label_stable', 'label_exact',
                           'official_current_center', 'official_prior_center']].copy()
        prediction['population_rate'] = rate
        prediction['personal_rate'] = ((test['past_stable_count']+5*rate)/(test['past_transition_n']+5)).to_numpy()
        fits = {}
        for method, categories in [('history', ()), ('history_P', P_COLUMNS), ('history_P_state', P_COLUMNS+STATE_COLUMNS)]:
            encoder = Encoder(train, w, categories)
            coefficient, fit = fit_logistic(encoder.transform(train), y, w)
            prediction[method] = expit(encoder.transform(test)@coefficient)
            fits[method] = {**fit, 'n_features': len(coefficient),
                            'coefficients_standardized_not_causal': dict(zip(encoder.names, map(float, coefficient)))}
        eligible = prediction.loc[prediction['eligible_label'] & np.isfinite(prediction['weight']) & (prediction['weight'] > 0)].copy()
        folds.append({'year': year, 'train_months': sorted(map(int, train['month'].unique())),
                      'n_train': len(train), 'n_test': len(eligible), 'train_stable_rate': rate,
                      'methods': {m: probability_metrics(eligible, eligible[m]) for m in METHODS}, 'fit': fits})
        tested.append(prediction)
        print(json.dumps({'year': year, 'train': len(train), 'test': len(eligible),
                          'brier': {m: round(folds[-1]['methods'][m]['brier'], 4) for m in METHODS}}), flush=True)
    predictions = pd.concat(tested, ignore_index=True)
    common = predictions.loc[predictions['eligible_label'] & np.isfinite(predictions['weight']) & (predictions['weight'] > 0)].copy()
    probabilities = {m: probability_metrics(common, common[m]) for m in METHODS}
    fitted = perf_counter()
    lookup = predictions.set_index(['month', 'userid'])
    casesfile = TRAJECTORY/'cases_private.json'
    trajectory_receipt = json.loads((ROOT/'docs/workstreams/20261017_reference_scaleup/regression_diagnostic_20261017.json').read_text())
    if sha(casesfile) != trajectory_receipt['source_cases_sha256']:
        raise ValueError('Frozen trajectory changed')
    pairs = [r for r in prepare_pairs(json.loads(casesfile.read_text()), months=MONTHS, n_per_month=192) if r['paired_eligible']]
    assert len(pairs) == 2284
    rows, p_rows, label_disagreement = [], [], []
    for r in pairs:
        item = lookup.loc[(r['month'], r['userid'])]
        if isinstance(item, pd.DataFrame):
            raise ValueError('Duplicate prediction key')
        if np.isfinite(item['label_stable']):
            label_disagreement.append(bool(item['label_stable']) != bool(abs(r['truth_delta_pp']) <= .5))
        p_rows.append({'month': r['month'], 'weight': r['design_survey_weight'],
                       'label_stable': float(abs(r['truth_delta_pp']) <= .5),
                       **{m: float(item[m]) for m in METHODS}})
        for repeat in (1, 2):
            rows.append({'month': r['month'], 'repeat': repeat, 'weight': r['design_survey_weight'],
                         'truth': r['truth_mean_pp'], 'prior': r['prior_mean_pp'],
                         'sim': r['model_repeats'][str(repeat)]['mean'],
                         **{m: float(item[m]) for m in METHODS}})
    diagnostic = {}
    for method in ('carry', 'pure_sim')+METHODS:
        if method == 'carry': values = [r['prior'] for r in rows]
        elif method == 'pure_sim': values = [r['sim'] for r in rows]
        else: values = [r['prior']+(1-r[method])*(r['sim']-r['prior']) for r in rows]
        diagnostic[method] = metric_cells(rows, values)
    selected = pd.DataFrame(p_rows)
    selected_probabilities = {m: probability_metrics(selected, selected[m]) for m in METHODS}
    end = perf_counter()
    result = {'status': 'completed_posthoc_past_only_retention_prediction', 'new_api_calls': 0,
              'refitted_q9_vectors': 0, 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'n_source_rows': len(source), 'n_forward_test_person_months': len(common),
              'n_simulation_person_months': len(pairs), 'ridge': RIDGE,
              'target': 'Observed |official Q9 derived mean(t)-mean(t-1)|<=0.5pp; not causal inattention.',
              'folds': folds, 'all_forward_probability_scores': probabilities,
              'frozen_simulation_support_probability_scores': selected_probabilities,
              'official_and_frozen_label_disagreement': {'n_comparable': len(label_disagreement), 'n_disagree': sum(label_disagreement)},
              'scalar_diagnostic': diagnostic,
              'limits': ['All 12 simulation periods previously inspected; no independent model validation.',
                         'Annual training uses years strictly earlier than test. Historical microdata release lag still prevents strict B claims.',
                         'Feature lagging is within-person; short histories retain missing flags, not deleted.',
                         'Stability is observed survey behavior, potentially rounding or reporting, not identified attention.',
                         'Scalar prior+(1-p_stable)*(sim-prior) is a diagnostic hybrid, not generated or refitted Q9 answers.',
                         'Training predicts stability, not center MAE. No hyperparameter selected on the 12 simulation months.',
                         'The LLM proposal already saw prior information; 1-p is not a Bayesian likelihood weight.'],
              'source_sha256': {str(datafile.relative_to(ROOT)): sha(datafile), str(casesfile.relative_to(ROOT)): sha(casesfile)},
              'implementation_sha256': sha(__file__),
              'timing_seconds': {'load_and_features': prepared-begin, 'fit_and_probability_evaluation': fitted-prepared,
                                 'frozen_scalar_evaluation': end-fitted, 'total_before_writing': end-begin}}
    out.mkdir(parents=True)
    predictions.to_parquet(out/'predictions_private.parquet', index=False)
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    return result
