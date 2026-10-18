"""Time-ordered prediction of reported Q9 changes, using strict personal lags.

These are statistical benchmarks and scalar diagnostics, not new LLM answers.
No API, no density fits, and no change to the pending frozen-context trial.
"""
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
import json
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import softmax, logsumexp

from .retention_predictability import (ROOT, CACHE, TRAJECTORY, YEARS, RIDGE,
    P_COLUMNS, STATE_COLUMNS, build_features, month_weights, category, sha)
from .response_gap import MONTHS, prepare_pairs
from .history_forward import metric_cells

NUMERIC = ('prior_pp', 'older_gap_pp', 'last_change_pp', 'prior_width_pp',
           'history_sd_pp', 'history_n', 'past_stable_rate', 'past_exact_rate')


def prepare_features(source):
    f = build_features(source)
    inverse = lambda x: np.sign(x)*np.expm1(np.abs(x))
    n = np.rint(np.expm1(f['history_count']))
    previous = f['official_prior_center']
    mean = inverse(f['history_mean'])
    older = (mean*n-previous)/(n-1).replace(0, np.nan)
    f['prior_pp'] = previous
    f['older_gap_pp'] = (older-previous).where(n > 1)
    f['last_change_pp'] = inverse(f['prior_change'])
    f['prior_width_pp'] = np.expm1(f['prior_iqr'])
    f['history_sd_pp'] = np.expm1(f['history_sd'])
    f['history_n'] = n
    f['delta_pp'] = f['official_current_center']-previous
    f['direction'] = classify(f['delta_pp'].to_numpy())
    return f


def classify(delta):
    """0 down, 1 stable (including both boundaries), 2 up; NaN stays NaN."""
    x = np.asarray(delta, float)
    return np.where(np.isfinite(x), np.where(x < -.5, 0, np.where(x > .5, 2, 1)), np.nan)


class Design:
    def __init__(self, train, w, categories=()):
        a = train[list(NUMERIC)].to_numpy(float)
        self.mean = np.array([np.average(a[np.isfinite(a[:, j]), j], weights=w[np.isfinite(a[:, j])])
                              if np.isfinite(a[:, j]).any() else 0. for j in range(a.shape[1])])
        filled = np.where(np.isfinite(a), a, self.mean)
        self.scale = np.sqrt(np.average((filled-self.mean)**2, weights=w, axis=0))
        self.scale[self.scale < 1e-8] = 1.
        self.levels = {'past_'+c: sorted(set(category(train['past_'+c]))) for c in categories}
        self.names = ['intercept']+list(NUMERIC)+[c+'_missing' for c in NUMERIC]
        self.names += [c+'='+v for c, levels in self.levels.items() for v in levels]

    def transform(self, rows):
        a = rows[list(NUMERIC)].to_numpy(float); missing = ~np.isfinite(a)
        columns = [np.ones((len(rows), 1)), (np.where(missing, self.mean, a)-self.mean)/self.scale, missing.astype(float)]
        for c, levels in self.levels.items():
            v = category(rows[c]).to_numpy()
            columns.append(np.column_stack([v == level for level in levels]).astype(float))
        return np.concatenate(columns, axis=1)


def fit_change(x, y, weights, huber=False):
    w = np.asarray(weights, float); w = w/w.sum()
    penalty = np.ones(x.shape[1]); penalty[0] = 0.
    gram = x.T@(w[:, None]*x)+RIDGE*np.diag(penalty)
    initial = np.linalg.solve(gram, x.T@(w*y))
    if not huber: return initial
    def objective(b):
        e = x@b-y; absolute = np.abs(e)
        loss = np.where(absolute <= 1., .5*e*e, absolute-.5)
        return float(w@loss+.5*RIDGE*np.dot(penalty*b, b)), x.T@(w*np.clip(e, -1., 1.))+RIDGE*penalty*b
    result = minimize(objective, initial, jac=True, method='L-BFGS-B',
                      options={'maxiter': 400, 'ftol': 1e-12, 'gtol': 1e-7})
    if not result.success: raise RuntimeError('Huber convergence failed: '+str(result.message))
    return result.x


