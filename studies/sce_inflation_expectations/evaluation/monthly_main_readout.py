"""All-response macro aggregation and frozen chronological convex combinations.

This module is evaluation-only. Macro model medians do not select people by
validity or values of their current human answers. Same-roster micro evaluation
remains in monthly_reconstruction and is reported separately.
"""
from pathlib import Path
import math

from .aggregate_blend import fit_weight,evaluate as blend_metrics
from .metrics import distribution_summary,compare_distributions,headline_errors,paired_month_mae_interval
from ..experiments.frozen_batch import ROOT,read_json,dump,sha
from ..experiments.state_continuity_execution import verify


def finite(x):return type(x) in (int,float) and math.isfinite(x)


def model_distribution(cases,field):
    key='mean' if field=='q9_mean' else 'point'
    rows=[r for r in cases if finite(r['survey_weight']) and r['survey_weight']>0
          and finite(r['arms']['monthly_reconstruction'][key])]
    if not rows:raise ValueError('No usable model aggregate; never silently drop a month')
    return [r['arms']['monthly_reconstruction'][key] for r in rows],[r['survey_weight'] for r in rows]


def chronological_blend(rows,fit_bounds,test_bounds):
    train=[r for r in rows if fit_bounds[0]<=r['month']<=fit_bounds[1]]
    test=[r for r in rows if test_bounds[0]<=r['month']<=test_bounds[1]]
    if not train or not test or max(r['month'] for r in train)>=min(r['month'] for r in test):
        raise ValueError('Nonempty disjoint chronological fit/evaluation scope required')
    result={}
    for loss in ('mae','mse'):
        a=fit_weight([r['truth_pp'] for r in train],[r['anchor_pp'] for r in train],[r['sim_pp'] for r in train],loss)
        error=[r['anchor_pp']+a*(r['sim_pp']-r['anchor_pp'])-r['truth_pp'] for r in test]
        carry=[r['anchor_pp']-r['truth_pp'] for r in test]
        result[loss]=dict(simulation_weight=a,history_weight=1-a,fit_months=[r['month'] for r in train],
            evaluation_months=[r['month'] for r in test],evaluation=blend_metrics(test,a),
            persistence=blend_metrics(test,0.),pure_simulation=blend_metrics(test,1.),
            paired_month_mae_interval=paired_month_mae_interval(error,carry,block_length=min(6,len(test)),seed=20261023))
    return result


def run(package,evaluation,truth,registry,out):
    package,evaluation,truth,registry,out=map(lambda x:Path(x).resolve(),(package,evaluation,truth,registry,out))
    p,m=verify(package)
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored aggregate readout directory required')
    tm=read_json(truth/'manifest.json');rm=read_json(registry/'manifest.json')
    if tm['protocol_sha256']!=m['protocol_sha256'] or sha(truth/'full_wave_private.json')!=tm['full_wave_sha256']:
        raise ValueError('Frozen truth provenance mismatch')
    if sha(registry/'past_public_headlines.json')!=rm['registry_sha256']:raise ValueError('National baseline registry changed')
    for f,h in rm['source_sha256'].items():
        if sha(ROOT/f)!=h:raise ValueError('National source changed: '+f)
    evaluated=read_json(evaluation/'summary.json')
    if evaluated['status']!='completed' or evaluated['receipt']['protocol_sha256']!=m['protocol_sha256']:
        raise ValueError('Completed actual-model evaluation required')
    cases=read_json(evaluation/'cases_private.json');full=read_json(truth/'full_wave_private.json')
    prep=read_json(ROOT/p['preparation']/'summary.json');before={r['month']:r['references'] for r in prep['months']}
    baselines={r['month']:r for r in read_json(registry/'past_public_headlines.json')}
    catalog=ROOT/'data/evaluation/sce_baselines_latest_20261007/aggregate_inputs.json'
    releases={r['reference_period']:r for r in read_json(catalog)['headline_releases']}
    rows=[];national=[]
    for month in p['months']:
        group=[r for r in cases if r['month']==int(month)];wave=full[month]
        result=dict(month=month,selected_n=len(group),whole_wave_n=len(wave),fields={})
        for field,prior in [('q9_mean','q9'),('q8_point','q8')]:
            x,w=model_distribution(group,field)
            human=[r for r in wave if finite(r[field]) and finite(r['weight']) and r['weight']>0]
            y,wy=[r[field] for r in human],[r['weight'] for r in human]
            result['fields'][field]=compare_distributions(x,w,y,wy)
            result['fields'][field]['previous_full_micro_median_pp']=before[month][prior]['past_reference']['median_pp']
        official=releases[month[:4]+'-'+month[-2:]]
        lag=baselines[month]
        cutoff=read_json(ROOT/p['delivery']/month/'environment.json')['provider_args']['targets'][0]['as_of']
        if cutoff!=lag['information_as_of']:raise ValueError('National baseline cutoff differs from model E')
        if sha(ROOT/official['source_file'])!=official['source_sha256']:raise ValueError('National target archive changed')
        row=dict(month=month[:4]+'-'+month[-2:],sim_pp=result['fields']['q9_mean']['simulated']['median_pp'],
            anchor_pp=lag['last_eligible_public_headline']['value_pp'],truth_pp=official['value_pp'],
            anchor_reference=lag['last_eligible_public_headline']['reference_period'],
            anchor_published_date=lag['last_eligible_public_headline']['published_date'],
            truth_published_date=official['published_date'])
        national.append(row);rows.append(result)
    full_metrics={}
    for field in ('q9_mean','q8_point'):
        observed=[r['fields'][field]['observed']['median_pp'] for r in rows]
        predicted=[r['fields'][field]['simulated']['median_pp'] for r in rows]
        previous=[r['fields'][field]['previous_full_micro_median_pp'] for r in rows]
        full_metrics[field]=dict(model=headline_errors(predicted,observed),
                                copy_previous_full_micro=headline_errors(previous,observed))
    combo=p['macro_combination']
    result=dict(status='completed_actual_model_three_level_readout',new_api_calls=0,
        protocol_sha256=m['protocol_sha256'],monthly=rows,full_wave_center_errors=full_metrics,
        official_national=dict(monthly=national,model=blend_metrics(national,1.),
            persistence=blend_metrics(national,0.),chronological_combinations=chronological_blend(national,combo['fit_months'],combo['evaluation_months'])),
        same_roster_evaluation=str((evaluation/'summary.json').relative_to(ROOT)),
        source_sha256={str(f.relative_to(ROOT)):sha(f) for f in [package/'protocol.json',evaluation/'summary.json',
            evaluation/'cases_private.json',truth/'full_wave_private.json',registry/'manifest.json',catalog,Path(__file__)]},
        limits=['Macro predictions aggregate all usable model fields without selecting by current human-answer validity.',
                'Same-roster micro, full-wave reconstruction and published national headline have distinct supports/definitions.',
                'Previously examined development months are not a blind test; no retrospective parameter changes.',
                'Monthly block intervals are retrospective uncertainty conditional on this pipeline, not proof of future performance.',
                'No target-month human value or national target is a live-model input.'])
    out.mkdir(parents=True);dump(out/'summary.json',result)
    return dict(status=result['status'],months=len(rows),new_api_calls=0)
