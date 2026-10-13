"""Time-separated reporting-pattern prediction without network or simulation.

Observed grids are labels, not identified psychological types. Personal history
conditions on earlier private questionnaires, so these predictions are A-line
diagnostics. All pseudocounts and comparisons are fixed in the protocol.
"""
from pathlib import Path
import hashlib
import json

import numpy as np
import pandas as pd

from ..evaluation.metrics import compare_distributions, distribution_summary, quantile


CLASS_NAMES = ('finer_than_5', '5_only', '10')
MODELS = ('training_population', 'demographic', 'demographic_personal_history',
          'previous_belief_shape', 'previous_belief_shape_personal_history')
BIN_FIELDS = [f'Q9_bin{i}' for i in range(1, 11)]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def classify(probabilities):
    p = np.asarray(probabilities, float)
    if p.ndim != 2 or p.shape[1] != 10:
        raise ValueError('Expected rows of ten probability bins')
    valid = (np.isfinite(p).all(axis=1) & (p >= 0).all(axis=1)
             & (p <= 100).all(axis=1) & (np.abs(p.sum(axis=1)-100) <= 1e-6))
    g5 = np.all(np.isclose(p/5, np.rint(p/5), atol=1e-8, rtol=0), axis=1)
    g10 = np.all(np.isclose(p/10, np.rint(p/10), atol=1e-8, rtol=0), axis=1)
    return valid, np.where(g10, 2, np.where(g5, 1, 0))


def prepare(frame):
    if frame.duplicated(['userid', 'date']).any():
        raise ValueError('Duplicate person-month')
    valid, labels = classify(frame[BIN_FIELDS].to_numpy(float))
    w = pd.to_numeric(frame.weight, errors='coerce').to_numpy(float)
    valid &= np.isfinite(w) & (w > 0)
    d = frame.loc[valid].copy()
    d['class'] = labels[valid]
    p = d[BIN_FIELDS].to_numpy(float)
    d['nonzero'] = (p > 0).sum(axis=1)
    d['max_mass'] = p.max(axis=1)
    d['zero_deflation'] = p[:, 5:].sum(axis=1) == 0
    for col in ('date', 'userid'):
        if not np.isfinite(pd.to_numeric(d[col], errors='coerce')).all():
            raise ValueError('Invalid panel key')
        d[col] = d[col].astype(int)
    d = d.sort_values(['userid', 'date']).reset_index(drop=True)
    for k in range(3):
        indicator = (d['class'] == k).astype(int)
        d[f'past_count_{k}'] = indicator.groupby(d.userid).cumsum()-indicator
    d['past_n'] = d.groupby('userid').cumcount()
    for col in ('date', 'class', 'nonzero', 'Q9_iqr', 'max_mass', 'zero_deflation'):
        d['previous_'+col] = d.groupby('userid')[col].shift()
    mi = d.date.floordiv(100)*12+d.date.mod(100)
    old = d.previous_date
    d['gap_months'] = mi-(old.floordiv(100)*12+old.mod(100))
    d['mw'] = d.weight/d.groupby('date').weight.transform('sum')
    d['demographic_key'] = (d['_AGE_CAT'].fillna('UNKNOWN').replace('', 'UNKNOWN').astype(str)+'|'
                            +d['_EDU_CAT'].fillna('UNKNOWN').replace('', 'UNKNOWN').astype(str)+'|'
                            +d['_NUM_CAT'].fillna('UNKNOWN').replace('', 'UNKNOWN').astype(str))
    return d, {'source_rows': len(frame), 'valid_rows': len(d),
               'excluded_invalid_probability_or_weight': len(frame)-len(d),
               'persons': int(d.userid.nunique()), 'months': int(d.date.nunique())}


def weighted_cuts(values, weights):
    x, w = np.asarray(values, float), np.asarray(weights, float)
    valid = np.isfinite(x) & (x >= 0) & np.isfinite(w) & (w > 0)
    if not valid.any():
        raise ValueError('Training state has no finite support')
    return [quantile(x[valid], w[valid], q) for q in (.25, .5, .75)]


