"""Reuse existing prompt assembly and official Core checks for monthly A inputs.

This command has no live execution mode. It produces a reviewable offline bundle,
an evaluation recipe and a budget estimate, never an API authorization.
"""
from datetime import datetime, timezone
from pathlib import Path

from .frozen_batch import ROOT, dump, read_json, sha
from .state_continuity_prompts import prepare as prepare_prompts
from .state_continuity_core import check as check_core


def evaluation_recipe():
    return {
        'schema_version': 1, 'research_line': 'A_independent_monthly_reconstruction',
        'target': 'SCE one-year-ahead Q8 and Q9 answers; not realized CPI',
        'q9_statistic': 'Frozen density mean per person, then design-weighted empirical-CDF median across people',
        'q8_statistic': 'Signed Q8 point answers, evaluated independently of Q9 validity',
        'weights': 'Raw respondent survey weight / actual within-cell inclusion probability; missing weight remains missing',
        'macro_views': [
            {'name': 'same_roster', 'truth': 'Current human answers on the same outcome-valid selected people',
             'purpose': 'Conditional simulation fit without sample-composition differences'},
            {'name': 'full_micro_wave', 'truth': 'Full current wave scored by the same frozen algorithm',
             'purpose': 'Whole-wave reconstruction including finite Core selection error'},
            {'name': 'official_national_headline', 'truth': 'Separately archived NYFed published monthly statistic',
             'purpose': 'National macro comparison; report scorer-definition gap separately'},
        ],
        'primary_metrics': ['Q9 monthly median MAE', 'Q9 cross-person W1'],
        'secondary_metrics': ['monthly median RMSE/bias', 'cross-person IQR relative to humans',
                              'individual-center MAE', 'rank correlation', 'Q8 counterparts'],
        'supports': {
            'all_current': 'All selected people with scorable current human answers, under the declared failure rule',
            'real_adjacent_returners': 'Same people with actual adjacent-month and current human answers valid for that field',
            'new_entrants': 'True SCE entrants; do not confuse first Core appearance with first survey appearance',
            'other_history_missing': 'Gap/left-boundary/partial-missing states listed separately',
            'change_W1': 'Only real adjacent human histories; never substitute synthetic prior for real change truth',
        },
        'baselines': {
            'retain_starting_state': 'All selected people; assigned synthetic and true observed states explicitly distinguished',
            'copy_true_own_previous': 'Only genuine adjacent valid own records',
            'national_persistence': 'Last eligible published national SCE statistic',
            'national_combination': 'Past national truth + current simulation; fit on earlier registered months and freeze for later evaluation',
        },
        'predeclared_groups': ['education x employment attachment plus unknown', 'age', 'income',
                               'numeracy', 'four Census regions', 'survey-entry status',
                               'initial-belief provenance'],
        'sparse_display': {'minimum_n': 20, 'minimum_weight_ess': 10,
                           'below_threshold': 'Descriptive only; disclose N/ESS/weight-valid coverage, do not rank mechanisms'},
        'failures': {'raw_response': 'Preserve original text, provider/finish reason and missingness',
                     'Q9': 'Proportional normalization only for ten finite nonnegative bins with positive total',
                     'primary': 'Explicit per-field retained starting state for failed/non-stop/unusable output, on fixed human-valid support',
                     'sensitivity': 'Actual usable-output support; report missing response and scorer-failure rates',
                     'no_deletion': 'No replacement respondents or paid retry to improve the reported score'},
        'interpretation': [
            'No claim that recent-donor initialization is causally better without a paired old/new initializer control.',
            'The main run evaluates the chosen whole configuration against baselines.',
            'Current-population A conditions and strict-B information eligibility are separate.',
            'Official national headline and same-roster micro medians are never pooled as one target.',
            'Overall W1 is not an average of subgroup W1; their difference is not a causal decomposition.',
        ],
        'remaining_registration': ['Final continuous months and source vintages',
                                   'Macro-combination fitting/evaluation split and seen-month registry',
                                   'Final paid scope, model/provider, budget, concurrency, stop/continuation authorization',
                                   'Strict-B population/initialization and sealing rules'],
    }


