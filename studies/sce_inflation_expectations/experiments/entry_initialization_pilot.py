"""Small actual-entry diagnostic, reusing frozen monthly prompts and the queue.

Selection reads profiles and past-state provenance only. Current questionnaire
answers are handled by a separate evaluation adapter, never by this module.
"""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
import math
from pathlib import Path

import numpy as np

from .frozen_batch import ROOT, dump, read_json, sha
from .state_continuity_core import check
from .state_continuity_dry_run import dry_run
from .state_continuity_execution import load_inputs, reserve, verify
from ..population.entry_initialization import month_index
from ..state_continuity_runtime import render_messages

MONTHS = ('202109', '202206', '202506')
ARM = 'monthly_reconstruction'
DEFAULT_ASSEMBLY = ROOT / 'outputs/sce_monthly_reconstruction_full_assembly_20261022_v4'
DEFAULT_PACKAGE = ROOT / 'outputs/sce_monthly_reconstruction_full_execution_20261022_v1'


def cohort(row, state, month):
    """Actual survey entrants are distinct from first appearances in a Core."""
    fields = state['fields']
    if row['survey_entry_status'] == 'entrant':
        if state['history_centers'] or any(f['source_kind'] != 'synthetic_donor' for f in fields.values()):
            raise ValueError('Actual entrants must not acquire an invented observed history')
        if any(not 1 <= month_index(month)-month_index(f['source_period']) <= 3 for f in fields.values()):
            raise ValueError('Entrant donor must precede the target by 1--3 months')
        return 'entrant'
    if row['survey_entry_status'] == 'returning' and all(
            f['source_kind'] == 'own_observed' and month_index(month)-month_index(f['source_period']) == 1
            for f in fields.values()):
        return 'returning'
    return None


def select_people(rows, states, month, n=24, seed=20261022):
    """Second-phase SRS within entry domains, retaining both selection stages."""
    pools = {'entrant': [], 'returning': []}
    for row in rows:
        label = cohort(row, states[row['persona']['agent_id']], month)
        if label is not None:
            pools[label].append(row)
    selected, support = [], {}
    for j, (label, candidates) in enumerate(pools.items()):
        candidates = sorted(candidates, key=lambda r: r['persona']['agent_id'])
        if len(candidates) < n:
            raise ValueError(f'{month} {label}: insufficient pre-outcome support')
        rng = np.random.default_rng(np.random.SeedSequence([seed, int(month), j]))
        indices = sorted(rng.choice(len(candidates), n, replace=False).tolist())
        second = n / len(candidates)
        for i in indices:
            row = deepcopy(candidates[i])
            first = row['inclusion_probability']
            row.update(parent_inclusion_probability=first, pilot_conditional_probability=second,
                       inclusion_probability=first*second)
            row['analysis_weight'] = (row['raw_survey_weight'] / row['inclusion_probability']
                                      if row['weight_valid'] else None)
            selected.append(row)
        support[label] = {'parent_eligible_n': len(candidates), 'selected_n': n,
                          'conditional_selection_probability': second}
    return sorted(selected, key=lambda r: r['persona']['agent_id']), support


