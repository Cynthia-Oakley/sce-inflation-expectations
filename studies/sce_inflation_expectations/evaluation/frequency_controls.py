"""Offline exploratory associations: synthetic contact, priors, errors, paired rule effect."""
from pathlib import Path
import json
import hashlib
import math

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.stats.multitest import multipletests

ROOT = Path(__file__).resolve().parents[3]
EVALUATION = ROOT / 'outputs/sce_purchase_frequency_evaluation_20261015_v1'
INPUT = ROOT / 'outputs/sce_purchase_frequency_trial_20261015_v1'
MATERIAL = ROOT / 'outputs/sce_purchase_frequency_preparation_20261015_v1'
FREQ = {'f_home': 'food_at_home', 'f_away': 'food_away_from_home',
        'f_house': 'household_cleaning_paper', 'f_care': 'personal_care_products'}
PROFILE = ['age_group', 'education_group', 'household_income_band', 'region',
           'numeracy', 'housing_tenure']
OUTCOMES = ['real_q9', 'data_q9', 'rule_q9', 'data_q9_abs_error', 'rule_q9_abs_error',
            'data_q8_abs_error', 'rule_q8_abs_error', 'change_q9', 'change_q9_abs_error',
            'change_q8_abs_error', 'change_gap', 'change_previous_distance']
CORE = ['C(month)', 'prior_q9', 'prior_iqr', 'history_anchor', 'has_history_anchor', 'history_n']
EXTRA = ['prior_q8'] + [f'C({p})' for p in PROFILE] + ['C(employment_coarse)',
         'share_food', 'share_gasoline', 'share_shelter', 'C(fed_confidence)']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def average_absolute_error(predictions, actual):
    return float(np.mean([abs(p - actual) for p in predictions]))


def quantile(values, q):
    a = np.sort(np.asarray(values, float))
    return float(a[max(0, min(len(a)-1, math.ceil(q * len(a)) - 1))])


def center_bridge(sim_q9, sim_q8, actual_q9, actual_q8):
    p9, p8, y9, y8 = [quantile(a, .5) for a in [sim_q9, sim_q8, actual_q9, actual_q8]]
    e9, e8 = p9-y9, p8-y8
    gap = (p9-p8) - (y9-y8)
    if abs(e9-e8-gap) > 1e-10:
        raise ValueError('center identity failed')
    return {'q9_center': p9, 'q8_center': p8, 'real_q9_center': y9, 'real_q8_center': y8,
            'q9_signed_error': e9, 'q8_signed_error': e8, 'density_point_gap_error': gap,
            'q9_absolute_error': abs(e9), 'q8_absolute_error': abs(e8)}


def variance_parts(values, groups):
    x = np.asarray(values, float); g = np.asarray(groups)
    grand = float(x.mean()); within = between = 0.0
    for name in sorted(set(g)):
        z = x[g == name]; w = len(z) / len(x)
        within += w * float(np.var(z)); between += w * (float(z.mean())-grand)**2
    total = float(np.var(x))
    assert abs(total-within-between) < 1e-9
    return {'total_variance': total, 'between_month_variance': between, 'within_month_variance': within,
            'between_month_share': between/total if total else None,
            'within_month_share': within/total if total else None}


