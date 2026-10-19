"""Post-hoc selection of archived replies using external attention probabilities.

No network client, executor, prompt changes, or density fitting. Allocation is
persisted before any current SCE answers are loaded for evaluation.
"""
from io import BytesIO
import hashlib
import importlib.util
import json
from pathlib import Path
from time import perf_counter
from zipfile import ZipFile

import numpy as np
import pandas as pd

from .attention_support import ARCHIVE, FEATURES, ROOT, cross_validate, fit_probabilities, harmonize, sha
from .cognition import _common_person_months

SEEDS = tuple(range(20261019, 20261039))
QUOTA = ((3, 48), (8, 28), (20, 20))
FOLDER = ROOT/'outputs/sce_information_exposure_trial_20261018_v1'
EVALUATION = ROOT/'outputs/sce_information_exposure_evaluation_20261019_v1'
READOUT = ROOT/'outputs/sce_information_exposure_readout_20261019_v1/summary.json'
PLAN = ROOT/'docs/workstreams/20261018_targeted_mechanisms/heterogeneous_news_offline_plan_20261019.md'


def stable_uniform(seed, person, purpose):
    payload = f'{seed}|{person}|{purpose}'.encode()
    # 53-bit fractions can be represented exactly and are always strictly < 1.
    number = int.from_bytes(hashlib.sha256(payload).digest()[:8], 'big') >> 11
    return number/2**53


def allocate(people, probabilities, seed):
    """Only IDs/probabilities enter; current outcomes cannot enter this API."""
    people = list(map(str, people))
    p = np.asarray(probabilities, dtype=float)
    if len(people) != 96 or len(set(people)) != 96 or p.shape != (96, 6):
        raise ValueError('One 96-person wave with six-class probabilities required')
    if not np.isfinite(p).all() or np.any(p < 0) or not np.allclose(p.sum(1), 1):
        raise ValueError('Invalid external probabilities')
    latent = []
    for uid, row in zip(people, p):
        category = min(int(np.searchsorted(np.cumsum(row), stable_uniform(seed, uid, 'class'), side='right')), 5)
        latent.append((category, stable_uniform(seed, uid, 'tie'), uid))
    ordered = sorted(latent)
    counts = [level for level, count in QUOTA for _ in range(count)]
    return {uid: count for (_, _, uid), count in zip(ordered, counts)}


def level_arm(level, mode):
    if mode not in ('complete', 'reduced') or level not in (3, 8, 20):
        raise ValueError('No archived response for requested exposure')
    return 'baseline' if (level, mode) == (8, 'complete') else f'news_{level}_{mode}'


def ranges(rows):
    return {key: {'min': float(min(r[key] for r in rows)),
                  'mean': float(np.mean([r[key] for r in rows])),
                  'max': float(max(r[key] for r in rows))} for key in rows[0]}