def state_keys(d, cuts):
    bins = d.previous_nonzero.to_numpy(float)
    bucket = np.where(bins == 1, 0, np.where(bins == 2, 1, np.where(bins <= 4, 2, 3)))
    bucket[~np.isfinite(bins)] = 4
    values = []
    for field in ('previous_Q9_iqr', 'previous_max_mass'):
        x = d[field].to_numpy(float)
        q = np.searchsorted(cuts[field], x, side='right')
        q[~np.isfinite(x) | (x < 0)] = 4
        values.append(q)
    return pd.Series([f'{a}|{b}|{c}' for a,b,c in zip(bucket, *values)], index=d.index)


def fit_table(train, key, prior, protocol):
    # Months have equal mass. Rescale only to make pseudocount units mean-one rows.
    w = train.mw.to_numpy()*len(train)/train.mw.sum()
    temporary = train.assign(_table_weight=w)
    result = {}
    for value, g in temporary.groupby(key, sort=True):
        if len(g) < protocol['table_min_rows'] or g.userid.nunique() < protocol['table_min_persons']:
            continue
        counts = np.bincount(g['class'], weights=g._table_weight, minlength=3)
        tau = protocol['table_prior_mass']
        result[str(value)] = ((counts+tau*prior)/(counts.sum()+tau)).tolist()
    return result


def fit_tables(d, protocol):
    lo, hi = protocol['train']
    train = d[(d.date >= lo) & (d.date <= hi)].copy()
    if train.empty:
        raise ValueError('Empty training set')
    counts = np.bincount(train['class'], weights=train.mw, minlength=3)
    prior = counts/counts.sum()
    if (prior <= 0).any():
        raise ValueError('All classes need training support')
    cuts = {field: weighted_cuts(train[field], train.mw)
            for field in ('previous_Q9_iqr', 'previous_max_mass')}
    train['state_key'] = state_keys(train, cuts)
    return {'population': prior.tolist(), 'demographic': fit_table(train, 'demographic_key', prior, protocol),
            'state': fit_table(train, 'state_key', prior, protocol), 'cuts': cuts,
            'training_rows': len(train), 'training_months': int(train.date.nunique())}


def history_probabilities(base, counts, prior_mass):
    base, counts = np.asarray(base, float), np.asarray(counts, float)
    return (prior_mass*base+counts)/(prior_mass+counts.sum(axis=1, keepdims=True))


def predictions(d, tables, protocol):
    population = np.tile(tables['population'], (len(d), 1))
    demo = np.array([tables['demographic'].get(k, tables['population']) for k in d.demographic_key])
    keys = state_keys(d, tables['cuts'])
    state = np.array([tables['state'].get(k, tables['population']) for k in keys])
    counts = d[[f'past_count_{k}' for k in range(3)]].to_numpy(float)
    alpha = protocol['personal_prior_mass']
    result = dict(zip(MODELS, [population, demo, history_probabilities(demo, counts, alpha),
                               state, history_probabilities(state, counts, alpha)]))
    for p in result.values():
        if not (np.isfinite(p).all() and (p > 0).all() and np.allclose(p.sum(axis=1), 1)):
            raise ValueError('Invalid predicted class probabilities')
    return result


def loss_rows(labels, probabilities):
    y, p = np.asarray(labels, int), np.asarray(probabilities, float)
    if p.shape != (len(y), 3) or not np.allclose(p.sum(axis=1), 1):
        raise ValueError('Loss expects valid three-class predictions')
    return .5*np.square(p-np.eye(3)[y]).sum(axis=1)


