"""Held-out external-survey probability checks; no current SCE answers or API."""
from collections import Counter
from io import BytesIO
import hashlib
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import logsumexp, softmax

ROOT = Path(__file__).resolve().parents[3]
ARCHIVE = ROOT/'data/raw/behavior_references/2026-10-18_subjective_models_v1/SubMod_Replication_220111.zip'
PARENT = ROOT/'outputs/sce_reference_validation_trial_20261017_v2'
MONTHS = (202009, 202109, 202206, 202312, 202410, 202503)
FEATURES = ['age_group', 'education_group', 'household_income_band', 'region']
SEEDS = (42, 43, 44)
REGIONS = {1: 'Northeast', 2: 'Midwest', 3: 'South', 4: 'West'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def harmonize(frame):
    """Input ages/incomes are source authors' bracket midpoints, not exact values."""
    out = frame.copy()
    out['age_group'] = np.where(out.age < 40, 'Under 40', np.where(out.age <= 60, '40 to 60', 'Over 60'))
    out['education_group'] = np.where(out.education <= 2, 'high_school', np.where(out.education <= 4, 'some_college', 'college'))
    out['household_income_band'] = np.where(out.income < 50000, 'under_50k', np.where(out.income <= 100000, '50k_to_100k', 'over_100k'))
    out.loc[out.income.isna(), 'household_income_band'] = 'missing'
    out['region'] = out.region.map(REGIONS)
    if out[FEATURES].isna().any().any():
        raise ValueError('Unknown common demographic coding')
    return out


def probability_scores(y, probability, ordinal=False):
    """Proper probability scores; Brier sums classes; RPS averages K-1 cutoffs."""
    y = np.asarray(y, dtype=int)
    p = np.asarray(probability, dtype=float)
    if p.ndim != 2 or len(y) != len(p) or not np.isfinite(p).all() or np.any(p < 0):
        raise ValueError('Invalid probability array')
    if not np.allclose(p.sum(axis=1), 1) or np.any(y < 0) or np.any(y >= p.shape[1]):
        raise ValueError('Invalid classes or sums')
    one_hot = np.eye(p.shape[1])[y]
    result = {'log_loss': float(-np.log(np.clip(p[np.arange(len(y)), y], 1e-12, 1)).mean()),
              'brier': float(np.square(p-one_hot).sum(axis=1).mean()),
              'accuracy': float((p.argmax(axis=1) == y).mean())}
    if ordinal:
        result['rps'] = float(np.square(np.cumsum(p-one_hot, axis=1)[:, :-1]).mean())
    return result


def fit_probabilities(train, test, y, k, columns):
    """Sum negative log likelihood + .5*||slopes||² (C=1); no intercept penalty."""
    train_arrays, test_arrays = [np.ones((len(train), 1))], [np.ones((len(test), 1))]
    for column in columns:
        levels = sorted(set(train[column].astype(str)))
        train_arrays.append(np.column_stack([train[column].astype(str).eq(v) for v in levels]).astype(float))
        test_arrays.append(np.column_stack([test[column].astype(str).eq(v) for v in levels]).astype(float))
    x, xt = np.concatenate(train_arrays, axis=1), np.concatenate(test_arrays, axis=1)
    initial = np.zeros((x.shape[1], k))
    initial[0] = np.log(np.bincount(y, minlength=k)/len(y))
    initial[0] -= initial[0].mean()
    target = np.eye(k)[y]
    def objective(flat):
        b = flat.reshape(x.shape[1], k)
        z = x@b
        loss = np.sum(logsumexp(z, axis=1)-z[np.arange(len(y)), y])+.5*np.sum(b[1:]**2)
        grad = x.T@(softmax(z, axis=1)-target)
        grad[1:] += b[1:]
        return float(loss), grad.ravel()
    result = minimize(objective, initial.ravel(), jac=True, method='L-BFGS-B',
                      options={'maxiter': 2000, 'ftol': 1e-12, 'gtol': 1e-6})
    if not result.success:
        raise ValueError('Multinomial convergence failed: '+str(result.message))
    return softmax(xt@result.x.reshape(x.shape[1], k), axis=1)


def cross_validate(frame, y, k, feature_sets, ordinal=False):
    y = np.asarray(y, dtype=int)
    counts = np.bincount(y, minlength=k)
    if counts.min() < 5:
        raise ValueError('Each class needs at least five observations')
    results = []
    for seed in SEEDS:
        predictions = {name: np.zeros((len(y), k)) for name in ['population']+list(feature_sets)}
        seen = np.zeros(len(y), dtype=int)
        rng = np.random.default_rng(seed)
        pieces = [np.array_split(rng.permutation(np.flatnonzero(y == c)), 5) for c in range(k)]
        for fold in range(5):
            test = np.sort(np.concatenate([parts[fold] for parts in pieces]))
            train = np.setdiff1d(np.arange(len(y)), test)
            # Training prevalence only: no holdout outcome is read by the predictor.
            prevalence = np.bincount(y[train], minlength=k)/len(train)
            predictions['population'][test] = prevalence
            for name, columns in feature_sets.items():
                predictions[name][test] = fit_probabilities(frame.iloc[train], frame.iloc[test], y[train], k, columns)
            seen[test] += 1
        if not np.all(seen == 1):
            raise ValueError('Holdout coverage mismatch')
        scores = {name: probability_scores(y, p, ordinal) for name, p in predictions.items()}
        results.append({'seed': seed, 'scores': scores,
                        'delta_vs_population': {name: {metric: value-scores['population'][metric]
                            for metric, value in score.items()} for name, score in scores.items() if name != 'population'}})
    return {'n': len(y), 'class_counts': counts.tolist(), 'folds': 5, 'seeds': list(SEEDS),
            'by_seed': results,
            'mean_scores': {name: {metric: float(np.mean([r['scores'][name][metric] for r in results]))
                for metric in results[0]['scores'][name]} for name in predictions}}


def cell_key(row):
    return tuple(str(row.get(c)) if row.get(c) is not None else 'missing' for c in FEATURES)


def support_summary(donors, profiles, weights):
    counts = Counter(cell_key(r) for r in donors[FEATURES].to_dict('records'))
    sizes = np.asarray([counts[cell_key(r)] for r in profiles], dtype=int)
    w = np.asarray(weights, dtype=float)
    if len(sizes) != len(w) or np.any(w <= 0) or not np.isfinite(w).all():
        raise ValueError('Bad target-support weights')
    return {'n': len(sizes), 'min_donors': int(sizes.min()), 'median_donors': float(np.median(sizes)),
            'donor_cell_counts': {str(n): int((sizes == n).sum()) for n in sorted(set(sizes))},
            'weighted_share_no_donor': float(w[sizes == 0].sum()/w.sum()),
            'weighted_share_fewer_than_10_donors': float(w[sizes < 10].sum()/w.sum())}


def analyze(out):
    begin = perf_counter()
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output directory required')
    digest = sha(ARCHIVE)
    if digest != 'ae34b5e4e67c5240bae5516eb10096e33e4a94266f8e4962631e437227e189d3':
        raise ValueError('Reference archive changed')
    with ZipFile(ARCHIVE) as archive:
        original = pd.read_stata(BytesIO(archive.read('out/data/associations.dta')), convert_categoricals=False)
    household = harmonize(original.loc[original.survey.eq('household')].reset_index(drop=True))
    if len(household) != 2126 or not household.ResponseId.is_unique:
        raise ValueError('Unexpected household sample')
    attentive = household.loc[household.follow_news.notna()].copy().reset_index(drop=True)
    attention = cross_validate(attentive, attentive.follow_news.astype(int).to_numpy()-1, 6,
                               {'demographics': FEATURES}, ordinal=True)
    channels = {}
    for shock in ('oil', 'int', 'gov', 'tax'):
        cols = ['super_narra_'+shock+'_costs', 'super_narra_'+shock+'_demand']
        group = household.loc[household.type.eq(shock) & household[cols].notna().all(axis=1)].copy().reset_index(drop=True)
        if not group[cols].isin([0, 1]).all().all():
            raise ValueError('Nonbinary joint channel')
        group['attention_category'] = group.follow_news.fillna(0).astype(int).astype(str)
        y = (group[cols[0]]*2+group[cols[1]]).astype(int).to_numpy()
        fit = cross_validate(group, y, 4, {'demographics': FEATURES,
            'demographics_and_observed_attention': FEATURES+['attention_category']})
        # Exact joint support, not two independently assigned binary personalities.
        observed = group.loc[group.follow_news.notna()]
        joint = pd.crosstab(observed.follow_news.astype(int),
                            (observed[cols[0]]*2+observed[cols[1]]).astype(int)).reindex(index=range(1, 7), columns=range(4), fill_value=0)
        fit['attention_channel_joint_6_by_4_counts'] = joint.to_numpy().tolist()
        fit['joint_cells_fewer_than_5'] = int((joint.to_numpy() < 5).sum())
        fit['observed_attention_missing'] = int(group.follow_news.isna().sum())
        channels[shock] = fit
    parent = json.loads((PARENT/'manifest.json').read_text())
    def frozen(name):
        path = PARENT/name
        if sha(path) != parent['prepared_file_sha256'][name]:
            raise ValueError('Archived input changed: '+name)
        return json.loads(path.read_text())
    links = frozen('evaluation_links_private.json')
    support = {}
    for month in MONTHS:
        pop = frozen(f'{month}/population.json')['personas']
        by_id = {r['agent_id']: r['design_survey_weight'] for r in links if r['month'] == month}
        profiles = [r['attributes'] for r in pop]
        weights = [by_id[r['agent_id']] for r in pop]
        support[str(month)] = {'attention_donors': support_summary(attentive, profiles, weights),
            'shock_donors': {shock: support_summary(household.loc[household.type.eq(shock) & household.follow_news.notna()], profiles, weights)
                             for shock in ('oil', 'int', 'gov', 'tax')}}
    result = {'new_api_calls': 0, 'new_density_fits': 0, 'current_sce_answers_read': False,
        'archive_sha256': digest, 'source': 'Andre et al. v1.0.1, Wave 3 household sample, February 2021',
        'plan_sha256': sha(ROOT/'docs/workstreams/20261018_targeted_mechanisms/attention_support_plan.md'),
        'method': 'Fixed C=1 L2 multinomial logistic; training-fold one-hot; five stratified folds repeated with seeds42/43/44; no tuning.',
        'common_features': FEATURES, 'attention': attention, 'channels': channels, 'sce_192_support_by_month': support,
        'limits': ['External sample unweighted: no survey weight field in this file.',
            'Attention is agreement, not article counts; demographic prediction is not individual identification.',
            'Cross-validation is within the external 2021 sample, not time validation or cross-survey validation.',
            'Cost/demand are shock-specific, jointly selectable; tariffs are not one of the four shocks.',
            'Observed external attention is unavailable for SCE; its channel prediction increment is diagnostic only.',
            'Exact-cell sparsity does not invalidate all transfer, but bars unsupported deterministic personal labels.',
            'No new SCE simulation or improvement in its MAE is produced.'],
        'seconds': perf_counter()-begin}
    out.mkdir(parents=True)
    (out/'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    return result