def analyze(out):
    began = perf_counter()
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output directory required')
    if sha(ARCHIVE) != 'ae34b5e4e67c5240bae5516eb10096e33e4a94266f8e4962631e437227e189d3':
        raise ValueError('External archive changed')
    with ZipFile(ARCHIVE) as archive:
        frame = pd.read_stata(BytesIO(archive.read('out/data/associations.dta')), convert_categoricals=False)
    donors = harmonize(frame.loc[frame.survey.eq('household') & frame.follow_news.notna()].copy()).reset_index(drop=True)
    y = donors.follow_news.astype(int).to_numpy()-1
    feature_sets = {column+'_only': [column] for column in FEATURES}
    feature_sets['joint_demographics'] = FEATURES
    cv = cross_validate(donors, y, 6, feature_sets, ordinal=True)

    manifest = json.loads((FOLDER/'manifest.json').read_text())
    source_hashes = {str(p.relative_to(ROOT)): sha(p) for p in [ARCHIVE, PLAN, FOLDER/'manifest.json', READOUT]}

    def frozen(name):
        path = FOLDER/name
        if sha(path) != manifest['prepared_file_sha256'][name]:
            raise ValueError('Archived allocation input changed: '+name)
        source_hashes[str(path.relative_to(ROOT))] = sha(path)
        return json.loads(path.read_text())

    protocol = frozen('protocol.json')
    links = frozen('evaluation_links_private.json')
    # This archived file contains only IDs, P, strata and weights, no answers.
    allowed_link_keys = {'month', 'agent_id', 'userid', 'profile', 'stratum', 'survey_weight',
                         'inclusion_probability', 'design_survey_weight'}
    if any(set(row)-allowed_link_keys for row in links):
        raise ValueError('Unexpected fields in answer-free identity link')
    link_by_key = {(r['month'], r['agent_id']): str(r['userid']) for r in links}
    profiles, identifiers = [], []
    for month in protocol['months']:
        pop = frozen(f'{month}/population.json')['personas']
        for person in pop:
            attributes = {key: person['attributes'].get(key) for key in FEATURES}
            if attributes['household_income_band'] is None:
                attributes['household_income_band'] = 'missing'
            profiles.append(attributes)
            identifiers.append((month, link_by_key[month, person['agent_id']]))
    target = pd.DataFrame(profiles)
    probabilities = fit_probabilities(donors, target, y, 6, FEATURES)
    indices = {month: [i for i, key in enumerate(identifiers) if key[0] == month] for month in protocol['months']}
    allocations = {}
    for seed in SEEDS:
        chosen = {}
        for month, index in indices.items():
            assignment = allocate([identifiers[i][1] for i in index], probabilities[index], seed)
            chosen.update({(month, uid): level for uid, level in assignment.items()})
        allocations[seed] = chosen
    out.mkdir(parents=True)
    allocation_path = out/'allocations_private.json'
    allocation_path.write_text(json.dumps({str(seed): [{'month': m, 'userid': uid, 'news_count': n}
        for (m, uid), n in selection.items()] for seed, selection in allocations.items()}, indent=2)+'\n')
    allocation_digest_before_truth = sha(allocation_path)
    (out/'external_prediction_summary.json').write_text(json.dumps(cv, indent=2, allow_nan=False)+'\n')

    # Only now open truth/scored replies, after allocations have been persisted.
    old_readout = json.loads(READOUT.read_text())
    for name in ('summary.json', 'cases_private.json'):
        path = EVALUATION/name
        if sha(path) != old_readout['source_sha256'][str(path.relative_to(ROOT))]:
            raise ValueError('Frozen evaluation changed')
        source_hashes[str(path.relative_to(ROOT))] = sha(path)
    scored = json.loads((EVALUATION/'summary.json').read_text())
    if scored['protocol'] != protocol:
        raise ValueError('Different archived protocol')
    cases = json.loads((EVALUATION/'cases_private.json').read_text())
    support = _common_person_months(cases, protocol['arms'], protocol['generation_repeats'], 'q9')
    groups = {month: sorted(str(uid) for m, uid in support if m == month) for month in protocol['months']}
    spec = importlib.util.spec_from_file_location('archived_exposure_report', ROOT/'scripts/report_sce_information_exposure.py')
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    arrays = []
    for month in protocol['months']:
        for repeat in protocol['generation_repeats']:
            rows = sorted([r for r in cases if r['month'] == month and r['repeat'] == repeat
                and (month, r['userid']) in support], key=lambda r: str(r['userid']))
            ids = [str(r['userid']) for r in rows]
            if ids != groups[month]:
                raise ValueError('Repeat support mismatch')
            arrays.append({'month': month, 'repeat': repeat, 'ids': ids,
                'y': np.array([r['real']['q9_mean'] for r in rows]),
                'prior': np.array([r['real']['previous_q9_mean'] for r in rows]),
                'w': np.array([r['survey_weight'] for r in rows]),
                'p': {a: np.array([r['arms'][a]['mean'] for r in rows]) for a in protocol['arms']}})

    def evaluate(selection, mode):
        cells = []
        for cell in arrays:
            counts = np.array([selection[cell['month'], uid] for uid in cell['ids']])
            prediction = np.array([cell['p'][level_arm(n, mode)][i] for i, n in enumerate(counts)])
            metrics = report.cell_metrics(cell['y'], cell['prior'], prediction, cell['w'])
            metrics['weighted_average_news_count'] = float(np.average(counts, weights=cell['w']))
            metrics['unweighted_average_news_count'] = float(counts.mean())
            cells.append({'month': cell['month'], 'repeat': cell['repeat'], 'arms': {'selected': metrics}})
        return report.summarize(cells, ['selected'])['selected'], cells

    by_seed = []
    for seed in SEEDS:
        matched = allocations[seed]
        shuffles = []
        for draw in range(20):
            rng = np.random.default_rng(seed*100+draw)
            randomized = {}
            for month, ids in groups.items():
                labels = [matched[month, uid] for uid in ids]
                randomized.update({(month, uid): int(n) for uid, n in zip(ids, rng.permutation(labels))})
            shuffles.append(randomized)
        result = {'seed': seed, 'modes': {}}
        for mode in ('complete', 'reduced'):
            point, cells = evaluate(matched, mode)
            null = [evaluate(selection, mode)[0] for selection in shuffles]
            mean_null = {key: float(np.mean([row[key] for row in null])) for key in point}
            uniform = old_readout['weighted_metrics']['baseline' if mode == 'complete' else 'news_8_reduced']
            result['modes'][mode] = {'matched': point, 'shuffled_mean': mean_null,
                'matched_minus_shuffled_mean': {key: point[key]-mean_null[key] for key in point},
                'matched_minus_uniform_8': {key: point[key]-uniform[key] for key in uniform},
                'monthly': [{'month': month, 'metrics': report.summarize([c for c in cells if c['month'] == month], ['selected'])['selected']}
                            for month in protocol['months']]}
        by_seed.append(result)
    if sha(allocation_path) != allocation_digest_before_truth:
        raise ValueError('Allocation modified after reading truth')
    summary = {'status': 'completed_offline_development_only', 'new_api_calls': 0, 'new_q9_fits': 0,
        'new_llm_answers': 0, 'new_cost_usd': 0, 'automatic_upgrade': False,
        'common_person_months': len(support), 'full_input_person_months': len(identifiers),
        'independent_people': len({uid for _, uid in support}), 'months': protocol['months'],
        'generation_repeats': protocol['generation_repeats'], 'assignment_seeds': list(SEEDS),
        'shuffle_controls_per_seed': 20, 'quota_per_96': {str(level): count for level, count in QUOTA},
        'quota_is_design_not_measured_population_frequency': True,
        'external_attention_predictive_checks': cv, 'by_assignment_seed': by_seed,
        'modes': {mode: {
            'uniform_8': old_readout['weighted_metrics']['baseline' if mode == 'complete' else 'news_8_reduced'],
            'carry': old_readout['weighted_metrics']['carry'],
            'matched_assignment_range_not_confidence_interval': ranges([row['modes'][mode]['matched'] for row in by_seed]),
            'shuffled_mean_assignment_range_not_confidence_interval': ranges([row['modes'][mode]['shuffled_mean'] for row in by_seed]),
            'matched_minus_shuffled_range_not_confidence_interval': ranges([row['modes'][mode]['matched_minus_shuffled_mean'] for row in by_seed]),
            'matched_minus_uniform_8_range_not_confidence_interval': ranges([row['modes'][mode]['matched_minus_uniform_8'] for row in by_seed]),
            'seeds_center_and_w1_better_than_shuffled_mean': sum(
                row['modes'][mode]['matched_minus_shuffled_mean']['center_mae_pp'] < 0
                and row['modes'][mode]['matched_minus_shuffled_mean']['w1_pp'] < 0 for row in by_seed)}
            for mode in ('complete', 'reduced')},
        'allocation_sha256_before_truth': allocation_digest_before_truth, 'source_sha256': source_hashes,
        'limits': ['All six months already inspected; no independent confirmation or causal human attention estimate.',
            'Ranks/quota translate survey agreement into experimental exposure, not measured article counts.',
            'Counts match but survey-weighted article totals may differ; report the discrepancy.',
            'Same stable random quantiles reused per ID; monthly quota rank may change exposure.',
            'External sample is unweighted and cross-survey/time transport remains unvalidated.',
            'Ranges describe assignment sensitivity, not confidence intervals or significance.',
            'Whole archived replies selected; no new simulation, cross-person interaction or 30-40 news condition.'],
        'seconds': perf_counter()-began}
    (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    return summary
