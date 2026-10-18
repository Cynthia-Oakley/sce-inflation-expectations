"""Prepare dated public-context blocks; reuse the common frozen trial executor."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from time import perf_counter
import json
import math

from .financial_outlook import add_block
from .frozen_batch import ROOT, read_json, dump, sha

PARENT = ROOT/'outputs/sce_reference_validation_trial_20261017_v2'
EVIDENCE = ROOT/'docs/workstreams/20261018_targeted_mechanisms/consumer_context_evidence.json'


def render_block(evidence, month, as_of):
    """Explicit A development selection, never automatic admission of MCP snapshots."""
    block = evidence['candidate_blocks'][str(month)]
    records = {r['evidence_id']: r for r in evidence['records']}
    chosen = [records[key] for key in block['evidence_ids']]
    if not chosen or len({r['evidence_id'] for r in chosen}) != len(chosen):
        raise ValueError('Nonempty unique source set required')
    cutoff = datetime.fromisoformat(as_of)
    for record in chosen:
        if (record['target_month'] != month or record['as_of'] != as_of
                or not record['date_gate_passed']
                or datetime.fromisoformat(record['published_date']).date() > cutoff.date()
                or record.get('evidence_use') == 'audit_only_not_agent_input'):
            raise ValueError('Wrong period or late/audit-only source')
        if (record['published_date'] == cutoff.date().isoformat()
                and (cutoff.hour, cutoff.minute, cutoff.second) != (23, 59, 59)):
            raise ValueError('Date-only evidence does not establish intraday eligibility')
    return block['text']+'\n\n'


def prepare(out, config):
    from socioverse.schemas import PopulationBundle
    from ..finance_validation_preparation import proportional_sample
    from ..prior_belief_experiment import message_hash
    begin = perf_counter(); out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Use a fresh ignored output directory')
    if config['mechanism'] != 'public_consumer_context' or config['arms'] != ['baseline', 'consumer_context']:
        raise ValueError('Only the registered public-context contrast is supported')
    evidence = read_json(EVIDENCE); parent = read_json(PARENT/'manifest.json')
    source = {str(p.relative_to(ROOT)): sha(p) for p in (EVIDENCE, PARENT/'manifest.json')}
    # Verify primary-source provenance; the raw originals never become prompt text.
    for record in evidence['records']:
        path = ROOT/record['source_file_local']
        if not path.resolve().is_relative_to(ROOT) or sha(path) != record['source_sha256']:
            raise ValueError('Official source archive changed')
        source[str(path.relative_to(ROOT))] = sha(path)
    truth = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json'
    source[str(truth.relative_to(ROOT))] = sha(truth)  # Hash only; current targets are never parsed.
    def frozen(name):
        path = PARENT/name
        if sha(path) != parent['prepared_file_sha256'][name]: raise ValueError('Parent input changed')
        source[str(path.relative_to(ROOT))] = sha(path)
        return read_json(path)
    links = frozen('evaluation_links_private.json'); out.mkdir(parents=True)
    selected_links = []; coverage = {}; jobs = []; estimate = reserve = 0.; max_chars = 0
    for month in config['months']:
        dest = out/str(month); dest.mkdir()
        pop = PopulationBundle.model_validate(frozen(f'{month}/population.json'))
        selected, pi2, allocation = proportional_sample(pop.personas, month, config['n_per_month'], config['sampling_seed'])
        pop.personas = [p for p in pop.personas if p.agent_id in selected]; pop.materialized_count = len(selected)
        dump(dest/'population.json', pop.model_dump(mode='json'))
        env = frozen(f'{month}/environment.json')
        block = render_block(evidence, month, env['provider_args']['targets'][0]['as_of'])
        env['provider_args']['persona_by_id'] = {p.agent_id: p.attributes for p in pop.personas}
        dump(dest/'environment.json', env)
        cfg = frozen(f'{month}/simulation_reference.json'); cfg['decision_args'] = {}
        dump(dest/'simulation.json', cfg)
        previews = {r['agent_id']: r for r in frozen(f'{month}/preview_reference.json')}
        chosen = [deepcopy(r) for r in links if r['month'] == month and r['agent_id'] in selected]
        if len(chosen) != config['n_per_month']: raise ValueError('Selected roster mismatch')
        for row in chosen:
            row['inclusion_probability'] *= pi2[row['agent_id']]
            row['design_survey_weight'] = row['survey_weight']/row['inclusion_probability']
        selected_links.extend(chosen)
        coverage[str(month)] = {'n': len(chosen), 'allocation': allocation,
                                'public_context_evidence_ids': evidence['candidate_blocks'][str(month)]['evidence_ids']}
        for arm in config['arms']:
            rows = {}
            for aid in sorted(selected):
                messages = previews[aid]['messages']
                if message_hash(messages) != previews[aid]['prompt_sha256']: raise ValueError('Base preview changed')
                changed = add_block(messages, block if arm == 'consumer_context' else '')
                if arm == 'baseline' and changed != messages: raise ValueError('Control drift')
                rows[aid] = {'messages': changed, 'prompt_sha256': message_hash(changed)}
                max_chars = max(max_chars, len(json.dumps(changed, ensure_ascii=False)))
            dump(dest/f'prompts_{arm}.json', {'month': month, 'arm': arm, 'rows': rows})
            bound = sum(((len(json.dumps(r['messages'], ensure_ascii=False).encode())+256)*config['price_input_per_mtok']
                         +config['max_tokens']*config['price_output_per_mtok'])/1e6 for r in rows.values())
            for repeat in config['generation_repeats']:
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'seed': 41+repeat,
                             'run_id': f'{out.name}-{month}-{arm}-r{repeat}', 'cap_usd': math.ceil(bound*1e6)/1e6})
                reserve += jobs[-1]['cap_usd']
    for job in jobs:
        old = next(j for j in parent['jobs'] if j['month'] == job['month'] and j['repeat'] == job['repeat'])
        usage = read_json(ROOT/'outputs/local_runs'/old['run_id']/'cost_ledger.json')
        estimate += usage['estimated_cost_usd']*config['n_per_month']/192*1.05
    if reserve > config['budget_cap_usd']: raise ValueError('Cap below conservative reservation')
    protocol = {**config, 'planned_calls': len(jobs)*config['n_per_month'], 'max_prompt_chars': max_chars+100,
        'research_line': 'A_conditional_returner_reconstruction',
        'primary_metric': 'q9_center_mae_pp', 'primary_weight': 'design_survey_weight',
        'comparison': 'Exact old prompts versus the same prompts plus dated public consumer-context/policy brief; no peer inflation forecast numbers.',
        'decision_rule': 'No automatic upgrade. Report center, W1, individual error, stable-case false moves and moving-case missed moves; do not retune text on these results.',
        'truth_isolation': 'Preparation hashes but never parses current SCE targets. Sampling uses only frozen P and links.',
        'limits': ['Three inspected development months, not independent goal confirmation.',
                   'Twenty-four people per month is a mechanism screen, not national reconstruction.',
                   'Public survey background is not personal measured exposure or beliefs.',
                   'Narrative and policy facts are bundled; no separate causal attribution.',
                   'True previous answers are A conditions; not recurrent or strict public B.',
                   'Two generations are repeated calls, not new people. Mutable model alias remains.']}
    dump(out/'protocol.json', protocol); dump(out/'evaluation_links_private.json', selected_links); dump(out/'coverage.json', coverage)
    for path in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'): source[str(path.relative_to(ROOT))] = sha(path)
    source['scripts/run_sce_frozen_trial.py'] = sha(ROOT/'scripts/run_sce_frozen_trial.py')
    files = {str(path.relative_to(out)): sha(path) for path in out.rglob('*.json')}
    manifest = {'jobs': jobs, 'planned_calls': protocol['planned_calls'], 'protocol_sha256': sha(out/'protocol.json'),
        'prepared_file_sha256': files, 'source_sha256': source, 'proposed_cap_usd': config['budget_cap_usd'],
        'conservative_reservation_usd': reserve, 'estimated_cost_usd': estimate,
        'timing_seconds': {'preparation': perf_counter()-begin}, 'new_api_calls': 0}
    dump(out/'manifest.json', manifest)
    dump(out/'authorization.json', {'approved': False, 'protocol_sha256': manifest['protocol_sha256'],
        'cap_usd': config['budget_cap_usd'], 'planned_calls': protocol['planned_calls'],
        'destination': config['destination'], 'user_confirmation': None})
    print('Prepared', protocol['planned_calls'], 'calls; estimate', round(estimate, 3), 'reservation', round(reserve, 3))
    return manifest
