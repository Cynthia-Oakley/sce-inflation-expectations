"""Offline analysis of the frozen A82 answers; no new generation or Q9 fitting.

Primary metrics are copied/cross-checked against the registered evaluator.
Additional period/group/update/regression diagnostics are descriptive. The
registered 48/34-month combination and all simulation mechanisms stay fixed.
"""
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import csv
import json
import math

import numpy as np
import pandas as pd

from ..experiments.frozen_batch import ROOT, read_json, dump, sha
from . import cognition as shared
from .metrics import compare_distributions, distribution_summary, headline_errors, paired_month_mae_interval, quantile, wasserstein1
from .aggregate_blend import fit_weight, evaluate as blend_metrics

MODEL = 'monthly_reconstruction'
PAST = 'monthly_past_reference'
PERIODS = {'2019': (201901, 201912), '2020–2021': (202001, 202112),
           '2022': (202201, 202212), '2023–2024': (202301, 202412),
           '2025（1–10月）': (202501, 202510),
           '拟权期2019–2022': (201901, 202212), '评价期2023–2025': (202301, 202510)}


def finite(x):
    return isinstance(x, (int, float, np.number)) and math.isfinite(float(x))


def averages(rows, names):
    return {k: float(np.mean([r[k] for r in rows if finite(r.get(k))]))
            if any(finite(r.get(k)) for r in rows) else None for k in names}


def compact(summary):
    return {q: v['aggregate_equal_month_repeat_cells']
            for q, v in summary['auxiliary_survey_weighted'].items() if q in ('q8', 'q9')}


def macro_scope(rows):
    s = [r['sim_pp'] for r in rows]; y = [r['truth_pp'] for r in rows]; a = [r['anchor_pp'] for r in rows]
    errors = np.asarray(s) - y; carry = np.asarray(a) - y
    return dict(n_months=len(rows), model=blend_metrics(rows, 1.), persistence=blend_metrics(rows, 0.),
                model_win_months=int(np.sum(abs(errors) < abs(carry) - 1e-10)),
                tie_months=int(np.sum(abs(abs(errors) - abs(carry)) <= 1e-10)),
                paired_mae=paired_month_mae_interval(errors, carry, block_length=min(6, len(rows)), seed=20261023))


def variance_parts(values, weights, labels):
    """Exact descriptive weighted law of total variance, same monthly support."""
    x, w = np.asarray(values, float), np.asarray(weights, float)
    mu = np.average(x, weights=w); total = np.average((x - mu) ** 2, weights=w)
    between = within = 0.
    for label in set(labels):
        selected = np.asarray([v == label for v in labels]); mass = w[selected].sum() / w.sum()
        center = np.average(x[selected], weights=w[selected])
        between += mass * (center - mu) ** 2
        within += mass * np.average((x[selected] - center) ** 2, weights=w[selected])
    if abs(total - between - within) > 1e-8 * max(1., total):
        raise ValueError('Variance identity failed')
    return dict(total_pp_squared=float(total), between_pp_squared=float(between), within_pp_squared=float(within))


