"""Evaluation-only monthly adapter over frozen queue output and existing metrics.

The live process never imports this module or opens current questionnaire
answers. No new scoring rule or fitted correction is introduced here.
"""
from collections import Counter,defaultdict
from copy import deepcopy
from pathlib import Path
import json

import pandas as pd

from . import cognition as shared
from .state_continuity import score,field_view,assemble_cases
from .metrics import distribution_summary,headline_errors,quantile,wasserstein1
from ..experiments.frozen_batch import ROOT,dump,read_json,sha
from ..experiments.state_continuity_execution import verify,load_inputs
from ..experiments.state_continuity_inputs import FRAME,BINS,anonymous_id,finite_point
from ..prior_belief_preparation import valid_bins
from ..scoring.sce_q9_frozen import provenance

ARM='monthly_reconstruction'
DEFAULT_WEIGHT='raw survey weight / actual within-cell SRS inclusion probability'


def weight_definition(protocol):
    if protocol.get('primary_weight')=='poststratified_weight':
        return 'Within-cell w/pi calibrated to full positive-weight frame cell mass; primary weighted empirical-CDF statistics'
    return DEFAULT_WEIGHT


def read_score_cache(folder):
    folder=Path(folder).resolve();receipt=read_json(folder/'cache_receipt.json')
    if receipt['cache_sha256']!=sha(folder/'scoring_cache_private.json') or receipt['scorer']!=provenance():
        raise ValueError('Incompatible or changed frozen Q9 cache')
    result={}
    for r in read_json(folder/'scoring_cache_private.json'):
        key=tuple(r['bins'])
        if key in result or not valid_bins(list(key)): raise ValueError('Duplicate/invalid frozen cache vector')
        result[key]=r['score']
    return result


def _fit_vector(bins):
    return bins,shared._score_bins(list(bins))


def install_score_cache(fitted):
    """Reuse exact frozen mean/IQR results in the existing case assembler."""
    from . import state_continuity
    original=state_continuity.score
    def cached(bins):
        return fitted[bins] if bins in fitted else original(bins)
    state_continuity.score=cached


