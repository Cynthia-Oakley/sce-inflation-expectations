#!/usr/bin/env python3
"""Score archived annual DeepSeek and optional exact-input Qwen offline."""
import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.annual_model_comparison import validated_answer
from studies.sce_inflation_expectations.household_state_analysis import density
from studies.sce_inflation_expectations.model_comparison_analysis import comparison_metrics
from studies.sce_inflation_expectations.model_counterfactual import guarded_payload
from studies.sce_inflation_expectations.scoring.sce_q9_frozen import provenance


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def lines(p):
    return [json.loads(s) for s in p.read_text().splitlines() if s]


@lru_cache(maxsize=None)
def fitted(bins):
    return density(list(bins))


def fit_raw(bins):
    if any(type(v) not in (float, int) or not math.isfinite(v) for v in bins):
        return {'mean': None, 'iqr': None, 'status': 'invalid_bins'}
    return fitted(tuple(bins))


def annual(monthly, arms):
    result = {}
    for arm in arms:
        errors, signed, medians, real, w1, iqrgaps, individual = [], [], [], [], [], [], []
        for month, m in sorted(monthly.items()):
            metric = m['Q9']
            if metric.get('n_common', 0) == 0:
                continue
            v = metric['arms'][arm]
            errors.append(v['sample_median_absolute_error_pp'])
            medians.append(v['distribution']['median'])
            real.append(metric['matched_real']['median'])
            signed.append(medians[-1] - real[-1])
            w1.append(v['wasserstein_1_pp'])
            iqrgaps.append(v['sample_iqr_absolute_gap_pp'])
            individual.append(v['individual_mae_pp'])
        result[arm] = {'months': len(errors), 'monthly_median_mae_pp': float(np.mean(errors)),
                       'monthly_median_rmse_pp': float(np.sqrt(np.mean(np.square(errors)))),
                       'monthly_median_bias_pp': float(np.mean(signed)),
                       'mean_wasserstein_pp': float(np.mean(w1)),
                       'mean_iqr_absolute_gap_pp': float(np.mean(iqrgaps)),
                       'equal_month_individual_mae_pp': float(np.mean(individual))}
        if len(medians) == 12:
            actual_change, predicted_change = np.diff(real), np.diff(medians)
            changed = np.abs(actual_change) > 1e-8
            result[arm]['trend'] = {
                'adjacent_pairs': 11, 'real_nonzero_changes': int(changed.sum()),
                'direction_matches_on_real_changes': int((np.sign(actual_change[changed]) ==
                                                          np.sign(predicted_change[changed])).sum()),
                'all_direction_matches_including_ties': int((np.sign(actual_change) ==
                                                             np.sign(predicted_change)).sum())}
    if 'qwen' in arms:
        baseline, trial = result['deepseek'], result['qwen']
        improved = sum(m['Q9']['arms']['qwen']['sample_median_absolute_error_pp'] <
                       m['Q9']['arms']['deepseek']['sample_median_absolute_error_pp']
                       for m in monthly.values() if m['Q9'].get('n_common', 0))
        reduction = 1 - trial['monthly_median_mae_pp'] / baseline['monthly_median_mae_pp'] if baseline['monthly_median_mae_pp'] else None
        result['development_gate'] = {'mae_relative_reduction': reduction, 'months_improved': improved,
            'worth_future_confirmation': bool(baseline['months'] == trial['months'] == 12 and
                reduction is not None and reduction >= .1 and improved >= 7 and
                trial['mean_wasserstein_pp'] <= baseline['mean_wasserstein_pp']),
            'meaning': 'pragmatic preregistered prioritization gate; not statistical significance'}
    return result