def monthly_analysis(cases, evaluated, readout):
    valid = [r for r in cases if finite(r['survey_weight']) and r['survey_weight'] > 0]
    support = shared._common_person_months(valid, [MODEL, PAST], [1], 'q9')
    grouped = defaultdict(list)
    for r in valid:
        if (r['month'], r['userid']) in support:
            grouped[r['month']].append(r)
    frozen = {r['month']: r for r in evaluated['fixed_roster']['arms'][MODEL]['auxiliary_survey_weighted']['q9']['cells']}
    national = {int(r['month'].replace('-', '')): r for r in readout['official_national']['monthly']}
    full = {int(r['month']): r for r in readout['monthly']}
    monthly = []; update_rows = []; variance = []; prior_bands = []; checks = 0
    for month, rows in sorted(grouped.items()):
        w = np.array([r['survey_weight'] for r in rows]); y = np.array([r['real']['q9_mean'] for r in rows])
        sim = np.array([r['arms'][MODEL]['mean'] for r in rows]); past = np.array([r['arms'][PAST]['mean'] for r in rows])
        comparison = compare_distributions(sim, w, y, w)
        cm = shared._q9_cell_metrics(rows, MODEL, w); cb = shared._q9_cell_metrics(rows, PAST, w)
        for key in cm:
            if finite(cm[key]) and finite(frozen[month].get(key)):
                if not np.isclose(cm[key], frozen[month][key], atol=1e-9, rtol=1e-9):
                    raise ValueError('Frozen metric disagreement: ' + key)
                checks += 1
        record = dict(month=month, n=len(rows), weight_ess=float(w.sum()**2 / (w @ w)),
            human_median_pp=comparison['observed']['median_pp'], model_median_pp=comparison['simulated']['median_pp'],
            past_median_pp=quantile(past, w, .5), model=cm, past=cb,
            centered_w1_pp=comparison['centered_w1_pp'],
            quantiles={name:[quantile(x,w,q) for q in [.01,.05,.1,.25,.5,.75,.9,.95,.99]]
                       for name,x in [('human',y),('model',sim),('past',past)]})
        # Signed terms add. Their absolute values / MAEs need not add.
        all_model = national[month]['sim_pp']; human_full = full[month]['fields']['q9_mean']['observed']['median_pp']
        parts = dict(model_same_support_pp=record['model_median_pp']-record['human_median_pp'],
            model_support_pp=all_model-record['model_median_pp'],
            sampling_pp=record['human_median_pp']-human_full,
            definition_pp=human_full-national[month]['truth_pp'])
        if not np.isclose(sum(parts.values()),all_model-national[month]['truth_pp'],atol=1e-10):
            raise ValueError('Signed macro error decomposition failed')
        record['signed_error_components']=parts; monthly.append(record)
        vp={name:variance_parts(x,w,[r['stratum'] for r in rows]) for name,x in [('human',y),('model',sim),('past',past)]}
        variance.append(dict(month=month,**vp))
        adjacent = [r for r in rows if finite(r['real']['previous_q9_mean'])]
        if not adjacent:continue
        aw=np.array([r['survey_weight'] for r in adjacent]); p=np.array([r['real']['previous_q9_mean'] for r in adjacent])
        dy=np.array([r['real']['q9_mean'] for r in adjacent])-p
        ds=np.array([r['arms'][MODEL]['mean'] for r in adjacent])-p
        true_distribution=distribution_summary(dy,aw); sim_distribution=distribution_summary(ds,aw)
        update_rows.append(dict(month=month,n=len(adjacent),human=true_distribution,model=sim_distribution,
            model_delta_w1_pp=wasserstein1(ds,aw,dy,aw),
            past_delta_w1_pp=wasserstein1(np.zeros(len(ds)),aw,dy,aw),
            human_unchanged_share=float(np.average(abs(dy)<1e-8,weights=aw)),
            model_unchanged_share=float(np.average(abs(ds)<1e-8,weights=aw)),
            human_large_change_share=float(np.average(abs(dy)>2,weights=aw)),
            model_large_change_share=float(np.average(abs(ds)>2,weights=aw)),
            direction_match_share=float(np.average(np.sign(np.where(abs(dy)<1e-8,0,dy))==np.sign(np.where(abs(ds)<1e-8,0,ds)),weights=aw))))
        lo,hi=quantile(p,aw,1/3),quantile(p,aw,2/3)
        bands=np.where(p<=lo,'低先验',np.where(p<=hi,'中先验','高先验'))
        for band in ('低先验','中先验','高先验'):
            idx=bands==band
            if not idx.any():continue
            prior_bands.append(dict(month=month,band=band,n=int(idx.sum()),
                real_mean_delta_pp=float(np.average(dy[idx],weights=aw[idx])),
                model_mean_delta_pp=float(np.average(ds[idx],weights=aw[idx])),
                real_median_delta_pp=quantile(dy[idx],aw[idx],.5),model_median_delta_pp=quantile(ds[idx],aw[idx],.5)))
    return monthly, update_rows, variance, prior_bands, checks


def group_analysis(evaluated):
    result = []
    for dimension, groups in evaluated['groups'].items():
        for label, group in groups.items():
            support = {v['month']:v for v in group['support_by_month']}
            model=group['arms'][MODEL]['auxiliary_survey_weighted']['q9']
            cells=model['cells']; eligible=[v for v in cells if not support[v['month']]['descriptive_only']]
            result.append(dict(dimension=dimension,label=label,
                person_months=group['q9_person_months'],eligible_months=len(eligible),total_months=len(cells),
                descriptive_only=len(eligible)==0,
                eligible_metrics=averages(eligible,list(model['aggregate_equal_month_repeat_cells'])),
                all_supported_metrics=model['aggregate_equal_month_repeat_cells'],support_by_month=list(support.values()),
                cells=[dict(v,eligible=not support[v['month']]['descriptive_only']) for v in cells]))
    return result