def prepare_truth(package,out,*,score_cache=None):
    package,out=Path(package).resolve(),Path(out).resolve();p,m=verify(package)
    if p['mechanism']!='monthly_reconstruction_v1' or out.exists(): raise ValueError('Fresh monthly truth folder required')
    preparation=ROOT/p['preparation'];chosen=read_json(preparation/'selected_private.json')
    # Explicit current-outcome projection, exclusively in the evaluation layer.
    raw=pd.read_parquet(FRAME,columns=['date','userid','weight','Q8v2part2',*BINS])
    initial=load_inputs(ROOT/p['input_templates'],p['months'])
    # Fit each unique questionnaire vector once, using independent CPU workers.
    # This changes throughput, not the frozen estimator or its parameters.
    from concurrent.futures import ProcessPoolExecutor
    import multiprocessing,os
    vectors={tuple(float(v) for v in row) for row in raw.loc[raw.date.isin([int(v) for v in p['months']]),BINS].itertuples(index=False,name=None)
             if valid_bins(list(row))}
    vectors.update(tuple(v[1]['fields']['q9']['value']) for v in initial.values())
    fitted=read_score_cache(score_cache) if score_cache is not None else {}
    missing=sorted(vectors-set(fitted))
    if missing:
        with ProcessPoolExecutor(max_workers=min(8,os.cpu_count() or 1),mp_context=multiprocessing.get_context('fork')) as pool:
            fitted.update(pool.map(_fit_vector,missing,chunksize=32))
    out.mkdir(parents=True)
    dump(out/'scoring_cache_private.json',[dict(bins=list(bins),score=result) for bins,result in fitted.items()])
    dump(out/'cache_receipt.json',dict(cache_sha256=sha(out/'scoring_cache_private.json'),scorer=provenance(),
         reused_cache=str(Path(score_cache).resolve().relative_to(ROOT)) if score_cache is not None else None,
         reused_vectors=len(vectors)-len(missing),new_fits=len(missing),
         source_note='Exact frozen mean/IQR/zero-deflation lookup; no fitted correction or model answer'))
    install_score_cache(fitted)
    print(f'Cached {len(fitted)} frozen vectors; new fits {len(missing)}',flush=True)
    first=next(iter(chosen));population_path=ROOT/p['delivery']/first/'population_state_private.json'
    salt=read_json(population_path)['anon_salt']
    identity={anonymous_id(u,salt):int(u) for u in raw.userid.unique()}
    rows=[];full={}
    for month in p['months']:
        weights=read_json(preparation/f'{month}_weights_private.json')
        frame=raw.loc[raw.date.eq(int(month))];by_uid={int(r['userid']):r for r in frame.to_dict('records')}
        all_actual={}
        for uid,r in by_uid.items():
            bins=[float(r[k]) if shared.finite(r[k]) else None for k in BINS]
            actual=fitted[tuple(bins)] if valid_bins(bins) else dict(mean=None,iqr=None,zero_deflation=None)
            all_actual[uid]=dict(q9_mean=actual['mean'],q9_iqr=actual['iqr'],q9_zero_deflation=actual['zero_deflation'],
                                  q9_bins=bins if valid_bins(bins) else [],q8_point=finite_point(r['Q8v2part2']))
        full[month]=[dict(q9_mean=all_actual[u]['q9_mean'],q8_point=all_actual[u]['q8_point'],
                         weight=float(r['weight']) if shared.finite(r['weight']) and r['weight']>0 else None) for u,r in by_uid.items()]
        for item in chosen[month]:
            aid=item['persona']['agent_id'];uid=identity[aid];real=deepcopy(all_actual[uid])
            init=initial[month,aid][1];prior=field_view(init);fields=init['fields']
            def adjacent(key):
                from ..population.entry_initialization import month_index
                f=fields[key]
                return f['source_kind']=='own_observed' and month_index(month)-month_index(f['source_period'])==1
            a8,a9=adjacent('q8'),adjacent('q9')
            real.update(previous_q9_mean=prior['mean'] if a9 else None,previous_q9_bins=prior['q9_bins'] if a9 else [],
                        previous_q8_point=prior['point'] if a8 else None)
            w=weights[aid]
            rows.append(dict(month=int(month),agent_id=aid,real=real,survey_weight=w['analysis_weight'],
                  raw_survey_weight=w['raw_survey_weight'],inclusion_probability=w['inclusion_probability'],
                  monthly_past_reference=prior,genuinely_observed_previous_q9=a9,genuinely_observed_previous_q8=a8,
                  initial_q8_provenance=('own_adjacent' if a8 else 'own_older') if fields['q8']['source_kind']=='own_observed' else fields['q8']['source_kind'],
                  initial_q9_provenance=('own_adjacent' if a9 else 'own_older') if fields['q9']['source_kind']=='own_observed' else fields['q9']['source_kind'],
                  profile=item['persona']['attributes'],stratum=w['stratum']))
        print(month+': isolated current truth '+str(len(chosen[month])),flush=True)
    dump(out/'truth_private.json',rows);dump(out/'full_wave_private.json',full)
    dump(out/'manifest.json',dict(protocol_sha256=m['protocol_sha256'],truth_sha256=sha(out/'truth_private.json'),
        full_wave_sha256=sha(out/'full_wave_private.json'),source_sha256={str(FRAME.relative_to(ROOT)):sha(FRAME)},
        analysis_source_sha256={str(f.relative_to(ROOT)):sha(f) for f in [Path(__file__),
            Path(__file__).with_name('state_continuity.py'),Path(__file__).with_name('cognition.py'),
            Path(__file__).with_name('metrics.py'),Path(__file__).with_name('aggregate_blend.py'),
            Path(__file__).with_name('monthly_main_readout.py')]},
        scope='evaluation_only_never_live_input',scorer=provenance(),person_months=len(rows),new_api_calls=0,
        grid_version=p.get('grid_version'),weight_definition=weight_definition(p)))
    dump(out/'baseline_summary.json',baseline_summary(rows,p['months'],weight_definition=weight_definition(p)))
    dump(out/'sampling_offset_summary.json',sampling_offsets(rows,full))
    return dict(person_months=len(rows),new_api_calls=0)