def prepare(out, *, assembly=DEFAULT_ASSEMBLY, source_package=DEFAULT_PACKAGE):
    """Prepare 3 x (24 entrants + 24 observed returners) x 2 = 288 calls."""
    out, assembly, source_package = (Path(p).resolve() for p in (out, assembly, source_package))
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored pilot directory required')
    original, original_manifest = verify(source_package)
    original_inputs = ROOT / original['preparation']
    old_prompts = assembly / 'prompts'
    original_people = read_json(original_inputs/'selected_private.json')
    original_nodes = {(r['month'], r['agent_id']): r for r in
                      read_json(original_inputs/'state_dependencies_private.json')}
    sources = {str(path.relative_to(ROOT)): sha(path) for path in
               (assembly/'manifest.json', source_package/'protocol.json',
                source_package/'manifest.json', original_inputs/'selected_private.json',
                original_inputs/'state_dependencies_private.json')}
    preparation, prompts = out/'inputs', out/'prompts'
    preparation.mkdir(parents=True); prompts.mkdir()
    chosen, nodes, coverage, sizes = {}, [], [], []
    selected_fields = ('raw_survey_weight', 'analysis_weight', 'weight_valid',
                       'inclusion_probability', 'stratum', 'parent_inclusion_probability',
                       'pilot_conditional_probability')
    for month in MONTHS:
        folder = old_prompts/month
        read = {}
        for name in ('templates_private.json', 'initial_states_private.json',
                     'timing_context_private.json', 'population.json', 'environment.json'):
            path = folder/name; read[name] = read_json(path)
            sources[str(path.relative_to(ROOT))] = sha(path)
        states = read['initial_states_private.json']
        people, support = select_people(original_people[month], states, month)
        chosen[month] = people; ids = {r['persona']['agent_id'] for r in people}
        destination = prompts/month; destination.mkdir()
        for name in ('templates_private.json', 'initial_states_private.json', 'timing_context_private.json'):
            dump(destination/name, {aid: read[name][aid] for aid in sorted(ids)})
        pop = deepcopy(read['population.json'])
        pop['personas'] = [p for p in pop['personas'] if p['agent_id'] in ids]
        pop['materialized_count'] = len(ids)
        dump(destination/'population.json', pop)
        dump(destination/'environment.json', read['environment.json'])
        dump(preparation/f'{month}_weights_private.json',
             {r['persona']['agent_id']: {k: r[k] for k in selected_fields} for r in people})
        ages = Counter(); source_counts = Counter()
        for row in people:
            aid = row['persona']['agent_id']
            message = render_messages(read['templates_private.json'][aid], states[aid], month,
                                      read['timing_context_private.json'][aid])
            sizes.append((len(message[0]['content']), len(json.dumps(message, ensure_ascii=False).encode())))
            for f in states[aid]['fields'].values():
                source_counts[f['source_kind']] += 1
                if f['source_kind'] == 'synthetic_donor':
                    ages[str(month_index(month)-month_index(f['source_period']))] += 1
            for repeat in (1, 2):
                node = deepcopy(original_nodes[month, aid])
                node.update(repeat=repeat, dependency=None,
                            core_entry_status='first_pilot_appearance',
                            logical_reuse_key=f'{month}|{aid}|r{repeat}|entry_initialization_pilot')
                nodes.append(node)
        coverage.append({'month': month, 'n': len(ids), 'cohorts': support,
                         'source_field_counts': dict(source_counts), 'donor_age_months': dict(ages),
                         'missing_raw_weight_n': sum(not r['weight_valid'] for r in people)})
    dump(preparation/'selected_private.json', chosen)
    dump(preparation/'state_dependencies_private.json', nodes)
    dump(preparation/'summary.json', {'months': coverage, 'person_months': 144,
         'logical_positions': len(nodes), 'new_api_calls': 0, 'source_sha256': sources})
    prompt_summary = {'coverage': coverage, 'runtime_character_cap': max(v[0] for v in sizes),
                      'runtime_utf8_byte_cap': max(v[1] for v in sizes), 'source_sha256': sources,
                      'new_api_calls': 0, 'note': 'Byte-identical subset of deferred full prompts; no recalibration or target selection.'}
    dump(prompts/'summary.json', prompt_summary)
    replay = dry_run(nodes, load_inputs(prompts, MONTHS))
    dump(out/'dry_run_private.json', replay)
    core = check(preparation, prompts, out/'core_engineering')
    if core['official_engine_units'] != 6 or core['decisions'] != 288 or replay['unique_request_slots'] != 288:
        raise ValueError('Exact six-unit / 288-position official check required')
    protocol = deepcopy(original)
    protocol.update(mechanism='entry_initialization_pilot_v1', months=list(MONTHS), arms=[ARM],
                    generation_repeats=[1, 2], n_per_month=48, planned_calls=288, logical_positions=288,
                    input_templates=str(prompts.relative_to(ROOT)), preparation=str(preparation.relative_to(ROOT)),
                    core_check=str((out/'core_engineering').relative_to(ROOT)),
                    max_prompt_chars=prompt_summary['runtime_character_cap'],
                    max_prompt_bytes=prompt_summary['runtime_utf8_byte_cap'],
                    technical_gate={'calls': 16, 'minimum_usable': 16},
                    concurrency_stages=[{'after_completed': 0, 'workers': 8}, {'after_completed': 16, 'workers': 64}],
                    research_line='A_new_entrant_recent_initialization_diagnostic_not_national',
                    created_at_utc=datetime.now(timezone.utc).isoformat(),
                    randomness={'selection_seed': 20261022, 'generation_seed': None,
                                'note': 'Two stochastic generations of the same 144 person-months; one fixed donor/news assignment.'})
    protocol.pop('macro_combination', None); protocol.pop('evaluation_recipe', None)
    protocol['estimated_cost_usd'] = 2*sum((chars/3*protocol['price_input_per_mtok']+
                                          350*protocol['price_output_per_mtok'])/1e6 for chars,_ in sizes)
    protocol['full_conservative_reservation_usd'] = 288*reserve(protocol, protocol['max_prompt_bytes'])
    protocol['budget_cap_usd'] = math.ceil(protocol['full_conservative_reservation_usd']*2)/2
    protocol['evaluation_rules'] = {
        'primary': 'Separate actual entrants and genuine observed-adjacent returners, never a national 50/50 mixture.',
        'weights': 'raw survey weight / first-stage six-cell pi / conditional second-stage entry-domain pi; equal-person sensitivity.',
        'metrics': 'Q9 center MAE/RMSE/bias, W1, between-person IQR and within-person probability IQR; Q8 separately.',
        'baselines': 'Assigned starting state for entrants, genuine own previous state for returners; labels kept distinct.',
        'missing': 'Primary fixed human-valid roster with explicit retained-state fallback; usable-output sensitivity and failure counts.',
        'interpretation': 'Descriptive applicability check; no randomization of initialization, no causal claim, no automatic adoption.',
        'limits': '24 per cohort/month and three seen months; no national inference or reliable fine-subgroup testing. No true entrant monthly delta.',
        'normal': 'No Core-to-Normal expansion in this paid diagnostic.'}
    package = out/'execution'; package.mkdir()
    dump(package/'protocol.json', protocol)
    sources.update({str(f.relative_to(ROOT)): sha(f) for folder in (preparation,prompts,out/'core_engineering')
                    for f in folder.rglob('*.json')})
    for path in original_manifest['source_sha256']:
        if Path(path).suffix == '.py':
            sources[path] = sha(ROOT/path)
    own = Path(__file__); sources[str(own.relative_to(ROOT))] = sha(own)
    dump(package/'manifest.json', {'protocol_sha256': sha(package/'protocol.json'),
         'source_sha256': sources, 'new_api_calls': 0, 'truth_in_execution_inputs': False,
         'authorization_status': 'not_authorized'})
    for name in sources:
        if Path(name).suffix == '.py':
            dest = package/'source_snapshot'/name; dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes((ROOT/name).read_bytes())
    result = {k: protocol[k] for k in ('planned_calls','estimated_cost_usd',
              'full_conservative_reservation_usd','budget_cap_usd')}
    result.update(person_months=144, official_core_units=6, months=coverage, new_api_calls=0,
                  status='prepared_not_paid_authorized', package=str(package.relative_to(ROOT)))
    dump(out/'summary.json', result)
    return result
