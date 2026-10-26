"""Isolated evaluation of a completed A82 personal-date run.

Generation imports no target data. This adapter reuses the original A82 truth,
the frozen density scorer and shared weighted metrics. It never selects an
answer or a technical repair by its distance from human outcomes.
"""
from collections import Counter
from copy import deepcopy
from pathlib import Path
import argparse
import json
import math

from . import cognition as shared
from .monthly_reconstruction import read_score_cache, summarize, support_by_month
from .monthly_main_readout import chronological_blend
from .metrics import compare_distributions, distribution_summary, headline_errors
from ..experiments.frozen_batch import ROOT, dump, read_json, sha
from ..prior_belief_preparation import valid_bins
from ..scoring.sce_q9_frozen import provenance

OLD_TRUTH = ROOT / 'outputs/sce_monthly_fine_full_truth_20261023_v3'
OLD_RESULT = ROOT / 'outputs/sce_monthly_main_six_repair_20261024_v1'
OLD_ASSEMBLY = ROOT / 'outputs/sce_monthly_fine_full_assembly_20261023_v3'
OLD_CASES_SHA256 = '23a482aa825d4c775a1c6d58b3ff84241f18f8b57765503aadabb338e00bc61c'
OLD_READOUT_SHA256 = '1e6aa55de2e64e0c720bf8fde1a1b2ec6b3ace1446ae1cc723fd9794c9903a6b'
ARM = 'monthly_reconstruction'  # Shared metric adapter's canonical arm name.
WEIGHT_DEFINITION = ('Original 54-cell masses, calibrated after prespecified '
                     'completion-date exclusions; weighted empirical-CDF statistics')


def _finite(value):
    return type(value) in (float, int) and math.isfinite(value)


def _verify_files(folder, mapping):
    folder = Path(folder).resolve()
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError('Nonempty frozen file hash map required')
    for name, digest in mapping.items():
        path = (folder / name).resolve()
        if not path.is_relative_to(folder) or sha(path) != digest:
            raise ValueError('Frozen file changed or escaped its directory: ' + name)


def validate_completed_view(view):
    """Reject engineering/incomplete generation before opening any target."""
    view = Path(view).resolve()
    receipt = read_json(view / 'receipt.json')
    if (receipt.get('status') != 'completed'
            or receipt.get('actual_model_results') is not True
            or receipt.get('unknown', 0) or receipt.get('unknown_intents', 0)
            or receipt.get('not_attempted', 0)):
        raise ValueError('Completed actual-model logical view required before truth access')
    manifest = read_json(view / 'manifest.json')
    if not {'receipt.json', 'logical_actions_private.jsonl'} <= set(manifest['files_sha256']):
        raise ValueError('Logical view must pin both its receipt and logical actions')
    _verify_files(view, manifest['files_sha256'])
    if receipt.get('logical_actions_sha256') != sha(view / 'logical_actions_private.jsonl'):
        raise ValueError('Logical action digest differs from its generation receipt')
    if not receipt.get('raw_ledger_manifests_sha256'):
        raise ValueError('Completed generation requires a nonempty immutable raw ledger chain')
    if receipt.get('raw_ledger_manifests_sha256'):
        # Production views live at <run>/generation_views/view_NNNN. Check the
        # raw immutable ledgers as well as the derived logical field overlay.
        run_dir = view.parent.parent
        raw_manifests = receipt['raw_ledger_manifests_sha256']
        _verify_files(run_dir, raw_manifests)
        for relative in raw_manifests:
            path = run_dir / relative
            _verify_files(path.parent, read_json(path)['files_sha256'])
    return receipt, manifest


