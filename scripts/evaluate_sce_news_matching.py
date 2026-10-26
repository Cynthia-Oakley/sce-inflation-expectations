#!/usr/bin/env python3
"""Evaluate news contrasts with shared statistics and explicit prior fallback."""
from pathlib import Path
import argparse
import sys
from copy import deepcopy
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from scripts.evaluate_sce_call_ledger import evaluate as base_evaluate
from studies.sce_inflation_expectations.experiments.frozen_batch import read_json,dump
from studies.sce_inflation_expectations.evaluation import cognition as shared


def fixed_roster(cases,protocol):
    """Prior scalar scores are operational fallback, never invented LLM replies.

    Across-person W1 uses density MEANS. The derived fallback is explicitly the
    real previous answer, not a newly generated or repaired model probability.
    """
    filled=deepcopy(cases);counts={a:0 for a in protocol['arms']}
    for row in filled:
        for arm in protocol['arms']:
            v=row['arms'][arm];r=row['real']
            if not shared.finite(v.get('mean')) or not shared.finite(v.get('iqr')):
                v.update(mean=r.get('previous_q9_mean'),iqr=r.get('previous_q9_iqr'),
                    zero_deflation=r.get('previous_q9_zero_deflation'),q9_bins=r.get('previous_q9_bins'),
                    operational_prior_fallback=True)
                counts[arm]+=1
            if not shared.finite(v.get('point')):
                v['point']=r.get('previous_q8_point')
    support9=shared._common_person_months(filled,protocol['arms'],[1,2],'q9')
    support8=shared._common_person_months(filled,protocol['arms'],[1,2],'q8')
    metrics={a:shared._summarize_arm(filled,a,protocol['months'],[1,2],support9,support8) for a in protocol['arms']}
    for v in metrics.values():
        for view in (v,v['auxiliary_survey_weighted']):
            cells=view['q9']['cells']
            errors=[c['q9_center_mae_pp'] for c in cells]
            view['q9']['aggregate_equal_month_repeat_cells']['q9_center_rmse_pp']=(
                float(np.sqrt(np.mean(np.square(errors)))) if all(shared.finite(v) for v in errors) else None)
    for row in filled:
        r=row['real'];row['arms']['carry']=dict(mean=r['previous_q9_mean'],iqr=r['previous_q9_iqr'],
            zero_deflation=r['previous_q9_zero_deflation'],point=r['previous_q8_point'],q9_bins=r['previous_q9_bins'])
    carry=shared._summarize_arm(filled,'carry',protocol['months'],[1,2],support9,support8)
    return dict(scope='Fixed human-valid roster; missing output explicitly replaced with real previous answer; not pure LLM accuracy.',
        primary_weight='design_survey_weight',primary_arms={a:v['auxiliary_survey_weighted'] for a,v in metrics.items()},
        same_support_carry=carry['auxiliary_survey_weighted'],
        common_q9_person_months=len(support9),common_q8_person_months=len(support8),fallback_counts=counts,arms=metrics)


def evaluate(ledger,out):
    result=base_evaluate(Path(ledger),Path(out));protocol=result['protocol']
    if protocol['mechanism']!='v32_news_matching':raise ValueError('News-specific extension required')
    cases=read_json(Path(out)/'cases_private.json')
    operational=fixed_roster(cases,protocol)
    dump(Path(out)/'fixed_roster_operational.json',operational)
    result.update(fixed_roster_operational=operational,
        primary_reporting='Operational fixed-roster and paired available-output results jointly; neither alone proves a mechanism.',
        assignment_seed_limitation='One allocation seed, two model repeats; no claim of assignment robustness.')
    dump(Path(out)/'summary.json',result);return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=evaluate(a.ledger,a.out);print(r['status'],r['common_q9_person_months'])
