"""Freeze existing grocery views for locked Qwen, with a reusable format gate."""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from .frozen_batch import ROOT, dump, read_json, sha
from .model_migration import validate_transport
from .procurement_prices import ARMS, PARENT
from ..model_counterfactual import preflight
from ..output_format_example import FORMAT_VERSION, append_format_example
from ..prior_belief_experiment import message_hash

MECHANISM = 'procurement_price_qwen'
MONTHS = [202009, 202109, 202206, 202312, 202410, 202503]
GATE_MONTHS = [202206, 202503]


def segments(month):
    return ([{'name': 'gate', 'n': 12, 'phase': 'gate'},
             {'name': 'remainder', 'n': 84, 'phase': 'main'}] if month in GATE_MONTHS
            else [{'name': 'all', 'n': 96, 'phase': 'main'}])


def ordered_ids(ids, month):
    """Predetermined selection uses anonymous IDs and month, never outcomes."""
    return sorted(ids, key=lambda aid: hashlib.sha256(
        f'sce-procurement-format-gate-v1|{month}|{aid}'.encode()).hexdigest())


def prepare(out, config):
    validate_transport(config)
    out = Path(out).resolve(); source = (ROOT/config['source_preparation']).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs') or not source.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output and existing local source required')
    if (config['mechanism'] != MECHANISM or config['months'] != MONTHS
            or config['n_per_month'] != 96 or config['arms'] != ARMS
            or config['generation_repeats'] != [1, 2] or config['allocation_seed'] != 20261019
            or config['temperature'] != .5 or config['max_tokens'] != 1024 or config['retry_max'] != 0):
        raise ValueError('One fixed 3456-call procurement protocol required')
    metadata = (ROOT/config['provider_metadata']).resolve()
    preflight({'route_candidate': config['route'], 'input_price_per_million': config['price_input_per_mtok'],
               'output_price_per_million': config['price_output_per_mtok']}, read_json(metadata))
    original = read_json(source/'manifest.json'); summary = read_json(source/'summary.json')
    if summary['months'] != MONTHS or summary['status'] != 'offline_complete_prompts_not_engine_or_paid_trial':
        raise ValueError('Completed original six-month preparation required')
    sources = {}
    for name, digest in original['source_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Original preparation source drift: '+name)
    for name, digest in original['output_sha256'].items():
        if sha(source/name) != digest:
            raise ValueError('Original prepared view drift: '+name)
    sources[str((source/'manifest.json').relative_to(ROOT))] = sha(source/'manifest.json')
    sources[str(metadata.relative_to(ROOT))] = sha(metadata)
    parent = read_json(PARENT/'manifest.json')
    def frozen(name):
        path = PARENT/name
        if sha(path) != parent['prepared_file_sha256'][name]:
            raise ValueError('Original frozen P/E/roster drift: '+name)
        sources[str(path.relative_to(ROOT))] = sha(path)
        return read_json(path)
    links = frozen('evaluation_links_private.json')
    truth = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json'
    sources[str(truth.relative_to(ROOT))] = sha(truth)  # Pin, do not read targets.
    jobs = []; maximum = 0; reserve = estimate = 0.
    out.mkdir(parents=True)
    for month in MONTHS:
        dest = out/str(month); dest.mkdir()
        population = frozen(f'{month}/population.json')
        environment = frozen(f'{month}/environment.json')
        simulation = frozen(f'{month}/simulation.json'); simulation['decision_args'] = {}
        people = {r['agent_id']: r for r in population['personas']}
        if len(people) != 96 or len(population['personas']) != 96:
            raise ValueError('Original 96-person roster required')
        ids = ordered_ids(people, month)
        prompts = {}
        for arm in ARMS:
            path = source/str(month)/f'prompts_{arm}_s{config["allocation_seed"]}.json'
            sources[str(path.relative_to(ROOT))] = sha(path)
            bundle = read_json(path)
            if bundle['month'] != month or bundle['arm'] != arm or set(bundle['rows']) != set(ids):
                raise ValueError('Original prompt/roster mismatch')
            for row in bundle['rows'].values():
                row['messages'] = append_format_example(row['messages'])
                row['prompt_sha256'] = message_hash(row['messages'])
                maximum = max(maximum, len(json.dumps(row['messages'], ensure_ascii=False)))
            prompts[arm] = bundle
            dump(dest/f'prompts_{arm}.json', bundle)
        for name, value in [('population', population), ('environment', environment), ('simulation', simulation)]:
            dump(dest/f'{name}.json', value)
        offset = 0
        for segment in segments(month):
            selected = ids[offset:offset+segment['n']]; offset += segment['n']
            part = dest/segment['name']; part.mkdir()
            pop = deepcopy(population); pop['personas'] = [people[i] for i in selected]
            for name, value in [('population', pop), ('environment', environment), ('simulation', simulation)]:
                dump(part/f'{name}.json', value)
            for arm in ARMS:
                bundle = deepcopy(prompts[arm]); bundle['rows'] = {i: bundle['rows'][i] for i in selected}
                dump(part/f'prompts_{arm}.json', bundle)
                sizes = [len(json.dumps(r['messages'], ensure_ascii=False).encode()) for r in bundle['rows'].values()]
                bound = sum(((n+1024)*config['price_input_per_mtok']+1024*config['price_output_per_mtok'])/1e6 for n in sizes)
                guess = sum((n/4*config['price_input_per_mtok']+300*config['price_output_per_mtok'])/1e6 for n in sizes)
                for repeat in [1, 2]:
                    cap = math.ceil(bound*1e6)/1e6; reserve += cap; estimate += guess
                    jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'seed': 41+repeat,
                        'segment': segment['name'], 'phase': segment['phase'],
                        'run_id': f'{out.name}-{month}-{arm}-{segment["name"]}-r{repeat}', 'cap_usd': cap})
    if reserve > config['budget_cap_usd']:
        raise ValueError('Conservative reservation exceeds batch cap')
    jobs.sort(key=lambda j: (j['phase'] != 'gate', j['month'], ARMS.index(j['arm']), j['repeat']))
    protocol = {**config, 'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'planned_calls': 3456, 'max_prompt_chars': maximum+100,
        'roster_segments': {str(m): segments(m) for m in MONTHS},
        'technical_gate': {'planned_calls': 144, 'months': GATE_MONTHS,
            'n_per_month': 12, 'minimum_valid_fraction': .99, 'criterion':
            'All 144 requests complete; >=99% strict nested numeric Q8/Q9, sum valid, finish=stop; locked route. No fitting gate.'},
        'output_format_version': FORMAT_VERSION,
        'evaluation_truth': str(truth.relative_to(ROOT)),
        'research_line': 'A_conditional_returner_mechanism_development',
        'primary_metric': 'cross_section_w1_pp',
        'primary_comparison': ['shuffled_role', 'matched_role'],
        'additional_comparisons': [['shared_price', 'matched_role'], ['shared_price', 'shuffled_role']],
        'scientific_rule': 'Technical pass permits remaining 3312 calls regardless of pilot accuracy. '
            'Development signal requires primary W1 paired interval upper bound <0, '
            'matched update W1 no worse than shuffled, and >=99% valid/scorable per arm. '
            'No automatic default upgrade; independent months and allocation seeds required.',
        'macro_center_role': 'Report raw MAE/RMSE and persistence; no fitted blend or claim of independent validation.',
        'limits': ['Six previously inspected months; synthetic procurement roles and national category price proxies.',
            'Role-to-visible-count 0/1/3/6/6 is an experimental assumption, not an estimated ATUS coefficient.',
            'Real previous personal answers are authorized A-line conditions, not autonomous B-line predictions.',
            'One fixed role allocation seed and two generations; repeated draws are not more people.',
            'Hosted weights/cutoff not fully verified; model held fixed across mechanism arms only.']}
    dump(out/'protocol.json', protocol); dump(out/'evaluation_links_private.json', links)
    for p in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        sources[str(p.relative_to(ROOT))] = sha(p)
    sources['scripts/run_sce_frozen_trial.py'] = sha(ROOT/'scripts/run_sce_frozen_trial.py')
    manifest = {'jobs': jobs, 'planned_calls': 3456, 'new_api_calls': 0,
        'protocol_sha256': sha(out/'protocol.json'), 'source_sha256': sources,
        'prepared_file_sha256': {str(p.relative_to(out)): sha(p) for p in out.rglob('*.json')},
        'estimated_cost_usd': estimate, 'conservative_reservation_usd': reserve,
        'gate_estimated_cost_usd': sum(j['cap_usd'] for j in jobs if j['phase']=='gate')}
    manifest['gate_conservative_reservation_usd'] = manifest.pop('gate_estimated_cost_usd')
    dump(out/'manifest.json', manifest)
    dump(out/'authorization.json', {'approved': False, 'protocol_sha256': manifest['protocol_sha256'],
        'cap_usd': config['budget_cap_usd'], 'planned_calls': 3456,
        'destination': config['destination'], 'user_confirmation': None})
    print(f'Prepared 144-call gate +3312 remaining; estimate ${estimate:.3f}, reserve ${reserve:.3f}', flush=True)
    return manifest
