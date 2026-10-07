#!/usr/bin/env python3
"""Offline matched model inputs from completed DeepSeek runs; no API/key access."""
import argparse,copy,hashlib,json,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from socioverse.schemas import EnvironmentBundle,PopulationBundle
from studies.sce_inflation_expectations.model import SCEEnvironmentProvider,build_sce_messages_v2

RUNS=['sce-local-openai-20261005T092656Z-202105-8d2e3b2c','sce-local-openai-20261005T092656Z-202106-e4f49f76']
MODELS=[('qwen/qwen-2.5-72b-instruct','deepinfra/fp8',.36,.40),
        ('meta-llama/llama-3.1-70b-instruct','deepinfra/turbo',.40,.40)]


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    references=[];request_rows=[];source_hashes={};preview_hashes={};observed_max=0
    for run_id in RUNS:
        folder=ROOT/'outputs/local_runs'/run_id
        paths=[folder/name for name in ['llm_calls.jsonl','population_effective.json','environment_effective.json']]
        source_hashes.update({str(p.relative_to(ROOT)):digest(p) for p in paths})
        calls=[json.loads(l) for l in paths[0].read_text().splitlines() if l]
        population=json.loads(paths[1].read_text());environment=json.loads(paths[2].read_text())
        if len(calls)!=300 or len({r['agent_id'] for r in calls})!=300:raise ValueError('need complete one-attempt baseline panel')
        ids=sorted(r['agent_id'] for r in calls);month=calls[0]['target_month']
        rng=np.random.default_rng(np.random.SeedSequence([42,int(month.replace('-','')),20261007]))
        chosen=sorted(rng.choice(ids,size=20,replace=False).tolist())
        people={p['agent_id']:p for p in population['personas']};call_map={r['agent_id']:r for r in calls}
        pop=copy.deepcopy(population);pop['personas']=[people[u] for u in chosen];pop['materialized_count']=20
        PopulationBundle.model_validate(pop)
        environment['provider_args'].pop('audit_dir',None);environment['provider_args'].pop('run_id',None)
        environment['provider_args']['persona_by_id']={u:people[u]['attributes'] for u in chosen}
        bundle=EnvironmentBundle.model_validate(environment);env=SCEEnvironmentProvider(bundle);env.reset(42);env.advance_to(1)
        observations={ob.agent_id:ob for ob in env.observe_batch(chosen,1)}
        inputs=args.out/month;inputs.mkdir();write(inputs/'population.json',pop);write(inputs/'environment.json',environment)
        for i,u in enumerate(chosen):
            row=call_map[u]
            if row['temperature']!=.5 or row['prompt_version']!='sce-q8-q9-v2-abstract' or row['max_tokens']!=1024 or row.get('error'):
                raise ValueError('reference config/error mismatch')
            text=row['prompt_text']
            if hashlib.sha256(text.encode()).hexdigest()!=row['prompt_sha256']:raise ValueError('reference prompt hash mismatch')
            messages=build_sce_messages_v2(observations[u],include_event_abstracts=True)
            if messages!=json.loads(text):raise ValueError('actual provider render differs from saved reference messages')
            if u in json.dumps(messages):raise ValueError('source identity embedded in transmitted messages')
            case=f'{month}_case_{i+1:02d}';preview_hashes[case]=row['prompt_sha256']
            observed_max=max(observed_max,int(row['usage']['prompt_tokens']))
            references.append({'case_id':case,'source_run_id':run_id,'source_agent_id':u,'reference_model':row['returned_model'],
                               'reference_response':row['raw_response_text'],'prompt_sha256':row['prompt_sha256']})
            for model,tag,pin,pout in MODELS:
                payload={'model':model,'messages':messages,'temperature':.5,'max_tokens':1024,
                         'response_format':{'type':'json_object'},
                         'provider':{'order':[tag],'allow_fallbacks':False,'require_parameters':True}}
                # IDs/reference answers remain outside the request body.
                request_rows.append({'case_id':case,'payload':payload,'route_candidate':tag,'input_price_per_million':pin,'output_price_per_million':pout})
    tokens=int(np.ceil(observed_max*1.5));costs={}
    for model,tag,pin,pout in MODELS:
        costs[model]={'target_answers':40,'max_attempts_with_one_retry':80,'input_token_budget_per_attempt':tokens,
                      'estimated_upper_token_cost_usd':80*(tokens*pin+1024*pout)/1e6,'route_candidate':tag}
    (args.out/'requests_prepared.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in request_rows))
    (args.out/'deepseek_reference_private.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in references))
    summary={'status':'prepared only; no model endpoint calls; provider health and budget not authorized',
             'reference_cases':len(references),'new_target_answers':len(request_rows),'per_model':costs,
             'reference_prompt_tokens_max':observed_max,'temperature':.5,'prompt_version':'sce-q8-q9-v2-abstract',
             'actual_provider_messages_matched_reference':True,'source_hashes':source_hashes,'case_prompt_hashes':preview_hashes,
             'no_true_sce_answers_in_requests':True,'real_llm_calls':0,
             'priority':'Qwen first; Llama route requires fresh health/parameter verification; no silent provider fallback',
             'limitations':['small A-line model sensitivity check; not national or B prediction validation',
                            'earlier models may still contain 2021 knowledge','only one generation per model/person; random and provider effects remain']}
    write(args.out/'summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['source_hashes','case_prompt_hashes']}))

if __name__=='__main__':main()
