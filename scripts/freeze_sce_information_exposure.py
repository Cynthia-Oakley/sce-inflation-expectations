#!/usr/bin/env python3
"""Freeze prepared information views for the existing executor; no API calls."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.experiments.frozen_batch import dump, read_json, sha, verify
from studies.sce_inflation_expectations.experiments.information_exposure import PARENT


def freeze(views, out):
    views, out = Path(views).resolve(), Path(out).resolve()
    if not views.is_relative_to(ROOT/'outputs') or out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Use existing ignored views and a fresh ignored trial directory')
    prepared = read_json(views/'summary.json')
    for name, digest in prepared['source_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('View source changed: '+name)
    arms = ['baseline', 'news_3_complete', 'news_20_complete', 'news_3_reduced', 'news_8_reduced', 'news_20_reduced']
    protocol = {'id': 'sce-information-exposure-v1', 'registered_at_utc': datetime.now(timezone.utc).isoformat(),
        'mechanism': 'news_count_by_macro_visibility', 'months': prepared['months'], 'n_per_month': 96,
        'arms': arms, 'generation_repeats': [1, 2], 'planned_calls': 6912,
        'research_line': 'A_conditional_returner_reconstruction', 'model': 'deepseek-flash',
        'official_advertised_version': 'DeepSeek-V4.1-Flash-1017', 'model_identity_limit': 'Mutable alias; exact weights and request-level switch time unverified.',
        'destination': 'https://api.deepseek.com', 'temperature': .5, 'max_tokens': 1024,
        'thinking': 'disabled', 'retry_max': 0, 'budget_cap_usd': 30.,
        'price_input_per_mtok': .3, 'price_output_per_mtok': 1.2, 'pricing_verified_date': '2026-10-18',
        'pricing_url': 'https://api-docs.deepseek.com/quick_start/pricing/',
        'sampling_seed': 20261018, 'dispatch_order_seed': 20261028,
        'sampling': 'Nested96 from archived192, age x income bounded largest remainder then SRS; missing income retained as its own stratum. Inclusion probabilities multiply.',
        'primary_metric': 'q9_center_mae_pp', 'primary_weight': 'design_survey_weight',
        'primary_comparator': 'baseline = eight news articles plus complete macro statistics, freshly generated in this same batch',
        'prespecified_contrasts': [['baseline', 'news_3_complete'], ['baseline', 'news_20_complete'],
            ['news_3_complete', 'news_3_reduced'], ['baseline', 'news_8_reduced'], ['news_20_complete', 'news_20_reduced']],
        'interactions': '(reduced-complete at3 or20) minus (reduced-complete at8); never select favorable contrasts only.',
        'secondary_metrics': ['individual_density_mean_mae_pp', 'cross_section_w1_pp', 'delta_w1_pp', 'across_person_iqr_pp',
            'individual_density_iqr_mae_pp', 'q8_center_mae_pp', 'stable_false_move', 'moving_missed_move', 'moving_wrong_direction'],
        'population_groups': ['education_group', 'numeracy', 'household_income_band', 'region'],
        'sampling_and_truth_boundary': 'Only frozen P/linkage and strict past answers are parsed. Current truth cache is hashed only. Actual past dates derive availability labels and never enter prompt text.',
        'information_change': prepared['boundaries'], 'reused_paid_calls': 0,
        'coverage_rule': 'Complete all72 cells; report invalid/scorer fractions, use all-arm/both-generation common support, no resampling or automatic retries.',
        'baseline_refs': ['copy_previous', 'history_anchor_half'],
        'screen': 'Development evidence only: center MAE and cross-section W1 both improve vs concurrent baseline, at least4/6 monthly center contrasts nonpositive, generation sensitivity and update errors reported. Raw center below.20 and below persistence is a separate project goal, never inferred from a scalar blend.',
        'uncertainty': 'Paired household clusters retain months/generations. Six selected months only; report every month and leave-one-month-out, no time-generalization confidence from thousands of requests.',
        'independent_validation': 'Not yet executed. If a candidate survives, freeze it and register four other unaffiliated months before calls. Do not relabel any current six as independent.',
        'limits': ['All six months already explored; no new blind-test claim.',
            'Returner-only conditional historical reconstruction with real own prior, not national census or autonomous B prediction.',
            '3/8/20 are treatment levels, not measured actual reading counts.',
            'News vintage limitations and synthetic CE/Fed confidence remain; no new Andre rows, Q1/Q2, psychology, quiz details or Event data added.',
            'Both generations are model repeats, not new households. No automatic upgrade or tuning on this batch.']}
    source = dict(prepared['source_sha256'])
    source[str((views/'summary.json').relative_to(ROOT))] = sha(views/'summary.json')
    truth = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json'
    source[str(truth.relative_to(ROOT))] = sha(truth)
    source[str(Path(__file__).relative_to(ROOT))] = sha(Path(__file__))
    out.mkdir(parents=True)
    dump(out/'evaluation_links_private.json', read_json(views/'evaluation_links_private.json'))
    source[str((views/'evaluation_links_private.json').relative_to(ROOT))] = sha(views/'evaluation_links_private.json')
    jobs, max_chars, reserve = [], 0, 0.
    for month in protocol['months']:
        dest = out/str(month)
        dest.mkdir()
        population = read_json(views/str(month)/'population.json')
        dump(dest/'population.json', population)
        source[str((views/str(month)/'population.json').relative_to(ROOT))] = sha(views/str(month)/'population.json')
        env = read_json(PARENT/str(month)/'environment.json')
        env['provider_args']['persona_by_id'] = {p['agent_id']: p['attributes'] for p in population['personas']}
        dump(dest/'environment.json', env)
        cfg = read_json(PARENT/str(month)/'simulation_reference.json')
        cfg['decision_args'] = {}
        dump(dest/'simulation.json', cfg)
        for arm in arms:
            original_arm = 'news_8_complete' if arm == 'baseline' else arm
            path = views/str(month)/f'prompts_{original_arm}.json'
            prompts = deepcopy(read_json(path))
            prompts['arm'] = arm
            dump(dest/f'prompts_{arm}.json', prompts)
            source[str(path.relative_to(ROOT))] = sha(path)
            bound = 0.
            for row in prompts['rows'].values():
                import json
                text = json.dumps(row['messages'], ensure_ascii=False)
                max_chars = max(max_chars, len(text))
                bound += ((len(text.encode())+256)*.3+1024*1.2)/1e6
            cap = math.ceil(bound*1e6)/1e6
            for repeat in (1, 2):
                jobs.append({'month': month, 'arm': arm, 'repeat': repeat, 'seed': 41+repeat,
                    'run_id': f'{out.name}-{month}-{arm}-r{repeat}', 'cap_usd': cap})
                reserve += cap
    # Six conditions are mixed within each month/repeat block, rather than all
    # short prompts preceding all long prompts across a mutable model version.
    rng = random.Random(protocol['dispatch_order_seed'])
    blocks = [(m, r) for m in protocol['months'] for r in (1, 2)]
    rng.shuffle(blocks)
    ordered = []
    for m, r in blocks:
        block = [j for j in jobs if j['month'] == m and j['repeat'] == r]
        rng.shuffle(block)
        ordered.extend(block)
    protocol['max_prompt_chars'] = max_chars+100
    dump(out/'protocol.json', protocol)
    for p in (ROOT/'studies/sce_inflation_expectations').rglob('*.py'):
        source[str(p.relative_to(ROOT))] = sha(p)
    source['scripts/run_sce_frozen_trial.py'] = sha(ROOT/'scripts/run_sce_frozen_trial.py')
    manifest = {'jobs': ordered, 'planned_calls': 6912, 'protocol_sha256': sha(out/'protocol.json'),
        'prepared_file_sha256': {str(p.relative_to(out)): sha(p) for p in out.rglob('*.json')},
        'source_sha256': source, 'proposed_cap_usd': 30., 'conservative_reservation_usd': reserve,
        'estimated_cost_usd': prepared['totals']['rough_input_cost_using_four_bytes_per_token_usd']+6912*300*1.2/1e6,
        'new_api_calls': 0, 'status': 'frozen_pending_engine_checks_and_authorization'}
    dump(out/'manifest.json', manifest)
    dump(out/'authorization.json', {'approved': False, 'protocol_sha256': manifest['protocol_sha256'],
        'cap_usd': 30., 'planned_calls': 6912, 'destination': protocol['destination'], 'user_confirmation': None})
    verify(out)
    print({'out': str(out), 'jobs': len(ordered), 'requests': 6912, 'estimated_cost_usd': manifest['estimated_cost_usd'],
        'conservative_reservation_usd': reserve, 'budget_cap_usd': 30., 'new_api_calls': 0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--views', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    freeze(args.views, args.out)
