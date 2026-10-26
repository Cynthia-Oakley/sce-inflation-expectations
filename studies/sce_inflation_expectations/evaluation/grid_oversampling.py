"""Outcome-free full-frame fine-grid allocation audit. No simulator imports."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import math
from pathlib import Path

import numpy as np
import pandas as pd

from .grid_dimension_selection import ROOT, CACHE, FEATURES, sha, dump, ess
from ..population.grid_sampling import plan_core, draw_core

GRIDS = {
    'education+numeracy+gender': ['education', 'numeracy', 'gender'],
    'education+numeracy+income+gender': ['education', 'numeracy', 'income', 'gender'],
    'education+numeracy+income+age': ['education', 'numeracy', 'income', 'age'],
}
SETTINGS = [(256, 4), (384, 6), (512, 8)]
SEEDS = [20261023, 20261024, 20261025, 20261026]


def load_population_frame():
    # The column projection deliberately excludes every current/past answer.
    f = pd.read_parquet(CACHE, columns=['date', 'userid', 'weight', '_EDU_CAT',
                                     'numeracy', 'income_group', 'age_group', 'gender'])
    f = f.loc[f.date.between(201901, 202510)].copy()
    if f.duplicated(['date', 'userid']).any():
        raise ValueError('Duplicate respondent-month')
    f['education'] = f._EDU_CAT.map({'High School': 'high_school', 'Some College': 'some_college', 'College': 'college'})
    f['income'] = f.income_group.map({'Under 50k': 'under_50k', '50k to 100k': '50k_100k', 'Over 100k': 'over_100k'})
    f['age'] = f.age_group.map({'Under 40': 'under_40', '40 to 60': '40_60', 'Over 60': 'over_60'})
    return f


def records_for(frame, fields):
    records = []
    for r in frame.to_dict('records'):
        known = all(r[k] in FEATURES[k] for k in fields)
        records.append({'id': int(r['userid']), 'weight': float(r['weight']),
                        'cell': '|'.join(r[k] for k in fields) if known else 'unknown'})
    return records


def summarize(rows):
    valid = [r for r in rows if r['feasible']]
    result = {'months': len(rows), 'feasible_months': len(valid),
              'floor_total_min': min(r['floor_total'] for r in rows),
              'floor_total_max': max(r['floor_total'] for r in rows)}
    for key in ['frame_strong_mass', 'unknown_mass', 'actual_draw_mass_cell_ess_ge_10',
                'actual_draw_global_ess', 'represented_frame_mass', 'enumerated_cell_mass',
                'max_cell_mass_error']:
        if valid:
            values = [r[key] for r in valid]
            result['mean_'+key] = float(np.mean(values))
            result['minimum_'+key] = float(min(values))
            result['maximum_'+key] = float(max(values))
    return result


def run(out):
    out = Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored output directory required')
    out.mkdir(parents=True)
    protocol = {'status': 'outcome_free_design_feasibility_not_predictive_validation',
                'grids': GRIDS, 'settings_budget_floor': SETTINGS, 'seeds': SEEDS,
                'period': ['201901', '202510'], 'new_api_calls': 0, 'q9_refits': 0,
                'allocation': 'min(floor, frame_n) in every occupied/unknown cell, remainder proportional to frame survey mass with count caps',
                'selection': 'seeded within-cell SRS without replacement, pi=n/N',
                'aggregation': 'raw survey w/pi, then within-cell ratio calibration to known frame weight mass',
                'limits': ['No current or past answers are loaded.',
                           'Four design draws are sampling diagnostics, not additional LLM generations.',
                           'Positive original weights only; excluded invalid weights counted, never replaced by one.',
                           'Frame support does not improve by oversampling; sparse original cells still need partial pooling.',
                           'No Normal expansion, production-default change or 82-month paid run.']}
    dump(out/'protocol.json', protocol)
    frame = load_population_frame()
    valid = np.isfinite(frame.weight) & frame.weight.gt(0)
    invalid_count = int((~valid).sum())
    frame = frame.loc[valid].copy()
    monthly = []
    for name, fields in GRIDS.items():
        for month, f in frame.groupby('date', sort=True):
            records = records_for(f, fields)
            counts = Counter(r['cell'] for r in records)
            grouped = defaultdict(list)
            for r in records:
                grouped[r['cell']].append(r['weight'])
            masses = {k: sum(v) for k, v in grouped.items()}; total = sum(masses.values())
            frame_strong = sum(masses[k] for k in counts if k != 'unknown' and counts[k] >= 20 and ess(grouped[k]) >= 10)/total
            for budget, floor in SETTINGS:
                row = {'grid': name, 'month': int(month), 'budget': budget, 'floor': floor,
                       'floor_total': sum(min(floor, n) for n in counts.values()),
                       'occupied_cells_including_unknown': len(counts),
                       'frame_strong_mass': frame_strong, 'unknown_mass': masses.get('unknown', 0)/total}
                if row['floor_total'] > budget or budget > len(records):
                    monthly.append({**row, 'feasible': False}); continue
                plan = plan_core(records, budget, minimum=floor)
                supported, effective, errors, represented = [], [], [], []
                for seed in SEEDS:
                    pick = draw_core(records, plan, seed=seed, month=int(month))
                    by_cell = defaultdict(list)
                    for r in pick:
                        by_cell[r['cell']].append(r['poststratified_weight'])
                    supported.append(sum(masses[k] for k, w in by_cell.items() if k != 'unknown' and ess(w) >= 10)/total)
                    effective.append(ess([r['poststratified_weight'] for r in pick]))
                    errors.append(max(abs(sum(by_cell[k])-masses[k])/total for k in masses))
                    represented.append(sum(masses[k] for k in by_cell)/total)
                row.update(feasible=True, actual_draw_mass_cell_ess_ge_10=float(np.mean(supported)),
                           actual_draw_global_ess=float(np.mean(effective)),
                           represented_frame_mass=float(np.mean(represented)),
                           max_cell_mass_error=float(max(errors)),
                           enumerated_cell_mass=sum(masses[k] for k, c in plan['cells'].items() if c['selected_n'] == c['frame_n'])/total)
                monthly.append(row)
        print(f'{name}: 82 months allocation diagnostics complete', flush=True)
    groups = {}
    for name, fields in GRIDS.items():
        groups[name] = {'fields': fields, 'cartesian_known_cells': math.prod(len(FEATURES[k]) for k in fields),
                        'settings': {f'{b}_floor_{n}': {
                            'all_82_months': summarize([r for r in monthly if r['grid'] == name and r['budget'] == b]),
                            'development_2019_2022': summarize([r for r in monthly if r['grid'] == name and r['budget'] == b and r['month'] <= 202212])}
                            for b, n in SETTINGS}}
    result = {'status': protocol['status'], 'completed_at_utc': datetime.now(timezone.utc).isoformat(),
              'new_api_calls': 0, 'q9_refits': 0, 'new_regressions': 0,
              'positive_weight_person_months': len(frame), 'invalid_weight_person_months_excluded': invalid_count,
              'source_sha256': {str(p.relative_to(ROOT)): sha(p) for p in [CACHE, Path(__file__), ROOT/'studies/sce_inflation_expectations/population/grid_sampling.py', ROOT/'studies/sce_inflation_expectations/population_stratification.py']},
              'protocol': protocol, 'grids': groups}
    dump(out/'monthly_summary.json', monthly)
    dump(out/'summary.json', result)
    print(out/'summary.json', flush=True)
    return result