def load():
    sources = {}; paths = [EVALUATION/'cases_private.json', MATERIAL/'assignments_private.json', MATERIAL/'prices.json']
    cases, assignments, prices = [json.loads(p.read_text()) for p in paths]
    lookup = {(r['month'], r['agent_id']): r for r in assignments}
    price = {int(r['target_month'].replace('-', '')): r for r in prices}
    configs = {}
    for month in sorted({r['month'] for r in cases}):
        p = INPUT/str(month)/'simulation_frequency_data.json'; paths.append(p)
        configs[month] = json.loads(p.read_text())['decision_args']['purchase_frequency_bundle']['parent']['parent']['base']
    groups = {}
    for r in cases:
        groups.setdefault((r['month'], r['agent_id']), []).append(r)
    result = []
    for (month, aid), repeats in groups.items():
        assert sorted(r['repeat'] for r in repeats) == [1, 2]
        r = repeats[0]; a = lookup[month, aid]; base = configs[month]
        for k in ['userid', 'profile', 'actual', 'previous', 'actual_point', 'previous_point']:
            assert repeats[0][k] == repeats[1][k]
        state = base['rows'][aid]['state']; baseline = base['baseline']
        row = {'month': month, 'agent_id': aid, 'userid': r['userid'],
               'real_q9': r['actual'], 'real_q8': r['actual_point'], 'prior_q9': r['previous'],
               'prior_q8': r['previous_point'], 'prior_iqr': state['high']-state['low'],
               'history_anchor': round(state['anchor'], 1) if state['anchor'] is not None else r['previous'],
               'has_history_anchor': int(state['anchor'] is not None), 'history_n': state['n_earlier_valid'],
               'fed_confidence': baseline['labels'][aid], 'survey_weight': r['survey_weight']}
        row.update({k: r['profile'].get(k) for k in PROFILE})
        employment = r['profile'].get('employment_status')
        row['employment_coarse'] = ('working_or_on_leave' if employment in ['employed', 'on_leave'] else
                                    'retired' if employment == 'retired' else 'other_nonemployment' if employment else None)
        shares = baseline['news']['rows'][aid]['spending_shares']
        row.update({'share_'+k: shares[k] for k in ['food', 'gasoline', 'shelter']})
        row.update({short: a['recorded_days_7d'][category] for short, category in FREQ.items()})
        row['total_category_days'] = sum(row[k] for k in FREQ)
        assert row['total_category_days'] > 0
        row['price_contact_proxy'] = sum(row[k]*price[month]['categories'][cat]['yoy_nsa_pct'] for k,cat in FREQ.items()) / row['total_category_days']
        for prefix, arm in [('data', 'frequency_data'), ('rule', 'frequency_rule'), ('old_c', 'reused_C')]:
            q9 = [p[arm] for p in repeats]; q8 = [p[arm+'_point'] for p in repeats]
            row[prefix+'_q9'] = float(np.mean(q9)) if all(finite(x) for x in q9) else None
            row[prefix+'_q8'] = float(np.mean(q8)) if all(finite(x) for x in q8) else None
            row[prefix+'_q9_abs_error'] = average_absolute_error(q9, r['actual']) if all(finite(x) for x in q9+[r['actual']]) else None
            row[prefix+'_q8_abs_error'] = average_absolute_error(q8, r['actual_point']) if all(finite(x) for x in q8+[r['actual_point']]) else None
            row[prefix+'_previous_distance'] = average_absolute_error(q9, r['previous']) if all(finite(x) for x in q9+[r['previous']]) else None
            row[prefix+'_gap'] = row[prefix+'_q9']-row[prefix+'_q8'] if all(finite(row[prefix+'_'+k]) for k in ['q9','q8']) else None
            bins = [p[arm+'_bins'] for p in repeats]
            row[prefix+'_deflation_probability'] = float(np.mean([sum(p[5:]) for p in bins]))
        for suffix in ['q9','q9_abs_error','q8_abs_error','gap','previous_distance']:
            row['change_'+suffix] = row['rule_'+suffix]-row['data_'+suffix] if all(finite(row[k+'_'+suffix]) for k in ['rule','data']) else None
        result.append(row)
    for p in paths:
        sources[str(p.relative_to(ROOT))] = sha(p)
    sources[str(Path(__file__).resolve().relative_to(ROOT))] = sha(__file__)
    return pd.DataFrame(result), cases, sources


def fit(frame, outcome, extra=False, proxy=False):
    terms = CORE + (EXTRA if extra else [])
    frequency_terms = ['price_contact_proxy', 'total_category_days'] if proxy else list(FREQ)
    formula = outcome + ' ~ ' + ' + '.join(terms+frequency_terms)
    model = smf.ols(formula, data=frame).fit(cov_type='HC3', use_t=True)
    if np.linalg.matrix_rank(model.model.exog) != model.model.exog.shape[1]:
        raise ValueError('rank-deficient diagnostic model')
    selected = frequency_terms + ['prior_q9']
    intervals = model.conf_int(); coefficients = {}
    for k in selected:
        v = {'coefficient': float(model.params[k]), 'ci95': intervals.loc[k].tolist(), 'p_value': float(model.pvalues[k])}
        if not all(math.isfinite(x) for x in [v['coefficient'],v['p_value'],*v['ci95']]):
            raise ValueError('nonfinite robust interval')
        coefficients[k] = v
    restrictions = np.zeros((len(frequency_terms),len(model.params)))
    for i,k in enumerate(frequency_terms): restrictions[i, list(model.params.index).index(k)] = 1
    test = model.wald_test(restrictions, use_f=True, scalar=True)
    leverage = np.asarray(model.get_influence().hat_matrix_diag)
    # Personal history appears in several correlated fields. A single partial
    # coefficient is not its total association and is never a psychological weight.
    prior_terms = ['prior_q9', 'prior_iqr', 'history_anchor', 'has_history_anchor', 'history_n'] + (['prior_q8'] if extra else [])
    prior_restrictions = np.zeros((len(prior_terms), len(model.params)))
    for i,k in enumerate(prior_terms): prior_restrictions[i,list(model.params.index).index(k)] = 1
    prior_test = model.wald_test(prior_restrictions, use_f=True, scalar=True)
    coherent = np.zeros((1,len(model.params)))
    for k in ['prior_q9','history_anchor'] + (['prior_q8'] if extra else []):
        coherent[0,list(model.params.index).index(k)] = 1
    combined = model.t_test(coherent)
    return {'outcome': outcome, 'formula': formula, 'n': int(model.nobs), 'parameters': len(model.params),
            'r_squared': float(model.rsquared), 'adjusted_r_squared': float(model.rsquared_adj),
            'frequency_joint_p_value': float(test.pvalue), 'max_leverage': float(leverage.max()),
            'coefficients': coefficients, 'personal_history_joint_p': float(prior_test.pvalue),
            'coherent_prior_level_association': {'coefficient':float(np.asarray(combined.effect).item()),
                 'ci95':combined.conf_int().ravel().tolist(),
                 'interpretation':'Modelled association when prior Q9/history center and, in full model, Q8 jointly shift by 1pp; not an intervention or update weight.'},
            'interval_method': 'OLS HC3, t reference; exploratory conditional associations'}