def baseline_summary(truths,months,*,weight_definition=DEFAULT_WEIGHT):
    """Register the assigned-start baseline on exactly the fixed current roster."""
    identities={a:i for i,a in enumerate(sorted({r['agent_id'] for r in truths}))}
    cases=[dict(month=r['month'],repeat=1,userid=identities[r['agent_id']],survey_weight=r['survey_weight'],
                real=r['real'],arms={'retain_starting_state':r['monthly_past_reference']}) for r in truths
           if shared.finite(r['survey_weight']) and r['survey_weight']>0]
    return dict(status='baseline_only_no_new_model_answers',new_api_calls=0,
                selected_person_months=len(truths),weighted_person_months=len(cases),
                results=summarize(cases,[int(m) for m in months],['retain_starting_state'],weight_definition=weight_definition),
                note='Includes real and explicitly synthetic starting states; genuine-own-lag baseline is evaluated separately.')


def sampling_offsets(truths,full):
    """After outcome-blind selection: quantify human Core vs full-wave support."""
    monthly=[]
    for month,wave in sorted(full.items()):
        selected=[r for r in truths if str(r['month'])==month]
        result={'month':month,'selected_n':len(selected),'full_wave_n':len(wave)}
        for field in ('q9_mean','q8_point'):
            sample=[(r['real'][field],r['survey_weight']) for r in selected
                    if shared.finite(r['real'][field]) and shared.finite(r['survey_weight']) and r['survey_weight']>0]
            whole=[(r[field],r['weight']) for r in wave
                   if shared.finite(r[field]) and shared.finite(r['weight']) and r['weight']>0]
            if not sample or not whole:result[field]=None;continue
            sv,sw=zip(*sample);fv,fw=zip(*whole)
            s=distribution_summary(sv,sw);f=distribution_summary(fv,fw)
            result[field]=dict(selected=s,full_wave=f,median_offset_pp=s['median_pp']-f['median_pp'],
                               w1_pp=wasserstein1(sv,sw,fv,fw))
        monthly.append(result)
    return dict(status='human_sampling_diagnostic_not_model_performance',monthly=monthly,
        median_offset_errors={field:headline_errors([r[field]['median_offset_pp'] for r in monthly if r[field]],
                                                   [0.]*sum(bool(r[field]) for r in monthly))
                              for field in ('q9_mean','q8_point')},
        limits=['One fixed preselected roster; not a repeated-sampling confidence interval.',
                'Does not include LLM response error or stochastic generation variability.'])


def summarize(cases,months,arms,*,weight_definition=DEFAULT_WEIGHT):
    q9=shared._common_person_months(cases,arms,[1],'q9');q8=shared._common_person_months(cases,arms,[1],'q8')
    result={a:shared._summarize_arm(cases,a,months,[1],q9,q8) for a in arms}
    for v in result.values():
        v['auxiliary_survey_weighted']['weight_definition']=weight_definition
        for side in (v,v['auxiliary_survey_weighted']):
            biases=[c['q9_center_bias_pp'] for c in side['q9']['cells'] if shared.finite(c['q9_center_bias_pp'])]
            side['q9']['center_headline_errors']=headline_errors(biases,[0.]*len(biases)) if biases else None
    return dict(q9_person_months=len(q9),q8_person_months=len(q8),arms=result)


def support_by_month(cases,months):
    field_support={field:shared._common_person_months(cases,[ARM],[1],field) for field in ('q9','q8')}
    result=[]
    for m in months:
        rows=[r for r in cases if r['month']==m]
        w=[r['survey_weight'] for r in rows if shared.finite(r['survey_weight']) and r['survey_weight']>0]
        ess=sum(w)**2/sum(v*v for v in w) if w else 0.
        item=dict(month=m,selected_n=len(rows),weight_ess=ess)
        for field,support in field_support.items():
            valid=[r for r in rows if (r['month'],r['userid']) in support]
            vw=[r['survey_weight'] for r in valid if shared.finite(r['survey_weight']) and r['survey_weight']>0]
            item[field+'_valid_n']=len(valid)
            item[field+'_weight_ess']=sum(vw)**2/sum(v*v for v in vw) if vw else 0.
        item['descriptive_only']=any(item[f+'_valid_n']<20 or item[f+'_weight_ess']<10 for f in ('q9','q8'))
        result.append(item)
    return result


