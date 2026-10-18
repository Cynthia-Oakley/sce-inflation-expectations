#!/usr/bin/env python3
"""Select already-generated information views using frozen past-only predictions."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.cognition import _common_person_months


def run(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output required')
    prediction = ROOT/'outputs/sce_retention_predictability_20261018_v2/predictions_private.parquet'
    prediction_summary = json.loads((prediction.parent/'summary.json').read_text())
    for fold in prediction_summary['folds']:
        if max(fold['train_months']) >= fold['year']*100+1:
            raise ValueError('Prediction training uses target year')
    # Deliberately do not load official_current_center/label_stable columns.
    f = pd.read_parquet(prediction, columns=['userid', 'month', 'history'])
    if f.duplicated(['userid', 'month']).any():
        raise ValueError('Duplicate frozen prediction')
    lookup = f.set_index(['month', 'userid'])['history'].to_dict()
    readout = ROOT/'outputs/sce_information_exposure_readout_20261019_v1/summary.json'
    result = json.loads(readout.read_text())
    evaluation = ROOT/'outputs/sce_information_exposure_evaluation_20261019_v1'
    scored = json.loads((evaluation/'summary.json').read_text())
    cases = json.loads((evaluation/'cases_private.json').read_text())
    protocol = scored['protocol']
    support = _common_person_months(cases, protocol['arms'], protocol['generation_repeats'], 'q9')
    reference = [r for r in cases if r['repeat'] == 1 and (r['month'], r['userid']) in support]
    chosen, missing, records = {}, 0, []
    for row in reference:
        key = (row['month'], row['userid'])
        p = lookup.get(key)
        good = p is not None and np.isfinite(p) and 0 <= p <= 1
        missing += not good
        chosen[key] = bool(good and p >= .5)
        records.append({'month': key[0], 'userid': key[1], 'past_keep_probability': float(p) if good else None,
                        'chosen_reduced': chosen[key]})
    groups = {month: sorted(k for k in chosen if k[0] == month) for month in protocol['months']}
    gates = {'matched_past_gate': chosen}
    for seed in range(20261019, 20261039):
        rng = np.random.default_rng(seed)
        gate = {}
        for month, keys in groups.items():
            shuffled = rng.permutation([chosen[k] for k in keys])
            gate.update(zip(keys, map(bool, shuffled)))
        gates[f'shuffled_{seed}'] = gate
    spec = importlib.util.spec_from_file_location('exposure_report', ROOT/'scripts/report_sce_information_exposure.py')
    report = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(report)
    cells = []
    for month in protocol['months']:
        for repeat in protocol['generation_repeats']:
            rows = [r for r in cases if r['month'] == month and r['repeat'] == repeat and (month, r['userid']) in support]
            y = np.array([r['real']['q9_mean'] for r in rows]); prior = np.array([r['real']['previous_q9_mean'] for r in rows])
            w = np.array([r['survey_weight'] for r in rows]); arms = {}
            for name, gate in gates.items():
                p = np.array([r['arms']['news_8_reduced' if gate[month, r['userid']] else 'baseline']['mean'] for r in rows])
                arms[name] = report.cell_metrics(y, prior, p, w)
                arms[name]['weighted_reduced_share'] = float(np.average([gate[month, r['userid']] for r in rows], weights=w))
            cells.append({'month': month, 'repeat': repeat, 'n': len(rows), 'arms': arms})
    aggregate = report.summarize(cells, list(gates))
    shuffled = [aggregate[name] for name in gates if name != 'matched_past_gate']
    summary = {'new_api_calls': 0, 'new_q9_fits': 0, 'status': 'completed_past_only_selection_of_existing_answers',
        'development_after_exposure_results': True, 'threshold_fixed': .5, 'missing_predictions': int(missing),
        'common_person_months': len(support), 'selected_reduced_n': sum(chosen.values()),
        'matched_gate': aggregate['matched_past_gate'],
        'all_complete': result['weighted_metrics']['baseline'], 'all_reduced': result['weighted_metrics']['news_8_reduced'],
        'carry': result['weighted_metrics']['carry'],
        'shuffled_range_20_draws_not_confidence_interval': {key: [min(s[key] for s in shuffled), float(np.mean([s[key] for s in shuffled])), max(s[key] for s in shuffled)]
            for key in shuffled[0]},
        'monthly_matched': [{'month': m, 'metrics': report.summarize([c for c in cells if c['month'] == m], ['matched_past_gate'])['matched_past_gate']} for m in protocol['months']],
        'automatic_upgrade': False,
        'limits': ['Only selects whole previously generated Q9 replies, no new simulated answers or observed true attention.',
            'All six development months inspected; not independent verification; threshold not tuned.',
            'Shuffling preserves counts rather than survey-weight totals; differences are descriptive.',
            'Official-derived stability labels and frozen approximate score differ for some responses.'],
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [prediction, prediction.parent/'summary.json', readout, evaluation/'cases_private.json',
            ROOT/'docs/workstreams/20261018_targeted_mechanisms/past_only_exposure_gate_plan_20261019.md']}}
    out.mkdir(parents=True)
    (out/'selection_records_private.json').write_text(json.dumps(records, ensure_ascii=False, indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print({key: summary[key] for key in ['common_person_months', 'selected_reduced_n', 'missing_predictions', 'matched_gate', 'shuffled_range_20_draws_not_confidence_interval']})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    run(parser.parse_args().out)
