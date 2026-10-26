"""Evaluation-only adapter for continuous states; reuses frozen Q9/cell metrics.

No population selection or prompt construction happens here. Current answers
are opened only by this module, in a separate process from the live executor.
"""
from collections import Counter, defaultdict
from copy import deepcopy
from functools import lru_cache
import json
import math
from pathlib import Path

from . import cognition as shared
from .metrics import headline_errors
from ..experiments.frozen_batch import ROOT, dump, read_json, sha
from ..experiments.state_continuity_execution import verify, load_inputs, node_key
from ..experiments.state_continuity import month_index
from ..prior_belief_preparation import valid_bins
from ..scoring.sce_q9_frozen import provenance

ARMS = ['observed_history', 'simulated_history']


@lru_cache(maxsize=12000)
def score(bins):
    return shared._score_bins(list(bins))


def field_view(state):
    values = state['fields']['q9']['value']
    return {**deepcopy(score(tuple(values))), 'q9_bins': values,
            'point': state['fields']['q8']['value']}


def prepare_truth(package, history, out):
    package, history, out = map(lambda x: Path(x).resolve(), (package, history, out)); p, m = verify(package)
    if out.exists() or not out.resolve().is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh isolated truth output required')
    nodes = read_json(ROOT / p['preparation'] / 'state_dependencies_private.json')
    ids = {(n['month'], n['agent_id']) for n in nodes}
    inputs = load_inputs(ROOT / p['input_templates'], p['months'])
    rows = []; sources = {}
    for month in p['months']:
        file = ROOT / 'outputs/sce_fullperiod_data_20261021_v1' / month / 'evaluation_truth/micro_truth.json'
        wf = history / f'{month}_weights_private.json'
        sources[str(file.relative_to(ROOT))] = sha(file); sources[str(wf.relative_to(ROOT))] = sha(wf)
        actual = read_json(file)['per_person']; by_id = {r['agent_id']: r for r in actual}
        if len(by_id) != len(actual): raise ValueError('Duplicate current truth ID')
        weights = read_json(wf)
        for _, aid in sorted(k for k in ids if k[0] == month):
            r = by_id[aid]; init = inputs[month, aid][1]; w = weights[aid]
            if not w['weight_valid'] or w['substituted_one_used']:
                raise ValueError('Authoritative survey weight required')
            # Q9 validity follows the raw ten bins, not availability of an
            # official derived mean computed using a different implementation.
            bins = r['q9_bins']; legal9 = valid_bins(bins)
            scored = score(tuple(bins)) if legal9 else dict(mean=None, iqr=None, zero_deflation=None,
                                                           scorer_status='invalid_human_bins')
            point = r['q8_point_pct']
            legal8 = (bool(r['q8_valid']) and type(point) in (int, float)
                      and math.isfinite(point) and abs(point) <= 100)
            prior = field_view(init); fields = init['fields']
            adjacent9 = (fields['q9']['source_kind'] == 'own_observed'
                         and month_index(month) - month_index(fields['q9']['source_period']) == 1)
            adjacent8 = (fields['q8']['source_kind'] == 'own_observed'
                         and month_index(month) - month_index(fields['q8']['source_period']) == 1)
            real = dict(q9_mean=scored['mean'], q9_iqr=scored['iqr'], q9_zero_deflation=scored['zero_deflation'],
                        q9_bins=bins if legal9 else [], q8_point=point if legal8 else None,
                        previous_q9_mean=prior['mean'] if adjacent9 else None,
                        previous_q9_bins=prior['q9_bins'] if adjacent9 else [],
                        previous_q8_point=prior['point'] if adjacent8 else None)
            rows.append(dict(month=int(month), agent_id=aid, real=real,
                             survey_weight=w['analysis_weight'], raw_survey_weight=w['survey_weight'],
                             inclusion_probability=w['inclusion_probability'],
                             monthly_past_reference=prior,
                             genuinely_observed_previous_q9=adjacent9,
                             genuinely_observed_previous_q8=adjacent8))
    out.mkdir(parents=True); dump(out / 'truth_private.json', rows)
    dump(out / 'manifest.json', dict(protocol_sha256=m['protocol_sha256'], source_sha256=sources,
         truth_sha256=sha(out / 'truth_private.json'), scope='Evaluation only; never passed to live runner',
         scorer=provenance(), person_months=len(rows), new_api_calls=0))
    return dict(person_months=len(rows), new_api_calls=0, truth_entered_prompts=False)