def evaluation_summary(d, probabilities):
    if d.empty:
        return {'rows': 0, 'months': 0}
    # Re-normalize each subgroup within month; each present month then equal.
    w = d.weight/d.groupby('date').weight.transform('sum')
    y = d['class'].to_numpy(int)
    brier = loss_rows(y, probabilities)
    logloss = -np.log(probabilities[np.arange(len(y)), y])
    correct = probabilities.argmax(axis=1) == y
    monthly = []
    for date, g in d.groupby('date', sort=True):
        idx = d.index.get_indexer(g.index)
        wg = w.loc[g.index].to_numpy()
        monthly.append({'month': int(date), 'rows': len(g), 'brier': float(wg@brier[idx]),
                        'log_loss': float(wg@logloss[idx]), 'accuracy': float(wg@correct[idx]),
                        'observed_class_proportions': (wg@np.eye(3)[y[idx]]).tolist(),
                        'predicted_class_proportions': (wg@probabilities[idx]).tolist()})
    return {'rows': len(d), 'persons': int(d.userid.nunique()), 'months': len(monthly),
            'brier': float(np.mean([m['brier'] for m in monthly])),
            'log_loss': float(np.mean([m['log_loss'] for m in monthly])),
            'accuracy': float(np.mean([m['accuracy'] for m in monthly])), 'monthly': monthly}


def cluster_interval(d, differences, repetitions=1000, seed=104729):
    people, pi = np.unique(d.userid, return_inverse=True)
    months, mi = np.unique(d.date, return_inverse=True)
    w = (d.weight/d.groupby('date').weight.transform('sum')).to_numpy()
    denominator = np.zeros((len(people), len(months)))
    numerator = denominator.copy()
    np.add.at(denominator, (pi, mi), w)
    np.add.at(numerator, (pi, mi), w*np.asarray(differences))
    rng = np.random.default_rng(seed)
    samples = []
    for start in range(0, repetitions, 100):
        count = min(100, repetitions-start)
        draws = rng.multinomial(len(people), np.full(len(people), 1/len(people)), size=count)
        den = draws@denominator
        if (den <= 0).any():
            raise ValueError('Bootstrap month without supported people')
        samples.extend(((draws@numerator)/den).mean(axis=1).tolist())
    estimate = float(np.mean(numerator.sum(axis=0)/denominator.sum(axis=0)))
    return {'difference': estimate, 'interval_95': np.quantile(samples, [.025,.975]).tolist(),
            'persons': len(people), 'repetitions': repetitions, 'seed': seed}


def block_interval(monthly_differences, repetitions=1000, block=6, seed=130363):
    delta = np.asarray(monthly_differences, float)
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, len(delta), size=(repetitions, int(np.ceil(len(delta)/block))))
    indices = ((starts[...,None]+np.arange(block))%len(delta)).reshape(repetitions,-1)[:,:len(delta)]
    return {'difference': float(delta.mean()), 'interval_95': np.quantile(delta[indices].mean(axis=1), [.025,.975]).tolist(),
            'months': len(delta), 'block_months': block, 'repetitions': repetitions, 'seed': seed}


def observed_shape_summary(d):
    test = d[(d.date >= 202201) & (d.date <= 202510)]
    result = {}
    for kind, g in test.groupby('class'):
        summary = {'rows': len(g), 'single_bin_fraction': float(np.average(g.nonzero == 1, weights=g.mw)),
                   'mean_nonzero_bins': float(np.average(g.nonzero, weights=g.mw)),
                   'zero_deflation_fraction': float(np.average(g.zero_deflation, weights=g.mw))}
        supported = g[np.isfinite(g.Q9_iqr) & (g.Q9_iqr >= 0)]
        summary['official_personal_uncertainty_median_pp'] = quantile(supported.Q9_iqr, supported.mw, .5) if len(supported) else None
        result[CLASS_NAMES[int(kind)]] = summary
    pairs = test[test.gap_months == 1]
    table = np.zeros((2,2))
    for _,g in pairs.groupby('date'):
        w = g.weight/g.weight.sum()
        np.add.at(table, (g.previous_zero_deflation.astype(int),g.zero_deflation.astype(int)), w)
    table /= table.sum()
    result['zero_deflation_transition'] = {'pairs': len(pairs), 'joint_probability_equal_month': table.tolist(),
         'probability_zero_now_if_zero_before': float(table[1,1]/table[1].sum()),
         'probability_zero_now_if_positive_before': float(table[0,1]/table[0].sum())}
    return result


