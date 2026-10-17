"""Prepare additive blocks from a completed frozen batch, without resampling it."""
from copy import deepcopy
import json
import math
from pathlib import Path
from time import perf_counter

from .financial_outlook import add_block
from .frozen_batch import ROOT, dump, read_json, sha


def prepare_blocks(out, config, parent_folder, make_blocks, extra_sources):
    """Adapter supplies blocks/coverage; shared code freezes jobs, scope and costs.

    The callback receives only P and local linkage, never current target answers.
    A previously completed baseline is pinned for later evaluation, not re-run.
    """
    from ..prior_belief_experiment import message_hash
    started = perf_counter(); out, parent_folder = Path(out).resolve(), Path(parent_folder).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Use a fresh ignored output directory')
    parent = read_json(parent_folder/'manifest.json'); old_protocol = read_json(parent_folder/'protocol.json')
    if sha(parent_folder/'protocol.json') != parent['protocol_sha256']:
        raise ValueError('Archived parent protocol changed')
    for key in ('months', 'n_per_month', 'generation_repeats', 'destination', 'model', 'temperature', 'thinking', 'max_tokens', 'retry_max'):
        if config[key] != old_protocol[key]: raise ValueError('Reused baseline must have identical '+key)
    source = {str(p.relative_to(ROOT)): sha(p) for p in extra_sources}
    source[str((parent_folder/'manifest.json').relative_to(ROOT))] = sha(parent_folder/'manifest.json')
    def frozen(name):
        path = parent_folder/name
        if sha(path) != parent['prepared_file_sha256'][name]: raise ValueError('Parent input changed: '+name)
        source[str(path.relative_to(ROOT))] = sha(path); return read_json(path)
    links = frozen('evaluation_links_private.json'); out.mkdir(parents=True)
    dump(out/'evaluation_links_private.json', links)
    coverage = {}; jobs = []; reserve = estimate = 0.; max_chars = 0
    for month in config['months']:
        dest = out/str(month); dest.mkdir()
        pop = frozen(f'{month}/population.json')
        if len(pop['personas']) != config['n_per_month']: raise ValueError('Parent roster count mismatch')
        for name in ('population.json', 'environment.json', 'simulation.json'):
            dump(dest/name, pop if name == 'population.json' else frozen(f'{month}/{name}'))
        previews = frozen(f'{month}/prompts_baseline.json')['rows']
        if set(previews) != {p['agent_id'] for p in pop['personas']}: raise ValueError('Parent prompt roster mismatch')
        # Save byte-identical original prompts for baseline reuse checks after execution.
        dump(dest/'prompts_baseline.json', {'month': month, 'arm': 'baseline', 'rows': previews})
        blocks, records, coverage[str(month)] = make_blocks(month, pop, [r for r in links if r['month'] == month])
        dump(dest/'mechanism_records_private.json', records)
        for arm in config['arms']:
            if set(blocks[arm]) != set(previews): raise ValueError('Mechanism roster mismatch')
            rows = {}
            for aid, preview in previews.items():
                if message_hash(preview['messages']) != preview['prompt_sha256']: raise ValueError('Parent prompt changed')
                changed = add_block(preview['messages'], blocks[arm][aid])
                rows[aid] = {'messages': changed, 'prompt_sha256': message_hash(changed)}
                max_chars = max(max_chars, len(json.dumps(changed, ensure_ascii=False)))
            dump(dest/f'prompts_{arm}.json', {'month': month, 'arm': arm, 'rows': rows})
            bound = sum(((len(json.dumps(r['messages'], ensure_ascii=False).encode())+256)*config['price_input_per_mtok']
                         +config['max_tokens']*config['price_output_per_mtok'])/1e6 for r in rows.values())
            for repeat in config['generation_repeats']:
                cap = math.ceil(bound*1e6)/1e6
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'seed': 41+repeat,
                    'run_id': f'{out.name}-{month}-{arm}-r{repeat}', 'cap_usd': cap})
                reserve += cap
                parent_job = next(j for j in parent['jobs'] if j['month'] == month and j['arm'] == 'baseline' and j['repeat'] == repeat)
                audit = ROOT/'outputs/local_runs'/parent_job['run_id']
                receipt = read_json(audit/'run_manifest.json')
                if receipt['status'] != 'completed' or receipt['protocol_sha256'] != parent['protocol_sha256']:
                    raise ValueError('Completed baseline required')
                estimate += receipt['cost']['estimated_cost_usd']*1.04
                for file in ('run_manifest.json', 'llm_calls.jsonl', 'study.duckdb'):
                    source[str((audit/file).relative_to(ROOT))] = sha(audit/file)
    if reserve > config['budget_cap_usd']: raise ValueError('Cap below conservative reservation')
    reused_eval = ROOT/config['reuse_baseline_evaluation']
    for file in ('summary.json', 'cases_private.json'):
        source[str((reused_eval/file).relative_to(ROOT))] = sha(reused_eval/file)  # Pin, not read current targets.
    truth = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json'
    source[str(truth.relative_to(ROOT))] = sha(truth)
    protocol = {**deepcopy(config), 'planned_calls': len(jobs)*config['n_per_month'], 'max_prompt_chars': max_chars+100,
        'research_line': 'A_conditional_returner_reconstruction', 'primary_metric': 'q9_center_mae_pp',
        'primary_weight': 'design_survey_weight', 'reused_baseline_calls': len(config['months'])*config['n_per_month']*len(config['generation_repeats']),
        'comparison': 'Original baseline reused. Matched versus within-month permuted joint synthetic psychological categories.',
        'truth_isolation': 'Prepare reads archived P/E, earlier answer prompts and linkage only; current target cache is hashed, not parsed.',
        'decision_rule': 'No automatic upgrade. Check macro MAE, personal MAE, cross-person W1, IQR and all months. Matching increment requires matched vs permuted evidence.',
        'limits': ['Already inspected months; not independent blind validation or strict B.',
                   'GSS 2018 current public release transferred across dates, adults vs SCE household heads, historical nominal family income proxy.',
                   'Synthetic categories are not observed psychology of these SCE people; assignment cannot identify its true relationship with inflation beliefs.',
                   'One frozen donor draw in paid trial; five offline draws assess allocation variability only.',
                   'Reused baseline is from an earlier API batch; mutable model alias/time may confound cross-batch contrasts.',
                   'Two generations do not double the number of respondents.']}
    dump(out/'protocol.json', protocol); dump(out/'coverage.json', coverage)
    for p in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'): source[str(p.relative_to(ROOT))] = sha(p)
    source['scripts/run_sce_frozen_trial.py'] = sha(ROOT/'scripts/run_sce_frozen_trial.py')
    manifest = {'jobs': jobs, 'planned_calls': protocol['planned_calls'], 'protocol_sha256': sha(out/'protocol.json'),
        'prepared_file_sha256': {str(p.relative_to(out)): sha(p) for p in out.rglob('*.json')},
        'source_sha256': source, 'proposed_cap_usd': config['budget_cap_usd'], 'conservative_reservation_usd': reserve,
        'estimated_cost_usd': estimate, 'timing_seconds': {'preparation': perf_counter()-started}, 'new_api_calls': 0}
    dump(out/'manifest.json', manifest)
    dump(out/'authorization.json', {'approved': False, 'protocol_sha256': manifest['protocol_sha256'],
        'cap_usd': config['budget_cap_usd'], 'planned_calls': protocol['planned_calls'], 'destination': config['destination'], 'user_confirmation': None})
    print('Prepared', protocol['planned_calls'], 'new calls, reused', protocol['reused_baseline_calls'],
          'estimated', round(estimate, 3), 'reserve', round(reserve, 3), 'cap', config['budget_cap_usd'], flush=True)
    return manifest
