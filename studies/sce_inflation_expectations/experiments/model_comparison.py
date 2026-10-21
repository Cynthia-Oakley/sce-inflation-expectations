"""Exact-message V3.2 comparison, reusing paid Qwen controls and shared runners."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

from .frozen_batch import ROOT, dump, read_json, sha
from ..model_counterfactual import preflight
from ..prior_belief_experiment import message_hash
from ..q9_normalization import POLICY

MODEL = 'deepseek/deepseek-v3.2'
ROUTE = 'atlas-cloud/fp8'
PROVIDER = 'AtlasCloud'
MONTHS = [202009, 202109, 202206, 202503]
MECHANISM = 'v32_same_input'
ARM = 'deepseek_v32'


def validate_v32_transport(protocol):
    prices = dict(prompt=.26, completion=.38)
    expected = dict(provider=dict(order=[ROUTE], allow_fallbacks=False,
        require_parameters=True, max_price=prices), reasoning=dict(enabled=False))
    if (protocol.get('mechanism') != MECHANISM or protocol.get('transport') != 'openrouter_locked'
            or protocol.get('destination') != 'https://openrouter.ai/api/v1'
            or protocol.get('model') != MODEL or protocol.get('route') != ROUTE
            or protocol.get('expected_provider') != PROVIDER
            or protocol.get('thinking') != 'disabled'
            or protocol.get('price_input_per_mtok') != .26
            or protocol.get('price_output_per_mtok') != .38
            or protocol.get('request_extra_body') != expected):
        raise ValueError('Registered V3.2 FP8 model/provider/reasoning/price lock required')


def prepare(out, config):
    """Read prompts and old model replies; target answers are only hashed here."""
    validate_v32_transport(config)
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored comparison directory required')
    if (config['months'] != MONTHS or config['n_per_month'] != 96
            or config['arms'] != [ARM] or config['generation_repeats'] != [1,2]
            or config['temperature'] != .5 or config['max_tokens'] != 1024
            or config['retry_max'] != 0 or config['q9_postprocessing'] != POLICY
            or not 1 <= config['max_workers'] <= 16
            or config['queue_technical_gate'] != dict(planned_calls=16,per_month=4,minimum_usable_fraction=.99)):
        raise ValueError('Registered four-month 96-person exact-message comparison required')
    parent = (ROOT/config['source_trial']).resolve()
    ledger = (ROOT/config['source_call_ledger']).resolve()
    evaluation = (ROOT/config['source_evaluation']).resolve()
    paths = (parent,ledger,evaluation,ROOT/config['provider_metadata'])
    if not all(p.is_relative_to(ROOT) for p in paths):
        raise ValueError('Local source evidence required')
    old_manifest = read_json(parent/'manifest.json')
    sources = {}
    def pinned(path, digest=None, load=True):
        actual = sha(path)
        if digest is not None and digest != actual:
            raise ValueError('Frozen source changed: '+str(path.relative_to(ROOT)))
        sources[str(path.relative_to(ROOT))] = actual
        return read_json(path) if load else None
    pinned(parent/'manifest.json')
    old = pinned(parent/'protocol.json', old_manifest['protocol_sha256'])
    if (old['model'] != 'qwen/qwen-2.5-72b-instruct' or old['route'] != 'deepinfra/fp8'
            or any(config[k] != old[k] for k in ('temperature','thinking','max_tokens','q9_postprocessing'))):
        raise ValueError('Archived Qwen sampling and normalization contract required')
    directory = pinned(ROOT/config['provider_metadata'])
    endpoint = preflight(dict(route_candidate=ROUTE,input_price_per_million=.26,
                              output_price_per_million=.38), directory)
    if (directory['data']['id'] != MODEL or endpoint['provider_name'] != PROVIDER
            or endpoint['quantization'] != 'fp8' or 'reasoning' not in endpoint['supported_parameters']):
        raise ValueError('Model identity, FP8 and reasoning-control metadata required')
    receipt = pinned(ledger/'run_receipt.json')
    lp = pinned(ledger/'protocol.json')
    lm = pinned(ledger/'manifest.json')
    if receipt['status'] != 'completed' or sha(ledger/'protocol.json') != lm['protocol_sha256']:
        raise ValueError('Complete archived paid Qwen ledger required')
    for k in ('model','route','temperature','max_tokens','request_extra_body'):
        if lp[k] != old[k]:raise ValueError('Archived transport changed: '+k)
    call_file = ledger/'new_calls_private.jsonl'
    pinned(call_file, load=False)
    controls = {}
    for line in call_file.read_text().splitlines():
        call = json.loads(line)
        if call['month'] not in MONTHS or call['arm'] != 'food_background':continue
        token = (call['month'],call['repeat'],call['agent_id'])
        if token in controls:raise ValueError('Duplicate archived control slot')
        if (call.get('error') or call['attempt_idx'] != 0 or call['returned_model'] != old['model']
                or call['returned_provider'] != 'DeepInfra' or call['extra_body'] != old['request_extra_body']
                or call['temperature'] != .5 or call['max_tokens'] != 1024):
            raise ValueError('Successful one-attempt original Qwen control required')
        controls[token] = call
    if len(controls) != 768:raise ValueError('Exactly 768 archived controls required')
    links = pinned(parent/'evaluation_links_private.json',
                   old_manifest['prepared_file_sha256']['evaluation_links_private.json'])
    links = [r for r in links if r['month'] in MONTHS]
    if len(links) != 384:raise ValueError('Exact original four-month evaluation links required')
    # Pin without reading current human outcomes or cached scored model outcomes.
    pinned(ROOT/old['evaluation_truth'], old_manifest['source_sha256'][old['evaluation_truth']], load=False)
    for name in ('summary.json','cases_private.json'):pinned(evaluation/name, load=False)
    out.mkdir(parents=True)
    jobs=[];maximum=0;reserve=0.;estimate=0.;matched=0
    for month in MONTHS:
        dest=out/str(month);dest.mkdir()
        for name in ('population.json','environment.json','simulation.json'):
            dump(dest/name,pinned(parent/str(month)/name,old_manifest['prepared_file_sha256'][f'{month}/{name}']))
        bundle=pinned(parent/str(month)/'prompts_food_background.json',
                      old_manifest['prepared_file_sha256'][f'{month}/prompts_food_background.json'])
        ids={r['agent_id'] for r in read_json(dest/'population.json')['personas']}
        if len(ids)!=96 or set(bundle['rows'])!=ids:raise ValueError('Same 96-person roster required')
        migrated=deepcopy(bundle);migrated['arm']=ARM
        for aid,row in migrated['rows'].items():
            if message_hash(row['messages'])!=row['prompt_sha256']:raise ValueError('Prompt hash changed')
            maximum=max(maximum,len(json.dumps(row['messages'],ensure_ascii=False)))
            for repeat in (1,2):
                c=controls[month,repeat,aid]
                if c['prompt_sha256']!=row['prompt_sha256'] or c['prompt_text']!=json.dumps(row['messages'],ensure_ascii=False):
                    raise ValueError('Original control and new prompt must be byte-identical')
                usage=c['usage'];estimate+=(usage['prompt_tokens']*.26+usage['completion_tokens']*.38)/1e6
                matched+=1
        dump(dest/f'prompts_{ARM}.json',migrated)
        sizes=[len(json.dumps(r['messages'],ensure_ascii=False).encode()) for r in migrated['rows'].values()]
        cap=math.ceil(sum(((size+1024)*.26+1024*.38)/1e6 for size in sizes)*1e6)/1e6
        for repeat in (1,2):
            reserve+=cap
            jobs.append(dict(month=month,arm=ARM,repeat=repeat,seed=41+repeat,
                run_id=f'{out.name}-{month}-{ARM}-r{repeat}',cap_usd=cap))
    if reserve>config['budget_cap_usd']:raise ValueError('Reservation exceeds requested budget')
    protocol=dict(config,registered_at_utc=datetime.now(timezone.utc).isoformat(),planned_calls=768,
        max_prompt_chars=maximum+100,provider_metadata_mode='frozen_batch_catalog',
        evaluation_truth=old['evaluation_truth'],primary_metric='cross_section_w1_pp',
        primary_comparison=[ARM],additional_comparisons=[],comparison_arms=['qwen_cached',ARM],
        comparison='New V3.2 replies versus 768 archived exact-message Qwen replies; never concurrent controls.',
        research_line='A_conditional_returner_development',
        scientific_rule='Report W1, delta W1, prior-stratum bias/retention, IQR, Q8 and monthly center MAE/RMSE; no automatic default upgrade.',
        macro_center_role='Four inspected months are development evidence; no four-month fit is an independent blend validation.',
        normalization_rule='Finite nonnegative ten-bin probabilities with positive sum are proportionally normalized in evaluation; raw responses retained.',
        limits=['Already inspected development months, not an independent confirmation.',
                'Changing the served model also changes provider/tokenizer/quantization implementation; no parameter-count-only causal claim.',
                'Same numeric temperature does not mean the same generation variance across models.',
                'Complete training cutoff and hosted weight provenance unverified; no leakage-free claim.',
                'Actual previous private responses and synthetic grocery role remain declared A-line conditions.'])
    dump(out/'protocol.json',protocol);dump(out/'evaluation_links_private.json',links)
    for path in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        if 'panel' not in path.relative_to(ROOT/'studies/sce_inflation_expectations').parts:
            sources[str(path.relative_to(ROOT))]=sha(path)
    for name in ('run_sce_frozen_trial.py','evaluate_sce_call_ledger.py','evaluate_sce_model_comparison.py',
                 'continue_sce_pending_calls.py'):
        p=ROOT/'scripts'/name;sources[str(p.relative_to(ROOT))]=sha(p)
    manifest=dict(jobs=jobs,planned_calls=768,new_api_calls=0,reused_control_responses=768,
        exact_message_comparisons=matched,current_target_answers_read=False,
        source_sha256=sources,protocol_sha256=sha(out/'protocol.json'),
        prepared_file_sha256={str(p.relative_to(out)):sha(p) for p in out.rglob('*.json')},
        estimated_cost_usd=estimate,estimate_basis='Archived Qwen token counts repriced at V3.2; different tokenizer/output may change actual cost.',
        conservative_reservation_usd=reserve)
    dump(out/'manifest.json',manifest)
    dump(out/'authorization.json',dict(approved=False,protocol_sha256=manifest['protocol_sha256'],
        cap_usd=config['budget_cap_usd'],planned_calls=768,destination=config['destination'],user_confirmation=None))
    return {k:manifest[k] for k in ('planned_calls','reused_control_responses','exact_message_comparisons',
        'estimated_cost_usd','conservative_reservation_usd','new_api_calls')}
