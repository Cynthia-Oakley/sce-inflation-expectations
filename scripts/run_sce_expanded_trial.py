#!/usr/bin/env python3
"""Prepare/dry-run/execute the approved expanded experiment in SocioVerse2.

Only never-started jobs run. Existing job folders are never overwritten or
automatically resumed. All job caps add to <= the approved $12 simulation cap.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OFFICIAL = ROOT.parent/'socioverse2_repo'

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def dump(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def verify(folder):
    m=json.loads((folder/'manifest.json').read_text())
    for name,digest in m['source_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Source changed: '+name)
    for name,digest in m['prepared_file_sha256'].items():
        if sha(folder/name)!=digest:raise ValueError('Prepared input changed: '+name)
    if sum(j['cap_usd'] for j in m['jobs'])>12+1e-9:raise ValueError('Budget sum')
    return m

def worker(folder,index,scripted):
    # Import the one-way exported copy through the official framework.
    sys.path.insert(0,str(OFFICIAL))
    from socioverse.engine import build_simulator
    from socioverse.schemas import EnvironmentBundle,PopulationBundle,SimulationConfig
    from studies.sce_inflation_expectations.expanded_state_runtime import ExpandedDecision
    from studies.sce_inflation_expectations.model import SCEEnvironmentProvider
    from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
    m=json.loads((folder/'manifest.json').read_text());job=m['jobs'][index]
    run_id=job['run_id']+('-engineering' if scripted else '')
    audit=ROOT/'outputs/local_runs'/run_id;audit.mkdir(parents=True,exist_ok=False)
    source=OFFICIAL/'studies/sce_inflation_expectations'
    snapshot=audit/'source_snapshot';snapshot.mkdir()
    source_hashes={}
    for p in source.rglob('*.py'):
        if '__pycache__' in p.parts:continue
        rel=p.relative_to(source);dest=snapshot/rel;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
        source_hashes[str(rel)]=sha(p)
    dest=folder/str(job['month'])
    env=EnvironmentBundle.model_validate_json((dest/'environment.json').read_text())
    pop=PopulationBundle.model_validate_json((dest/'population.json').read_text())
    cfg=SimulationConfig.model_validate_json((dest/f"simulation_{job['arm']}.json").read_text())
    env.provider_args.update(audit_dir=str(audit),run_id=run_id,
                            persona_by_id={p.agent_id:p.attributes for p in pop.personas})
    cfg.seed=42+job['repeat']-1
    cfg.decision_args.update(llm_kind='scripted' if scripted else 'openai',seed=cfg.seed,
        run_id=run_id,audit_dir=str(audit),model='deepseek-flash',temperature=.5,
        max_tokens=1024,retry_max=0,max_calls=96,extra_body={'thinking':{'type':'disabled'}},
        price_input_per_mtok=.3,price_output_per_mtok=1.2,cost_cap_usd=job['cap_usd'])
    check=SCEEnvironmentProvider(env.model_copy(deep=True));check.audit_dir=None;check.reset(cfg.seed);check.advance_to(1)
    # Instantiate a scripted provider for input checks so no credential is read.
    check_args={**cfg.decision_args,'llm_kind':'scripted'};decision=ExpandedDecision(**check_args)
    previews={r['agent_id']:r for r in json.loads((dest/f"preview_{job['arm']}.json").read_text())}
    for ob in check.observe_batch([p.agent_id for p in pop.personas],1):
        if message_hash(decision.build_llm_messages(ob))!=previews[ob.agent_id]['prompt_sha256']:
            raise ValueError('Runtime input hash differs')
    for name,b in [('population_effective',pop),('environment_effective',env),('simulation_effective',cfg)]:dump(audit/(name+'.json'),b.model_dump(mode='json'))
    sim=build_simulator(env_bundle=env,pop_bundle=pop,sim_config=cfg,store_path=audit/'study.duckdb')
    statuses=Counter();original=sim.decision.decide_batch
    def counted(obs,memories):
        actions=original(obs,memories);statuses.update(str(a.payload.get('validation_status')) for a in actions);return actions
    sim.decision.decide_batch=counted
    started=datetime.now(timezone.utc).isoformat();history=sim.run()
    dump(audit/'metrics_history.json',history.model_dump(mode='json') if hasattr(history,'model_dump') else {'rows':history.rows})
    cost=sim.decision.cost_summary()
    result=dict(run_id=run_id,month=job['month'],arm=job['arm'],repeat=job['repeat'],
                llm_kind='scripted' if scripted else 'openai',started_at_utc=started,
                finished_at_utc=datetime.now(timezone.utc).isoformat(),decisions_by_validation_status=dict(statuses),
                cost=cost,source_snapshot_sha256=source_hashes,store_path=str(audit/'study.duckdb'),
                artifact_sha256={name:sha(dest/name) for name in ['population.json','environment.json',f"simulation_{job['arm']}.json"]})
    dump(audit/'run_manifest.json',result);dump(audit/'cost_ledger.json',cost)
    if not scripted and cost['call_count']!=96:raise RuntimeError('Expected 96 attempted requests; no automatic continuation')
    print(json.dumps({'run_id':run_id,'statuses':dict(statuses),'cost':cost['estimated_cost_usd']}),flush=True)
    return 0

def dispatch(folder,phase,scripted,workers):
    m=verify(folder)
    if not scripted:
        from studies.sce_inflation_expectations.news_label_trial import dotenv_values
        import os
        config=dotenv_values(OFFICIAL/'.env')
        host=(os.environ.get('SV_LLM_BASE_URL') or config.get('SV_LLM_BASE_URL') or '').rstrip('/')
        if host not in ('https://api.deepseek.com','https://api.deepseek.com/v1'):
            raise ValueError('Official DeepSeek endpoint required; no model calls started')
        if not (os.environ.get('SV_LLM_API_KEY') or config.get('SV_LLM_API_KEY')):
            raise ValueError('Official DeepSeek credential missing')
        checks=json.loads((folder/'engineering_checks.json').read_text())
        if len(checks)!=16 or any(r['exit_code'] for r in checks):raise ValueError('16 offline cells required')
        if phase=='evaluation':
            lock=json.loads((folder/'weight_lock.json').read_text())
            if lock['protocol_sha256']!=sha(folder/'protocol.json'):raise ValueError('Weight protocol mismatch')
    export=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/export_study_runtime.py')],cwd=ROOT,capture_output=True,text=True)
    if export.returncode:raise RuntimeError(export.stdout+export.stderr)
    jobs=[(i,j) for i,j in enumerate(m['jobs']) if (scripted and j['repeat']==1) or (not scripted and j['phase']==phase)]
    existing=[j['run_id'] for _,j in jobs if (ROOT/'outputs/local_runs'/(j['run_id']+('-engineering' if scripted else ''))).exists()]
    if existing:raise ValueError('Existing jobs require explicit review, never auto-resume: '+str(existing))
    def one(item):
        i,j=item;log=folder/(j['run_id']+('-engineering' if scripted else '')+'.log')
        command=[sys.executable,'-B',str(Path(__file__).resolve()),'worker','--folder',str(folder),'--job-index',str(i)]
        if scripted:command.append('--scripted')
        with log.open('x') as handle:rc=subprocess.run(command,cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT).returncode
        print(j['month'],j['arm'],j['repeat'],'completed' if rc==0 else 'stopped',flush=True)
        return dict(job_index=i,run_id=j['run_id'],exit_code=rc)
    results=[]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(one,item) for item in jobs]
        for future in as_completed(futures):
            results.append(future.result());dump(folder/('engineering_checks.json' if scripted else phase+'_dispatch.json'),results)
    if any(r['exit_code'] for r in results):raise RuntimeError('Some jobs stopped; preserve evidence, do not automatically retry')

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','dry-run','development','evaluation','worker'])
    p.add_argument('--folder',type=Path,required=True);p.add_argument('--job-index',type=int);p.add_argument('--scripted',action='store_true');p.add_argument('--workers',type=int,default=8)
    args=p.parse_args();folder=args.folder.resolve()
    if args.action=='worker':return worker(folder,args.job_index,args.scripted)
    sys.path.insert(0,str(ROOT))
    if args.action=='prepare':
        from studies.sce_inflation_expectations.expanded_state_inputs import prepare
        m=prepare(folder);print('Prepared',m['planned_calls'],'calls; caps',m['total_job_caps_usd']);return 0
    dispatch(folder,args.action,args.action=='dry-run',args.workers);return 0

if __name__=='__main__':
    sys.exit(main())