def wls(X, y, w):
    """Descriptive WLS only; no iid coefficient significance claims."""
    root=np.sqrt(w); b,_,rank,_=np.linalg.lstsq(X*root[:,None],y*root,rcond=None)
    residual=y-X@b; sse=float(np.dot(w,residual**2)); sst=float(np.dot(w,(y-np.average(y,weights=w))**2))
    return dict(r2=1-sse/sst,sse=sse,rank=int(rank)),b,residual


def regression_diagnostic(cases, protocol):
    rows=[r for r in cases if finite(r['survey_weight']) and r['survey_weight']>0
          and all(finite(x) for x in (r['real']['q9_mean'],r['real']['previous_q9_mean'],r['arms'][MODEL]['mean']))]
    histories={}
    for month in sorted({r['month'] for r in rows}):
        states=read_json(ROOT/protocol['input_templates']/str(month)/'initial_states_private.json')
        for r in (r for r in rows if r['month']==month):
            h=states[r['agent_id']]['history_centers']
            if any(int(v['source_period'])>=month for v in h):raise ValueError('Future history in diagnostic input')
            histories[month,r['agent_id']]=(len(h),float(np.mean([v['center'] for v in h])) if len(h)>=2 else None)
    data=[]
    for r in rows:
        n,typical=histories[r['month'],r['agent_id']];lag=r['real']['previous_q9_mean']
        data.append(dict(y=r['real']['q9_mean'],sim=r['arms'][MODEL]['mean'],lag=lag,
            history_gap=(typical-lag) if typical is not None else 0.,history_missing=float(typical is None),history_n=n,
            month=str(r['month']),agent_id=r['agent_id'],weight=r['survey_weight'],**r['profile']))
    df=pd.DataFrame(data);y=df.y.to_numpy(float)
    w=(df.weight/df.groupby('month').weight.transform('sum')).to_numpy(float)
    one=np.ones((len(df),1));lag=df[['lag']].to_numpy(float);sim=df[['sim']].to_numpy(float)
    numeric=df[['lag','history_gap','history_n','history_missing']].to_numpy(float)
    labels=['month','age_group','education_group','household_income_band','numeracy','region','employment_status','housing_tenure']
    categorical=pd.get_dummies(df[labels].fillna('unknown').astype(str),drop_first=True,dtype=float)
    control=np.column_stack([one,numeric,categorical.to_numpy(float)])
    specifications=[('simulation_only',np.column_stack([one,sim])),('lag_only',np.column_stack([one,lag])),
        ('lag_plus_simulation',np.column_stack([one,lag,sim])),('past_history_P_month',control),
        ('past_history_P_month_plus_simulation',np.column_stack([control,sim]))]
    fits={};betas={};residuals={}
    for name,x in specifications:
        fits[name],betas[name],residuals[name]=wls(x,y,w)
    last=betas['past_history_P_month_plus_simulation']
    ncols=['intercept','lag','history_gap','history_n','history_missing',*categorical.columns,'simulation']
    baseline=fits['past_history_P_month']; augmented=fits['past_history_P_month_plus_simulation']
    return dict(n_person_months=len(df),n_people=int(df.agent_id.nunique()),n_months=int(df.month.nunique()),
        weights='Design weights normalized separately within month, so months have equal total mass.',
        fits=fits,incremental_r2=augmented['r2']-baseline['r2'],
        partial_r2=(baseline['sse']-augmented['sse'])/baseline['sse'],
        coefficients={k:float(v) for k,v in zip(ncols,last) if k in ['lag','history_gap','history_n','history_missing','simulation']},
        limits=['Descriptive in-sample WLS, not forecast validation or causal effects.',
                'Month fixed effects absorb common monthly shifts; remaining simulation coefficient is conditional.',
                'No iid standard errors/p-values: repeated people and common months are not independent.',
                'history_gap is earlier typical mean minus lag; insufficient history uses zero gap plus missing indicator.'])


