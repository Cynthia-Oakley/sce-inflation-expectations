"""Cached nine-cell household diagnostics and Q8-only raw response recovery.

Never imports a simulator, Q9 scorer, provider, or credential reader.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import math

import numpy as np

from .metrics import quantile, wasserstein1
from .response_gap import (MONTHS, REPEATS, MIN_CELL_N, prepare_pairs,
                           summarize_slice, _scope_slice, _mean_metrics,
                           reconcile, ess, finite)

ROOT=Path(__file__).resolve().parents[3]
AGES=('Under 40','40 to 60','Over 60')
EDUCATION=('high_school','some_college','college')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path,obj):
    Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def grid_key(row):
    p=row['profile'];a=p.get('age_group');e=p.get('education_group')
    return a+'|'+e if a in AGES and e in EDUCATION else 'unclassified'


def variance_parts(values,weights,groups):
    """Exact weighted ANOVA identity; weights within every source month sum to 1."""
    v=np.asarray(values,float);w=np.asarray(weights,float)
    if not len(v) or len(v)!=len(groups) or v.shape!=w.shape or not np.isfinite(v).all() or not np.isfinite(w).all() or np.any(w<=0):
        raise ValueError('Finite values and positive matching weights required')
    w=w/w.sum();mean=float(w@v);between=within=0.;parts={}
    for group in sorted(set(groups)):
        mask=np.array([g==group for g in groups]);mass=float(w[mask].sum());ww=w[mask]/mass
        gm=float(ww@v[mask]);gv=float(ww@((v[mask]-gm)**2))
        within+=mass*gv;between+=mass*(gm-mean)**2
        parts[group]={'weight_share':mass,'mean_pp':gm,'within_variance_pp2':gv}
    total=float(w@((v-mean)**2))
    if not np.isclose(total,within+between,atol=1e-9,rtol=1e-10):raise ValueError('Variance identity failed')
    return {'total_variance_pp2':total,'within_grid_variance_pp2':within,
            'between_grid_variance_pp2':between,'identity_residual_pp2':total-within-between,
            'groups':parts}


def persistence(rows):
    w=np.asarray([r['design_survey_weight'] for r in rows]);w=w/w.sum()
    old=np.asarray([r['prior_mean_pp'] for r in rows]);old=old-float(w@old);vp=float(w@(old**2))
    truth=np.asarray([r['truth_mean_pp'] for r in rows]);truth-=float(w@truth)
    model_cov=[]
    for rep in REPEATS:
        pred=np.asarray([r['model_repeats'][str(rep)]['mean'] for r in rows]);pred-=float(w@pred)
        model_cov.append(float(w@(old*pred)))
    tc=float(w@(old*truth));mc=float(np.mean(model_cov))
    return {'prior_variance_pp2':vp,'truth_prior_covariance_pp2':tc,'model_prior_covariance_pp2':mc,
            'truth_on_prior_slope':tc/vp if vp>1e-12 else None,
            'model_on_prior_slope':mc/vp if vp>1e-12 else None}


def cell(rows,month):
    result=dict(month=month,**summarize_slice(rows))
    result['support']='sparse' if result['suppressed'] else ('weak' if result['ess']<10 else 'strong')
    if result['suppressed']:return result
    valid=[r for r in rows if r['paired_eligible']];w=[r['design_survey_weight'] for r in valid]
    y=[r['truth_mean_pp'] for r in valid];yc=np.asarray(y)-quantile(y,w,.5)
    for rep_obj in result['model_repeat_cells']:
        pred=[r['model_repeats'][str(rep_obj['repeat'])]['mean'] for r in valid]
        rep_obj['metrics']['centered_w1_pp']=wasserstein1(np.asarray(pred)-quantile(pred,w,.5),w,yc,w)
    result['model_average_of_repeat_metrics']=_mean_metrics([r['metrics'] for r in result['model_repeat_cells']])
    old=[r['prior_mean_pp'] for r in valid]
    result['copy_previous']['centered_w1_pp']=wasserstein1(np.asarray(old)-quantile(old,w,.5),w,yc,w)
    result['persistence']=persistence(valid)
    return result


def grid_analysis(cases,source_summary):
    pairs=prepare_pairs(cases,months=MONTHS,n_per_month=192)
    allcells=[cell([r for r in pairs if r['month']==m],m) for m in MONTHS]
    check=reconcile(allcells,source_summary)
    if not check['passed']:raise ValueError('Main reference metrics differ')
    grids={}
    for a in AGES:
        for e in EDUCATION:
            key=a+'|'+e;monthly=[cell([r for r in pairs if r['month']==m and grid_key(r)==key],m) for m in MONTHS]
            strong=[{**c,'suppressed':c['support']!='strong'} for c in monthly]
            slopes=[c['persistence'] for c in monthly if c['support']=='strong']
            denom=sum(c['prior_variance_pp2'] for c in slopes)
            grids[key]={'age':a,'education':e,'monthly':monthly,
                'reportable_scope':_scope_slice(monthly,MONTHS),'strong_scope':_scope_slice(strong,MONTHS),
                'support_counts':dict(Counter(c['support'] for c in monthly)),
                'minimum_assigned_n':min(c['n_assigned'] for c in monthly),
                'maximum_assigned_n':max(c['n_assigned'] for c in monthly),
                'n_common_person_months':sum(c['n'] for c in monthly),
                'persistence_strong_cells':{'months':[c['month'] for c in monthly if c['support']=='strong'],
                    'truth_on_prior_slope':sum(c['truth_prior_covariance_pp2'] for c in slopes)/denom if denom>1e-12 else None,
                    'model_on_prior_slope':sum(c['model_prior_covariance_pp2'] for c in slopes)/denom if denom>1e-12 else None}}
    decomposition=[]
    for m in MONTHS:
        rows=[r for r in pairs if r['month']==m and r['paired_eligible']]
        groups=[grid_key(r) for r in rows];w=[r['design_survey_weight'] for r in rows]
        real=variance_parts([r['truth_mean_pp'] for r in rows],w,groups)
        models=[variance_parts([r['model_repeats'][str(rep)]['mean'] for r in rows],w,groups) for rep in REPEATS]
        fields=('total_variance_pp2','within_grid_variance_pp2','between_grid_variance_pp2')
        model={k:float(np.mean([v[k] for v in models])) for k in fields}
        loss={k:real[k]-model[k] for k in fields}
        decomposition.append({'month':m,'truth':{k:real[k] for k in fields},'model':model,'truth_minus_model':loss,
                              'unclassified_weight_share':real['groups'].get('unclassified',{}).get('weight_share',0)})
    meanparts={arm:_mean_metrics([c[arm] for c in decomposition]) for arm in ['truth','model','truth_minus_model']}
    deficit=meanparts['truth_minus_model']['total_variance_pp2']
    meanparts['within_share_of_variance_deficit']=meanparts['truth_minus_model']['within_grid_variance_pp2']/deficit if deficit>0 else None
    return {'status':'completed_cached_household_grid_diagnostic','date_beijing':'2026-10-19','new_api_calls':0,'new_q9_fits':0,
        'months':list(MONTHS),'assigned_person_months':len(pairs),'common_person_months':sum(r['paired_eligible'] for r in pairs),
        'unclassified_assigned_person_months':sum(grid_key(r)=='unclassified' for r in pairs),
        'unclassified_common_person_months':sum(grid_key(r)=='unclassified' and r['paired_eligible'] for r in pairs),
        'grid_definitions':{'ages':list(AGES),'education':list(EDUCATION),'n_min':10,'ess_strong_min':10},
        'overall':_scope_slice(allcells,MONTHS),'grids':grids,
        'variance_decomposition':{'monthly':decomposition,'equal_month_means':meanparts,
            'interpretation':'Exact weighted variance identity, including unknown grid. Not a decomposition of MAE, IQR or causal effects.'},
        'reconciliation':check,'limitations':['Already inspected development months; no independent validation.',
          'Returner conditional reconstruction with true personal priors, not nationwide or B recursive forecasts.',
          'n<10 suppresses metrics; ESS<10 weak support. Scope means compare only identical reportable months.',
          'Persistence slopes are within-month/grid descriptive associations, not structural learning weights.',
          'Two generations computed separately before averaging; neither synthetic Normal nor repeated output adds independent people.']}


def point_from_raw(text,arm,previous):
    """Recover Q8 alone even if Q9 is absent, invalid or non-additive."""
    candidate=(text or '').strip()
    if candidate.startswith('```'):
        candidate=candidate.strip('`').strip()
        if candidate.lower().startswith('json'):candidate=candidate[4:].strip()
    try:obj=json.loads(candidate)
    except ValueError:
        a,b=candidate.find('{'),candidate.rfind('}')
        if a<0 or b<=a:raise ValueError('No JSON object')
        obj=json.loads(candidate[a:b+1])
    if not isinstance(obj,dict):raise ValueError('Q8 object required')
    key='point_pct' if arm=='direct' or previous is None else 'point_revision_pp'
    wrong='point_revision_pp' if key=='point_pct' else 'point_pct'
    if wrong in obj:raise ValueError('Wrong Q8 branch')
    value=obj.get(key)
    if isinstance(value,bool):raise ValueError('Boolean point is invalid')
    try:value=float(value)
    except (TypeError,ValueError):raise ValueError('Missing or bad Q8 number')
    if not math.isfinite(value):raise ValueError('Nonfinite point')
    result=value if key=='point_pct' else float(Decimal(str(previous))+Decimal(str(value)))
    if not math.isfinite(result):raise ValueError('Nonfinite reconstructed point')
    return result


def point_metrics(rows,arm,weighted):
    raw_w=np.array([r['survey_weight'] if weighted else 1 for r in rows],float);w=raw_w/raw_w.sum()
    pred=np.array([r[arm] for r in rows]);truth=np.array([r['truth'] for r in rows])
    out={'n':len(rows),'ess':ess(raw_w),'center_pp':quantile(pred,raw_w,.5),'truth_center_pp':quantile(truth,raw_w,.5),
         'center_mae_pp':abs(quantile(pred,raw_w,.5)-quantile(truth,raw_w,.5)),
         'personal_mae_pp':float(w@abs(pred-truth)),
         'personal_rmse_pp':float(np.sqrt(w@((pred-truth)**2))),
         'w1_pp':wasserstein1(pred,raw_w,truth,raw_w),'iqr_pp':quantile(pred,raw_w,.75)-quantile(pred,raw_w,.25),
         'truth_iqr_pp':quantile(truth,raw_w,.75)-quantile(truth,raw_w,.25)}
    if all(finite(r['previous']) for r in rows):
        prior=np.array([r['previous'] for r in rows]);dp,dy=pred-prior,truth-prior
        out.update(delta_w1_pp=wasserstein1(dp,raw_w,dy,raw_w),abs_update_mean_pp=float(w@abs(dp)),
                   truth_abs_update_mean_pp=float(w@abs(dy)),stable_share=float(w@(abs(dp)<=.5)),truth_stable_share=float(w@(abs(dy)<=.5)))
    return out


def q8_summary(rows):
    scopes={}
    for name,predicate,arms in [
        ('q8_only_common',lambda r:finite(r['truth']) and all(finite(r[a]) for a in ['direct','revision']),['direct','revision']),
        ('q8_with_prior_common',lambda r:finite(r['truth']) and all(finite(r[a]) for a in ['direct','revision','previous']),['direct','revision','previous']),
        ('old_q9_common',lambda r:r['old_q9_common'] and finite(r['truth']) and all(finite(r[a]) for a in ['direct','revision']),['direct','revision'])]:
        chosen=[r for r in rows if predicate(r)];modes={}
        for mode,weighted in [('equal_people',False),('survey_weighted_auxiliary',True)]:
            cells=[]
            for m in sorted({r['month'] for r in rows}):
                for rep in REPEATS:
                    rr=[r for r in chosen if r['month']==m and r['repeat']==rep]
                    cells.append({'month':m,'repeat':rep,'n':len(rr),'metrics':{a:point_metrics(rr,a,weighted) for a in arms} if rr else {}})
            modes[mode]={'cells':cells,'metrics':{a:_mean_metrics([c['metrics'][a] for c in cells if a in c['metrics']]) for a in arms},
                         'covered_month_repeat_cells':sum(bool(c['metrics']) for c in cells),'planned_month_repeat_cells':len(cells)}
        scopes[name]={'generation_rows':len(chosen),'person_months':len({(r['month'],r['agent_id']) for r in chosen}),**modes}
    return scopes


def q8_analysis(folder,evaluation):
    folder=Path(folder);evaluation=Path(evaluation);manifest=json.loads((folder/'manifest.json').read_text())
    protocol=json.loads((folder/'protocol.json').read_text());cases=json.loads((evaluation/'cases_private.json').read_text())
    if sha(folder/'protocol.json')!=manifest['protocol_sha256']:raise ValueError('Protocol changed')
    records={(r['month'],r['repeat'],r['agent_id']):{
        'month':r['month'],'repeat':r['repeat'],'agent_id':r['agent_id'],'truth':r['actual_point'],
        'previous':r['previous_point'],'survey_weight':r['survey_weight'],'old_q9_common':r['common'],
        'direct':None,'revision':None,'direct_error':None,'revision_error':None} for r in cases}
    original={(r['month'],r['repeat'],r['agent_id']):r for r in cases}
    sources={str((folder/'manifest.json').relative_to(ROOT)):sha(folder/'manifest.json'),
             str((evaluation/'cases_private.json').relative_to(ROOT)):sha(evaluation/'cases_private.json')}
    coverage=Counter();seen=set();matched=0
    for job in manifest['jobs']:
        log=ROOT/'outputs/local_runs'/job['run_id']/'llm_calls.jsonl';sources[str(log.relative_to(ROOT))]=sha(log)
        calls=[json.loads(t) for t in log.read_text().splitlines()]
        if len(calls)!=protocol['n_per_month']:raise ValueError('Call count mismatch')
        for c in calls:
            key=(job['month'],job['repeat'],c['agent_id']);identity=(*key,job['arm'])
            if identity in seen:raise ValueError('Duplicate call')
            seen.add(identity);row=records[key];raw=c.get('raw_response_text') or ''
            if hashlib.sha256(raw.encode()).hexdigest()!=c['raw_response_sha256']:raise ValueError('Raw hash drift')
            try:
                value=point_from_raw(raw,job['arm'],row['previous'])
            except (ValueError,TypeError,KeyError,OverflowError) as exc:
                row[job['arm']+'_error']=str(exc);coverage[job['arm']+':q8_invalid']+=1
                continue
            row[job['arm']]=round(value,4);coverage[job['arm']+':q8_valid']+=1
            old=original[key][job['arm']+'_point']
            if finite(old):
                if abs(value-old)>0.000051:raise ValueError('Previously valid Q8 differs')
                matched+=1
            else:coverage[job['arm']+':q8_recovered_despite_joint_invalid']+=1
    if len(seen)!=protocol['planned_calls']:raise ValueError('Assigned calls incomplete')
    rows=list(records.values())
    scopes=q8_summary(rows)
    old_summary=json.loads((evaluation/'summary.json').read_text())
    for arm in ['direct','revision']:
        actual=scopes['old_q9_common']['equal_people']['metrics'][arm]['center_mae_pp']
        expected=old_summary['results'][arm]['aggregate']['q8_sample_center_mae_pp']
        if not np.isclose(actual,expected,atol=1e-8,rtol=0):raise ValueError('Old Q8 subset convention differs')
    summary={'status':'completed_q8_only_cached_revision_recovery','date_beijing':'2026-10-19','new_api_calls':0,'new_q9_fits':0,
        'assigned_generation_rows':len(rows),'planned_original_calls':protocol['planned_calls'],'coverage':dict(coverage),
        'missing_previous_q8_person_months':len({(r['month'],r['agent_id']) for r in rows if r['previous'] is None}),
        'previously_valid_point_values_matched':matched,'old_q9_subset_metrics_reconciled':True,
        'point_precision':'round 4 decimals, same as archived runtime action; raw source hashes retained',
        'scopes':scopes,'source_sha256':sources,
        'limitations':['Original prompts changed both Q8 and Q9. This recovers Q8 evidence; it does not isolate Q8-only intervention.',
            'Four previously inspected development months, 24 people each, two generations; not new independent validation.',
            'Equal-person primary convention retained from old pilot, survey-weighted auxiliary shown separately; not nationwide.',
            'Point changes and negative absolute inflation are legal finite Q8 values; no probability repair or normalization.']}
    return summary,rows


def run(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh private output directory required')
    source=ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1'
    grid=grid_analysis(json.loads((source/'cases_private.json').read_text()),json.loads((source/'summary.json').read_text()))
    grid['source_sha256']={str((source/f).relative_to(ROOT)):sha(source/f) for f in ['cases_private.json','summary.json']}
    q8,rows=q8_analysis(ROOT/'outputs/sce_revision_format_trial_20261015_v1',ROOT/'outputs/sce_revision_format_evaluation_20261015_v1')
    out.mkdir(parents=True);dump(out/'grid_summary.json',grid);dump(out/'q8_summary.json',q8);dump(out/'q8_recovered_private.json',rows)
    dump(out/'receipt.json',{'completed_at_utc':datetime.now(timezone.utc).isoformat(),'new_api_calls':0,'new_q9_fits':0,
         'grid_module_sha256':sha(Path(__file__)),'reconciliation_passed':grid['reconciliation']['passed']})
    return grid,q8
