"""Q2-specific facts and preparation; execution/scoring remain shared."""
from collections import Counter
from copy import deepcopy
from pathlib import Path
from time import perf_counter
import json
import math

from .frozen_batch import ROOT, read_json, dump, sha

PARENT = ROOT/'outputs/sce_reference_validation_trial_20261017_v2'
Q2_CACHE = ROOT/'outputs/sce_history_mechanism_diagnostic_20261017_v2/q2_selected_private.json'
Q2_RECEIPT = ROOT/'docs/workstreams/20261017_reference_scaleup/history_mechanism_verification_20261017.json'
LABELS = {1: 'much worse', 2: 'somewhat worse', 3: 'about the same', 4: 'somewhat better', 5: 'much better'}


def previous(month):
    return month-1 if month % 100 > 1 else (month//100-1)*100+12


def q2_lookup():
    if sha(Q2_CACHE) != read_json(Q2_RECEIPT)['Q2_cache_sha256']:
        raise ValueError('Validated Q2 cache changed')
    data = read_json(Q2_CACHE)
    result = {(row['month'], row['userid']): row['Q2'] for row in data}
    if len(result) != len(data) or any(code is not None and (type(code) is not int or code not in LABELS) for code in result.values()):
        raise ValueError('Unique legal Q2 observations required')
    return result


def render_q2(record):
    if set(record) != {'target_month', 'source_month', 'q2_code'} or record['source_month'] != previous(record['target_month']):
        raise ValueError('Only exact previous-month Q2 is permitted')
    code = record['q2_code']
    if code is None: return ''
    if type(code) is not int or code not in LABELS: raise ValueError('Invalid Q2 code')
    return ('Your household financial outlook in your previous survey:\n'
            f'You expected your household financial situation 12 months after that survey '
            f'to be {LABELS[code]} than it was then.\n\n')


def add_block(messages, block):
    """Preserve every original byte outside one inserted personal-state block."""
    from ..revision_format_runtime import REPLY_MARKER
    if len(messages) != 1 or messages[0]['role'] != 'user' or messages[0]['content'].count(REPLY_MARKER) != 1:
        raise ValueError('Expected one direct-answer questionnaire boundary')
    result = deepcopy(messages)
    result[0]['content'] = result[0]['content'].replace(REPLY_MARKER, block+REPLY_MARKER, 1)
    return result


def prepare(out, config):
    from socioverse.schemas import PopulationBundle
    from ..finance_validation_preparation import proportional_sample
    from ..prior_belief_experiment import message_hash
    begin = perf_counter(); out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Use a new ignored output directory')
    if config['mechanism'] != 'previous_financial_outlook' or config['arms'] != ['baseline', 'previous_financial_outlook']:
        raise ValueError('This adapter only adds prior Q2')
    parent = read_json(PARENT/'manifest.json'); lookup = q2_lookup()
    source = {str(p.relative_to(ROOT)): sha(p) for p in (PARENT/'manifest.json', Q2_CACHE, Q2_RECEIPT)}
    truth_file = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json'
    source[str(truth_file.relative_to(ROOT))] = sha(truth_file)  # Pin only; never parse current targets here.
    def frozen(name):
        p = PARENT/name
        if sha(p) != parent['prepared_file_sha256'][name]: raise ValueError('Parent input changed: '+name)
        source[str(p.relative_to(ROOT))] = sha(p); return read_json(p)
    links = frozen('evaluation_links_private.json'); out.mkdir(parents=True)
    selected_links = []; coverage = {}; jobs = []; estimate = reserve = 0.; max_chars = 0
    for month in config['months']:
        dest = out/str(month); dest.mkdir()
        pop = PopulationBundle.model_validate(frozen(f'{month}/population.json'))
        selected, pi2, allocation = proportional_sample(pop.personas, month, config['n_per_month'], config['sampling_seed'])
        pop.personas = [p for p in pop.personas if p.agent_id in selected]; pop.materialized_count = len(selected)
        dump(dest/'population.json', pop.model_dump(mode='json'))
        env = frozen(f'{month}/environment.json')
        env['provider_args']['persona_by_id'] = {p.agent_id: p.attributes for p in pop.personas}
        dump(dest/'environment.json', env)
        cfg = frozen(f'{month}/simulation_reference.json'); cfg['decision_args'] = {}
        dump(dest/'simulation.json', cfg)
        previews = {row['agent_id']: row for row in frozen(f'{month}/preview_reference.json')}
        chosen = [deepcopy(row) for row in links if row['month'] == month and row['agent_id'] in selected]
        if len(chosen) != config['n_per_month']: raise ValueError('Selected link roster mismatch')
        records = {}
        for row in chosen:
            row['inclusion_probability'] *= pi2[row['agent_id']]
            row['design_survey_weight'] = row['survey_weight']/row['inclusion_probability']
            records[row['agent_id']] = {'target_month': month, 'source_month': previous(month),
                'q2_code': lookup.get((previous(month), row['userid']))}
        selected_links.extend(chosen); dump(dest/'mechanism_records.json', records)
        coverage[str(month)] = {'n': len(chosen), 'prior_q2_codes': dict(Counter(str(r['q2_code']) for r in records.values())),
                                'allocation': allocation}
        for arm in config['arms']:
            rows = {}
            for aid in sorted(selected):
                messages = previews[aid]['messages']
                if message_hash(messages) != previews[aid]['prompt_sha256']: raise ValueError('Parent preview hash mismatch')
                block = render_q2(records[aid]) if arm != 'baseline' else ''
                changed = add_block(messages, block)
                if not block and changed != messages: raise ValueError('Empty block changed base')
                rows[aid] = {'messages': changed, 'prompt_sha256': message_hash(changed)}
                text = json.dumps(changed, ensure_ascii=False); max_chars = max(max_chars, len(text))
            dump(dest/f'prompts_{arm}.json', {'month': month, 'arm': arm, 'rows': rows})
            bound = sum(((len(json.dumps(r['messages'], ensure_ascii=False).encode())+256)*config['price_input_per_mtok']
                         +config['max_tokens']*config['price_output_per_mtok'])/1e6 for r in rows.values())
            for repeat in config['generation_repeats']:
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'seed': 41+repeat,
                    'run_id': f'{out.name}-{month}-{arm}-r{repeat}', 'cap_usd': math.ceil(bound*1e6)/1e6})
                reserve += jobs[-1]['cap_usd']
        # Use the actual completed parent usage as an estimate, not a price quote.
    for job in jobs:
        parent_job = next(j for j in parent['jobs'] if j['month'] == job['month'] and j['repeat'] == job['repeat'])
        ledger = read_json(ROOT/'outputs/local_runs'/parent_job['run_id']/'cost_ledger.json')
        estimate += ledger['estimated_cost_usd']*config['n_per_month']/192
    estimate *= 1.03
    if reserve > config['budget_cap_usd']: raise ValueError('Configured cap below conservative reservation')
    protocol = {**config, 'planned_calls': len(jobs)*config['n_per_month'], 'max_prompt_chars': max_chars+100,
        'research_line': 'A_conditional_returner_reconstruction',
        'comparison': 'Same exact base plus only observed previous-month Q2; no prescribed inflation effect.',
        'primary_metric': 'q9_center_mae_pp', 'primary_weight': 'design_survey_weight',
        'secondary_metrics': ['individual_density_mean_mae_pp', 'cross_section_w1_pp', 'delta_w1_pp', 'individual_density_iqr_mae_pp'],
        'decision_rule': 'No automatic upgrade. Report center and individual/distribution tradeoffs, coverage and per-month changes.',
        'truth_isolation': 'Preparation reads only frozen P/E/prompt/links and validated Q2 cache, not current inflation answers.',
        'limits': ['Four inspected months; exploratory, not new independent blind validation.',
                   'Previous real Q2 and prior Q8/Q9 are private A conditions, not strict public B inputs.',
                   'Two generations are API variability, not additional respondents. Mutable model alias remains.']}
    dump(out/'protocol.json', protocol); dump(out/'evaluation_links_private.json', selected_links)
    dump(out/'coverage.json', coverage)
    # Pin maintained Python sources once, without altering any archived runner.
    for p in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        source[str(p.relative_to(ROOT))] = sha(p)
    source['scripts/run_sce_frozen_trial.py'] = sha(ROOT/'scripts/run_sce_frozen_trial.py')
    files = {str(p.relative_to(out)): sha(p) for p in out.rglob('*.json')}
    manifest = {'jobs': jobs, 'planned_calls': protocol['planned_calls'], 'protocol_sha256': sha(out/'protocol.json'),
        'prepared_file_sha256': files, 'source_sha256': source, 'proposed_cap_usd': config['budget_cap_usd'],
        'conservative_reservation_usd': reserve, 'estimated_cost_usd': estimate,
        'timing_seconds': {'preparation': perf_counter()-begin}, 'new_api_calls': 0}
    dump(out/'manifest.json', manifest)
    dump(out/'authorization.json', {'approved': False, 'protocol_sha256': manifest['protocol_sha256'],
        'cap_usd': config['budget_cap_usd'], 'planned_calls': protocol['planned_calls'],
        'destination': config['destination'], 'user_confirmation': None})
    print('Prepared', protocol['planned_calls'], 'calls; estimated', round(estimate, 3),
          'conservative reserve', round(reserve, 3), 'cap', config['budget_cap_usd'], flush=True)
    return manifest
