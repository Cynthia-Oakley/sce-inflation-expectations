#!/usr/bin/env python3
"""Post-hoc High/Low population-margin sensitivity; never changes model answers."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studies.sce_inflation_expectations.evaluation.cognition import ARMS, _common_person_months, _q9_cell_metrics


def main(evaluation, reference, out):
    evaluation, reference, out = evaluation.resolve(), reference.resolve(), out.resolve()
    if out.exists() or not out.is_relative_to(ROOT / 'outputs'):
        raise ValueError('Fresh ignored output required')
    casepath = evaluation / 'cases_private.json'
    rows = json.loads(casepath.read_text())
    support = _common_person_months(rows, list(ARMS), [1, 2], 'q9')
    con = duckdb.connect()
    totals = con.execute('SELECT date, CAST(_NUM_CAT AS VARCHAR), count(*), sum(weight) FROM read_parquet(?) WHERE date IN (202004,202105,202111,202203) GROUP BY 1,2 ORDER BY 1,2', [str(reference)]).fetchall()
    con.close()
    by = defaultdict(dict)
    for month, label, n, w in totals:
        by[month][label] = {'n': n, 'weight_sum': w}
    margins = {str(m): {'n_respondents': sum(d['n'] for d in groups.values()),
        'low_unweighted_share': groups['Low']['n'] / sum(d['n'] for d in groups.values()),
        'low_survey_weighted_share': groups['Low']['weight_sum'] / sum(d['weight_sum'] for d in groups.values())}
        for m, groups in by.items()}
    scenarios = ('equal_selected_people', 'parent_inverse_inclusion_times_survey_weight',
                 'full_sce_numeracy_margin_calibration')
    metrics = {name: {a: [] for a in ARMS} for name in scenarios}
    for month in (202004, 202105, 202111, 202203):
        target = {g: d['weight_sum'] / sum(v['weight_sum'] for v in by[month].values())
                  for g, d in by[month].items()}
        for repeat in (1, 2):
            subset = [r for r in rows if r['month'] == month and r['repeat'] == repeat
                      and (month, r['userid']) in support]
            original = np.array([r['survey_weight'] for r in subset], float)
            groups = np.array([r['numeracy'] for r in subset])
            calibrated = original.copy()
            for group in ('High', 'Low'):
                ix = groups == group
                if original[ix].sum() <= 0:
                    raise ValueError('Selected group has no positive supported mass')
                calibrated[ix] *= target[group] / original[ix].sum()
                assert abs(calibrated[ix].sum() - target[group]) < 1e-12
            assert abs(calibrated.sum() - 1) < 1e-12
            for arm in ARMS:
                for name, weights in zip(scenarios, (None, original, calibrated)):
                    cell = _q9_cell_metrics(subset, arm, weights)
                    metrics[name][arm].append({'month': month, 'repeat': repeat, **cell})
    keys = ('q9_center_mae_pp', 'individual_density_iqr_mae_pp', 'cross_section_w1_pp',
            'delta_w1_pp', 'probability_tv_pct')
    aggregate = {name: {a: {k: float(np.mean([v[k] for v in cells])) for k in keys}
                        for a, cells in arms.items()} for name, arms in metrics.items()}
    result = {'status': 'post_run_population_weight_sensitivity_no_api_no_protocol_change',
        'population_source_sha256': hashlib.sha256(reference.read_bytes()).hexdigest(),
        'case_source_sha256': hashlib.sha256(casepath.read_bytes()).hexdigest(),
        'planned_sample_low_share': 10/24, 'parent_roster_low_share': 49/192,
        'full_sce_month_margins': margins,
        'equal_month_full_sce_low_unweighted_share': float(np.mean([v['low_unweighted_share'] for v in margins.values()])),
        'equal_month_full_sce_low_survey_weighted_share': float(np.mean([v['low_survey_weighted_share'] for v in margins.values()])),
        'n_common_q9_person_months': len(support), 'aggregate': aggregate, 'cells': metrics,
        'calibration_rule': 'For each month and generation, multiply each selected common-case survey/design weight by target full-SCE survey-weighted numeracy-group share divided by the selected within-group weight sum. Both model and matched real distribution receive identical weights. Recompute weighted quantiles and errors before equal-month/repeat averaging.',
        'limitations': ['Post hoc descriptive sensitivity, not a new primary test or independent validation.',
            'Matches only High/Low margins; selected returners may differ within these groups in age, income, previous beliefs and other characteristics.',
            'Full SCE means the source survey respondents, not a verified US population numeracy distribution.',
            'No new LLM/MCP calls and no alteration of original scored answers or protocol.']}
    out.mkdir(parents=True)
    (out / 'population_weights_sensitivity.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(out)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evaluation', type=Path, required=True)
    p.add_argument('--reference', type=Path, default=ROOT / 'outputs/sce_behavior_mechanism_audit_20261014_v3/reference_with_controls_private.parquet')
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    main(args.evaluation, args.reference, args.out)
