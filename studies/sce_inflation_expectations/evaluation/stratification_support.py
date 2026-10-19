"""Outcome-free support and proposed allocations for the six-cell draft."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path

import pandas as pd

from ..population_stratification import EDUCATION, WORK, cell_key, allocate_core

ROOT = Path(__file__).resolve().parents[3]


def support(rows):
    weights = [r['weight'] for r in rows]
    total = sum(weights)
    ess = total**2/sum(w*w for w in weights) if weights else 0.0
    return {'n': len(rows), 'ess': ess, 'mass': total,
            'status': 'sparse' if len(rows) < 10 else 'weak' if ess < 10 else 'strong'}


def run(out):
    if out.exists():
        raise ValueError('Fresh output required')
    source = ROOT/'outputs/sce_reference_validation_evaluation_20261017_v1/cases_private.json'
    cases = json.loads(source.read_text())
    # Do not pass outcomes, model predictions or errors into any grouping rule.
    assigned = [{'month': r['month'], 'profile': r['profile'], 'weight': r['design_survey_weight']}
                for r in cases if r['repeat'] == 1]
    months = sorted({r['month'] for r in assigned})
    cache = ROOT/'outputs/sce_population_associations_20261015_v1/analysis_frame_private.parquet'
    fields = ['date', 'weight', '_EDU_CAT', 'employment', 'panel_status', 'raw_prior_valid']
    frame = pd.read_parquet(cache, columns=fields)
    frame = frame.loc[frame.date.isin(months) & frame.panel_status.eq('adjacent_returner') & frame.raw_prior_valid.eq(True)]
    frame = frame.loc[frame.weight.gt(0) & frame.weight.notna()]
    keys = [e+'|'+w for e in EDUCATION for w in WORK]; result = []
    for month in months:
        own = [r for r in assigned if r['month'] == month]
        available = frame.loc[frame.date.eq(month)].to_dict('records')
        groups = {k: [r for r in own if cell_key(r['profile']) == k] for k in keys+['unknown']}
        pool = {k: [r for r in available if cell_key(r) == k] for k in keys+['unknown']}
        counts = {k: len(v) for k,v in pool.items()}; mass = {k: sum(r['weight'] for r in v) for k,v in pool.items()}
        allocation = allocate_core(counts, mass, 192, minimum=12)
        result.append({'month': month, 'current_assigned': {k: support(v) for k,v in groups.items()},
            'available_historical_prior_frame': {k: support(v) for k,v in pool.items()},
            'draft_n192_allocation': {k: {'n': allocation[k], 'frame_n': counts[k],
                'within_cell_inclusion_probability_if_srs': allocation[k]/counts[k] if counts[k] else None}
                for k in counts}})
    report = {'status': 'six_cell_design_support_only_not_applied', 'new_llm_calls': 0,
        'fields': ['education_group_3', 'employment_attached_2'], 'cells': keys, 'unknown': 'separate',
        'employment_definition': 'employed or on_leave vs unemployed/retired/disabled/student/homemaker/other; not a BLS/CPS employment rate definition',
        'primary_cells_total': len(months)*6,
        'current_primary_cells_strong': sum(x['status']=='strong' for m in result for k,x in m['current_assigned'].items() if k!='unknown'),
        'monthly': result, 'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [source, cache]},
        'limits': ['No actual resampling, population change or Normal expansion performed.',
            'Available frame uses only adjacent-returner/prior validity and P; current inflation answers not used to select.',
            'Historical-prior frame count is a preparation pool, not nationwide coverage or a completed runtime eligibility audit.',
            'Minimum 12 is a draft coverage floor, not a power calculation or guarantee of sampled ESS>=10.',
            'Age/income margins and retired/other subgroups remain separate diagnostics; do not multiply all attributes.',
            'Normal donors must later preserve whole Q8/Q9 payloads and disclose fallback, not invent individual histories.']}
    out.mkdir(parents=True); (out/'summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report
