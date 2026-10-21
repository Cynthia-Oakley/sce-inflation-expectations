"""Prepare a single Qwen migration arm; reuse exactly matched DeepSeek answers."""
from copy import deepcopy
from pathlib import Path
import json
import math
from .frozen_batch import ROOT,read_json,dump,sha

MODEL='qwen/qwen-2.5-72b-instruct'
ROUTE='deepinfra/fp8'
PARENT=ROOT/'outputs/sce_temperature_trial_20261019_v1'
BASELINE=ROOT/'outputs/sce_temperature_evaluation_20261019_v1'


def validate_transport(protocol):
    if protocol.get('mechanism') == 'v32_same_input':
        from .model_comparison import validate_v32_transport
        return validate_v32_transport(protocol)
    prices={'prompt':protocol['price_input_per_mtok'],'completion':protocol['price_output_per_mtok']}
    expected={'provider':{'order':[ROUTE],'allow_fallbacks':False,'require_parameters':True,'max_price':prices}}
    if (protocol.get('transport')!='openrouter_locked' or protocol['destination']!='https://openrouter.ai/api/v1'
            or protocol['model']!=MODEL or protocol.get('route')!=ROUTE or protocol['thinking']!='disabled'
            or protocol.get('request_extra_body')!=expected):
        raise ValueError('Registered Qwen model, destination, route and price lock required')


def prepare(out,config):
    validate_transport(config);out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored directory required')
    if (config['mechanism']!='fixed_model_migration' or config['arms']!=['qwen'] or config['n_per_month']!=24
            or config['months']!=[202004,202105,202111,202203] or config['generation_repeats']!=[1,2]
            or config['temperature']!=.5 or config['retry_max']!=0):
        raise ValueError('Registered 192-call one-model migration only')
    parent=read_json(PARENT/'manifest.json');sources={}
    def frozen(name):
        p=PARENT/name
        if sha(p)!=parent['prepared_file_sha256'][name]:raise ValueError('Archived input drift')
        sources[str(p.relative_to(ROOT))]=sha(p);return read_json(p)
    previous=frozen('protocol.json');links=frozen('evaluation_links_private.json')
    for name in ['evaluation_truth','evaluation_bin_reference']:
        p=ROOT/previous[name]
        if sha(p)!=parent['source_sha256'][previous[name]]:raise ValueError('Archived truth drift')
        sources[previous[name]]=sha(p)  # Pin targets without reading.
    for name in ['summary.json','cases_private.json']:
        sources[str((BASELINE/name).relative_to(ROOT))]=sha(BASELINE/name)
    jobs=[];reserve=estimate=0.;maximum=0;out.mkdir(parents=True)
    for month in config['months']:
        dest=out/str(month);dest.mkdir()
        for name in ['population.json','environment.json','simulation.json']:
            dump(dest/name,frozen(f'{month}/{name}'))
        baseline=frozen(f'{month}/prompts_baseline.json');dump(dest/'prompts_baseline.json',baseline)
        migrated=deepcopy(baseline);migrated['arm']='qwen';dump(dest/'prompts_qwen.json',migrated)
        if len(baseline['rows'])!=24:raise ValueError('Exactly matching old roster required')
        sizes=[len(json.dumps(v['messages'],ensure_ascii=False).encode()) for v in baseline['rows'].values()]
        maximum=max(maximum,max(len(json.dumps(v['messages'],ensure_ascii=False)) for v in baseline['rows'].values()))
        bound=sum(((n+1024)*config['price_input_per_mtok']+1024*config['price_output_per_mtok'])/1e6 for n in sizes)
        guess=sum((n/4*config['price_input_per_mtok']+300*config['price_output_per_mtok'])/1e6 for n in sizes)
        for repeat in [1,2]:
            cap=math.ceil(bound*1e6)/1e6;reserve+=cap;estimate+=guess
            jobs.append({'month':month,'arm':'qwen','repeat':repeat,'seed':41+repeat,
                         'run_id':f'{out.name}-{month}-qwen-r{repeat}','cap_usd':cap})
    if reserve>config['budget_cap_usd']:raise ValueError('Conservative reservation exceeds cap')
    protocol={**config,'planned_calls':192,'max_prompt_chars':maximum+100,
        'evaluation_truth':previous['evaluation_truth'],'evaluation_bin_reference':previous['evaluation_bin_reference'],
        'evaluation_truth_format':'legacy_revision_format','reuse_baseline_trial':str(PARENT.relative_to(ROOT)),
        'reuse_baseline_evaluation':str(BASELINE.relative_to(ROOT)),
        'research_line':'A_conditional_returner_development','comparison':'Same direct Q8/Q9 messages; Qwen newly generated, archived DeepSeek .5 repeats 1/2 reused.',
        'primary_metric':'cross_section_w1_pp','macro_center_role':'Descriptive; no automatic veto or default-upgrade from raw center MAE.',
        'technical_gate':'192 responses complete; >=99% valid and scorable; locked model/provider; zero retries. Not a scientific success gate.',
        'limits':['Four inspected months, 24/month, no national or independent validation claim.',
                  'Archived DeepSeek control is not a contemporaneously randomized model comparison.',
                  'Same numerical temperature does not equate randomness across different models.',
                  'Hosted weight revision and full knowledge cutoff remain unverified; no leakage-free claim.',
                  'No macro blending weights fitted on these four outcome months.']}
    dump(out/'protocol.json',protocol);dump(out/'evaluation_links_private.json',links)
    metadata=ROOT/config['provider_metadata']
    sources[str(metadata.relative_to(ROOT))]=sha(metadata)
    for p in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):sources[str(p.relative_to(ROOT))]=sha(p)
    sources['scripts/run_sce_frozen_trial.py']=sha(ROOT/'scripts/run_sce_frozen_trial.py')
    manifest={'jobs':jobs,'planned_calls':192,'protocol_sha256':sha(out/'protocol.json'),
        'prepared_file_sha256':{str(p.relative_to(out)):sha(p) for p in out.rglob('*.json')},
        'source_sha256':sources,'estimated_cost_usd':estimate,'conservative_reservation_usd':reserve,'new_api_calls':0}
    dump(out/'manifest.json',manifest)
    dump(out/'authorization.json',{'approved':False,'protocol_sha256':manifest['protocol_sha256'],
        'cap_usd':config['budget_cap_usd'],'planned_calls':192,'destination':config['destination'],'user_confirmation':None})
    print(f'Prepared 8 units/192 new calls; estimate ${estimate:.3f}, reserve ${reserve:.3f}, cap ${config["budget_cap_usd"]:.2f}',flush=True)
    return manifest


