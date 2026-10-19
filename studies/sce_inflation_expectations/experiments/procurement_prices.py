"""Adapt prepared grocery-price prompts to the shared, zero-spend engine path.

This package intentionally has no live transport or scoring truth. A later real
trial must be newly frozen with an actual model, prices and explicit budget.
"""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from .frozen_batch import ROOT, ENGINEERING_ONLY, read_json, dump, sha

PARENT = ROOT/'outputs/sce_news_breadth_trial_20261019_v2'
ARMS = ['shared_price', 'matched_role', 'shuffled_role']


def prepare(out, config):
    out = Path(out).resolve()
    source = (ROOT/config['source_preparation']).resolve()
    if (out.exists() or not out.is_relative_to(ROOT/'outputs')
            or not source.is_relative_to(ROOT/'outputs')):
        raise ValueError('Fresh ignored destination and local preparation source required')
    if (set(config) != {'mechanism','source_preparation','allocation_seed'}
            or config['mechanism'] != 'procurement_price_engineering'):
        raise ValueError('Engineering adapter does not accept paid model or budget settings')
    original = read_json(source/'manifest.json'); summary = read_json(source/'summary.json')
    if summary['status'] != 'offline_complete_prompts_not_engine_or_paid_trial':
        raise ValueError('Completed offline prompt preparation required')
    if config['allocation_seed'] not in summary['allocation_seeds']:
        raise ValueError('Existing prespecified allocation seed required')
    for name,digest in original['source_sha256'].items():
        path = (ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != digest:
            raise ValueError('Source preparation drift: '+name)
    for name,digest in original['output_sha256'].items():
        path = (source/name).resolve()
        if not path.is_relative_to(source) or sha(path) != digest:
            raise ValueError('Prepared prompt drift: '+name)
    parent = read_json(PARENT/'manifest.json')
    sources = {str((source/'manifest.json').relative_to(ROOT)):sha(source/'manifest.json'),
        str((PARENT/'manifest.json').relative_to(ROOT)):sha(PARENT/'manifest.json')}
    jobs = []; maximum = 0; n = None; seed = config['allocation_seed']
    out.mkdir(parents=True)
    for month in summary['months']:
        dest = out/str(month); dest.mkdir()
        for name in ['population.json','environment.json','simulation.json']:
            rel = f'{month}/{name}'; path = PARENT/rel
            if sha(path) != parent['prepared_file_sha256'][rel]:
                raise ValueError('Original P/E/config changed: '+rel)
            sources[str(path.relative_to(ROOT))] = sha(path)
            value = read_json(path)
            if name == 'simulation.json':
                value = deepcopy(value); value['decision_args'] = {}
            dump(dest/name,value)
        population = read_json(dest/'population.json')
        ids = {r['agent_id'] for r in population['personas']}
        n = len(ids) if n is None else n
        if len(ids) != n:
            raise ValueError('Common configured roster size required')
        for arm in ARMS:
            path = source/str(month)/f'prompts_{arm}_s{seed}.json'
            sources[str(path.relative_to(ROOT))] = sha(path)
            prompts = read_json(path)
            if (prompts['month'] != month or prompts['arm'] != arm or set(prompts['rows']) != ids):
                raise ValueError('Prepared prompt/roster/arm mismatch')
            maximum = max(maximum,max(len(__import__('json').dumps(r['messages'],ensure_ascii=False)) for r in prompts['rows'].values()))
            dump(dest/f'prompts_{arm}.json',prompts)
            jobs.append({'month':month,'arm':arm,'repeat':1,'seed':42,
                'run_id':f'{out.name}-{month}-{arm}-r1','cap_usd':0.})
    protocol = {
        'id':'sce-procurement-price-engineering-v1', 'registered_at_utc':datetime.now(timezone.utc).isoformat(),
        'mechanism':config['mechanism'], 'execution_mode':ENGINEERING_ONLY,
        'source_preparation':config['source_preparation'], 'allocation_seed':seed,
        'months':summary['months'], 'n_per_month':n, 'arms':ARMS, 'generation_repeats':[1],
        'planned_calls':0, 'engineering_decision_count':len(jobs)*n,
        'model':'NOT_CONFIGURED_ENGINEERING_ONLY', 'destination':None,
        'temperature':.5, 'thinking':'disabled', 'max_tokens':1024, 'max_prompt_chars':maximum+100,
        'retry_max':0, 'budget_cap_usd':0., 'price_input_per_mtok':0., 'price_output_per_mtok':0.,
        'research_line':'A_conditional_returner_development',
        'limits':['Scripted engine outputs check integration only, not behavioral efficacy.',
            'One prespecified allocation seed / one engineering generation; not a paid-trial registration.',
            'No current target answers, truth cache or research evaluation in this package.',
            'Live model/destination/prices remain unconfigured; paid execution always rejected.']}
    dump(out/'protocol.json',protocol)
    for path in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        sources[str(path.relative_to(ROOT))] = sha(path)
    sources['scripts/run_sce_frozen_trial.py'] = sha(ROOT/'scripts/run_sce_frozen_trial.py')
    manifest = {'jobs':jobs,'planned_calls':0,'new_api_calls':0,
        'protocol_sha256':sha(out/'protocol.json'), 'source_sha256':sources,
        'prepared_file_sha256':{str(p.relative_to(out)):sha(p) for p in out.rglob('*.json')},
        'status':'engineering_only_no_live_transport','conservative_reservation_usd':0.}
    dump(out/'manifest.json',manifest)
    dump(out/'authorization.json',{'approved':False,'execution_mode':ENGINEERING_ONLY,
        'protocol_sha256':manifest['protocol_sha256'],'planned_calls':0,'cap_usd':0.,
        'destination':None,'user_confirmation':None,
        'note':'Cannot authorize this package for paid execution; freeze a new model-specific package.'})
    print(f'Prepared {len(jobs)} engineering cells / {len(jobs)*n} scripted decisions / 0 model calls',flush=True)
    return manifest