def run(declaration, out):
    declaration,out=Path(declaration).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh output required')
    source=read_json(declaration)
    for name,digest in source['source_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Frozen result changed: '+name)
    folder=ROOT/source['analysis_run']; evaluated=read_json(folder/'evaluation/summary.json')
    readout=read_json(folder/'readout/summary.json');cases=read_json(folder/'evaluation/cases_private.json')
    protocol=read_json(ROOT/'outputs/sce_monthly_fine_full_execution_20261023_v3/protocol.json')
    print('复用已有评价；计算逐月、更新和方差诊断…',flush=True)
    monthly,updates,variance,bands,checks=monthly_analysis(cases,evaluated,readout)
    national=readout['official_national']['monthly'];yearly=[];periods=[]
    for label,bounds in {**{str(y):(y*100+1,y*100+12) for y in range(2019,2026)},**PERIODS}.items():
        scope=[r for r in national if bounds[0]<=int(r['month'].replace('-',''))<=bounds[1]]
        row=dict(period=label,**macro_scope(scope))
        if len(label)==4:yearly.append(row)
        if label in PERIODS:periods.append(row)
    original=ROOT/source['original_run'];old=read_json(original/'evaluation/summary.json');old_macro=read_json(original/'readout/summary.json')
    update_summary=averages(updates,['model_delta_w1_pp','past_delta_w1_pp','human_unchanged_share','model_unchanged_share',
        'human_large_change_share','model_large_change_share','direction_match_share'])
    update_summary.update(person_months=sum(r['n'] for r in updates),n_months=len(updates))
    variance_summary={name:averages([r[name] for r in variance],list(variance[0][name])) for name in ('human','model','past')}
    denominator=variance_summary['human']['total_pp_squared']-variance_summary['model']['total_pp_squared']
    within_share=((variance_summary['human']['within_pp_squared']-variance_summary['model']['within_pp_squared'])/denominator) if denominator>1e-10 else None
    print('逐月指标核对完成；计算个人层面描述性增量回归…',flush=True)
    regression=regression_diagnostic(cases,protocol)
    fixed={k:compact(v) for k,v in evaluated['fixed_roster']['arms'].items()}
    genuine={k:compact(v) for k,v in evaluated['genuine_previous_only']['arms'].items()}
    result=dict(status='completed_frozen_A82_offline_analysis',created_at_utc=datetime.now(timezone.utc).isoformat(),
        new_api_calls=0,new_q9_density_fits=0,configuration_changes=False,
        scope=source,primary_support=dict(q9=evaluated['fixed_roster']['q9_person_months'],q8=evaluated['fixed_roster']['q8_person_months'],
            genuine_q9=evaluated['genuine_previous_only']['q9_person_months'],genuine_q8=evaluated['genuine_previous_only']['q8_person_months']),
        quality=evaluated['quality'],fixed_roster=fixed,genuine_previous_only=genuine,
        usable_output_sensitivity={k:compact(v) for k,v in evaluated['usable_output_sensitivity']['arms'].items()},
        full_wave=readout['full_wave_center_errors'],official_national=readout['official_national'],
        macro_whole=macro_scope(national),yearly=yearly,periods=periods,monthly=monthly,
        update_summary=update_summary,update_monthly=updates,prior_bands=bands,
        variance_summary=variance_summary,variance_monthly=variance,variance_gap_within_grid_share=within_share,
        groups=group_analysis(evaluated),regression=regression,
        technical_sensitivity=dict(original_model=compact(old['fixed_roster']['arms'][MODEL]),
            original_national=old_macro['official_national']['model'],
            main_and_repaired_q9_mae_difference_pp=fixed[MODEL]['q9']['q9_center_mae_pp']-compact(old['fixed_roster']['arms'][MODEL])['q9']['q9_center_mae_pp']),
        centered_w1_mean_pp=float(np.mean([r['centered_w1_pp'] for r in monthly])),
        signed_error_component_means=averages([r['signed_error_components'] for r in monthly],list(monthly[0]['signed_error_components'])),
        frozen_metric_crosschecks=checks,
        limits=['A retrospective conditional reconstruction; not strict-B forecast.',
                'Official nationwide, full-micro wave and same-roster metrics have different supports/definitions.',
                '48 months fit weights; later 34 months evaluate weights; some development months previously examined.',
                'No causal subgroup claims or response-level iid confidence intervals.',
                'Spearman follows the frozen ordinary-rank implementation; other primary aggregates use design weights.',
                'Centered W1 and variance decomposition are evaluation diagnostics, not corrected predictions.',
                'Single generation; repair attempts are not representative repeats; no identified LLM sampling variance.'])
    out.mkdir(parents=True);dump(out/'summary.json',result)
    with (out/'monthly_national.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(national[0]));writer.writeheader();writer.writerows(national)
    files=[declaration,folder/'evaluation/summary.json',folder/'evaluation/cases_private.json',folder/'readout/summary.json',
        original/'evaluation/summary.json',original/'readout/summary.json',Path(__file__),ROOT/'scripts/analyze_sce_fullperiod_run.py']
    dump(out/'manifest.json',dict(source_sha256={str(p.relative_to(ROOT)):sha(p) for p in files},
         output_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()},new_api_calls=0))
    return dict(status=result['status'],output=str(out),frozen_metric_crosschecks=checks,new_api_calls=0)
