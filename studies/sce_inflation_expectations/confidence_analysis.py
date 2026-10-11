"""Evaluation only: raw SCE answers never imported by simulation providers."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from openpyxl import load_workbook
from .confidence_experiment import ARMS
from .confidence_trial import MONTHS, sha, dump, check_frozen
from .household_state_analysis import density
from .news_exposure_analysis import describe, finite, statistics
from .monthly_analysis import weighted_summary, date_group
from .scoring.sce_q9_frozen import provenance

TRUTH_FIELDS = ['date', 'userid', 'weight', 'Q8v2part2', 'Q9_mean', 'Q9_iqr'] + [f'Q9_bin{i}' for i in range(1, 11)]


def prepare_truth(root, out):
    """Fresh evaluation cache extracted from official raw workbook, no P/E edits."""
    root, out = Path(root).resolve(), Path(out).resolve()
    if out.exists() or not out.is_relative_to(root / 'data/evaluation'):
        raise ValueError('fresh evaluation-only directory required')
    source = root / 'data/raw/sce_audit_20260928/micro_2020_2024.xlsx'
    workbook = load_workbook(source, read_only=True, data_only=True)
    iterator = workbook[workbook.sheetnames[0]].iter_rows(values_only=True)
    next(iterator)
    header = list(next(iterator))
    indices = {name: header.index(name) for name in TRUTH_FIELDS}
    records = []
    for row in iterator:
        if str(row[indices['date']]) not in MONTHS:
            continue
        records.append({name: row[index] for name, index in indices.items()})
    workbook.close()
    data = pd.DataFrame(records, columns=TRUTH_FIELDS)
    if data.empty or data.duplicated(['date', 'userid']).any() or set(data.date.astype(int).astype(str)) != set(MONTHS):
        raise ValueError('truth month/identity coverage')
    out.mkdir(parents=True)
    data.to_parquet(out / 'raw_reference.parquet', index=False)
    receipt = {'source': str(source.relative_to(root)), 'source_sha256': sha(source),
               'created_at_utc': datetime.now(timezone.utc).isoformat(), 'fields': TRUTH_FIELDS,
               'months': list(MONTHS), 'rows': len(data), 'parquet_sha256': sha(out / 'raw_reference.parquet'),
               'purpose': 'evaluation only; never read by preparation or simulation', 'new_api_calls': 0}
    dump(out / 'receipt.json', receipt)
    return receipt


def paired_metrics(rows, point=False, bootstrap=1000):
    common = [r for r in rows if all(finite(r.get(k)) for k in ('real',) + ARMS)]
    real = np.asarray([r['real'] for r in common])
    result = {'n_selected': len(rows), 'n_common': len(common), 'n_excluded': len(rows)-len(common),
              'real': describe(real, point), 'arms': {}, 'confidence_minus_no_confidence': {}}
    for arm in ARMS:
        result['arms'][arm] = statistics([r[arm] for r in common], real, point)
        valid_weight = [r for r in common if finite(r.get('weight')) and r['weight'] > 0]
        weights = [r['weight'] for r in valid_weight]
        sw = weighted_summary([r[arm] for r in valid_weight], weights, interpolate_median=point)
        rw = weighted_summary([r['real'] for r in valid_weight], weights, interpolate_median=point)
        result['arms'][arm]['weighted_auxiliary'] = {'simulated': sw, 'real': rw,
            'median_absolute_error_pp': abs(sw['weighted_median_pp']-rw['weighted_median_pp']) if valid_weight else None}
        groups = {}
        for key in ('housing_tenure', 'age_group', 'numeracy', 'answer_date_group'):
            categories = sorted({str(r.get(key) if key == 'answer_date_group' else r['profile'].get(key)) for r in common})
            groups[key] = {}
            for category in categories:
                subset = [r for r in common if str(r.get(key) if key == 'answer_date_group' else r['profile'].get(key)) == category]
                groups[key][category] = {'n': len(subset), 'comparison': statistics([r[arm] for r in subset], [r['real'] for r in subset], point) if len(subset) >= 5 else None}
        result['arms'][arm]['groups'] = groups
    if not common:
        return result
    keys = ('median_absolute_error_pp', 'distribution_W1_pp', 'IQR_absolute_gap_pp')
    intervals = {key: [] for key in keys}
    rng = np.random.default_rng(42)
    for idx in rng.integers(0, len(common), size=(bootstrap, len(common))):
        scores = {arm: statistics(np.asarray([r[arm] for r in common])[idx], real[idx], point) for arm in ARMS}
        for key in keys:
            intervals[key].append(scores[ARMS[1]][key] - scores[ARMS[0]][key])
    for key in keys:
        result['confidence_minus_no_confidence'][key] = {'change_pp': result['arms'][ARMS[1]][key] - result['arms'][ARMS[0]][key],
            'paired_person_bootstrap_95_interval_pp': np.quantile(intervals[key], [.025, .975]).tolist()}
    result['bootstrap_scope'] = 'fixed news/confidence conditional person sample; repeat generations and periods reported separately'
    result['average_response_shift_pp'] = float(np.mean([r[ARMS[1]] - r[ARMS[0]] for r in common]))
    return result


def analyze(root, trial, truth_dir, out):
    root, trial, truth_dir, out = (Path(p).resolve() for p in (root, trial, truth_dir, out))
    if out.exists() or not out.is_relative_to(root / 'outputs'):
        raise ValueError('fresh ignored analysis directory required')
    plan = json.loads((trial / 'trial_manifest.json').read_text())
    if plan['status'] != 'completed_pending_analysis' or len(plan['jobs']) != 16:
        raise ValueError('requires all sixteen completed real cells')
    check_frozen(root, trial, plan)
    scorer = provenance()
    if not scorer['live_matches_pinned']:
        raise ValueError('scorer drift')
    truth_receipt = json.loads((truth_dir / 'receipt.json').read_text())
    if sha(truth_dir / 'raw_reference.parquet') != truth_receipt['parquet_sha256'] or sha(root / truth_receipt['source']) != truth_receipt['source_sha256']:
        raise ValueError('truth source drift')
    truth_data = pd.read_parquet(truth_dir / 'raw_reference.parquet')
    truth = {(str(int(r['date'])), f"sce_u{int(r['userid'])}"): r for r in truth_data.to_dict('records')}
    links = json.loads((trial / 'evaluation_links_private.json').read_text())
    output = {'status': 'completed_offline_analysis', 'scorer': scorer, 'months': {}, 'runs': [],
              'trial': str(trial.relative_to(root)), 'trial_manifest_sha256': sha(trial / 'trial_manifest.json'),
              'truth_receipt': truth_receipt, 'actual_calls': 0, 'conservative_cost_usd': 0., 'not_vendor_invoice': True,
              'new_analysis_api_calls': 0, 'limits': plan['limitations'], 'evaluation': plan['preregistered_evaluation']}
    private = []
    for month in MONTHS:
        month_links = [r for r in links if r['month'] == month]
        profiles = {p['agent_id']: p['attributes'] for p in json.loads((trial / month / 'population.json').read_text())['personas']}
        dates_path = root / 'outputs/monthly_inputs_20261011T124521Z_77e69c5a/n48' / month / 'survey_dates.jsonl'
        dates = {r['agent_id']: r['survey_date'] for r in map(json.loads, dates_path.read_text().splitlines())}
        cutoff = plan['metadata'][month]['as_of']
        real_fit = {r['agent_id']: density([truth[(month, r['source_agent_id'])][f'Q9_bin{i}'] for i in range(1, 11)]) for r in month_links}
        result = {'metadata': plan['metadata'][month], 'repeats': {}}
        full = truth_data[truth_data.date.astype(int) == int(month)]
        # Full-month reference uses published individual derived values; selected
        # real answers below use exactly the same frozen scorer as simulations.
        result['full_month_official_derived_reference'] = {
            'Q9': weighted_summary(full.Q9_mean, full.weight),
            'Q8': weighted_summary(full.Q8v2part2, full.weight, interpolate_median=True),
            'note': 'Official derived micro reference, not rerun scorer or web headline; used only as auxiliary nationwide comparison.'}
        for repeat in (1, 2):
            answers = {}
            for arm in ARMS:
                job = next(j for j in plan['jobs'] if j['month'] == month and j['arm'] == arm and j['repeat'] == repeat)
                run_dir = root / 'outputs/local_runs' / job['run_id']
                manifest = json.loads((run_dir / 'run_manifest.json').read_text())
                if job.get('exit_code') != 0 or manifest['llm_kind'] != 'openai' or manifest['execution_purpose'] != 'confidence_behaviour_trial':
                    raise ValueError('real run identity')
                for name, h in manifest['effective_artifact_sha256'].items() | manifest['source_snapshot_sha256'].items():
                    if sha(run_dir / name) != h:
                        raise ValueError('effective input or execution source hash changed')
                    if name.startswith('source_snapshot/study/'):
                        frozen = plan['code_sha256'].get('studies/sce_inflation_expectations/' + name.removeprefix('source_snapshot/study/'))
                        if frozen and h != frozen:
                            raise ValueError('executed study differs from frozen source')
                calls = [json.loads(line) for line in (run_dir / 'llm_calls.jsonl').read_text().splitlines()]
                previews = {p['agent_id']: p for p in json.loads((trial / month / f'preview_{arm}.json').read_text())}
                if len(calls) != 48 or {c['agent_id'] for c in calls} != set(previews):
                    raise ValueError('call roster')
                for call in calls:
                    if call['attempt_idx'] != 0 or call['requested_model'] != plan['model'] or call['temperature'] != .5 or call['prompt_text'] != json.dumps(previews[call['agent_id']]['messages'], ensure_ascii=False):
                        raise ValueError('actual prompt/model/temperature changed')
                    if call['prompt_sha256'] != previews[call['agent_id']]['prompt_sha256'] or hashlib.sha256((call['raw_response_text'] or '').encode()).hexdigest() != call['raw_response_sha256']:
                        raise ValueError('raw prompt/answer hash')
                with duckdb.connect(manifest['store_path'], read_only=True) as db:
                    raw = db.execute('SELECT agent_id,action_payload FROM panel WHERE step=1').fetchall()
                if len(raw) != 48 or {aid for aid, _ in raw} != set(previews):
                    raise ValueError('trajectory roster')
                answers[arm] = {aid: json.loads(p) if isinstance(p, str) else p for aid, p in raw}
                ledger = json.loads((run_dir / 'cost_ledger.json').read_text())
                output['conservative_cost_usd'] += ledger['estimated_cost_usd']
                output['actual_calls'] += len(calls)
                output['runs'].append({'month': month, 'arm': arm, 'repeat': repeat, 'calls': len(calls),
                    'estimated_cost_usd': ledger['estimated_cost_usd'], 'usage_input_tokens': ledger['total_prompt_tokens'],
                    'usage_output_tokens': ledger['total_completion_tokens'],
                    'returned_models': dict(Counter(c['returned_model'] for c in calls)),
                    'fingerprints': dict(Counter(c['system_fingerprint'] for c in calls)),
                    'statuses': dict(Counter(p['validation_status'] for p in answers[arm].values())),
                    'llm_calls_sha256': sha(run_dir / 'llm_calls.jsonl'), 'store_sha256': sha(Path(manifest['store_path']))})
            rows = {q: [] for q in ('Q9', 'Q8', 'personal_uncertainty', 'raw_deflation_probability')}
            fit_status = Counter()
            for link in month_links:
                aid = link['agent_id']
                real = truth[(month, link['source_agent_id'])]
                bins = {'real': [real[f'Q9_bin{i}'] for i in range(1, 11)]}
                for arm in ARMS:
                    p = answers[arm][aid]
                    bins[arm] = [p[f'q9_bin{i}'] for i in range(1, 11)] if p['validation_status'] == 'valid' else [None]*10
                fits = {'real': real_fit[aid], **{arm: density(bins[arm]) for arm in ARMS}}
                fit_status.update(f'{key}:{v["status"]}' for key, v in fits.items())
                base = {'agent_id': aid, 'profile': profiles[aid], 'weight': real['weight'],
                        'answer_date_group': date_group(dates[link['source_agent_id']], cutoff)}
                for q, field in (('Q9', 'mean'), ('personal_uncertainty', 'iqr')):
                    rows[q].append({**base, **{k: v[field] for k, v in fits.items()}})
                rows['Q8'].append({**base, 'real': real['Q8v2part2'], **{arm: answers[arm][aid]['point_pct'] if answers[arm][aid]['validation_status'] == 'valid' else None for arm in ARMS}})
                rows['raw_deflation_probability'].append({**base, **{key: sum(v[5:]) if all(finite(x) for x in v) and abs(sum(v)-100) <= .5 else None for key, v in bins.items()}})
            result['repeats'][str(repeat)] = {q: paired_metrics(rr, point=q == 'Q8') for q, rr in rows.items()}
            result['repeats'][str(repeat)]['fit_status_counts'] = dict(fit_status)
            private.extend({'month': month, 'repeat': repeat, 'measure': q, **r} for q, rr in rows.items() for r in rr)
        output['months'][month] = result
    output['across_months_by_repeat'] = {}
    for repeat in (1, 2):
        entry = {}
        for measure in ('Q9', 'Q8'):
            cells = [output['months'][m]['repeats'][str(repeat)][measure] for m in MONTHS]
            entry[measure] = {arm: {k: float(np.mean([c['arms'][arm][k] for c in cells])) for k in ('median_absolute_error_pp', 'distribution_W1_pp', 'IQR_absolute_gap_pp')} for arm in ARMS}
            entry[measure]['months_both_median_and_W1_improve'] = sum(c['arms'][ARMS[1]]['median_absolute_error_pp'] < c['arms'][ARMS[0]]['median_absolute_error_pp'] and c['arms'][ARMS[1]]['distribution_W1_pp'] < c['arms'][ARMS[0]]['distribution_W1_pp'] for c in cells)
        output['across_months_by_repeat'][str(repeat)] = entry
    output['candidate_upgrade_gate_passed'] = all(output['across_months_by_repeat'][str(r)]['Q9']['months_both_median_and_W1_improve'] >= 3 and all(output['across_months_by_repeat'][str(r)]['Q9'][ARMS[1]][k] < output['across_months_by_repeat'][str(r)]['Q9'][ARMS[0]][k] for k in ('median_absolute_error_pp', 'distribution_W1_pp')) for r in (1, 2))
    if output['actual_calls'] != 768 or output['conservative_cost_usd'] > plan['proposed_simulation_cap_usd']:
        raise ValueError('overall budget/call count')
    out.mkdir()
    dump(out / 'summary.json', output)
    dump(out / 'paired_evaluation_private.json', private)
    return output


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['prepare-truth', 'analyze'])
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--trial', type=Path)
    parser.add_argument('--truth', type=Path)
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    if args.mode == 'prepare-truth':
        result = prepare_truth(root, args.out)
        print(json.dumps({'rows': result['rows'], 'new_api_calls': 0}))
    else:
        if args.trial is None or args.truth is None:
            parser.error('analysis requires --trial and --truth')
        result = analyze(root, args.trial, args.truth, args.out)
        print(json.dumps({k: result[k] for k in ('actual_calls', 'conservative_cost_usd', 'across_months_by_repeat', 'candidate_upgrade_gate_passed')}))
