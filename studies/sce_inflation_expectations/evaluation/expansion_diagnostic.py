"""Offline diagnostics and finite-population sampling for the next SCE pilot.

Official microdata means are used for large-scale sampling; frozen fitted means
remain the separate measure for saved LLM comparisons. No simulation imports.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from .behavior_comparison import dump, sha
from .metrics import quantile, wasserstein1
from ..belief_dynamics.data import load_reference_frame, legal_bins_mask, previous_calendar_month

ARMS = ('own_previous', 'own_state', 'own_state_guided', 'copy_previous', 'history_anchor_half')
SIZES = (12, 24, 48, 96, 192)
REPEATS = 200
SEED = 20261014


def covariance_parts(previous, current):
    """Exact descriptive Var(y)=Var(p)+Var(y-p)+2Cov(p,y-p)."""
    p, y = np.asarray(previous, float), np.asarray(current, float)
    if len(p) != len(y) or len(p) < 2 or not np.isfinite(p).all() or not np.isfinite(y).all():
        raise ValueError('Need matched finite values')
    pc, yc = p-p.mean(), y-y.mean()
    d = y-p
    vp, vy, vd = float(np.mean(pc**2)), float(np.mean(yc**2)), float(np.var(d))
    cov = float(np.mean(pc*(d-d.mean())))
    retention = float(np.mean(pc*yc)/vp) if vp > 0 else None
    explained = retention**2*vp if retention is not None else 0.0
    residual = float(np.mean((yc-(retention or 0)*pc)**2))
    return dict(previous_variance=vp, current_variance=vy, update_variance=vd,
                twice_previous_update_covariance=2*cov,
                identity_error=vy-(vp+vd+2*cov), descriptive_retention_slope=retention,
                lag_associated_variance=explained, residual_variance=residual,
                projection_identity_error=vy-explained-residual,
                mean_update=float(d.mean()), mean_abs_update=float(np.abs(d).mean()))


def curve_summary(values):
    a = np.asarray(values, float)
    return dict(mean=float(a.mean()), median=float(np.median(a)), p90=float(np.quantile(a,.9)))


def sample_metrics_sorted(x, population_weights, indexes, weighted):
    """Exact W1 against this same sorted finite pool, including ties."""
    w = np.asarray(population_weights if weighted else np.ones(len(x)), float)
    full = w/w.sum()
    selected = np.zeros(len(x)); selected[indexes] = w[indexes]
    selected /= selected.sum()
    fullcdf, samplecdf = np.cumsum(full), np.cumsum(selected)
    def qs(cdf, q):
        return float(x[min(np.searchsorted(cdf, q, side='left'), len(x)-1)])
    median_error = abs(qs(samplecdf,.5)-qs(fullcdf,.5))
    iqr_error = abs((qs(samplecdf,.75)-qs(samplecdf,.25))-(qs(fullcdf,.75)-qs(fullcdf,.25)))
    w1 = float(np.dot(np.diff(x), np.abs(samplecdf[:-1]-fullcdf[:-1])))
    return dict(center_error_pp=median_error, w1_pp=w1, iqr_error_pp=iqr_error)


def diagnostic_cells(rows):
    output = []
    for month in sorted({r['month'] for r in rows}):
        for repeat in (1,2):
            group = [r for r in rows if r['month']==month and r['repeat']==repeat
                     and all(r['Q9'].get(k) is not None for k in ('real','previous',*ARMS))]
            p = np.array([r['Q9']['previous'] for r in group])
            real = np.array([r['Q9']['real'] for r in group])
            shift = abs(quantile(real,None,.5)-quantile(p,None,.5))
            for arm in ('real',*ARMS):
                y = np.array([r['Q9'][arm] for r in group])
                output.append(dict(month=month, repeat=repeat, condition=arm, n=len(y),
                    **covariance_parts(p,y), center=quantile(y,None,.5),
                    real_center=quantile(real,None,.5), center_abs_error_pp=abs(quantile(y,None,.5)-quantile(real,None,.5)),
                    cross_iqr=quantile(y,None,.75)-quantile(y,None,.25),
                    cross_w1_pp=wasserstein1(y,None,real,None),
                    centered_w1_pp=wasserstein1(y-quantile(y,None,.5),None,real-quantile(real,None,.5),None),
                    cohort_center_movement_pp=shift,
                    movement_group='small' if shift<=.25 else 'medium' if shift<=.75 else 'large'))
    return output


def valid_population_pools(reference):
    # Only current weights define the current-wave pool. A zero/missing previous
    # survey weight does not invalidate an otherwise legal previous answer.
    base = reference[legal_bins_mask(reference) & np.isfinite(reference.Q9_mean)].copy()
    f = base[np.isfinite(base.weight) & (base.weight>0)].copy()
    f['previous_date'] = f.date.map(previous_calendar_month)
    prev = base[['userid','date','Q9_mean']].rename(columns={'date':'previous_date','Q9_mean':'previous_mean'})
    pool = f.merge(prev,on=['userid','previous_date'],how='inner',validate='one_to_one')
    return f,pool


def long_population(reference, out, draws=REPEATS):
    f,pool = valid_population_pools(reference)
    rng = np.random.default_rng(SEED)
    month_rows, samples, baseline_rows = [], [], []
    full_groups = {int(m):g for m,g in f.groupby('date')}
    for month,g in pool.groupby('date'):
        month=int(month)
        whole=full_groups[month]
        g=g.sort_values('Q9_mean')
        x,w=g.Q9_mean.to_numpy(float),g.weight.to_numpy(float)
        wholex,wholew=whole.Q9_mean.to_numpy(float),whole.weight.to_numpy(float)
        full_median=quantile(wholex,wholew,.5)
        pooled_median=quantile(x,w,.5)
        month_rows.append(dict(month=month,full_n=len(whole),returner_n=len(g),
            full_weighted_median=full_median,returner_weighted_median=pooled_median,
            returner_median_gap_pp=abs(pooled_median-full_median),
            returner_full_w1_pp=wasserstein1(x,w,wholex,wholew),
            returner_weighted_iqr=quantile(x,w,.75)-quantile(x,w,.25)))
        last=full_groups.get(previous_calendar_month(month))
        if last is not None:
            last_median=quantile(last.Q9_mean.to_numpy(float),last.weight.to_numpy(float),.5)
            shift=full_median-last_median
            baseline_rows.append(dict(month=month, full_median=full_median,
                previous_full_median=last_median, headline_style_copy_abs_error_pp=abs(shift),
                signed_movement_pp=shift,
                movement_group='small' if abs(shift)<=.25 else 'medium' if abs(shift)<=.75 else 'large',
                matched_returner_copy_center_error_pp=abs(quantile(g.previous_mean.to_numpy(float),w,.5)-pooled_median),
                matched_returner_copy_w1_pp=wasserstein1(g.previous_mean.to_numpy(float),w,x,w)))
        for n in SIZES:
            if n>len(g): continue
            for draw in range(draws):
                indexes=rng.choice(len(g),size=n,replace=False)
                for weighted in (False,True):
                    samples.append(dict(month=month,n=n,draw=draw,weighting='survey_weight' if weighted else 'equal',
                                        **sample_metrics_sorted(x,w,indexes,weighted)))
    sample_frame=pd.DataFrame(samples)
    sample_frame.to_parquet(out/'sampling_draws_aggregate.parquet',index=False)
    curves=[]
    for (weighting,n),g in sample_frame.groupby(['weighting','n']):
        m=g.groupby('month').center_error_pp.mean()
        curves.append(dict(weighting=weighting,n=int(n),months=int(g.month.nunique()),
            draws_per_month=draws,**{k:curve_summary(g[k]) for k in ('center_error_pp','w1_pp','iqr_error_pp')},
            fraction_months_mean_center_error_le_half_pp=float((m<=.5).mean())))
    groups=[]
    for key in ('small','medium','large'):
        g=[r for r in baseline_rows if r['movement_group']==key]
        if g: groups.append(dict(movement_group=key,n_months=len(g),
            copy_center_mae_pp=float(np.mean([r['headline_style_copy_abs_error_pp'] for r in g]))))
    return dict(months=len(month_rows),valid_full_rows=len(f),returner_rows=len(pool),
        monthly_population=month_rows,monthly_baselines=baseline_rows,movement_groups=groups,sampling_curves=curves)


def run(root: Path, out: Path, draws=REPEATS):
    if out.exists(): raise FileExistsError('Use a new output directory')
    out.mkdir(parents=True)
    source=root/'outputs/sce_behavior_comparison_u1_20261014_v1'
    manifest=json.loads((source/'manifest.json').read_text())
    for name in ('evaluation_rows_private.json','summary.json'):
        if sha(source/name)!=manifest['files_sha256'][name]: raise ValueError('Frozen U1 input changed')
    rows=json.loads((source/'evaluation_rows_private.json').read_text())
    cells=diagnostic_cells(rows)
    conditions=[]
    for arm in ('real',*ARMS):
        g=[r for r in cells if r['condition']==arm]
        fields=('current_variance','previous_variance','update_variance','twice_previous_update_covariance',
                'descriptive_retention_slope','lag_associated_variance','residual_variance',
                'mean_abs_update','cross_iqr','center_abs_error_pp','cross_w1_pp','centered_w1_pp')
        conditions.append(dict(condition=arm,**{k:float(np.mean([r[k] for r in g])) for k in fields}))
    reference=load_reference_frame()
    long=long_population(reference,out,draws)
    result=dict(version='sce-expansion-diagnostic-v2',new_api_calls=0,new_cost_usd=0,
        seed=SEED,sizes=SIZES,draws_per_month=draws,
        small_sample_measure='frozen Q9 fitted mean, equal person weights, equal month-repeat cells',
        population_measure='official microdata Q9_mean; distinct from frozen small-cohort score and published headline',
        source_sha256={str((source/'evaluation_rows_private.json').relative_to(root)):sha(source/'evaluation_rows_private.json'),
                       'outputs/sce_age_reporting_audit_20261012_v1/reference_private.parquet':sha(root/'outputs/sce_age_reporting_audit_20261012_v1/reference_private.parquet')},
        unique_people=len({r['userid'] for r in rows}),cells=cells,conditions=conditions,**long,
        limits=['Exploratory fixed-month description, not causal decomposition or national simulation validation.',
                'Variance identity includes covariance; fitted lag association is not a structural updating coefficient.',
                'Sampling exercise estimates finite-pool subsample instability, not effect power or official design uncertainty.',
                'Repeat generations are not independent human subjects. Returner pools exclude first-time respondents.',
                'Movement classes use outcome changes only for retrospective evaluation; not future-input features.'])
    dump(out/'summary.json',result)
    dump(out/'manifest.json',dict(files_sha256={'summary.json':sha(out/'summary.json'),
        'sampling_draws_aggregate.parquet':sha(out/'sampling_draws_aggregate.parquet')},
        implementation_sha256=sha(Path(__file__)),new_api_calls=0))
    return result
