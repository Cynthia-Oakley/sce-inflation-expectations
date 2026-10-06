#!/usr/bin/env python3
"""Audit development months and GSS2018 donor support; no model calls."""
from pathlib import Path
import sys,argparse,json,hashlib,uuid
from datetime import datetime,timezone
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'studies/sce_inflation_expectations'))
from household_state_audit import audit_sce,prepare_gss,audit_support,PROFILE,NUMERACY_ANSWERS

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--source',type=Path,default=ROOT/'data/raw/sce_audit_20260928/micro_2020_2024.xlsx')
 ap.add_argument('--gss',type=Path,required=True)
 ap.add_argument('--months',default='202105,202106')
 ap.add_argument('--cache',type=Path,help='Reuse locally serialized development rows from a prior attempt; record its hash.')
 args=ap.parse_args();args.source=args.source.resolve();args.gss=args.gss.resolve();args.cache=args.cache.resolve() if args.cache else None;months=set(map(int,args.months.split(',')))
 if not months<= {202105,202106}:ap.error('This audit is limited to already used development months.')
 run='household_psychology_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
 out=ROOT/'outputs'/run;out.mkdir(exist_ok=False)
 # P and evaluation fields share a local read only for this offline descriptive audit.
 cols=['date','userid','weight','Q1','Q2','Q9_mean','Q8v2part2']+PROFILE+list(NUMERACY_ANSWERS)
 print('Reading current SCE workbook; development months only',flush=True)
 source=(pd.read_json(args.cache,lines=True) if args.cache else pd.read_excel(args.source,skiprows=1,usecols=cols))
 frame=source[source.date.isin(months)].copy();del source
 frame.to_json(out/'evaluation_development_rows.jsonl',orient='records',lines=True)
 frame[['date','userid','Q1']+PROFILE].to_json(out/'profile_candidates.jsonl',orient='records',lines=True)
 result=audit_sce(frame)
 for month,t in frame.groupby('date'):
  result['months'][str(int(month))]['profile_missing_n']={c:int(t[c].isna().sum()) for c in PROFILE}
 gcols=['year','id','age','educ','degree','income16','region','happy','satfin','trust','ballot','wtssall','wtssnr','wtssps','wtssnrps']
 g=pd.read_stata(args.gss,columns=gcols,convert_categoricals=False)
 labeled=pd.read_stata(args.gss,columns=['degree','income16','region','happy','satfin','trust'],convert_categoricals=True)
 maps={c:{str(int(code)):str(label) for code,label in zip(g[c],labeled[c]) if pd.notna(code)} for c in labeled}
 for c in ['happy','satfin']:
  if set(maps[c])!={'1','2','3'}:raise ValueError('unexpected psychological categories')
 (out/'gss_field_labels.json').write_text(json.dumps(maps,ensure_ascii=False,indent=2)+'\n')
 donors=prepare_gss(g,maps)
 # Shared category strings are checked against actual target coding before support.
 for c in ['_AGE_CAT','_EDU_CAT','_REGION_CAT']:
  if not set(frame[c].dropna())<=set(donors[c].dropna()):raise ValueError(f'crosswalk mismatch {c}: {set(frame[c])}')
 dcols=['id','happy','satfin','trust','ballot','donor_weight','_AGE_CAT','_EDU_CAT','_HH_INC_CAT','_REGION_CAT']
 donors[dcols].to_json(out/'gss2018_candidate_donors.jsonl',orient='records',lines=True)
 result['gss']={'n':len(g),'happy_valid_n':int(g.happy.isin([1,2,3]).sum()),'satfin_valid_n':int(g.satfin.isin([1,2,3]).sum()),
  'happy_satfin_joint_n':len(donors),'with_age_education_region_n':int(donors[['_AGE_CAT','_EDU_CAT','_REGION_CAT']].notna().all(axis=1).sum()),
  'with_unambiguous_historical_family_income_n':int(donors[['_AGE_CAT','_EDU_CAT','_REGION_CAT','_HH_INC_CAT']].notna().all(axis=1).sum()),
  'income90k_109999_n':int((donors.income16==22).sum()),'trust_joint_n':int(donors.trust.isin([1,2,3]).sum()),'weight':'wtssps',
  'weight_note':'Current NORC FAQ recommends WTSSPS. Current revised file used for A exploration only; not a proven 2021 B vintage.',
  'income_note':'INCOME16 total family income, historical nominal categories; not exact contemporaneous SCE household income. $90k-$109999 excluded from income-key matching; no midpoint or random split.',
  'ballot_joint_counts':{str(int(k)):len(v) for k,v in donors.groupby('ballot')},
  'joint_weighted_distribution':{f'{int(h)}|{int(s)}':float(v.donor_weight.sum()/donors.donor_weight.sum()) for (h,s),v in donors.groupby(['happy','satfin'])},'support':{}}
 for month,t in frame.groupby('date'):
  result['gss']['support'][str(int(month))]={}
  for name,keys in [('age_education_region',['_AGE_CAT','_EDU_CAT','_REGION_CAT']),('plus_income_proxy',['_AGE_CAT','_EDU_CAT','_REGION_CAT','_HH_INC_CAT']),('age_education_income_proxy',['_AGE_CAT','_EDU_CAT','_HH_INC_CAT']),('age_education',['_AGE_CAT','_EDU_CAT'])]:
   result['gss']['support'][str(int(month))][name]=audit_support(t,donors,keys)
 result['candidate_file_hashes']={n:digest(out/n) for n in ['profile_candidates.jsonl','gss2018_candidate_donors.jsonl','gss_field_labels.json']}
 snapshot=out/'source_snapshot';snapshot.mkdir()
 for code in [Path(__file__),ROOT/'studies/sce_inflation_expectations/household_state_audit.py']: (snapshot/code.name).write_bytes(code.read_bytes())
 result['run_id']=run;result['sources']={'sce':{'path':str(args.source.relative_to(ROOT)),'sha256':digest(args.source)},'gss':{'path':str(args.gss.relative_to(ROOT)),'sha256':digest(args.gss)},'module_sha256':digest(ROOT/'studies/sce_inflation_expectations/household_state_audit.py'),'entry_sha256':digest(Path(__file__))}
 result['cache_reuse']=None if not args.cache else {'path':str(args.cache.relative_to(ROOT)),'sha256':digest(args.cache),'note':'Locally created development extract reused; no independent vintage proof.'}
 result['scope']={'simulation_llm_calls':0,'paid_mcp_calls':0,'line':'A offline development descriptive audit','changed_runtime_inputs':False,'q9':'Official derived mean, no refitting. Finite official means used independently of raw-bin validity. Q8 signed point evaluated separately.','unimplemented':'No psychological population assignment or runtime integration; no causal conclusion.'}
 (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
 print('RESULT_DIR='+str(out),flush=True)
 for m,x in result['months'].items():print(m, 'numeracy',x['numeracy_check'],'Q1 coefficients',x['adjusted_mean_association']['coefficients_pp'],flush=True)
 print('GSS joint',result['gss']['happy_satfin_joint_n'],flush=True)
if __name__=='__main__':main()