def reuse_rounding(root):
    oldfile = root/'outputs/sce_age_reporting_audit_20261012_v3/summary.json'
    old = json.loads(oldfile.read_text())
    for rel, expected in old['rounding']['scorer']['live_sha256'].items():
        if sha(root/rel) != expected:
            raise ValueError('Frozen scoring kernel drift')
    for rec in old['rounding']['source_audit']:
        if sha(root/rec['path']) != rec['sha256']:
            raise ValueError('Legacy model response drift')
    rawfile = root/'outputs/sce_age_reporting_audit_20261012_v3/rounding_private.json'
    truthfile = root/'outputs/sce_confidence_analysis_20261011_v2/paired_evaluation_private.json'
    rows = json.loads(rawfile.read_text())
    truths = {(str(r['month']),r['repeat'],r['agent_id']):r['real']
              for r in json.loads(truthfile.read_text()) if r['measure']=='Q9'}
    grouped = {}
    for r in rows:
        grouped.setdefault((r['month'],r['arm'],r['repeat']),{}).setdefault(r['private_agent_id'],{})[r['scenario']] = r
    scenarios = ['deterministic_5','deterministic_10','balanced_random_5']
    cells = []
    for (month, arm, repeat), by_id in sorted(grouped.items()):
        common = []
        for pid, versions in by_id.items():
            truth = truths.get((str(month), repeat, pid))
            if truth is not None and np.isfinite(truth) and all(s in versions and versions[s]['status']=='ok'
                         and versions[s]['rounded_mean'] is not None and np.isfinite(versions[s]['rounded_mean']) for s in scenarios):
                common.append((truth,versions))
        if not common:
            raise ValueError('No common support across rounding scenarios')
        base = np.array([v[scenarios[0]]['original_mean'] for _,v in common])
        truth = np.array([t for t,_ in common])
        equal = np.ones(len(base))
        original = compare_distributions(base,equal,truth,equal)
        before = distribution_summary(base,equal)
        for s in scenarios:
            after = np.array([v[s]['rounded_mean'] for _,v in common])
            scored = compare_distributions(after,equal,truth,equal)
            shape = distribution_summary(after,equal)
            cells.append({'month':str(month),'arm':arm,'repeat':repeat,'scenario':s,'n_common':len(common),
                          'original_center_mae_pp':original['median_error_pp'], 'mapped_center_mae_pp':scored['median_error_pp'],
                          'original_w1_pp':original['w1_pp'],'mapped_w1_pp':scored['w1_pp'],
                          'original_person_iqr_pp':before['iqr_pp'],'mapped_person_iqr_pp':shape['iqr_pp'],
                          'real_person_iqr_pp':original['observed']['iqr_pp'],
                          'original_variance_pp2':before['std_pp']**2,'mapped_variance_pp2':shape['std_pp']**2,
                          'signed_center_shift_pp':scored['median_bias_pp']-original['median_bias_pp'],
                          'family_changed_fraction':float(np.mean([v[s]['original_family']!=v[s]['rounded_family'] for _,v in common]))})
    aggregate = {}
    for s in scenarios:
        r = [c for c in cells if c['scenario']==s]
        names = [k for k in r[0] if k.endswith(('_pp','_pp2','fraction'))]
        aggregate[s] = {k:float(np.mean([c[k] for c in r])) for k in names}
        aggregate[s]['cells'] = len(r)
    return {'cells':cells,'aggregate':aggregate,'common_mask_all_scenarios':True,
            'sources':{str(p.relative_to(root)):sha(p) for p in [oldfile,rawfile,truthfile]},
            'scorer':old['rounding']['scorer'], 'legacy_cell_shifts':old['rounding']['aggregate'],
            'notice':'Mechanical measurement sensitivity; 4 development months, no selected best mapping, not national prediction. New diagnostics use empirical left-inverse median; legacy shifts use their disclosed np.median.'}