def assemble_cases(nodes, positions, truths, initials=None):
    """Strict keys, independent Q8/Q9 validity, explicit operational fallback."""
    index = {node_key(r): r for r in positions}
    if len(index) != len(positions) or set(index) != {node_key(n) for n in nodes}:
        raise ValueError('Complete exact logical output scope required')
    target = {(str(r['month']), r['agent_id']): r for r in truths}
    people = {aid: i for i, aid in enumerate(sorted({n['agent_id'] for n in nodes}))}
    if len(target) != len(truths) or set(target) != {(n['month'], n['agent_id']) for n in nodes}:
        raise ValueError('Unique complete evaluation truth scope required')
    cases = {}; operational = {}; quality = Counter()
    for node in nodes:
        key = (node['month'], node['agent_id'], node['repeat']); aid = node['agent_id']
        truth = target[key[:2]]; pos = index[node_key(node)]; arm = node['arm']
        base = dict(month=int(key[0]), agent_id=aid, userid=people[aid], repeat=key[2],
                    numeracy='Unspecified', survey_weight=truth['survey_weight'],
                    raw_parent_survey_weight=truth['raw_survey_weight'],
                    sampling_weight=1 / truth['inclusion_probability'], real=deepcopy(truth['real']), arms={},
                    survey_entry_status=node['survey_entry_status'], core_entry_status=node['core_entry_status'])
        if key not in cases: cases[key] = deepcopy(base); operational[key] = deepcopy(base)
        view = field_view(pos['state_after']); before = field_view(pos['state_before'])
        changed = pos['state_after']['transition']['field_updated_from_model']
        raw_view = deepcopy(view)
        if not changed['q9']:
            raw_view.update(mean=None, iqr=None, zero_deflation=None, q9_bins=[])
            quality[arm + ':q9_retained_input'] += 1
        if not changed['q8']:
            raw_view['point'] = None; quality[arm + ':q8_retained_input'] += 1
        if changed['q9'] and (not shared.finite(view['mean']) or not shared.finite(view['iqr'])):
            view.update({k: before[k] for k in ('mean', 'iqr', 'zero_deflation', 'q9_bins')})
            view['evaluation_only_input_scalar_fallback'] = True
            quality[arm + ':density_fit_fallback'] += 1
        if pos['state_after']['transition']['q9_proportional_normalization']:
            quality[arm + ':normalized_q9'] += 1
        cases[key]['arms'][arm] = raw_view; operational[key]['arms'][arm] = view
        for row in (cases[key], operational[key]):
            row['arms']['monthly_past_reference'] = deepcopy(truth['monthly_past_reference'])
            genuine = deepcopy(truth['monthly_past_reference'])
            if not truth['genuinely_observed_previous_q9']:
                genuine.update(mean=None, iqr=None, zero_deflation=None, q9_bins=[])
            if not truth['genuinely_observed_previous_q8']: genuine['point'] = None
            row['arms']['genuine_previous_only'] = genuine
    return list(cases.values()), list(operational.values()), dict(quality)


def summarize(cases, months, repeats):
    support9 = shared._common_person_months(cases, ARMS, repeats, 'q9')
    support8 = shared._common_person_months(cases, ARMS, repeats, 'q8')
    by_arm = {a: shared._summarize_arm(cases, a, months, repeats, support9, support8) for a in ARMS}
    for result in by_arm.values():
        result['auxiliary_survey_weighted']['weight_definition'] = 'Authoritative survey weight / actual marginal SRS inclusion probability'
        for view in (result, result['auxiliary_survey_weighted']):
            cells = view['q9']['cells']; biases = [c['q9_center_bias_pp'] for c in cells]
            view['q9']['center_headline_errors'] = (headline_errors(biases, [0] * len(biases))
                 if biases and all(shared.finite(v) for v in biases) else None)
    genuine9 = shared._common_person_months(cases, [*ARMS, 'genuine_previous_only'], repeats, 'q9')
    genuine8 = shared._common_person_months(cases, [*ARMS, 'genuine_previous_only'], repeats, 'q8')
    genuine = {a: shared._summarize_arm(cases, a, months, repeats, genuine9, genuine8)['auxiliary_survey_weighted']
               for a in [*ARMS, 'genuine_previous_only']}
    reference9 = shared._common_person_months(cases, [*ARMS, 'monthly_past_reference'], repeats, 'q9')
    reference8 = shared._common_person_months(cases, [*ARMS, 'monthly_past_reference'], repeats, 'q8')
    reference = {a: shared._summarize_arm(cases, a, months, repeats, reference9, reference8)['auxiliary_survey_weighted']
                 for a in [*ARMS, 'monthly_past_reference']}
    return dict(q9_person_months=len(support9), q8_person_months=len(support8),
                design_weighted_primary={a: r['auxiliary_survey_weighted'] for a, r in by_arm.items()},
                equal_person_sensitivity={a: {k: r[k] for k in ('q9', 'q8')} for a, r in by_arm.items()},
                genuine_previous_only_support=dict(q9_person_months=len(genuine9), q8_person_months=len(genuine8), arms=genuine),
                monthly_past_reference_support=dict(q9_person_months=len(reference9), q8_person_months=len(reference8), arms=reference))