def finish(inputs, families, environments, out, *, delivery, policy_supplement=None, confidence_supplement=None,
           prepared_prompts=None):
    inputs, families, environments, out, delivery = map(lambda x: Path(x).resolve(),
                                                       (inputs, families, environments, out, delivery))
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored assembly folder required')
    prep = read_json(inputs/'summary.json')
    if prep.get('mechanism') != 'monthly_reconstruction' or prep['recursive_dependencies'] != 0:
        raise ValueError('Independent monthly inputs required')
    out.mkdir(parents=True)
    prompts = out/'prompts'
    if prepared_prompts is None:
        prompt_receipt = prepare_prompts(inputs, inputs, environments, prompts,
            family_projection=families, policy_supplement=policy_supplement,
            delivery=delivery, mode='monthly_reconstruction', confidence_supplement=confidence_supplement)
    else:
        import os,shutil
        prepared_prompts=Path(prepared_prompts).resolve()
        prompt_receipt=read_json(prepared_prompts/'summary.json')
        if (prompt_receipt['preparation_mode']!='monthly_reconstruction' or
            prompt_receipt['logical_positions']!=prep['logical_positions'] or
            [r['month'] for r in prompt_receipt['coverage']]!=[r['month'] for r in prep['months']]):
            raise ValueError('Reusable complete prompt scope mismatch')
        for name,digest in prompt_receipt['source_sha256'].items():
            if sha(ROOT/name)!=digest: raise ValueError('Prepared prompt source changed: '+name)
        shutil.copytree(prepared_prompts,prompts,copy_function=os.link)
    core_receipt = check_core(inputs, prompts, out/'core_engineering')
    recipe = evaluation_recipe(); dump(out/'evaluation_recipe.json', recipe)
    manifest = {
        'status': 'offline_monthly_A_bundle_complete_not_paid_authorized',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'new_api_calls': 0, 'new_model_answers': 0,
        'months': [r['month'] for r in prep['months']], 'n_per_month': 512,
        'generation_repeats': [1], 'person_months': prep['person_months'],
        'recursive_dependencies': 0, 'official_core': core_receipt,
        'inputs': str(inputs.relative_to(ROOT)), 'families': str(families.relative_to(ROOT)),
        'environments': str(environments.relative_to(ROOT)), 'delivery': str(delivery.relative_to(ROOT)),
        'input_manifest_sha256': sha(inputs/'summary.json'),
        'family_manifest_sha256': sha(families/'summary.json'),
        'prompt_manifest_sha256': sha(prompts/'summary.json'),
        'core_manifest_sha256': sha(out/'core_engineering/summary.json'),
        'budget_estimate_not_authorization': {
            'prospective_model': 'deepseek/deepseek-v3.2',
            'prospective_provider_route': 'OpenRouter -> siliconflow/fp8',
            'temperature': .5, 'reasoning': 'disabled', 'max_output_tokens': 1024,
            'unique_calls_before_any_eligible_prior-response_reuse': prompt_receipt['planned_unique_requests'],
            'estimated_usd': prompt_receipt['estimated_cost_usd'],
            'conservative_usd': prompt_receipt['conservative_reservation_usd'],
            'rate_basis': 'Previously registered .259 input / .8 output USD per million tokens; reconfirm before paid freeze',
        },
        'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in [
            Path(__file__), ROOT/'studies/sce_inflation_expectations/experiments/state_continuity_prompts.py',
            ROOT/'studies/sce_inflation_expectations/experiments/monthly_reconstruction_inputs.py',
        ]},
        'limits': ['Offline fixtures verify wiring; they are not LLM results or a fitted score.',
                   'The three-month bundle is the integration sample for a scalable main pipeline, not a new continuity trial.',
                   'No live runner authorization or numerical performance gate is created here.',
                   'Full-period P/E and strict-B eligibility remain separately tracked.'],
    }
    dump(out/'manifest.json', manifest)
    return manifest
