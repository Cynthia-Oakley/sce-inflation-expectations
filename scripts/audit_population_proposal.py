"""Read-only independent checks of the October 3 population proposal; no API calls.
Writes aggregate evidence to a new ignored outputs directory. Source files unchanged.
"""
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import hashlib, json, sys, uuid, shutil, subprocess, tempfile
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'studies/sce_inflation_expectations/scoring'))
from analyze_sce_wave_stats import employment_code
from sce_q9_frozen import score_q9_frozen, provenance
from sce_q9 import weighted_empirical_quantile

def score(bins):
    return asdict(score_q9_frozen(bins))
def wm(g, col='Q9_mean'):
    g=g.dropna(subset=[col,'weight']);g=g[g.weight>0]
    return float(weighted_empirical_quantile(g[col].tolist(),g.weight.tolist(),.5)) if len(g) else None

def main():
    out=ROOT/'outputs'/('population_review_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]);out.mkdir()
    source=ROOT/'data/raw/sce_audit_20260928/micro_2020_2024.xlsx'
    cols=['date','userid','tenure','weight','Q43','Q9_mean','Q8v2part2','_AGE_CAT','_EDU_CAT','_HH_INC_CAT','_REGION_CAT']+[f'Q10_{i}' for i in range(1,11)]
    df=pd.read_excel(source,skiprows=1,usecols=cols).dropna(subset=['date','userid']).sort_values(['userid','date'])
    df['employment']=df.apply(employment_code,axis=1)
    df['housing_past']=df.groupby('userid').Q43.ffill()
    df['employment_coarse']=df.employment.map(lambda x:x if x in ('employed','retired') else 'other_nonworking_or_unknown')
    main_df=df[df.date.between(202101,202112)]
    result={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'source_rows':len(df),'main_unique_ids':int(main_df.userid.nunique()),'main_rows':len(main_df),'months':{}}
    for m,g in main_df.groupby('date'):
        cats=g[['_AGE_CAT','_EDU_CAT','employment']].fillna('unknown')
        cells=cats.value_counts();w=g.weight.fillna(0).to_numpy()
        byemp=[]
        for name,h in g.groupby('employment'):
            byemp.append({'group':name,'n':len(h),'median':wm(h)})
        past=df[df.date<m];old=set(past.userid);prev=set(df[df.date== (m-1 if m%100>1 else m-89)].userid)
        entries=g[~g.userid.isin(old)];ret=g[g.userid.isin(prev)]
        result['months'][str(int(m))]={'n':len(g),'housing_observed':int(g.Q43.notna().sum()),'housing_from_past_or_same':int(g.housing_past.notna().sum()),'q43_given_tenure1':int(((g.tenure==1)&g.Q43.notna()).sum()),'tenure1':int((g.tenure==1).sum()),'fine_nonempty_cells':len(cells),'fine_cells_lt5':int((cells<5).sum()),'fine_cells_expected_lt5_at300':int((cells/len(g)*300<5).sum()),'fine_cells_expected_lt5_at500':int((cells/len(g)*500<5).sum()),'coarse_nonempty_cells':int(g[['_AGE_CAT','_EDU_CAT','employment_coarse']].fillna('unknown').value_counts().size),'kish_ess_full':float(w.sum()**2/(w@w)),'employment_groups':byemp,'new_seen_n':len(entries),'continuing_prev_n':len(ret),'entrant_median':wm(entries),'continuing_median':wm(ret)}
    result['summary']={'housing_coverage_raw':float(main_df.Q43.notna().mean()),'housing_coverage_past_or_same':float(main_df.housing_past.notna().mean()),'housing_note':'Past/same survey observation only; NOT proof of historical public availability or current unchanged tenure.'}
    # Re-evaluate exact frozen production wrapper against all sealed records;
    # deduplicate vectors only to save deterministic fitting work.
    sealed=ROOT/'outputs/scorer_holdout_20261003T023026Z_77ebb305/records.jsonl'
    rows=[json.loads(s) for s in sealed.read_text().splitlines()]
    vectors={json.dumps([r[f'Q9_bin{i}'] for i in range(1,11)]):[r[f'Q9_bin{i}'] for i in range(1,11)] for r in rows}
    print('population audit done; scoring',len(vectors),'unique vectors',flush=True)
    with ProcessPoolExecutor(max_workers=3) as pool:
        fits=dict(zip(vectors,pool.map(score,vectors.values(),chunksize=12)))
    mismatches=[];maxdiff=0.
    for r in rows:
        a=fits[json.dumps([r[f'Q9_bin{i}'] for i in range(1,11)])];b=r['fits']['candidate']
        bad=(a['status']!=b['status'] or a['family']!=b['family'])
        for f in ('mean','p25','p50','p75','iqr','prob_deflation','fit_loss'):
            if a.get(f) is None or b.get(f) is None:bad|=(a.get(f)!=b.get(f))
            else:
                d=abs(a[f]-b[f]);maxdiff=max(maxdiff,d);bad|=(not np.isfinite(d) or d>1e-8)
        if bad:mismatches.append({'date':r['date'],'excel_row':r['excel_row']})
    # Standalone study layout smoke test, no changes to runtime repo.
    with tempfile.TemporaryDirectory() as td:
        dest=Path(td)/'studies/sce_inflation_expectations/scoring';dest.parent.mkdir(parents=True)
        shutil.copytree(ROOT/'studies/sce_inflation_expectations/scoring',dest,ignore=shutil.ignore_patterns('__pycache__'))
        code=f'import sys;sys.path.insert(0,{str(dest)!r});import sce_q9_frozen'
        proc=subprocess.run([sys.executable,'-c',code],cwd=td,capture_output=True,text=True)
        standalone={'returncode':proc.returncode,'stderr_last_line':proc.stderr.splitlines()[-1] if proc.stderr else ''}
    result['scorer']={'sealed_records':len(rows),'unique_vectors':len(vectors),'mismatches':mismatches,'max_abs_difference':maxdiff,'provenance':provenance(),'standalone_import':standalone}
    # Latest user's 73-person run: distinguish personal point errors from headline errors.
    run=ROOT/'outputs/local_runs/sce-local-openai-20261003T055121Z-1dc7cd15'
    panel=[json.loads(s) for s in (run/'panel_live.jsonl').read_text().splitlines()]
    sim=[]
    for r in panel:
        p=r.get('action_payload') or {}
        if p.get('validation_status')!='valid':continue
        sim.append({'userid':int(r['agent_id'].removeprefix('sce_u')),'date':int(p['target_month'].replace('-','')),'sim_q8':p['point_pct'],'bins':[p[f'q9_bin{i}'] for i in range(1,11)]})
    sim=pd.DataFrame(sim);paired=sim.merge(main_df,on=['userid','date'],validate='one_to_one')
    err=(paired.sim_q8-paired.Q8v2part2).dropna()
    result['pilot']={'run_id':run.name,'matched_rows':len(paired),'q8_personal_medae':float(err.abs().median()),'q8_personal_mae':float(err.abs().mean()),'q8_personal_bias':float(err.mean())}
    # Score each distinct simulated vector once; compare same scorer on real raw bins
    # only if those are already archived in truth data; no inferential claims here.
    with ProcessPoolExecutor(max_workers=3) as pool:
        simulated_fits=list(pool.map(score,paired.bins.tolist(),chunksize=12))
    paired['sim_q9']=[r['mean'] for r in simulated_fits]
    er=(paired.sim_q9-paired.Q9_mean).dropna()
    result['pilot'].update(q9_vs_official_personal_medae=float(er.abs().median()),q9_vs_official_personal_mae=float(er.abs().mean()),q9_note='Compared to official individual Q9_mean for metric identification; includes approximate scoring difference.')
    result['pilot']['months']={str(int(m)):{'sim_q9_equal_median':float(g.sim_q9.median()),'sim_q9_weighted_median':wm(g,'sim_q9'),'real_panel_q9_official_weighted_median':wm(g),'real_full_q9_official_weighted_median':wm(main_df[main_df.date==m]),'sim_q9_std':float(g.sim_q9.std()),'real_panel_q9_std':float(g.Q9_mean.std())} for m,g in paired.groupby('date')}
    (out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(out,flush=True)
    print(json.dumps({'population':result['summary'],'scorer':{k:v for k,v in result['scorer'].items() if k!='provenance'},'pilot':{k:v for k,v in result['pilot'].items() if k!='months'}},ensure_ascii=False),flush=True)

if __name__=='__main__':main()
