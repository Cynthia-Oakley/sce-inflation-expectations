"""Offline-only prior effect evaluation: fitting, identity, copying and updates."""
from collections import Counter
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from .confidence_trial import check_frozen, dump, sha
from .household_state_analysis import density
from .lifetime_analysis import metrics, point_value, SCORE_KEYS
from .news_exposure_analysis import finite, statistics
from .prior_belief_preparation import ARMS, MONTHS, month_offset, signed_point
from .prior_belief_experiment import message_hash
from .scoring.sce_q9_frozen import provenance


def copying_and_updates(rows, arm):
    complete = [r for r in rows if all(finite(r.get(k)) for k in ('real', arm, 'own_prior'))]
    if not complete:
        return {'n': 0}
    observed = np.array([r['real'] - r['own_prior'] for r in complete])
    predicted = np.array([r[arm] - r['own_prior'] for r in complete])
    nonzero = abs(observed) > 1e-9
    identity = {'n': len(complete), 'mean_signed_update_pp': float(predicted.mean()),
        'mean_absolute_update_pp': float(abs(predicted).mean()),
        'real_mean_signed_update_pp': float(observed.mean()),
        'update_MAE_pp': float(abs(predicted - observed).mean()),
        'real_nonzero_update_n': int(nonzero.sum()),
        'update_sign_agreement': float(np.mean(np.sign(predicted[nonzero]) == np.sign(observed[nonzero]))) if nonzero.any() else None,
        'scope': 'signed-center changes relative to own observed t-1; overlapping horizons, not evidence of causal learning'}
    supplied = [r for r in complete if r['supplied_priors'].get(arm) is not None and r['raw_answers'].get(arm) is not None]
    distances = [float(np.abs(np.asarray(r['raw_answers'][arm]) - r['supplied_priors'][arm]).sum()) for r in supplied]
    identity['supplied_prior_raw_copying'] = {'n': len(supplied),
        'exact_copy_n': sum(x <= 1e-9 for x in distances),
        'mean_probability_L1_percentage_points': float(np.mean(distances)) if distances else None}
    return identity


def evaluate_rows(rows, point=False, bootstrap=1000):
    result = metrics(rows, point=point, bootstrap=bootstrap, arms=ARMS)
    # Generic three-group evaluation reports permuted-minus-own. Present the
    # predeclared primary own-minus-permuted as well, without refitting anything.
    opposite = result['contrasts'].get('permuted_previous_minus_own_previous')
    if opposite:
        inverse = {}
        for k in SCORE_KEYS:
            value = opposite[k]
            interval = value['paired_person_bootstrap_95_interval_pp']
            inverse[k] = {'change_pp': -value['change_pp'],
                'paired_person_bootstrap_95_interval_pp': None if interval is None else [-interval[1], -interval[0]]}
        inverse['average_response_shift_pp'] = -opposite['average_response_shift_pp']
        result['contrasts']['own_previous_minus_permuted_previous'] = inverse
    common = [r for r in rows if all(finite(r.get(k)) for k in ('real',) + ARMS + ('own_prior',))]
    result['prior_persistence_common_sample'] = statistics(
        [r['own_prior'] for r in common], [r['real'] for r in common], point=point)
    if not point:
        result['updates_and_copying'] = {arm: copying_and_updates(common, arm) for arm in ARMS}
    return result