def prepare_completion(out, config):
    """New sealed package, explicit authorization, no overwrite or automatic retry.

    Reuse only complete 24-response jobs. A stopped job is generated as a fresh
    whole unit; its partial answers remain archived and never enter evaluation.
    """
    parent=(ROOT/config['completion_of']).resolve();out=Path(out).resolve()
    if (config.get('retry_interrupted_unit_once') is not True or out.exists()
            or not parent.is_relative_to(ROOT/'outputs') or not out.is_relative_to(ROOT/'outputs')):
        raise ValueError('Explicit one-time fresh completion required')
    original=read_json(parent/'manifest.json');protocol=read_json(parent/'protocol.json')
    validate_transport(protocol)
    if protocol.get('reused_completed_jobs') or protocol['mechanism']!='fixed_model_migration':
        raise ValueError('Only an initial registered migration may be completed once')
    if sha(parent/'protocol.json')!=original['protocol_sha256']:
        raise ValueError('Original protocol drift')
    for name,digest in original['prepared_file_sha256'].items():
        if sha(parent/name)!=digest:raise ValueError('Original frozen inputs changed')
    sources={}
    for name,digest in original['source_sha256'].items():
        if name.endswith('.py'):continue  # Original code is preserved in the source snapshot.
        if sha(ROOT/name)!=digest:raise ValueError('Original non-code source drift')
        sources[name]=digest
    for name in ['manifest.json','protocol.json','real_dispatch.json']:
        sources[str((parent/name).relative_to(ROOT))]=sha(parent/name)
    jobs=[];reused={};spent=0.;pending_reserve=0.
    for old in original['jobs']:
        job=deepcopy(old);audit=ROOT/'outputs/local_runs'/old['run_id']
        receipt=read_json(audit/'run_manifest.json') if (audit/'run_manifest.json').exists() else None
        if receipt is not None:spent+=receipt['cost']['estimated_cost_usd']
        if receipt is not None and receipt['status']=='completed':
            if (receipt['protocol_sha256']!=original['protocol_sha256'] or receipt['llm_kind']!='openai'
                    or receipt['cost']['call_count']!=protocol['n_per_month']):
                raise ValueError('Invalid original completed job')
            reused[old['run_id']]=original['protocol_sha256']
            for name in ['run_manifest.json','llm_calls.jsonl','study.duckdb']:
                sources[str((audit/name).relative_to(ROOT))]=sha(audit/name)
            engineering=audit.with_name(audit.name+'-engineering')/'run_manifest.json'
            sources[str(engineering.relative_to(ROOT))]=sha(engineering)
        else:
            job['run_id']=f'{out.name}-{old["month"]}-qwen-r{old["repeat"]}'
            pending_reserve+=job['cap_usd']
        jobs.append(job)
    if len(reused)!=3 or len(jobs)-len(reused)!=5 or spent+pending_reserve>protocol['budget_cap_usd']:
        raise ValueError('Registered 72 reused / 120 new one-time completion and remaining budget required')
    out.mkdir(parents=True)
    for name in original['prepared_file_sha256']:
        if name=='protocol.json':continue
        (out/name).parent.mkdir(parents=True,exist_ok=True)
        dump(out/name,read_json(parent/name))
    protocol={**protocol,'completion_of':str(parent.relative_to(ROOT)),'reused_completed_jobs':reused,
        'new_planned_calls':120,'completion_original_estimated_cost_usd':spent,
        'completion_total_reserved_usd':spent+pending_reserve,
        'completion_note':'192 evaluated responses: 72 original complete jobs plus 120 new requests. '
            'Two original partial successes and one connection error are retained outside the evaluated support. '
            'Original cap includes both packages; no further retries.'}
    dump(out/'protocol.json',protocol)
    for p in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):sources[str(p.relative_to(ROOT))]=sha(p)
    sources['scripts/run_sce_frozen_trial.py']=sha(ROOT/'scripts/run_sce_frozen_trial.py')
    manifest={**original,'jobs':jobs,'new_planned_calls':120,'new_api_calls':0,
        'protocol_sha256':sha(out/'protocol.json'),'source_sha256':sources,
        'prepared_file_sha256':{str(p.relative_to(out)):sha(p) for p in out.rglob('*.json')},
        'conservative_reservation_usd':pending_reserve,'original_spent_plus_new_reserved_usd':spent+pending_reserve}
    dump(out/'manifest.json',manifest)
    dump(out/'authorization.json',{'approved':False,'protocol_sha256':manifest['protocol_sha256'],
        'cap_usd':protocol['budget_cap_usd'],'planned_calls':192,'new_planned_calls':120,
        'destination':protocol['destination'],'user_confirmation':None})
    print(f'Completion prepared: 72 original + 120 new; total conservative ${spent+pending_reserve:.4f} / $1',flush=True)
    return manifest
