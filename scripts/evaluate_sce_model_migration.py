"""Score complete model-migration months after a stopped batch, without reruns.

The original packages/receipts remain immutable. A derived evaluation-only
manifest selects months solely by complete repeated jobs, never by accuracy.
"""
import argparse
from pathlib import Path
import sys
from collections import Counter
from run_sce_frozen_trial import ROOT
from studies.sce_inflation_expectations.experiments.frozen_batch import verify,read_json,dump,sha
from studies.sce_inflation_expectations.evaluation.frozen_trial import evaluate


def main(folder,scope,out):
    folder,scope,out=folder.resolve(),scope.resolve(),out.resolve();m,p=verify(folder)
    if scope.exists() or not scope.is_relative_to(ROOT/'outputs') or out.exists():
        raise ValueError('Fresh ignored scope and evaluation directories required')
    if p['mechanism']!='fixed_model_migration':raise ValueError('Only a model migration is supported')
    completed=[]
    for month in p['months']:
        jobs=[j for j in m['jobs'] if j['month']==month]
        good=True
        for j in jobs:
            path=ROOT/'outputs/local_runs'/j['run_id']/'run_manifest.json'
            # A dispatched but unfinished worker must finish before selecting scope.
            if path.parent.exists() and not path.exists():raise ValueError('A worker is still running')
            good &= path.exists() and read_json(path)['status']=='completed'
        if good:completed.append(month)
    if not completed:raise ValueError('No fully completed month')
    jobs=[j for j in m['jobs'] if j['month'] in completed];sources=dict(m['source_sha256']);reused={}
    for j in jobs:
        d=ROOT/'outputs/local_runs'/j['run_id'];rec=read_json(d/'run_manifest.json')
        reused[j['run_id']]=rec['protocol_sha256']
        for name in ['run_manifest.json','llm_calls.jsonl','study.duckdb']:
            sources[str((d/name).relative_to(ROOT))]=sha(d/name)
    for name in ['manifest.json','protocol.json','real_dispatch.json']:
        sources[str((folder/name).relative_to(ROOT))]=sha(folder/name)
    sources[str(Path(__file__).resolve().relative_to(ROOT))]=sha(Path(__file__))
    scope.mkdir()
    for name in m['prepared_file_sha256']:
        if name=='protocol.json':continue
        if name=='evaluation_links_private.json':
            value=[r for r in read_json(folder/name) if r['month'] in completed]
        elif '/' in name and int(name.split('/')[0]) not in completed:continue
        else:value=read_json(folder/name)
        (scope/name).parent.mkdir(parents=True,exist_ok=True);dump(scope/name,value)
    protocol={**p,'months':completed,'planned_calls':len(jobs)*p['n_per_month'],'new_planned_calls':0,
        'reused_completed_jobs':reused,'evaluation_only':True,'analysis_of_trial':str(folder.relative_to(ROOT)),
        'planned_original_months':p['months'],'excluded_incomplete_months':[v for v in p['months'] if v not in completed],
        'selection_rule':'Include a month only if every originally planned arm/repeat job completed; no selection by outcome or validity.',
        'completion_note':'Evaluation-only reuse. This artifact cannot authorize or generate new model answers.'}
    dump(scope/'protocol.json',protocol)
    manifest={**m,'jobs':jobs,'planned_calls':protocol['planned_calls'],'new_planned_calls':0,'protocol_sha256':sha(scope/'protocol.json'),
        'prepared_file_sha256':{str(f.relative_to(scope)):sha(f) for f in scope.rglob('*.json')},'source_sha256':sources}
    dump(scope/'manifest.json',manifest)
    dump(scope/'authorization.json',{'approved':False,'reason':'Evaluation-only; no new API requests permitted.'})
    verify(scope);result=evaluate(scope,out)
    dump(out/'partial_scope_receipt.json',{'original_trial':str(folder.relative_to(ROOT)),'included_months':completed,
        'excluded_incomplete_months':protocol['excluded_incomplete_months'],'new_api_calls':0,'evaluated_responses':len(jobs)*p['n_per_month'],
        'selection_rule':protocol['selection_rule'],'original_manifest_sha256':sha(folder/'manifest.json')})
    print('Complete-month evaluation:',completed,'Excluded:',protocol['excluded_incomplete_months'],'New API calls: 0')


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('--folder',type=Path,required=True);a.add_argument('--scope',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    q=a.parse_args();main(q.folder,q.scope,q.out)
