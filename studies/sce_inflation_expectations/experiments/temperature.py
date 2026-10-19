"""Freeze a temperature-only contrast using already prepared direct prompts."""
from copy import deepcopy
from pathlib import Path
import json
import math
from .frozen_batch import ROOT, dump, read_json, sha

PARENT = ROOT/'outputs/sce_q8_only_trial_20261019_v3'
ARMS = {'baseline': .5, 'temperature_08': .8, 'temperature_10': 1.0}


def prepare(out, config):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    if (config['mechanism'] != 'temperature_sensitivity' or config['arm_temperatures'] != ARMS
            or config['arms'] != list(ARMS) or config['temperature'] != .5
            or config['months'] != [202004, 202105, 202111, 202203]
            or config['n_per_month'] != 24 or config['generation_repeats'] != [1, 2, 3, 4]):
        raise ValueError('Registered small temperature-only design required')
    parent = read_json(PARENT/'manifest.json'); sources = {}
    def frozen(name):
        path = PARENT/name
        if sha(path) != parent['prepared_file_sha256'][name]:
            raise ValueError('Prepared parent input changed: '+name)
        sources[str(path.relative_to(ROOT))] = sha(path)
        return read_json(path)
    old_protocol = frozen('protocol.json')
    for name in ['evaluation_truth', 'evaluation_bin_reference']:
        path = ROOT/old_protocol[name]
        if sha(path) != parent['source_sha256'][old_protocol[name]]:
            raise ValueError('Cached evaluation truth changed')
        sources[old_protocol[name]] = sha(path)  # Pin only, do not parse targets.
    links = frozen('evaluation_links_private.json')
    jobs = []; maximum = 0; reserve = estimate = 0.
    out.mkdir(parents=True)
    for month in config['months']:
        dest = out/str(month); dest.mkdir()
        for name in ['population.json', 'environment.json', 'simulation.json']:
            dump(dest/name, frozen(f'{month}/{name}'))
        original = frozen(f'{month}/prompts_direct.json')
        if len(original['rows']) != 24:
            raise ValueError('Exactly the same archived roster required')
        sizes = [len(json.dumps(r['messages'], ensure_ascii=False).encode()) for r in original['rows'].values()]
        maximum = max(maximum, max(len(json.dumps(r['messages'], ensure_ascii=False)) for r in original['rows'].values()))
        cap = math.ceil(sum(((n+256)*config['price_input_per_mtok']+config['max_tokens']*config['price_output_per_mtok'])/1e6 for n in sizes)*1e6)/1e6
        guess = sum((n/4*config['price_input_per_mtok']+300*config['price_output_per_mtok'])/1e6 for n in sizes)
        for arm in config['arms']:
            value = deepcopy(original); value['arm'] = arm
            dump(dest/f'prompts_{arm}.json', value)
        # Rotate arm order so temperature is not confounded with batch position.
        for repeat in config['generation_repeats']:
            arms = config['arms']; shift = (repeat-1) % len(arms)
            for arm in arms[shift:]+arms[:shift]:
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'seed': 41+repeat,
                             'run_id': f'{out.name}-{month}-{arm}-r{repeat}', 'cap_usd': cap})
                reserve += cap; estimate += guess
    if reserve > config['budget_cap_usd']:
        raise ValueError('Conservative reservation exceeds proposed cap')
    protocol = {**config, 'planned_calls': len(jobs)*24, 'max_prompt_chars': maximum+100,
        'evaluation_truth': old_protocol['evaluation_truth'],
        'evaluation_bin_reference': old_protocol['evaluation_bin_reference'],
        'evaluation_truth_format': 'legacy_revision_format',
        'research_line': 'A_conditional_returner_development',
        'comparison': 'Identical direct Q8/Q9 messages; only requested temperature differs.',
        'primary_comparison': 'temperature_10 minus baseline; temperature_08 is secondary sensitivity',
        'primary_metric': 'survey_weight_sensitivity_q9_cross_section_w1_pp',
        'secondary_metrics': ['q9_center_mae_pp', 'q8_center_mae_pp', 'within_person_repeat_variance',
                              'between_person_repeat_mean_variance', 'noise_adjusted_between_variance'],
        'candidate_gate': 'Exploratory only: primary paired Q9 W1 upper95<0, Q9 center point no worse, model validity>=99%; no automatic default upgrade.',
        'limits': ['Four inspected development months, not independent validation.',
                   'Four generations are repeats of identical virtual people, not extra sampled households.',
                   'Survey weights are archived sensitivity weights, not a fresh national sample.',
                   'Temperature can add random variation without useful personal heterogeneity.',
                   'Noise decomposition is equal-person descriptive and does not identify human psychology.']}
    dump(out/'protocol.json', protocol); dump(out/'evaluation_links_private.json', links)
    for path in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        sources[str(path.relative_to(ROOT))] = sha(path)
    sources['scripts/run_sce_frozen_trial.py'] = sha(ROOT/'scripts/run_sce_frozen_trial.py')
    files = {str(p.relative_to(out)): sha(p) for p in out.rglob('*.json')}
    manifest = {'jobs': jobs, 'planned_calls': protocol['planned_calls'], 'protocol_sha256': sha(out/'protocol.json'),
                'prepared_file_sha256': files, 'source_sha256': sources,
                'conservative_reservation_usd': reserve, 'estimated_cost_usd': estimate, 'new_api_calls': 0}
    dump(out/'manifest.json', manifest)
    dump(out/'authorization.json', {'approved': False, 'protocol_sha256': manifest['protocol_sha256'],
         'cap_usd': config['budget_cap_usd'], 'planned_calls': protocol['planned_calls'],
         'destination': config['destination'], 'user_confirmation': None})
    print(f'Prepared {len(jobs)} units / {protocol["planned_calls"]} calls; estimate ${estimate:.3f}, reserve ${reserve:.3f}, cap ${config["budget_cap_usd"]:.2f}', flush=True)
    return manifest
