#!/usr/bin/env python3
"""Describe sensitivity to missing replies, without API calls or density fits."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__ = [str(ROOT/'studies'), *studies.__path__]
from studies.sce_inflation_expectations.evaluation import cognition as shared
from scripts.report_sce_information_exposure import cell_metrics, summarize


def report(evaluation, out):
    if out.exists():
        raise ValueError('Fresh sensitivity output required')
    scored = json.loads((evaluation/'summary.json').read_text())
    protocol = scored['protocol']
    cases = json.loads((evaluation/'cases_private.json').read_text())
    pair = ['matched_role', 'shuffled_role']
    support = shared._common_person_months(cases, pair, protocol['generation_repeats'], 'q9')
    cells, full = [], []
    for month in protocol['months']:
        for repeat in protocol['generation_repeats']:
            rows = shared._cell_rows(cases, month, repeat, support)
            y = np.array([r['real']['q9_mean'] for r in rows])
            previous = np.array([r['real']['previous_q9_mean'] for r in rows])
            w = np.array([r['survey_weight'] for r in rows])
            cells.append({'month': month, 'repeat': repeat, 'n': len(rows),
                'arms': {a: cell_metrics(y, previous,
                    np.array([r['arms'][a]['mean'] for r in rows]), w) for a in pair}})
            rows = [r for r in cases if r['month'] == month and r['repeat'] == repeat
                and shared.finite(r['real']['q9_mean']) and shared.finite(r['real']['previous_q9_mean'])]
            y = np.array([r['real']['q9_mean'] for r in rows])
            previous = np.array([r['real']['previous_q9_mean'] for r in rows])
            w = np.array([r['survey_weight'] for r in rows])
            full.append({'month': month, 'repeat': repeat, 'n': len(rows),
                'arms': {'carry': cell_metrics(y, previous, previous, w)}})
    result = {'new_api_calls': 0, 'new_density_fits': 0,
        'purpose': 'Sensitivity to missing shared-price responses; does not replace registered all-arm common-support comparison.',
        'pair_only_person_months': len(support), 'pair_only_metrics': summarize(cells, pair),
        'full_valid_truth_roster_person_months': sum(c['n'] for c in full)//len(protocol['generation_repeats']),
        'full_roster_carry_metrics': summarize(full, ['carry']),
        'note': 'Full-roster baseline and main model estimates have different support; no direct performance comparison. Pair-only support is exploratory.'}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evaluation', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    result = report(args.evaluation, args.out)
    print('Pair-only support:', result['pair_only_person_months'])
