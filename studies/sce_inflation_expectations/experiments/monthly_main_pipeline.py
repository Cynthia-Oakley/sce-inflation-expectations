"""One explicitly authorized launch; generation and truth evaluation are separate processes."""
from pathlib import Path
import subprocess,sys
from .frozen_batch import ROOT,read_json,dump,sha
from .state_continuity_execution import verify


def plan(package,calls,truth,evaluation,registry,readout):
    package,calls,truth,evaluation,registry,readout=map(lambda x:Path(x).resolve(),(package,calls,truth,evaluation,registry,readout))
    p,m=verify(package)
    tm=read_json(truth/'manifest.json')
    if tm['protocol_sha256']!=m['protocol_sha256']:raise ValueError('Truth must match the frozen candidate package')
    for name,key in [('truth_private.json','truth_sha256'),('full_wave_private.json','full_wave_sha256')]:
        if sha(truth/name)!=tm[key]:raise ValueError('Isolated truth changed')
    for name,digest in tm.get('analysis_source_sha256',{}).items():
        if sha(ROOT/name)!=digest:raise ValueError('Frozen evaluation dependency changed: '+name)
    if p.get('grid_version')!='education_numeracy_age_income_54_v1' or p.get('strict_B_eligible'):
        raise ValueError('Registered 54-cell historical-A pipeline required')
    for f in [calls,evaluation,readout]:
        if f.exists() or not f.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored stage outputs required')
    all_paths=[package,calls,truth,evaluation,registry,readout]
    if any(a==b or a in b.parents or b in a.parents for i,a in enumerate(all_paths) for b in all_paths[i+1:]):
        raise ValueError('Disjoint execution/evaluation paths required')
    script=lambda n:str(ROOT/'scripts'/n)
    commands=[
        [sys.executable,script('run_sce_monthly_reconstruction.py'),'run','--package',str(package),'--out',str(calls)],
        [sys.executable,script('evaluate_sce_monthly_reconstruction.py'),'evaluate','--package',str(package),
         '--calls',str(calls),'--truth',str(truth),'--out',str(evaluation)],
        [sys.executable,script('readout_sce_monthly_main.py'),'--package',str(package),'--evaluation',str(evaluation),
         '--truth',str(truth),'--registry',str(registry),'--out',str(readout)]]
    return dict(status='offline_plan_not_execution',protocol_sha256=m['protocol_sha256'],commands=commands,
                planned_calls=p['planned_calls'],budget_cap_usd=p['budget_cap_usd'],
                authorization_file_exists=(package/'authorization.json').exists(),new_api_calls=0)


def execute(package,calls,truth,evaluation,registry,readout,out):
    args=[package,calls,truth,evaluation,registry,readout];review=plan(*args)
    package,out=Path(package).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh private orchestration folder required')
    if any(out==Path(v).resolve() or out in Path(v).resolve().parents or Path(v).resolve() in out.parents for v in args):
        raise ValueError('Pipeline receipt folder must be disjoint from all stages')
    p,m=verify(package);a=read_json(package/'authorization.json')
    if not a.get('approved') or a['protocol_sha256']!=m['protocol_sha256']:raise ValueError('Existing human authorization required')
    for k in ('planned_calls','budget_cap_usd','destination','model','route'):
        if a.get(k)!=p[k]:raise ValueError('Authorization scope mismatch: '+k)
    if (package/'execution_registration.json').exists():raise ValueError('Never restart an attempted package')
    out.mkdir(parents=True);dump(out/'plan.json',review)
    for i,command in enumerate(review['commands']):
        with (out/f'phase_{i+1}.log').open('x') as log:
            done=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        if done.returncode:
            result=dict(status='stopped_no_automatic_restart',phase=i+1,exit_code=done.returncode)
            dump(out/'receipt.json',result);return result
        if i==0:
            r=read_json(Path(calls)/'receipt.json')
            if r['status']!='completed' or r['attempts']!=p['planned_calls']:
                result=dict(status='generation_stopped_no_evaluation',receipt=r)
                dump(out/'receipt.json',result);return result
    result=dict(status='generation_and_separate_process_evaluation_complete',protocol_sha256=m['protocol_sha256'],
                call_receipt=str((Path(calls)/'receipt.json').resolve().relative_to(ROOT)),
                aggregate_readout=str((Path(readout)/'summary.json').resolve().relative_to(ROOT)))
    dump(out/'receipt.json',result);return result
