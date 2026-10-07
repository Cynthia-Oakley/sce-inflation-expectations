#!/usr/bin/env python3
"""Profile-only monthly drift and B donor diagnostics, no model/network calls."""
import argparse,hashlib,json,sys
from pathlib import Path
from datetime import datetime,timezone
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.monthly_population import PROFILE_COLUMNS
from studies.sce_inflation_expectations.population_forecast import ATTRIBUTES,profile_view,donor_probabilities,synthesize
from socioverse.schemas import PopulationBundle
from studies.sce_inflation_expectations.core_normal import build_expansion
FIELDS=ATTRIBUTES+['age_education_income_region_joint']


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def probs(frame,field,weighted):
    w=pd.to_numeric(frame.weight,errors='coerce') if weighted else pd.Series(1.,index=frame.index)
    valid=np.isfinite(w)&(w>0)
    return (w[valid].groupby(frame.loc[valid,field]).sum()/w[valid].sum()).to_dict()
def tvd(a,b):return sum(abs(a.get(k,0)-b.get(k,0)) for k in set(a)|set(b))/2

def load_profiles(out):
    files=[ROOT/'data/raw/sce_p_sources/micro_2017_2019.xlsx',ROOT/'data/raw/sce_audit_20260928/micro_2020_2024.xlsx',ROOT/'data/raw/sce_audit_20260928/micro_latest.xlsx']
    columns=PROFILE_COLUMNS+['weight','survey_date'];frames=[];sources=[]
    for file in files:
        manifest=json.loads((file.parent/'manifest.json').read_text())
        evidence=next(r for r in manifest if r['file']==file.name)
        h=sha(file);key=hashlib.sha256((h+json.dumps(columns)).encode()).hexdigest()[:20]
        if h!=evidence['sha256']:raise ValueError('workbook differs from archived source manifest')
        cache=ROOT/'data/cache'/f'monthly_profiles_{key}.parquet'
        if cache.exists():d=pd.read_parquet(cache,columns=PROFILE_COLUMNS+['weight']);print('Cached profiles:',file.name,flush=True)
        else:
            print('Reading only population fields:',file.name,flush=True)
            d=pd.read_excel(file,sheet_name='Data',header=1,usecols=columns)
            cache.parent.mkdir(parents=True,exist_ok=True);d.to_parquet(cache,index=False)
            d=d[PROFILE_COLUMNS+['weight']]
        frames.append(d);sources.append({'source_file':str(file.relative_to(ROOT)),'source_sha256':h,
                                        'snapshot_observed_at':evidence['retrieved_at'],'source_url':evidence['url'],
                                        'historical_first_published_at':None,'cache_file':str(cache.relative_to(ROOT)),'cache_sha256':sha(cache)})
    d=pd.concat(frames,ignore_index=True);d.date=pd.to_numeric(d.date,errors='raise').astype(int)
    d.userid=pd.to_numeric(d.userid,errors='raise').astype(int)
    if d.duplicated(['date','userid']).any():raise ValueError('overlap/duplicate profile rows')
    view=profile_view(d)
    view['age_education_income_region_joint']=view[['age_group','education_group','household_income_band','region']].agg('|'.join,axis=1)
    view.to_parquet(out/'profile_view.parquet',index=False)
    dump(out/'source_manifest.json',sources);return view


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    out=args.out;out.mkdir(parents=True,exist_ok=False);d=load_profiles(out)
    waves={int(m):g for m,g in d.groupby('date')};monthly=[];margins={};seen=set();previous=set()
    for m,g in sorted(waves.items()):
        ids=set(g.userid);w=pd.to_numeric(g.weight,errors='coerce');valid=np.isfinite(w)&(w>0)
        row={'month':m,'n':len(g),'weight_valid_n':int(valid.sum()),'weight_ess':float(w[valid].sum()**2/(w[valid]**2).sum()),
             'adjacent_retention':None if not previous else len(ids&previous)/len(previous),
             'new_to_previous_fraction':None if not previous else len(ids-previous)/len(ids),
             'first_seen_in_available_files_fraction':None if not seen else len(ids-seen)/len(ids),
             'returning_after_gap_fraction':None if not seen else len((ids-previous)&seen)/len(ids),
             'margins':{f:{'raw':probs(g,f,False),'weighted':probs(g,f,True)} for f in FIELDS}}
        margins[m]=row['margins'];monthly.append(row);seen|=ids;previous=ids
    drift=[]
    for m in waves:
        index=m//100*12+m%100-1
        for lag in [1,9,10,12]:
            old_i=index-lag;old=old_i//12*100+old_i%12+1
            if old not in waves:continue
            for f in FIELDS:
                for kind in ['raw','weighted']:
                    drift.append({'month':m,'lag':lag,'field':f,'kind':kind,'tvd':tvd(margins[m][f][kind],margins[old][f][kind])})
    # Distribution forecast validation only; latest snapshots and assumed lag do not certify historical posting dates.
    forecast=[]
    for m,g in sorted(waves.items()):
        if m<202001:continue
        idx=m//100*12+m%100-1;old_i=idx-10;end=old_i//12*100+old_i%12+1
        for window in [1,12]:
            try:donors,p,months=donor_probabilities(d,end,window)
            except ValueError:continue
            for f in FIELDS:
                estimate=pd.Series(p).groupby(donors[f]).sum().to_dict()
                forecast.append({'month':m,'window':window,'field':f,'tvd':tvd(estimate,margins[m][f]['weighted']),
                                 'donor_end':months[-1],'availability':'assumed_conservative_t_minus_10_not_historical_posting_proof'})
    dump(out/'monthly_profile_stats.json',monthly);dump(out/'drift.json',drift);dump(out/'forecast_distribution_validation.json',forecast)
    summaries={}
    for f in FIELDS:
        summaries[f]={}
        for lag in [1,10,12]:
            vals=[x['tvd'] for x in drift if x['field']==f and x['lag']==lag and x['kind']=='weighted']
            summaries[f][f'lag_{lag}']={'mean_tvd':float(np.mean(vals)),'p90_tvd':float(np.quantile(vals,.9))}
        for window in [1,12]:
            vals=[r['tvd'] for r in forecast if r['field']==f and r['window']==window]
            summaries[f][f'donor_window_{window}']={'mean_tvd':float(np.mean(vals)),'p90_tvd':float(np.quantile(vals,.9))}
    latest=int(d.date.max());current=waves[latest]
    from_manifest=json.loads((ROOT/'data/raw/sce_audit_20260928/manifest.json').read_text())
    snapshot=next(x for x in from_manifest if x['file']=='micro_latest.xlsx')['retrieved_at']
    # A current-cutoff pilot from an actually observed-before-cutoff snapshot, not the historical lag assumption.
    for window in [1,12]:
        bundle,meta,prov=synthesize(d,target_month='2026-10',donor_end=latest,available_at=snapshot,cutoff='2026-09-30T23:59:59-04:00',n=len(current),core_n=300,window=window)
        PopulationBundle.model_validate(bundle)
        folder=out/f'population_B_2026_10_window_{window}';folder.mkdir()
        dump(folder/'population_candidate.json',bundle);dump(folder/'sampling_meta.json',meta);dump(folder/'donor_provenance_private.json',prov)
        donors,p,_=donor_probabilities(d,latest,window)
        realized=pd.DataFrame([{f:person['attributes'].get(f,'unknown') for f in ATTRIBUTES} for person in bundle['personas']])
        realized['weight']=1.
        dump(folder/'sampling_distribution_diagnostics.json',
             {f:{'synthetic_to_donor_tvd':tvd(probs(realized,f,False),pd.Series(p).groupby(donors[f]).sum().to_dict())}
              for f in ATTRIBUTES})
        plan=build_expansion(bundle,meta['core_ids'],meta['core_ids'],{person['agent_id']:1. for person in bundle['personas']})
        if not np.isclose(plan.atom_weights().sum(),len(current)):raise ValueError('Core/Normal mass inconsistent')
        dump(folder/'core_normal_support_diagnostic.json',
             {'status':'hypothetical all selected Core valid; only profile support and total mass checked; no answers generated',
              'report':plan.report()})
    months=sorted(waves);middle=[r for r in monthly if r['month']>=202001]
    summary={'first_month':months[0],'last_month':months[-1],'months':len(months),'profile_rows':len(d),'unique_people':int(d.userid.nunique()),
             'created_utc':datetime.now(timezone.utc).isoformat(),
             'source_code_sha256':{str(file.relative_to(ROOT)):sha(file) for file in
                                    [Path(__file__),ROOT/'studies/sce_inflation_expectations/population_forecast.py',
                                     ROOT/'studies/sce_inflation_expectations/monthly_population.py',ROOT/'studies/sce_inflation_expectations/core_normal.py']},
             'wave_size_min':min(r['n'] for r in monthly),'wave_size_median':float(np.median([r['n'] for r in monthly])),'wave_size_max':max(r['n'] for r in monthly),
             'weighted_ess_median':float(np.median([r['weight_ess'] for r in middle])),
             'new_to_previous_median':float(np.median([r['new_to_previous_fraction'] for r in middle if r['new_to_previous_fraction'] is not None])),
             'return_after_gap_median':float(np.median([r['returning_after_gap_fraction'] for r in middle if r['returning_after_gap_fraction'] is not None])),
             'latest_margins':margins[latest],'drift_summary':summaries,'forecast_population_validation':'description only; no Q8/Q9 outcomes; assumed posting lag for historical validation',
             'prospective_candidate':'2026-10 from snapshot observed 2026-09-28; historical 2025-10 profiles reused as synthetic types',
             'missing_weight_rows':sum(r['n']-r['weight_valid_n'] for r in monthly),'real_llm_calls':0,'source_configs_modified':False}
    dump(out/'summary.json',summary);print(json.dumps({k:v for k,v in summary.items() if k not in ['latest_margins','drift_summary']}),flush=True)

if __name__=='__main__':main()
