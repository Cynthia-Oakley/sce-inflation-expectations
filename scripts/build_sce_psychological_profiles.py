#!/usr/bin/env python3
"""Build offline candidate sidecars, not runtime population or new answers."""
from pathlib import Path
import argparse,hashlib,json,sys,uuid,re
from datetime import datetime,timezone
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'studies/sce_inflation_expectations'))
from psychological_profiles import build_sidecars,candidate_text,BASIC,FINE

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--profiles',type=Path,required=True);ap.add_argument('--donors',type=Path,required=True)
 ap.add_argument('--source-hash',required=True);ap.add_argument('--draws',type=int,default=5);ap.add_argument('--seed',type=int,default=42);ap.add_argument('--min-ess',type=float,default=10)
 ap.add_argument('--role-root',type=Path,required=True,help='Existing core/normal basket split; role labels never influence assignment.')
 a=ap.parse_args()
 if a.draws<1:ap.error('draws must be positive')
 if not re.fullmatch(r'[0-9a-f]{64}',a.source_hash):ap.error('source-hash must be an actual SHA-256')
 origin=json.loads((a.donors.parent/'summary.json').read_text())
 if origin['sources']['gss']['sha256']!=a.source_hash:ap.error('source hash disagrees with donor audit provenance')
 for file in [a.profiles,a.donors]:
  if origin['candidate_file_hashes'].get(file.name)!=hashlib.sha256(file.read_bytes()).hexdigest():ap.error('candidate file disagrees with audit hash')
 p=pd.read_json(a.profiles,lines=True);d=pd.read_json(a.donors,lines=True)
 allowed={'date','userid','Q1','_AGE_CAT','_EDU_CAT','_HH_INC_CAT','_REGION_CAT','_NUM_CAT'}
 if not set(p)<=allowed:raise ValueError('profile file contains nonwhitelisted fields, possibly evaluation truth')
 roles={}
 for month in p.date.unique():
  roster={}
  for role in ['core','normal']:
   path=a.role_root/str(int(month))/'roles'/role/'population.json'
   for person in json.loads(path.read_text())['personas']:
    uid=person['agent_id']
    if uid in roster:raise ValueError('duplicate role ID')
    roster[uid]=role
  if set(roster)!={f'sce_u{int(u)}' for u in p.loc[p.date==month,'userid']}:raise ValueError('roles do not cover complete monthly population')
  roles[str(int(month))]=roster
 out=ROOT/'outputs'/('psychological_profiles_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]);out.mkdir(exist_ok=False)
 summary={'candidate_only':True,'source_hash':a.source_hash,'draws':a.draws,'seed':a.seed,'min_ess':a.min_ess,
  'matching':'age/education/historical family-income proxy/region; sparse fine pools drop region, retain income. Missing essential X unsupported.',
  'threshold_note':'10 is an exploratory development parameter, not a literature-derived rule or frozen final setting.',
  'simulation_calls':0,'runtime_population_changed':False,'normal_answer_estimator_changed':False,'draw_summaries':[],'input_hashes':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in [a.profiles,a.donors]},
  'code_hashes':{str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [Path(__file__),ROOT/'studies/sce_inflation_expectations/psychological_profiles.py']}}
 for draw in range(a.draws):
  records=build_sidecars(p,d,seed=a.seed,draw=draw,min_ess=a.min_ess,source_hash=a.source_hash)
  for r in records:r['population_role']=roles[r['target_month']][r['agent_id']]
  dst=out/f'draw_{draw:02d}';dst.mkdir()
  (dst/'sidecars.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
  (dst/'candidate_text_preview.jsonl').write_text(''.join(json.dumps({'agent_id':r['agent_id'],'month':r['target_month'],'candidate_text':candidate_text(r)},ensure_ascii=False)+'\n' for r in records))
  bymonth={}
  for month in roles:
   rows=[r for r in records if r['target_month']==month];assigned=[r for r in rows if r['support_status']=='synthetic_assigned']
   bymonth[month]={'n':len(rows),'assigned_n':len(assigned),'unknown_n':len(rows)-len(assigned),'pooled_region_n':sum(r['fallback_tier']==1 for r in assigned),
    'roles':{role:{'n':sum(r['population_role']==role for r in rows),'assigned_n':sum(r['population_role']==role for r in assigned)} for role in ['core','normal']},
    'joint_assigned_counts':{f'{h}|{s}':sum(r['psychological_attributes']=={'HAPPY':h,'SATFIN':s} for r in assigned) for h in [1,2,3] for s in [1,2,3]},
    'max_donor_reuse_n':max((sum(x['donor_local_id']==r['donor_local_id'] for x in assigned) for r in assigned),default=0)}
  # Fixed synthetic states are required only where matching P has not changed.
  byid={}
  for r in records:byid.setdefault(r['agent_id'],[]).append(r)
  stable=[v for v in byid.values() if len(v)==2 and v[0].get('matching_values')==v[1].get('matching_values') and v[0]['fallback_tier']==v[1]['fallback_tier'] and v[0]['support_status']=='synthetic_assigned']
  inconsistent=sum(v[0]['donor_local_id']!=v[1]['donor_local_id'] for v in stable)
  if inconsistent:raise ValueError('unstable matching assignment across months')
  summary['draw_summaries'].append({'draw':draw,'months':bymonth,'stable_covariate_repeated_ids':len(stable),'inconsistent_ids':inconsistent})
 snapshot=out/'source_snapshot';snapshot.mkdir()
 for code in [Path(__file__),ROOT/'studies/sce_inflation_expectations/psychological_profiles.py']:(snapshot/code.name).write_bytes(code.read_bytes())
 summary['valid_for_use']=True
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
 print('SIDECAR_DIR='+str(out))
 print(json.dumps(summary['draw_summaries'][0],ensure_ascii=False))
if __name__=='__main__':main()