def fit_direction(x, y, weights):
    w = np.asarray(weights, float); w = w/w.sum(); y = np.asarray(y, int)
    proportions = np.bincount(y, weights=w, minlength=3)
    initial = np.zeros((x.shape[1], 2)); initial[0] = np.log(np.maximum(proportions[[0, 2]], 1e-8)/max(proportions[1], 1e-8))
    target = np.column_stack((y == 0, y == 2)); penalty = np.ones((x.shape[1], 1)); penalty[0] = 0.
    def objective(flat):
        b = flat.reshape(x.shape[1], 2); z = np.zeros((len(x), 3)); z[:, [0, 2]] = x@b
        p = softmax(z, axis=1)
        loss = w@(logsumexp(z, axis=1)-z[np.arange(len(y)), y])+.5*RIDGE*np.sum(penalty*b*b)
        gradient = x.T@(w[:, None]*(p[:, [0, 2]]-target))+RIDGE*penalty*b
        return float(loss), gradient.ravel()
    result = minimize(objective, initial.ravel(), jac=True, method='L-BFGS-B',
                      options={'maxiter': 400, 'ftol': 1e-12, 'gtol': 1e-7})
    if not result.success: raise RuntimeError('Direction convergence failed: '+str(result.message))
    return result.x.reshape(x.shape[1], 2)


def direction_probabilities(x, b):
    z = np.zeros((len(x), 3)); z[:, [0, 2]] = x@b
    return softmax(z, axis=1)


def direction_metrics(rows, probabilities):
    y = rows['direction'].to_numpy(int); w = month_weights(rows); p = np.asarray(probabilities)
    predicted = p.argmax(1); confusion = np.zeros((3, 3))
    np.add.at(confusion, (y, predicted), w)
    recall = np.divide(np.diag(confusion), confusion.sum(1), out=np.zeros(3), where=confusion.sum(1)>0)
    return {'n': len(y), 'months': int(rows.month.nunique()),
            'brier_three_classes': float(w@np.sum((p-np.eye(3)[y])**2, axis=1)),
            'log_loss': float(-w@np.log(np.maximum(p[np.arange(len(y)), y], 1e-12))),
            'accuracy': float(w@(predicted == y)), 'recall_down_stable_up': recall.tolist(),
            'confusion_joint_weight_down_stable_up': confusion.tolist()}