def analyze(root, trial, out):
    root, trial, out = (Path(p).resolve() for p in (root, trial, out))
    if out.exists() or not out.is_relative_to(root / 'outputs'):
        raise ValueError('fresh ignored analysis output required')
    plan = json.loads((trial / 'trial_manifest.json').read_text())
    if plan['status'] != 'completed_pending_analysis' or len(plan['jobs']) != 24 or any(j.get('exit_code') != 0 for j in plan['jobs']):
        raise ValueError('24 completed real cells required')
    check_frozen(root, trial, plan)
    scorer = provenance()
    if not scorer['live_matches_pinned']:
        raise ValueError('frozen scorer drift')
    candidate_summary_path = root / next(p for p in plan['source_sha256'] if p.endswith('sce_prior_preparation_20261013_v4/summary.json'))
    candidate = candidate_summary_path.parent
    reference = candidate / 'labeled_reference_private.parquet'
    if sha(reference) != plan['source_sha256'][str(reference.relative_to(root))]:
        raise ValueError('current/previous evaluation reference drift')
    data = pd.read_parquet(reference)
    index = {(int(r['date']), f"sce_u{int(r['userid'])}"): r for r in data.to_dict('records')}
    links = json.loads((trial / 'evaluation_links_private.json').read_text())
    result = {'status': 'completed_offline_analysis', 'scorer': scorer, 'trial': str(trial.relative_to(root)),
        'trial_manifest_sha256': sha(trial / 'trial_manifest.json'), 'evaluation_reference_sha256': sha(reference),
        'months': {}, 'runs': [], 'actual_calls': 0, 'conservative_cost_usd': 0., 'new_analysis_api_calls': 0,
        'evaluation': plan['preregistered_evaluation'], 'limits': plan['limitations'], 'not_vendor_invoice': True,
        'median_convention': 'existing project empirical quantile for Q9, interpolation for Q8; same for all arms and persistence; earlier preparation np.median diagnostics may differ for even n'}
    private = []
    for month in MONTHS:
        selected = [r for r in links if r['month'] == month]
        ids = {r['agent_id'] for r in selected}
        if len(ids) != 12 or len(selected) != 12:
            raise ValueError('fixed twelve-person selection required')
        profiles = {p['agent_id']: p['attributes'] for p in json.loads((trial / month / 'population.json').read_text())['personas']}
        result['months'][month] = {'metadata': plan['metadata'][month], 'repeats': {}}
        for repeat in (1, 2):
            answers, supplied = {}, {}
            for arm in ARMS:
                job = next(j for j in plan['jobs'] if (j['month'], j['arm'], j['repeat']) == (month, arm, repeat))
                run = root / 'outputs/local_runs' / job['run_id']
                manifest = json.loads((run / 'run_manifest.json').read_text())
                if manifest['llm_kind'] != 'openai' or manifest['n_agents'] != 12 or manifest['execution_purpose'] != 'observed_prior_behaviour_trial':
                    raise ValueError('actual run identity mismatch')
                for name, h in {**manifest['effective_artifact_sha256'], **manifest['source_snapshot_sha256']}.items():
                    if sha(run / name) != h:
                        raise ValueError('actual input/code snapshot drift')
                    if name.startswith('source_snapshot/study/'):
                        frozen = plan['code_sha256'].get('studies/sce_inflation_expectations/' + name.removeprefix('source_snapshot/study/'))
                        if frozen is None or frozen != h:
                            raise ValueError('actual provider not in frozen source list')
                if manifest['source_snapshot_sha256']['source_snapshot/run_sce_local.py'] != plan['code_sha256']['scripts/run_sce_local.py']:
                    raise ValueError('executed entry mismatch')
                calls = [json.loads(l) for l in (run / 'llm_calls.jsonl').read_text().splitlines()]
                previews = {r['agent_id']: r for r in json.loads((trial / month / f'preview_{arm}.json').read_text())}
                if len(calls) != 12 or {c['agent_id'] for c in calls} != ids:
                    raise ValueError('actual call count/roster')
                for call in calls:
                    p = previews[call['agent_id']]
                    if (call['attempt_idx'] != 0 or call['requested_model'] != plan['model']
                            or call['temperature'] != .5 or call['max_tokens'] != 1024
                            or call['prompt_text'] != json.dumps(p['messages'], ensure_ascii=False)
                            or call['prompt_sha256'] != message_hash(p['messages'])
                            or hashlib.sha256((call['raw_response_text'] or '').encode()).hexdigest() != call['raw_response_sha256']):
                        raise ValueError('actual message/model/response differs from frozen case')
                with duckdb.connect(str(run / 'study.duckdb'), read_only=True) as db:
                    raw = db.execute("SELECT agent_id,action_payload FROM panel WHERE step=1 AND action_kind='sce_answer'").fetchall()
                if len(raw) != 12 or {a for a, _ in raw} != ids:
                    raise ValueError('trajectory count/roster')
                answers[arm] = {aid: json.loads(p) if isinstance(p, str) else p for aid, p in raw}
                config = json.loads((trial / month / f'simulation_{arm}.json').read_text())
                supplied[arm] = {aid: row['prior'] for aid, row in config['decision_args']['prior_bundle']['rows'].items()}
                ledger = json.loads((run / 'cost_ledger.json').read_text())
                if ledger['call_count'] != len(calls) or ledger['estimated_cost_usd'] is None or ledger['estimated_cost_usd'] > job['job_cap_usd'] + 1e-9:
                    raise ValueError('call ledger or cost cap mismatch')
                result['actual_calls'] += len(calls)
                result['conservative_cost_usd'] += ledger['estimated_cost_usd']
                result['runs'].append({'month': month, 'arm': arm, 'repeat': repeat, 'calls': len(calls),
                    'estimated_cost_usd': ledger['estimated_cost_usd'], 'input_tokens': ledger['total_prompt_tokens'],
                    'output_tokens': ledger['total_completion_tokens'], 'returned_models': dict(Counter(c['returned_model'] for c in calls)),
                    'validation_counts': dict(Counter(p['validation_status'] for p in answers[arm].values())),
                    'llm_calls_sha256': sha(run / 'llm_calls.jsonl'), 'store_sha256': sha(run / 'study.duckdb')})
            rows = {q: [] for q in ('Q9', 'Q8', 'personal_uncertainty', 'raw_deflation_probability')}
            for link in selected:
                aid = link['agent_id']
                actual = index[int(month), link['source_agent_id']]
                old = index[month_offset(month, -1), link['source_agent_id']]
                bins = {'real': [float(actual[f'Q9_bin{i}']) for i in range(1, 11)],
                        'own_prior': [float(old[f'Q9_bin{i}']) for i in range(1, 11)]}
                bins.update({a: [answers[a][aid][f'q9_bin{i}'] for i in range(1, 11)] if answers[a][aid]['validation_status'] == 'valid' else [None] * 10 for a in ARMS})
                fits = {a: density(v) for a, v in bins.items()}
                weight = float(actual['weight'])
                base = {'agent_id': aid, 'profile': profiles[aid], 'weight': weight if finite(weight) else None,
                    'raw_answers': {a: v if all(finite(x) for x in v) else None for a, v in bins.items() if a in ARMS},
                    'supplied_priors': {a: None if supplied[a][aid] is None else [supplied[a][aid]['q9'][f'bin{i}'] for i in range(1, 11)] for a in ARMS}}
                for q, field in (('Q9', 'mean'), ('personal_uncertainty', 'iqr')):
                    rows[q].append({**base, **{a: v[field] for a, v in fits.items()}})
                rows['Q8'].append({**base, 'real': signed_point(actual['Q8v2part2']), 'own_prior': signed_point(old['Q8v2part2']),
                                  **{a: point_value(answers[a][aid]) for a in ARMS}})
                rows['raw_deflation_probability'].append({**base, **{a: sum(v[5:]) if all(finite(x) for x in v) and abs(sum(v) - 100) <= .5 else None for a, v in bins.items()}})
            cell = {q: evaluate_rows(rr, point=q == 'Q8') if q in ('Q9', 'Q8') else metrics(rr, arms=ARMS)
                    for q, rr in rows.items()}
            result['months'][month]['repeats'][str(repeat)] = cell
            private.extend({'month': month, 'repeat': repeat, 'measure': q, **r} for q, rr in rows.items() for r in rr)
    result['across_months_by_repeat'] = {}
    for repeat in (1, 2):
        cells = [result['months'][m]['repeats'][str(repeat)]['Q9'] for m in MONTHS]
        totals = {a: {k: float(np.mean([c['arms'][a][k] for c in cells]))
                         if all(finite(c['arms'][a][k]) for c in cells) else None for k in SCORE_KEYS} for a in ARMS}
        totals['own_prior_persistence'] = {k: float(np.mean([c['prior_persistence_common_sample'][k] for c in cells]))
            if all(finite(c['prior_persistence_common_sample'][k]) for c in cells) else None for k in SCORE_KEYS}
        totals['own_vs_no_prior_both_improve_months'] = sum(all(finite(c['arms'][a][k]) for a in ARMS[:2] for k in SCORE_KEYS[:2])
            and all(c['arms']['own_previous'][k] < c['arms']['no_prior'][k] for k in SCORE_KEYS[:2]) for c in cells)
        result['across_months_by_repeat'][str(repeat)] = totals
    result['candidate_continue_gate_passed'] = all(
        s['own_vs_no_prior_both_improve_months'] >= 3 and all(finite(s[a][k]) for a in ARMS[:2] for k in SCORE_KEYS[:2])
        and all(s['own_previous'][k] < s['no_prior'][k] for k in SCORE_KEYS[:2])
        for s in result['across_months_by_repeat'].values())
    if result['actual_calls'] != 288 or result['conservative_cost_usd'] > plan['proposed_simulation_cap_usd'] + 1e-9:
        raise ValueError('total call or cost cap mismatch')
    out.mkdir(parents=True)
    dump(out / 'summary.json', result)
    dump(out / 'paired_evaluation_private.json', private)
    return result


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trial', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args(argv)
    result = analyze(Path(__file__).resolve().parents[2], args.trial, args.out)
    print(json.dumps({k: result[k] for k in ('actual_calls', 'conservative_cost_usd', 'across_months_by_repeat', 'candidate_continue_gate_passed')}))