def describe(frame, cases):
    columns = list(FREQ)+['price_contact_proxy','total_category_days','prior_q9']
    monthly=[]
    for month,g in frame.groupby('month',sort=True):
        monthly.append({'month':int(month),'n':len(g),**{k:{'mean':float(g[k].mean()),'sd':float(g[k].std(ddof=0)),
                         'iqr':quantile(g[k],.75)-quantile(g[k],.25)} for k in columns}})
    bridges=[]
    for month in sorted({r['month'] for r in cases}):
        for repeat in [1,2]:
            rows=[r for r in cases if r['month']==month and r['repeat']==repeat and r['common'] and finite(r['actual_point'])]
            for arm in ['reused_C','frequency_data','frequency_rule']:
                b=center_bridge([r[arm] for r in rows],[r[arm+'_point'] for r in rows],
                                [r['actual'] for r in rows],[r['actual_point'] for r in rows])
                bridges.append({'month':month,'repeat':repeat,'arm':arm,'n':len(rows),**b})
    common_people = frame.loc[frame['real_q9'].map(finite)]
    def person_means(subset):
        return {arm:{k:float(subset[arm+'_'+k].mean()) for k in ['q9_abs_error','q8_abs_error','gap','deflation_probability','previous_distance']} for arm in ['old_c','data','rule']}
    return {'monthly_inputs':monthly,'price_proxy_variance':variance_parts(frame['price_contact_proxy'],frame['month']),
            'frequency_correlations':frame[list(FREQ)].corr().to_dict(), 'center_bridges':bridges,
            'per_person_means_common_188':person_means(common_people),
            'per_person_means_all_192_auxiliary':person_means(frame)}


def run(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('fresh ignored output directory required')
    frame,cases,sources=load()
    q9=frame.loc[frame['real_q9'].map(finite)].copy()
    required=PROFILE+['employment_coarse','prior_q8','fed_confidence','share_food','share_gasoline','share_shelter']
    complete=q9.dropna(subset=required).copy()
    models={}; core_same={}; core_all={}
    for y in OUTCOMES:
        models[y]=fit(complete,y,extra=True)
        core_same[y]=fit(complete,y)
        core_all[y]=fit(q9,y)
    adjusted=multipletests([models[y]['frequency_joint_p_value'] for y in OUTCOMES],method='fdr_bh')[1]
    for y,p in zip(OUTCOMES,adjusted): models[y]['frequency_joint_bh_p']=float(p)
    proxy={y:fit(complete,y,extra=True,proxy=True) for y in ['real_q9','data_q9','rule_q9','change_q9','change_q9_abs_error']}
    stability=[]
    for month in sorted(complete['month'].unique()):
        part=complete.loc[complete.month.ne(month)]
        # Compact controls avoid estimating rare demographic groups on only three periods.
        stability.append({'omitted_month':int(month),'rule_minus_data':fit(part,'change_q9'),
                          'error_difference':fit(part,'change_q9_abs_error')})
    summary={'status':'completed_offline_exploratory_control_analysis','new_api_calls':0,'source_sha256':sources,
             'sample':{'person_months':len(frame),'q9_scorable':len(q9),'full_complete_cases':len(complete),
                       'distinct_people_q9':int(q9.userid.nunique()),'generation_repeats_averaged':2,
                       'complete_cases_by_month':{str(k):int(v) for k,v in complete.groupby('month').size().items()},
                       'missing_full_controls':{k:int(q9[k].isna().sum()) for k in required if q9[k].isna().any()}},
             'full_models':models,'core_same_sample':core_same,'core_all_available':core_all,
             'proxy_models':proxy,'leave_one_month_out':stability,**describe(frame,cases),
             'limits':['Post-result exploratory analysis; no independent confirmation.',
                       'Synthetic frequencies are not observed shopping behavior or personal price perception.',
                       'No simultaneous no-frequency control; regression cannot separate frequency addition, added category prices and earlier-batch drift.',
                       'Person-level error regression does not identify four-period aggregate median-MAE causes.',
                       'Paired differences remove additive fixed backgrounds, not all unobserved treatment-effect heterogeneity.',
                       'HC3 intervals condition on selected periods/donors/two generations; not national inference or full donor/model uncertainty.',
                       'Price contact proxy uses summed category days; not trips, actual attention weights or a personal CPI.']}
    out.mkdir(parents=True); frame.to_json(out/'person_month_private.json',orient='records',indent=2,force_ascii=False)
    dump(out/'summary.json',summary)
    print(json.dumps({'sample':summary['sample'],'price_proxy_variance':summary['price_proxy_variance'],
                      'full_models':{y:{'joint_p':models[y]['frequency_joint_p_value'],'bh_p':models[y]['frequency_joint_bh_p'],
                                        'prior_coefficient':models[y]['coefficients']['prior_q9']['coefficient']} for y in OUTCOMES}},ensure_ascii=False))
    return summary
