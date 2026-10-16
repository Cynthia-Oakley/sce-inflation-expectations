#!/usr/bin/env python3
"""Household financial-circumstances pilot; no auto-resume/retry and explicit authorization gate."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,wait,FIRST_COMPLETED
from datetime import datetime,timezone
import json
import hashlib
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
OFFICIAL=ROOT.parent/'socioverse2_repo'
sys.path.insert(0,str(ROOT))


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path,value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def verify(folder):
    folder=Path(folder).resolve()
    m=json.loads((folder/'manifest.json').read_text())
    for name,digest in m['source_sha256'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path)!=digest:raise ValueError('source changed: '+name)
    for name,digest in m['prepared_file_sha256'].items():
        path=(folder/name).resolve()
        if not path.is_relative_to(folder) or sha(path)!=digest:raise ValueError('prepared input changed: '+name)
    if sha(folder/'protocol.json')!=m['protocol_sha256']:raise ValueError('protocol changed')
    if not m['jobs'] or len({j['run_id'] for j in m['jobs']})!=len(m['jobs']):raise ValueError('unique jobs required')
    for job in m['jobs']:
        if job['arm'] not in ('baseline','financial_facts','financial_perspective') or job['repeat'] not in (1,2):raise ValueError('unknown trial cell')
        if Path(job['run_id']).name!=job['run_id'] or not job['run_id']:raise ValueError('invalid run identifier')
        if not math.isfinite(job['cap_usd']) or job['cap_usd']<=0:raise ValueError('invalid job budget')
    if not math.isfinite(m['proposed_cap_usd']) or m['proposed_cap_usd']<=0:raise ValueError('invalid total budget')
    if sum(j['cap_usd'] for j in m['jobs'])>m['proposed_cap_usd']+1e-9:raise ValueError('budget sum')
    protocol=json.loads((folder/'protocol.json').read_text())
    expected={'model':'deepseek-flash','temperature':.5,'max_tokens':1024,'retry_max':0}
    if any(protocol.get(key)!=value for key,value in expected.items()):raise ValueError('frozen model settings mismatch')
    if protocol.get('thinking') not in ('disabled', {'type':'disabled'}):raise ValueError('disabled thinking required')
    if protocol.get('planned_calls')!=m['planned_calls']:raise ValueError('planned scope mismatch')
    if protocol.get('price_input_per_mtok',.3)!=.3 or protocol.get('price_output_per_mtok',1.2)!=1.2:raise ValueError('frozen token prices mismatch')
    return m


def authorization_gate(folder,m):
    auth=json.loads((folder/'authorization.json').read_text())
    if auth.get('approved') is not True or auth.get('protocol_sha256')!=m['protocol_sha256'] or auth.get('cap_usd')!=m['proposed_cap_usd'] or auth.get('planned_calls')!=m['planned_calls']:
        raise ValueError('specific matching scope/budget authorization required')
    checks=json.loads((folder/'engineering_checks.json').read_text())
    if len(checks)!=len(m['jobs']) or {r['job_index'] for r in checks}!=set(range(len(m['jobs']))) or any(r['exit_code'] for r in checks):
        raise ValueError('all offline cells required')
    for check in checks:
        job=m['jobs'][check['job_index']]
        if check['run_id']!=job['run_id']:raise ValueError('offline cell mismatch')
        receipt=json.loads((ROOT/'outputs/local_runs'/(job['run_id']+'-engineering')/'run_manifest.json').read_text())
        if (receipt.get('protocol_sha256')!=m['protocol_sha256'] or receipt.get('status')!='completed'
                or receipt.get('llm_kind')!='scripted' or receipt.get('cost',{}).get('call_count')!=0
                or receipt.get('actual_input_hashes_match') is not True):raise ValueError('verified zero-API offline receipt required')
    from studies.sce_inflation_expectations.news_label_trial import dotenv_values
    values=dotenv_values(OFFICIAL/'.env')
    host=(os.environ.get('SV_LLM_BASE_URL') or values.get('SV_LLM_BASE_URL') or '').rstrip('/')
    if host not in ('https://api.deepseek.com','https://api.deepseek.com/v1') or not (os.environ.get('SV_LLM_API_KEY') or values.get('SV_LLM_API_KEY')):
        raise ValueError('official DeepSeek endpoint/credential required')


def worker(folder,index,scripted):
    m=verify(folder)
    if index is None or not 0<=index<len(m['jobs']):raise ValueError('valid job index required')
    sys.path.insert(0,str(OFFICIAL))
    if not scripted:authorization_gate(folder,m)
    from socioverse.engine import build_simulator
    from socioverse.schemas import EnvironmentBundle,PopulationBundle,SimulationConfig
    from studies.sce_inflation_expectations.household_finance_runtime import HouseholdFinanceDecision
    from studies.sce_inflation_expectations.model import SCEEnvironmentProvider
    from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
    job=m['jobs'][index]
    run_id=job['run_id']+('-engineering' if scripted else '')
    audit=ROOT/'outputs/local_runs'/run_id;audit.mkdir(parents=True,exist_ok=False)
    runtime=OFFICIAL/'studies/sce_inflation_expectations'
    prefix='studies/sce_inflation_expectations/'
    for name,digest in m['source_sha256'].items():
        if name.startswith(prefix) and name.endswith('.py') and sha(runtime/name[len(prefix):])!=digest:
            raise ValueError('exported runtime source changed: '+name)
    snapshot=audit/'source_snapshot';snapshot.mkdir();hashes={}
    for source in runtime.rglob('*.py'):
        if '__pycache__' in source.parts:continue
        rel=source.relative_to(runtime);dest=snapshot/rel;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,dest);hashes[str(rel)]=sha(source)
    shutil.copy2(Path(__file__),audit/'runner_source.py')
    dest=folder/str(job['month'])
    env=EnvironmentBundle.model_validate_json((dest/'environment.json').read_text())
    pop=PopulationBundle.model_validate_json((dest/'population.json').read_text())
    cfg=SimulationConfig.model_validate_json((dest/f"simulation_{job['arm']}.json").read_text())
    n=len(pop.personas)
    payload_path=Path(cfg.decision_args['household_finance_payloads_file']).resolve()
    if payload_path!=(dest/'household_finance_payloads.json').resolve() or cfg.decision_args['household_finance_payloads_sha256']!=sha(payload_path):
        raise ValueError('frozen month-specific household_finance payload required')
    env.provider_args.update(audit_dir=str(audit),run_id=run_id,persona_by_id={p.agent_id:p.attributes for p in pop.personas})
    cfg.seed=41+job['repeat']
    cfg.decision_args.update(llm_kind='scripted' if scripted else 'openai',seed=cfg.seed,
        run_id=run_id,audit_dir=str(audit),model='deepseek-flash',temperature=.5,max_tokens=1024,
        retry_max=0,max_calls=n,extra_body={'thinking':{'type':'disabled'}},
        price_input_per_mtok=.3,price_output_per_mtok=1.2,cost_cap_usd=job['cap_usd'])
    check=SCEEnvironmentProvider(env.model_copy(deep=True));check.audit_dir=None;check.reset(cfg.seed);check.advance_to(1)
    decision=HouseholdFinanceDecision(**{**cfg.decision_args,'llm_kind':'scripted'})
    previews={r['agent_id']:r['prompt_sha256'] for r in json.loads((dest/f"preview_{job['arm']}.json").read_text())}
    if set(previews)!={p.agent_id for p in pop.personas}:raise ValueError('preview roster mismatch')
    for ob in check.observe_batch([p.agent_id for p in pop.personas],1):
        if message_hash(decision.build_llm_messages(ob))!=previews[ob.agent_id]:raise ValueError('actual message drift')
    shutil.copy2(payload_path,audit/'household_finance_payloads.json')
    shutil.copy2(dest/f"preview_{job['arm']}.json",audit/'frozen_preview.json')
    for name,bundle in [('population_effective',pop),('environment_effective',env),('simulation_effective',cfg)]:
        dump(audit/(name+'.json'),bundle.model_dump(mode='json'))
    sim=build_simulator(env_bundle=env,pop_bundle=pop,sim_config=cfg,store_path=audit/'study.duckdb')
    statuses=Counter();base=sim.decision.decide_batch
    def counted(obs,memories):
        actions=base(obs,memories);statuses.update(str(a.payload.get('validation_status')) for a in actions);return actions
    sim.decision.decide_batch=counted
    started=datetime.now(timezone.utc).isoformat();completed=False
    try:
        sim.run()
        cost=sim.decision.cost_summary()
        if sum(statuses.values())!=n or cost['call_count']!=(0 if scripted else n):
            raise RuntimeError('incomplete job; preserve without retry')
        completed=True
    finally:
        cost=sim.decision.cost_summary()
        result={'run_id':run_id,'month':job['month'],'arm':job['arm'],'repeat':job['repeat'],
        'n':n,'llm_kind':'scripted' if scripted else 'openai','started_at_utc':started,
        'finished_at_utc':datetime.now(timezone.utc).isoformat(),'cost':cost,
        'decisions_by_validation_status':dict(statuses),'source_snapshot_sha256':hashes,
        'status':'completed' if completed else 'stopped_partial_no_retry',
        'actual_input_hashes_match':True,'protocol_sha256':m['protocol_sha256'],
        'household_finance_payloads_sha256':sha(payload_path),'new_api_calls':cost['call_count']}
        dump(audit/'run_manifest.json',result);dump(audit/'cost_ledger.json',cost)
    print(json.dumps({'month':job['month'],'arm':job['arm'],'repeat':job['repeat'],'statuses':dict(statuses),
                      'cost':cost['estimated_cost_usd']}),flush=True)


def dispatch(folder,scripted,workers):
    m=verify(folder)
    if not 1<=workers<=4:raise ValueError('workers must be 1..4')
    if not scripted:
        authorization_gate(folder,m)
    exported=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/export_study_runtime.py')],cwd=ROOT,capture_output=True,text=True)
    if exported.returncode:raise RuntimeError(exported.stdout+exported.stderr)
    for job in m['jobs']:
        if (ROOT/'outputs/local_runs'/(job['run_id']+('-engineering' if scripted else ''))).exists():
            raise ValueError('existing job: no automatic rerun/resume')
    def one(index):
        job=m['jobs'][index];log=folder/(job['run_id']+('-engineering' if scripted else '')+'.log')
        cmd=[sys.executable,'-B',str(Path(__file__).resolve()),'worker','--folder',str(folder),'--job-index',str(index)]
        if scripted:cmd.append('--scripted')
        childenv=dict(os.environ,OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        with log.open('x') as handle:rc=subprocess.run(cmd,cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT,env=childenv).returncode
        print(job['month'],job['arm'],job['repeat'],'completed' if rc==0 else 'stopped',flush=True)
        return {'job_index':index,'run_id':job['run_id'],'exit_code':rc}
    results=[];next_index=0;failed=False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        active={}
        while next_index<len(m['jobs']) and len(active)<workers:
            active[pool.submit(one,next_index)]=next_index;next_index+=1
        while active:
            done,_=wait(active,return_when=FIRST_COMPLETED)
            for future in done:
                active.pop(future)
                result=future.result();results.append(result);failed=failed or bool(result['exit_code'])
            dump(folder/('engineering_checks.json' if scripted else 'real_dispatch.json'),results)
            # Finish only already-running jobs after an error; no further jobs,
            # no cancellation of a request whose usage may already be billed.
            while not failed and next_index<len(m['jobs']) and len(active)<workers:
                active[pool.submit(one,next_index)]=next_index;next_index+=1
    if any(r['exit_code'] for r in results):raise RuntimeError('one or more cells stopped; no automatic retry')


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','dry-run','run','worker'])
    p.add_argument('--folder',type=Path,required=True);p.add_argument('--workers',type=int,default=4)
    p.add_argument('--job-index',type=int);p.add_argument('--scripted',action='store_true');args=p.parse_args()
    folder=args.folder.resolve()
    if args.action=='prepare':
        from studies.sce_inflation_expectations.household_finance_preparation import prepare
        m=prepare(folder);print('prepared',m['planned_calls'],'requests; reserve',round(m['conservative_reservation_usd'],4),'cap',m['proposed_cap_usd']);return
    if args.action=='worker':return worker(folder,args.job_index,args.scripted)
    dispatch(folder,args.action=='dry-run',args.workers)


if __name__=='__main__':main()