def evaluate(package, calls, truth, out):
    package, calls, truth, out = map(lambda x: Path(x).resolve(), (package, calls, truth, out)); p, manifest = verify(package)
    if out.exists() or not out.resolve().is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh evaluation output required')
    receipt = read_json(calls / 'receipt.json'); tm = read_json(truth / 'manifest.json')
    cm = read_json(calls / 'manifest.json')
    if (not receipt.get('actual_model_results') or receipt.get('protocol_sha256') != manifest['protocol_sha256']
            or cm['protocol_sha256'] != manifest['protocol_sha256']):
        raise ValueError('Engineering fixtures or another package are not model results')
    for name, digest in cm['files_sha256'].items():
        if sha(calls / name) != digest: raise ValueError('Call ledger changed')
    if receipt['status'] != 'completed' or receipt['attempts'] != p['planned_calls']:
        raise ValueError('Partial trial requires a separate declared partial-analysis plan')
    if tm['protocol_sha256'] != manifest['protocol_sha256'] or sha(truth / 'truth_private.json') != tm['truth_sha256']:
        raise ValueError('Truth/package provenance mismatch')
    nodes = read_json(ROOT / p['preparation'] / 'state_dependencies_private.json')
    positions = [json.loads(line) for line in (calls / 'positions_private.jsonl').read_text().splitlines()]
    cases, operational, quality = assemble_cases(nodes, positions, read_json(truth / 'truth_private.json'), None)
    months = [int(m) for m in p['months']]; repeats = p['generation_repeats']
    selected_months = defaultdict(set)
    for n in nodes: selected_months[n['agent_id']].add(n['month'])
    continuous = {a for a, ms in selected_months.items() if len(ms) == len(months)}
    groups = {'continuous_three_months': summarize([r for r in operational if r['agent_id'] in continuous], months, repeats)}
    for dim in ('survey_entry_status', 'core_entry_status'):
        groups[dim] = {v: summarize([r for r in operational if r[dim] == v], months, repeats)
                       for v in sorted({r[dim] for r in operational})}
    human9 = {(r['month'], r['userid']) for r in operational if shared.finite(r['real']['q9_mean']) and shared.finite(r['real']['q9_iqr'])}
    human8 = {(r['month'], r['userid']) for r in operational if shared.finite(r['real']['q8_point'])}
    result = dict(status='completed', protocol=p, protocol_sha256=manifest['protocol_sha256'],
                  selected_person_months=len({(r['month'], r['userid']) for r in cases}),
                  human_valid_roster=dict(q9=len(human9), q8=len(human8)), quality=quality,
                  fixed_roster_operational=summarize(operational, months, repeats),
                  paired_actual_outputs=summarize(cases, months, repeats),
                  by_month={str(m): summarize([r for r in operational if r['month'] == m], [m], repeats) for m in months},
                  by_repeat={str(rep): summarize([r for r in operational if r['repeat'] == rep], months, [rep]) for rep in repeats},
                  groups=groups, receipt=receipt, scorer=provenance(),
                  source_sha256={str(f.relative_to(ROOT)): sha(f) for f in
                     [calls / 'receipt.json', calls / 'calls_private.jsonl', calls / 'positions_private.jsonl', truth / 'truth_private.json']},
                  limits=['Selected mixed-entry cohort, not national SCE.',
                          'Q9 centers are across-person medians of frozen fitted density means; Q8 separate.',
                          'Real monthly previous baseline only on genuinely observed adjacent-month sources.',
                          'Retained state/normalization/failed-density fallback are explicit, not fresh model answers.',
                          'Three fixed months cannot establish generalization or a causal mechanism.'])
    out.mkdir(parents=True); dump(out / 'cases_private.json', cases); dump(out / 'operational_cases_private.json', operational)
    dump(out / 'summary.json', result)
    return dict(status='completed', selected_person_months=result['selected_person_months'], new_api_calls=0,
                operational_q9_person_months=result['fixed_roster_operational']['q9_person_months'])