def evaluate(package,calls,truth,out):
    package,calls,truth,out=map(lambda x:Path(x).resolve(),(package,calls,truth,out));p,m=verify(package)
    if out.exists(): raise ValueError('Fresh evaluation output required')
    receipt=read_json(calls/'receipt.json');tm=read_json(truth/'manifest.json');cm=read_json(calls/'manifest.json')
    if not receipt.get('actual_model_results') or receipt['status']!='completed' or receipt['attempts']!=p['planned_calls']:
        raise ValueError('Complete actual-model ledger required; never score engineering fixtures')
    if any(x.get('protocol_sha256')!=m['protocol_sha256'] for x in (receipt,tm,cm)):
        raise ValueError('Mixed package provenance')
    for name,digest in cm['files_sha256'].items():
        if sha(calls/name)!=digest: raise ValueError('Call ledger changed')
    if sha(truth/'truth_private.json')!=tm['truth_sha256']: raise ValueError('Truth changed')
    nodes=read_json(ROOT/p['preparation']/'state_dependencies_private.json')
    cache_receipt=read_json(truth/'cache_receipt.json')
    if cache_receipt['cache_sha256']!=sha(truth/'scoring_cache_private.json') or cache_receipt['scorer']!=provenance():
        raise ValueError('Frozen scoring cache changed')
    install_score_cache({tuple(r['bins']):r['score'] for r in read_json(truth/'scoring_cache_private.json')})
    positions=[json.loads(l) for l in (calls/'positions_private.jsonl').read_text().splitlines()]
    originals,operational,quality=assemble_cases(nodes,positions,read_json(truth/'truth_private.json'))
    months=[int(v) for v in p['months']]
    def summarise(rows,periods,arms):
        return summarize(rows,periods,arms,weight_definition=weight_definition(p))
    valid=lambda r:shared.finite(r['survey_weight']) and r['survey_weight']>0
    weighted=[r for r in operational if valid(r)]
    actual_weighted=[r for r in originals if valid(r)]
    truth_by_key={(r['month'],r['agent_id']):r for r in read_json(truth/'truth_private.json')}
    for r in operational:
        t=truth_by_key[r['month'],r['agent_id']];r['stratum']=t['stratum'];r['profile']=t['profile']
        r['initial_q9_provenance']=t.get('initial_q9_provenance','legacy_unspecified')
    groups={}
    dimensions=['survey_entry_status','stratum','initial_q9_provenance',
                'education_group','numeracy','age_group','household_income_band','region']
    for dimension in dimensions:
        def label(r):
            value=r.get(dimension) if dimension in dimensions[:3] else r['profile'].get(dimension)
            return str(value) if value is not None else 'unknown'
        groups[dimension]={}
        for value in sorted({label(r) for r in weighted}):
            subset=[r for r in weighted if label(r)==value]
            groups[dimension][value]=summarise(subset,months,[ARM])
            groups[dimension][value]['support_by_month']=support_by_month(subset,months)
    result=dict(status='completed',new_api_calls=0,selected_person_months=len(operational),
        missing_weight_person_months=len(operational)-len(weighted),quality=quality,receipt=receipt,
        grid_version=p.get('grid_version'),primary_result_path='auxiliary_survey_weighted',
        fixed_roster=summarise(weighted,months,[ARM,'monthly_past_reference']),
        usable_output_sensitivity=summarise(actual_weighted,months,[ARM,'monthly_past_reference']),
        genuine_previous_only=summarise(weighted,months,[ARM,'genuine_previous_only']),
        by_month={str(month):summarise([r for r in weighted if r['month']==month],[month],[ARM,'monthly_past_reference']) for month in months},
        groups=groups,scorer=provenance(),
        limits=['A conditional reconstruction, not strict-B forecasting.',
                'This summary evaluates same-roster micro truth. Full-wave/national/combinations are separately reported.',
                'Missing raw weights excluded only from weighted summaries, never from simulation roster.',
                'Single main generation; subgroup findings descriptive, not causal.'])
    out.mkdir(parents=True);dump(out/'cases_private.json',operational);dump(out/'raw_output_cases_private.json',originals)
    dump(out/'summary.json',result)
    return dict(status='completed',person_months=len(operational),new_api_calls=0)