def bootstrap_panel(rows, arms):
    if 'qwen' not in arms:
        return None
    people = sorted({r['panel_case'] for r in rows})
    array = np.full((12, len(people), 3), np.nan)
    for row in rows:
        month = row['month'] % 100 - 1
        values = [row['Q9'].get(k) for k in ['real', 'deepseek', 'qwen']]
        if all(type(v) in (float, int) and math.isfinite(v) for v in values):
            array[month, people.index(row['panel_case'])] = values
    rng = np.random.default_rng(42)
    values = []
    for _ in range(2000):
        sample = array[:, rng.integers(0, len(people), len(people)), :]
        differences = []
        for m in sample:
            m = m[np.isfinite(m).all(axis=1)]
            if not len(m):
                break
            actual, ds, qw = np.median(m, axis=0)
            differences.append(abs(qw - actual) - abs(ds - actual))
        if len(differences) == 12:
            values.append(float(np.mean(differences)))
    return {'resamples': len(values), 'seed': 42, 'unit': 'respondent entire-year block',
            'qwen_minus_deepseek_monthly_median_mae_pp_percentile_interval':
                list(map(float, np.quantile(values, [.025, .975]))) if values else None,
            'limitations': 'conditional on fixed old panel and one generated reply per case; no model draw or month resampling'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inputs', type=Path, required=True)
    ap.add_argument('--receipt', type=Path, required=True)
    ap.add_argument('--run', type=Path)
    ap.add_argument('--truth', type=Path, default=ROOT / 'data/evaluation/sce_truth_main2021.json')
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    plan = json.loads((args.inputs / 'summary.json').read_text())
    receipt = json.loads(args.receipt.read_text())
    assert sha(args.inputs / 'deepseek_reference_private.jsonl') == receipt['reference_sha256']
    assert sha(args.inputs / 'requests_prepared.jsonl') == receipt['requests_sha256']
    assert sha(args.truth) == receipt['evaluation_truth_sha256']
    scorer = provenance()
    assert scorer['live_matches_pinned']
    refs = lines(args.inputs / 'deepseek_reference_private.jsonl')
    source = ROOT / 'outputs/local_runs' / plan['source_run_id'] / 'llm_calls.jsonl'
    assert sha(source) == plan['source_sha256'][str(source.relative_to(ROOT))]
    truth = {(int(r['date']), 'sce_u' + str(int(r['userid']))): r
             for r in json.loads(args.truth.read_text())['per_person']}
    requests = {r['case_id']: r for r in lines(args.inputs / 'requests_prepared.jsonl')}
    for ref in refs:
        assert hashlib.sha256(json.dumps(requests[ref['case_id']]['payload']['messages'], ensure_ascii=False).encode()).hexdigest() == ref['prompt_sha256']
    qwen, run = {}, None
    if args.run:
        run = json.loads((args.run / 'run_summary.json').read_text())
        assert run['status'] != 'running' and run['requests_sha256'] == plan['requests_sha256']
        for call in lines(args.run / 'llm_calls.jsonl'):
            if call.get('error') or 'answer' not in call:
                continue
            case = call['case_id']
            assert case not in qwen
            payload = guarded_payload(requests[case])
            assert hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest() == call['payload_sha256']
            answer, error = validated_answer(call['response']['choices'][0]['message']['content'])
            assert not error and answer == call['answer']
            qwen[case] = answer
    arms = ['deepseek', *(['qwen'] if args.run else [])]
    private, monthly, statuses = [], {}, Counter()
    for ref in refs:
        month = ref['month']
        person = truth[(month, ref['source_agent_id'])]
        ds, error = validated_answer(ref['reference_response'])
        assert not error
        answers = {'deepseek': ds}
        if ref['case_id'] in qwen:
            answers['qwen'] = qwen[ref['case_id']]
        fits = {'real': fit_raw([person[f'Q9_bin{i}'] for i in range(1, 11)]),
                **{arm: fit_raw(a['bins']) for arm, a in answers.items()}}
        statuses.update(f'{arm}:{v["status"]}' for arm, v in fits.items())
        private.append({'case_id': ref['case_id'], 'panel_case': ref['panel_case'], 'month': month,
            'Q9': {k: f['mean'] for k, f in fits.items()},
            'Q8': {'real': person.get('Q8v2part2'), **{k: a['point_pct'] for k, a in answers.items()}},
            'Q9_official_person_mean': person.get('Q9_mean')})
    for month in range(202101, 202113):
        sub = [r for r in private if r['month'] == month]
        q9 = [r['Q9'] for r in sub]
        q8 = [r['Q8'] for r in sub]
        monthly[str(month)] = {
            'Q9': comparison_metrics(q9, arms) if any(all(r.get(k) is not None for k in ['real', *arms]) for r in q9) else {'n_common': 0},
            'Q8_secondary': comparison_metrics(q8, arms) if any(all(r.get(k) is not None for k in ['real', *arms]) for r in q8) else {'n_common': 0}}
    full_rows = []
    for call in lines(source):
        month = int(call['target_month'].replace('-', ''))
        person = truth[(month, call['agent_id'])]
        answer, error = validated_answer(call['raw_response_text'])
        assert not error
        full_rows.append({'month': month, 'real': fit_raw([person[f'Q9_bin{i}'] for i in range(1, 11)])['mean'],
                         'deepseek': fit_raw(answer['bins'])['mean']})
    full_months = {str(month): {'Q9': comparison_metrics([r for r in full_rows if r['month'] == month], ['deepseek'])}
                   for month in range(202101, 202113)}
    complete = [r['panel_case'] for r in private if all(r['Q9'].get(k) is not None for k in ['real', *arms])]
    counts = Counter(complete)
    full_panel = {person for person, n in counts.items() if n == 12}
    sensitivity = {}
    if full_panel:
        sensitivity = {str(month): {'Q9': comparison_metrics([r['Q9'] for r in private if r['month'] == month and r['panel_case'] in full_panel], arms)}
                       for month in range(202101, 202113)}
    result = {'status': 'complete model comparison' if len(qwen) == 240 else 'DeepSeek-only or incomplete Qwen diagnostic',
        'months': monthly, 'annual': annual(monthly, arms), 'fitting_statuses': dict(statuses),
        'complete_year_common_panel': {'n_persons': len(full_panel), 'annual': annual(sensitivity, arms) if sensitivity else None},
        'deepseek_73_background_only': {'annual': annual(full_months, ['deepseek']), 'months': full_months},
        'bootstrap_diagnostic': bootstrap_panel(private, arms), 'qwen_unique_valid_raw': len(qwen),
        'run': run, 'scorer': scorer, 'new_calls_in_analysis': 0,
        'estimand': 'equal-weight matched old panel sample; not official national headline; old 4-signal E',
        'limitations': ['development year, one draw, fixed old panel selected for persistence',
                        'model/provider/quantization/date effects not separated',
                        'same approximate scorer applied to real and generated Q9',
                        'Qwen shortlist chosen after prior May/June diagnostics, not a blind model contest'],
        'source_hashes': {str(p.resolve().relative_to(ROOT)): sha(p) for p in
                          [source, args.truth, Path(__file__).resolve(), args.receipt,
                           ROOT / 'studies/sce_inflation_expectations/model_comparison_analysis.py',
                           ROOT / 'studies/sce_inflation_expectations/household_state_analysis.py',
                           *[ROOT / 'studies/sce_inflation_expectations/scoring' / name
                             for name in ['sce_q9_frozen.py', 'sce_q9.py', 'beta_fit_kernel.py']]]}}
    if args.run:
        result['source_hashes'].update({str(p.resolve().relative_to(ROOT)): sha(p) for p in
                                       [args.run / 'llm_calls.jsonl', args.run / 'run_summary.json']})
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    (args.out / 'paired_evaluation_private.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False, allow_nan=False) + '\n' for r in private))
    snapshot = args.out / 'scorer_snapshot'
    snapshot.mkdir()
    for name in ['sce_q9_frozen.py', 'sce_q9.py', 'beta_fit_kernel.py']:
        (snapshot / name).write_bytes((ROOT / 'studies/sce_inflation_expectations/scoring' / name).read_bytes())
    if all(m['Q9'].get('n_common', 0) for m in monthly.values()):
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        x = np.arange(1, 13)
        fig, axes = plt.subplots(2, 1, figsize=(9, 6), sharex=True, constrained_layout=True)
        axes[0].plot(x, [m['Q9']['matched_real']['median'] for m in monthly.values()], label='Matched real sample', color='black')
        for arm in arms:
            axes[0].plot(x, [m['Q9']['arms'][arm]['distribution']['median'] for m in monthly.values()], marker='o', label=arm)
            axes[1].plot(x, [m['Q9']['arms'][arm]['distribution']['iqr'] for m in monthly.values()], marker='o', label=arm)
        axes[1].plot(x, [m['Q9']['matched_real']['iqr'] for m in monthly.values()], label='Matched real sample', color='black')
        axes[0].set_title('2021 old-input matched panel: Q9-derived expectations')
        axes[0].set_ylabel('Across-person median (%)')
        axes[1].set_ylabel('Across-person IQR (pp)')
        axes[1].set_xlabel('Month of 2021; common scored cases within each month')
        for ax in axes:
            ax.legend()
            ax.grid(alpha=.2)
        fig.savefig(args.out / 'monthly_comparison.png', dpi=180)
        plt.close(fig)
    print(json.dumps({'status': result['status'], 'annual': result['annual'],
                      'full_panel_n': len(full_panel), 'out': str(args.out)}, ensure_ascii=False), flush=True)


if __name__ == '__main__': main()