def run(root, out, protocol_path):
    root, out = Path(root).resolve(), Path(out).resolve()
    protocol_path = Path(protocol_path).resolve()
    if out.exists():
        raise FileExistsError('Use a new output directory')
    protocol = json.loads(protocol_path.read_text())
    out.mkdir(parents=True)
    dump(out/'protocol_snapshot.json', protocol)
    cache = root/protocol['source_cache']
    receipt = json.loads(cache.with_name('extraction_receipt.json').read_text())
    if sha(cache) != receipt['cache_sha256']:
        raise ValueError('Reference cache hash drift')
    for rec in receipt['sources']:
        if sha(root/rec['path']) != rec['sha256']:
            raise ValueError('Official workbook hash drift')
    frame = pd.read_parquet(cache)
    if len(frame) != receipt['rows']:
        raise ValueError('Reference cache rows drift')
    d, coverage = prepare(frame)
    tables = fit_tables(d, protocol)
    dump(out/'fitted_tables.json',tables)
    p = predictions(d,tables,protocol)
    periods = {}
    for name in ('validation','evaluation'):
        lo,hi = protocol[name]
        mask = (d.date >= lo)&(d.date <= hi)
        sub = d.loc[mask]
        periods[name] = {model:evaluation_summary(sub,p[model][mask]) for model in MODELS}
    print('Finished validation/evaluation class forecasts', flush=True)
    testmask = (d.date >= protocol['evaluation'][0])&(d.date <= protocol['evaluation'][1])
    test = d.loc[testmask]
    contrasts = []
    for model, baseline in protocol['main_contrasts']:
        diff = loss_rows(test['class'],p[model][testmask])-loss_rows(test['class'],p[baseline][testmask])
        monthly = [a['brier']-b['brier'] for a,b in zip(periods['evaluation'][model]['monthly'],periods['evaluation'][baseline]['monthly'])]
        c = protocol['person_cluster_bootstrap']; b = protocol['month_block_bootstrap']
        contrasts.append({'model':model,'baseline':baseline,
                          'person_cluster':cluster_interval(test,diff,c['repetitions'],c['seed']),
                          'month_block':block_interval(monthly,b['repetitions'],b['block_months'],b['seed'])})
        print('Finished clustered diagnostic',model,flush=True)
    subgroup_masks = {'no_past_observable':d.past_n == 0,'one_or_two_past':d.past_n.between(1,2),
                      'three_or_more_past':d.past_n >= 3,'exact_adjacent_calendar':d.gap_months == 1}
    subgroups = {}
    for name, group in subgroup_masks.items():
        mask = testmask & group
        subgroups[name] = {model:evaluation_summary(d.loc[mask],p[model][mask]) for model in MODELS}
    for year in sorted(test.date.floordiv(100).unique()):
        mask = testmask & (d.date.floordiv(100)==year)
        subgroups[str(year)] = {model:evaluation_summary(d.loc[mask],p[model][mask]) for model in MODELS}
    # Person-level forecasts remain local for independent audits, never sent to an API.
    private = d[['userid','date','class','past_n','gap_months','weight']].copy()
    for model in MODELS:
        for k in range(3):
            private[f'{model}_p{k}'] = p[model][:,k]
    private.to_parquet(out/'predictions_private.parquet',index=False)
    sensitivity = reuse_rounding(root)
    summary = {'protocol':protocol,'coverage':coverage,'periods':periods,'contrasts':contrasts,
               'subgroups':subgroups,'observed_shapes':observed_shape_summary(d),'rounding_reuse':sensitivity,
               'training_support':{'demographic_cells':len(tables['demographic']),'state_cells':len(tables['state']),
                                   'rows':tables['training_rows'],'months':tables['training_months'],'cuts':tables['cuts']},
               'source_hashes':{protocol['source_cache']:sha(cache),str(protocol_path.relative_to(root)):sha(protocol_path)},
               'code_hashes':{str(Path(__file__).resolve().relative_to(root)):sha(__file__)},
               'new_api_calls':0,'simulation_changed':False}
    dump(out/'summary.json',summary)
    print(json.dumps({'output':str(out),'rows':coverage['valid_rows'],
                      'evaluation_brier':{m:periods['evaluation'][m]['brier'] for m in MODELS},'new_api_calls':0}),flush=True)
    return summary