def run(out):
    begin = perf_counter(); out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'): raise ValueError('Fresh ignored directory required')
    datafile = CACHE/'analysis_frame_private.parquet'
    if sha(datafile) != json.loads((CACHE/'summary.json').read_text())['analysis_frame_sha256']:
        raise ValueError('Validated cached data changed')
    frame = prepare_features(pd.read_parquet(datafile)); tested = []; folds = []
    for year in YEARS:
        train = frame.loc[(frame.year < year) & frame.eligible_label & np.isfinite(frame.weight) & (frame.weight > 0)].copy()
        test = frame.loc[frame.year == year].copy(); w = month_weights(train)
        assert train.month.max() < test.month.min()
        prediction = test[['userid', 'month', 'year', 'weight', 'eligible_label', 'direction', 'delta_pp',
                           'older_gap_pp', 'official_current_center', 'official_prior_center']].copy()
        population = np.bincount(train.direction.astype(int), weights=w, minlength=3)
        for i in range(3): prediction[f'population_p{i}'] = population[i]
        fits = {}
        for block, categories in [('history', ()), ('history_P_state', P_COLUMNS+STATE_COLUMNS)]:
            encoder = Design(train, w, categories); x, xt = encoder.transform(train), encoder.transform(test)
            coefficient = fit_direction(x, train.direction.to_numpy(int), w)
            probability = direction_probabilities(xt, coefficient)
            for i in range(3): prediction[f'{block}_p{i}'] = probability[:, i]
            for loss in (('mse', 'huber') if block == 'history' else ('huber',)):
                b = fit_change(x, train.delta_pp.to_numpy(float), w, loss == 'huber')
                prediction[block+'_'+loss] = xt@b
                fits[block+'_'+loss] = dict(zip(encoder.names, map(float, b)))
        eligible = prediction.loc[prediction.eligible_label & np.isfinite(prediction.weight) & (prediction.weight > 0)].copy()
        scores = {method: direction_metrics(eligible, eligible[[method+f'_p{i}' for i in range(3)]])
                  for method in ('population', 'history', 'history_P_state')}
        folds.append({'year': year, 'train_months': sorted(map(int, train.month.unique())), 'train_n': len(train),
                      'test_n': len(eligible), 'direction_scores': scores, 'change_coefficients_standardized_not_causal': fits})
        tested.append(prediction)
        print(json.dumps({'year': year, 'test_n': len(eligible), 'direction_accuracy': {k:round(v['accuracy'], 4) for k,v in scores.items()}}), flush=True)
    predictions = pd.concat(tested, ignore_index=True)
    common = predictions.loc[predictions.eligible_label & np.isfinite(predictions.weight) & (predictions.weight > 0)].copy()
    direction_scores = {method: direction_metrics(common, common[[method+f'_p{i}' for i in range(3)]])
                        for method in ('population', 'history', 'history_P_state')}
    bins = np.digitize(common.older_gap_pp.to_numpy(), [-2., -.5, .5, 2.], right=True)
    grouped = []
    for label, mask in [(str(i), (bins == i)&np.isfinite(common.older_gap_pp)) for i in range(5)]:
        d = common.loc[mask]; weights = month_weights(d); y = d.direction.to_numpy(int)
        grouped.append({'older_gap_bin': label, 'n': len(d), 'observed_rates_down_stable_up': np.bincount(y, weights=weights, minlength=3).tolist(),
                        'average_delta_pp': float(weights@d.delta_pp.to_numpy())})
    casesfile = TRAJECTORY/'cases_private.json'
    receipt = json.loads((ROOT/'docs/workstreams/20261017_reference_scaleup/regression_diagnostic_20261017.json').read_text())
    if sha(casesfile) != receipt['source_cases_sha256']: raise ValueError('Frozen trajectories changed')
    pairs = [r for r in prepare_pairs(json.loads(casesfile.read_text()), months=MONTHS, n_per_month=192) if r['paired_eligible']]
    assert len(pairs) == 2284
    lookup = predictions.set_index(['month', 'userid']); rows = []
    for r in pairs:
        item = lookup.loc[(r['month'], r['userid'])]
        if isinstance(item, pd.DataFrame): raise ValueError('Duplicate person-month')
        for repeat in (1, 2):
            rows.append({'month': r['month'], 'repeat': repeat, 'weight': r['design_survey_weight'],
                         'truth': r['truth_mean_pp'], 'prior': r['prior_mean_pp'], 'sim': r['model_repeats'][str(repeat)]['mean'],
                         **{method: float(item[method]) for method in ('history_mse', 'history_huber', 'history_P_state_huber')}})
    scalar = {}
    for method in ('carry', 'pure_sim', 'history_mse', 'history_huber', 'history_P_state_huber'):
        values = [r['prior'] if method == 'carry' else r['sim'] if method == 'pure_sim' else r['prior']+r[method] for r in rows]
        scalar[method] = metric_cells(rows, values)
    elapsed = perf_counter()-begin
    result = {'status':'completed_past_only_direction_and_size_diagnostic', 'completed_at_utc':datetime.now(timezone.utc).isoformat(),
        'new_api_calls':0, 'refitted_q9_vectors':0, 'n_forward_person_months':len(common), 'n_forward_months':int(common.month.nunique()),
        'n_frozen_person_months':len(pairs), 'ridge':RIDGE, 'huber_transition_pp':1., 'folds':folds,
        'direction_metrics':direction_scores, 'older_gap_bins':grouped, 'frozen_scalar_diagnostic':scalar,
        'limits':['Past-only annual forecasting with official-derived training labels; current-year earlier real answers allowed: A, not autonomous B.',
                  '12 inspected simulation months use frozen means and design weights; scalar statistical predictions are not new LLM Q9 answers.',
                  'No current macro or news features; failure here does not establish those signals as causal or sufficient.',
                  'Conditional mean/Huber-center predictors do not reconstruct the full response distribution.',
                  'Older gap and subsequent change share the prior; measurement error and regression to mean compete with behavioral explanations.',
                  'All model choices fixed before this run; no threshold or coefficient selection on the 12 months.'],
        'source_sha256':{str(datafile.relative_to(ROOT)):sha(datafile), str(casesfile.relative_to(ROOT)):sha(casesfile)},
        'implementation_sha256':sha(__file__), 'total_seconds_before_writing':elapsed}
    out.mkdir(parents=True); predictions.to_parquet(out/'predictions_private.parquet', index=False)
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return result