def _validate_production_origin(inputs, view, receipt):
    """Bind the standalone evaluator to the strictly checked full-A run."""
    from ..experiments.full_a_personal_terminal import checked, _validate_input
    run_dir = view.parent.parent
    if view.parent.name != 'generation_views':
        raise ValueError('Logical view must belong to a registered full-A Terminal run')
    config, protocol = checked(run_dir, authorized=True)
    if (Path(config['input_package']).resolve() != inputs
            or receipt.get('protocol_sha256') != sha(run_dir / 'protocol.json')):
        raise ValueError('Logical view, authorized run and input scope differ')
    _validate_input(inputs)  # Independent 82-month/512-origin/14-exclusion checks; no target read.
    from ..experiments import frozen_message_queue as queue
    from ..q9_normalization import response_point, response_view
    main_intents, main_replies = queue.archive(run_dir / 'main')
    repair_intents, repair_replies = queue.archive(run_dir / 'repair')
    main = {r['key']: r for r in main_replies}
    repair = {r['key'].removeprefix('repair1|'): r for r in repair_replies}
    for row in main_replies + repair_replies:
        if row.get('actual_model_results') is not True:
            raise ValueError('Engineering replies cannot be promoted to research evaluation')
    for line in (view / 'logical_actions_private.jsonl').read_text().splitlines():
        action = json.loads(line)
        first, second = main.get(action['key']), repair.get(action['key'])
        if first is None:
            raise ValueError('Completed logical action has no original raw reply')
        for field in ('q8', 'q9'):
            source = 'main' if queue.fields(first)[field] else (
                'repair' if second is not None and queue.fields(second)[field] else 'initial_fallback')
            selected = first if source == 'main' else second if source == 'repair' else None
            expected = None
            if selected is not None:
                if selected['prompt_sha256'] != action['prompt_sha256']:
                    raise ValueError('Logical action and raw reply have different prompts')
                expected = (response_point(selected['raw_response_text']) if field == 'q8'
                            else response_view(selected['raw_response_text'])['bins'])
            actual = action['effective_q8'] if field == 'q8' else action['effective_q9_bins']
            if (source != action['field_source'][field] or actual != expected
                    or action['field_updated'][field] != (selected is not None)):
                raise ValueError('Logical overlay differs from preserved raw main/repair fields')


def _verify_cell_mass(month, current_weights, original_weights):
    old, new = Counter(), Counter()
    for aid, row in original_weights.items():
        old[row.get('profile_cell') or row['stratum']] += row['poststratified_weight']
    for aid, row in current_weights.items():
        cell = original_weights[aid].get('profile_cell') or original_weights[aid]['stratum']
        if (row.get('profile_cell') or row['stratum']) != cell:
            raise ValueError('A respondent changed grid cells during date filtering')
        new[cell] += row['analysis_weight']
    if set(old) != set(new) or any(not math.isclose(old[k], new[k], rel_tol=1e-12, abs_tol=1e-10) for k in old):
        raise ValueError('Original positive grid masses not preserved for ' + month)


def action_view(action, prior, cache):
    """Apply declared per-field fallback without discarding a respondent."""
    if action.get('arm') != 'T0' or action.get('repeat') != 1:
        raise ValueError('Only frozen T0 / one-generation logical records are supported')
    point, bins = action.get('effective_q8'), action.get('effective_q9_bins')
    updated = action['field_updated']
    needs = action['needs_initial_fallback']
    if any(bool(updated[k]) == bool(needs[k]) for k in ('q8', 'q9')):
        raise ValueError('Updated and initial-fallback flags must be complementary')
    if updated['q8'] and not _finite(point):
        raise ValueError('Updated Q8 must contain a finite point')
    if updated['q9'] and (not valid_bins(bins) or not math.isclose(sum(bins), 100., abs_tol=1e-8)):
        raise ValueError('Updated Q9 must contain the registered normalized probabilities')
    operational = deepcopy(prior)
    actual = dict(mean=None, iqr=None, zero_deflation=None, q9_bins=[], point=None)
    quality = Counter()
    if updated['q8']:
        operational['point'] = actual['point'] = point
    else:
        quality['q8_retained_input'] += 1
    if updated['q9']:
        fitted = deepcopy(cache[tuple(bins)])
        actual.update(fitted, q9_bins=bins)
        if _finite(fitted.get('mean')) and _finite(fitted.get('iqr')):
            operational.update(fitted, q9_bins=bins)
        else:
            operational['evaluation_only_input_scalar_fallback'] = True
            quality['density_fit_fallback'] += 1
    else:
        quality['q9_retained_input'] += 1
    return operational, actual, quality


def _score_new_vectors(actions, cache, workers):
    vectors = {tuple(a['effective_q9_bins']) for a in actions if a['field_updated']['q9']}
    missing = sorted(vectors - set(cache))
    if missing:
        from concurrent.futures import ProcessPoolExecutor
        import multiprocessing
        from .monthly_reconstruction import _fit_vector
        with ProcessPoolExecutor(max_workers=workers,
                                 mp_context=multiprocessing.get_context('fork')) as pool:
            cache.update(pool.map(_fit_vector, missing, chunksize=32))
    return len(missing)


def evaluate(inputs, view, out, *, truth=OLD_TRUTH, old_result=OLD_RESULT, workers=8):
    inputs, view, out, truth, old_result = map(lambda p: Path(p).resolve(),
                                              (inputs, view, out, truth, old_result))
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored evaluation output required')
    receipt, view_manifest = validate_completed_view(view)  # Must be first.
    _validate_production_origin(inputs, view, receipt)
    im = read_json(inputs / 'manifest.json')
    _verify_files(inputs, im['files_sha256'])
    inp = read_json(inputs / 'summary.json')
    if inp.get('status') != 'ready':
        raise ValueError('Prepared input package has not passed its full offline checks')
    if receipt.get('input_manifest_sha256') != sha(inputs / 'manifest.json'):
        raise ValueError('Generation view belongs to a different input package')
    actions = [json.loads(line) for line in (view / 'logical_actions_private.jsonl').read_text().splitlines()]
    action_by_id = {(str(a['month']), a['agent_id']): a for a in actions}
    if len(action_by_id) != len(actions):
        raise ValueError('Duplicate logical person-month')
    months = sorted({m for m, _ in action_by_id})
    expected_months = [str(201901 + (i // 12) * 100 + i % 12) for i in range(82)]
    if months != expected_months:
        raise ValueError('The registered final A scope is all 82 historical months')
    planned = set()
    weights = {}
    initial_states = {}
    sources = inp.get('source_sha256', inp.get('input_files_sha256', {}))
    for month in months:
        p = read_json(inputs / month / 'prompts.json')['rows']
        w = read_json(inputs / month / 'weights_private.json')
        if set(p) != set(w):
            raise ValueError('Prompt and evaluation-weight identities differ')
        old_weight_path = ROOT / 'outputs/sce_monthly_fine_full_inputs_20261023_v2' / f'{month}_weights_private.json'
        if sources.get(str(old_weight_path.relative_to(ROOT))) != sha(old_weight_path):
            raise ValueError('Original population-weight source must be pinned')
        _verify_cell_mass(month, w, read_json(old_weight_path))
        state_path = OLD_ASSEMBLY / 'prompts' / month / 'initial_states_private.json'
        relative = str(state_path.relative_to(ROOT))
        if sources.get(relative) != sha(state_path):
            raise ValueError('The original input initial-state source must be pinned')
        states = read_json(state_path)
        for aid, row in p.items():
            planned.add((month, aid))
            if action_by_id.get((month, aid), {}).get('prompt_sha256') != row['prompt_sha256']:
                raise ValueError('Logical output and frozen prompt hash differ')
            weights[month, aid] = w[aid]
            initial_states[month, aid] = states[aid]
    if planned != set(action_by_id):
        raise ValueError('Logical output scope differs from input scope')
    if receipt.get('planned_calls') != len(planned):
        raise ValueError('Generation receipt and logical record counts differ')
    # Only now read previously frozen evaluation-only targets.
    tm = read_json(truth / 'manifest.json')
    _verify_files(truth, {'truth_private.json': tm['truth_sha256'],
                          'full_wave_private.json': tm['full_wave_sha256']})
    original_truth = read_json(truth / 'truth_private.json')
    truth_by_id = {(str(t['month']), t['agent_id']): t for t in original_truth}
    if not planned <= set(truth_by_id):
        raise ValueError('Original frozen truth does not cover the planned people')
    cache = read_score_cache(truth)
    new_fits = _score_new_vectors(actions, cache, workers)
    identities = {aid: i for i, aid in enumerate(sorted({t['agent_id'] for t in original_truth}))}
    # Digests are from the pre-existing A82 analysis manifest, not selected after this run.
    if (sha(old_result / 'evaluation/cases_private.json') != OLD_CASES_SHA256
            or sha(old_result / 'readout/summary.json') != OLD_READOUT_SHA256):
        raise ValueError('The registered old-A comparison or national anchor changed')
    old_cases = read_json(old_result / 'evaluation/cases_private.json')
    old_by_id = {(str(t['month']), t['agent_id']): t for t in old_cases}
    cases, actual_cases, quality = [], [], Counter()
    for key, action in action_by_id.items():
        t, w = truth_by_id[key], weights[key]
        original_fields = initial_states[key]['fields']
        prior = t['monthly_past_reference']
        if (prior['point'] != original_fields['q8']['value']
                or prior['q9_bins'] != original_fields['q9']['value']):
            raise ValueError('Cached starting-state scores differ from the original model input')
        weight = w['analysis_weight']
        if not _finite(weight) or weight <= 0:
            raise ValueError('Positive finite registered evaluation weight required')
        operational, actual, q = action_view(action, prior, cache)
        quality.update(q)
        genuine = deepcopy(t['monthly_past_reference'])
        if not t['genuinely_observed_previous_q9']:
            genuine.update(mean=None, iqr=None, zero_deflation=None, q9_bins=[])
        if not t['genuinely_observed_previous_q8']:
            genuine['point'] = None
        common = dict(month=int(key[0]), agent_id=key[1], userid=identities[key[1]], repeat=1,
                      survey_weight=weight, real=deepcopy(t['real']), profile=t['profile'],
                      raw_parent_survey_weight=t.get('raw_survey_weight'),
                      sampling_weight=(1 / t['inclusion_probability']
                                       if _finite(t.get('inclusion_probability'))
                                       and t['inclusion_probability'] > 0 else None),
                      stratum=t['stratum'], initial_q9_provenance=t['initial_q9_provenance'],
                      survey_entry_status=old_by_id[key]['survey_entry_status'])
        arms = {ARM: operational, 'monthly_past_reference': t['monthly_past_reference'],
                'genuine_previous_only': genuine, 'old_A82': old_by_id[key]['arms'][ARM]}
        cases.append(dict(common, arms=deepcopy(arms)))
        arms[ARM] = actual
        actual_cases.append(dict(common, arms=deepcopy(arms)))
    mm = [int(m) for m in months]
    def summarise(rows, arms):
        return summarize(rows, mm, arms, weight_definition=WEIGHT_DEFINITION)
    groups = {}
    for dimension in ('education_group', 'numeracy', 'age_group', 'household_income_band',
                      'region', 'stratum', 'survey_entry_status', 'initial_q9_provenance'):
        def label(r):
            v = r.get(dimension, r['profile'].get(dimension))
            return 'unknown' if v is None else str(v)
        groups[dimension] = {}
        for value in sorted({label(r) for r in cases}):
            rows = [r for r in cases if label(r) == value]
            groups[dimension][value] = summarise(rows, [ARM, 'monthly_past_reference'])
            groups[dimension][value]['support_by_month'] = support_by_month(rows, mm)
    # Reuse the old archived national targets and registered persistence anchors.
    # They stay a fixed reference; personal-date A has no single global as_of.
    old_readout = read_json(old_result / 'readout/summary.json')
    national_by_month = {r['month'].replace('-', ''): r
                         for r in old_readout['official_national']['monthly']}
    full_wave = read_json(truth / 'full_wave_private.json')
    national, full_monthly = [], []
    for month in months:
        rows = [r for r in cases if str(r['month']) == month]
        item = dict(month=month, fields={})
        for field, model_key in (('q9_mean', 'mean'), ('q8_point', 'point')):
            model = [r for r in rows if _finite(r['arms'][ARM][model_key])]
            human = [r for r in full_wave[month]
                     if _finite(r[field]) and _finite(r['weight']) and r['weight'] > 0]
            item['fields'][field] = compare_distributions(
                [r['arms'][ARM][model_key] for r in model], [r['survey_weight'] for r in model],
                [r[field] for r in human], [r['weight'] for r in human])
        full_monthly.append(item)
        national.append(dict(national_by_month[month],
                             sim_pp=item['fields']['q9_mean']['simulated']['median_pp']))
    from .aggregate_blend import evaluate as blend_metrics
    result = dict(status='completed_full_a_personal_evaluation', configuration='T0',
                  new_api_calls=0, new_q9_density_fits=new_fits,
                  primary_result_path='auxiliary_survey_weighted',
                  weight_definition=WEIGHT_DEFINITION,
                  selected_person_months=len(cases), quality=dict(quality),
                  fixed_roster=summarise(cases, [ARM, 'monthly_past_reference']),
                  genuine_previous_only=summarise(cases, [ARM, 'genuine_previous_only']),
                  usable_output_sensitivity=summarise(actual_cases, [ARM, 'monthly_past_reference']),
                  old_new_same_roster=summarise(cases, [ARM, 'old_A82']), groups=groups,
                  full_wave_monthly=full_monthly,
                  full_wave_center_errors={field: headline_errors(
                      [r['fields'][field]['simulated']['median_pp'] for r in full_monthly],
                      [r['fields'][field]['observed']['median_pp'] for r in full_monthly])
                      for field in ('q9_mean', 'q8_point')},
                  official_national=dict(monthly=national, model=blend_metrics(national, 1.),
                      persistence=blend_metrics(national, 0.),
                      chronological_combinations=chronological_blend(
                          national, ['2019-01', '2022-12'], ['2023-01', '2025-10'])),
                  generation_receipt=receipt, scorer=provenance(),
                  limits=['Personal-date A reconstruction has no single global forecast cutoff.',
                          'The old public-headline anchor is a fixed comparison reference, not an input to each person.',
                          'Same-roster micro, full-wave and official headline supports remain distinct.',
                          'Both compared A configurations were developed after inspecting some historical outcomes.',
                          'No claim of independent validation or absence of pretrained future knowledge.',
                          'Core is directly simulated and weighted; no Normal expansion or recursive B chain.'])
    out.mkdir(parents=True)
    dump(out / 'summary.json', result)
    dump(out / 'cases_private.json', cases)
    dump(out / 'raw_output_cases_private.json', actual_cases)
    dump(out / 'scoring_cache_private.json', [dict(bins=list(k), score=v) for k, v in cache.items()])
    sources = [inputs / 'manifest.json', view / 'manifest.json', truth / 'manifest.json',
               truth / 'truth_private.json', old_result / 'readout/summary.json',
               old_result / 'evaluation/cases_private.json', Path(__file__)]
    dump(out / 'manifest.json', dict(new_api_calls=0,
         source_sha256={str(p.relative_to(ROOT)): sha(p) for p in sources},
         files_sha256={name: sha(out / name) for name in
                       ('summary.json', 'cases_private.json', 'raw_output_cases_private.json',
                        'scoring_cache_private.json')}))
    return dict(status=result['status'], new_api_calls=0, person_months=len(cases),
                new_q9_density_fits=new_fits)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--view', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--workers', type=int, default=8, choices=range(1, 9))
    a = p.parse_args(argv)
    print(json.dumps(evaluate(a.inputs, a.view, a.out, workers=a.workers), ensure_ascii=False))
