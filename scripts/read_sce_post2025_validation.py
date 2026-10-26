#!/usr/bin/env python3
"""Canonical design-weighted readout from completed scores; zero API/refits.

The shared cognition evaluator retains both equal-person and weighted branches.
Always use its weighted branch or the equivalent shared readout for this trial.
The v1 evaluation wrapper's national-center reconstruction mixed those branches;
that derived field is explicitly quarantined here, without altering old outputs.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
import numpy as np

from studies.sce_inflation_expectations.experiments.frozen_batch import read_json,dump,sha
from studies.sce_inflation_expectations.evaluation import cognition as shared
from studies.sce_inflation_expectations.evaluation.price_background_readout import summarize
from studies.sce_inflation_expectations.evaluation.procurement_gap import band
from studies.sce_inflation_expectations.evaluation.model_dispersion import analyze
from scripts.evaluate_sce_post2025_validation import same_support_baselines


def national_cells(readout, monthly_truth, arm):
    truth={r['month']:r for r in monthly_truth}
    cells=[]
    for cell in readout['cells']:
        month=cell['month'];a=cell['arms'][arm];t=truth[month]
        cells.append(dict(month=month,repeat=cell['repeat'],n=cell['n'],ess=cell['ess'],
            model_center_pp=a['predicted_center_pp'],sample_real_center_pp=a['truth_center_pp'],
            official_national_center_pp=t['official_national']['q9_headline_pp'],
            full_wave_frozen_center_pp=t['full_wave']['frozen_score_median_pp'],
            model_national_abs_error_pp=abs(a['predicted_center_pp']-t['official_national']['q9_headline_pp']),
            model_full_wave_abs_error_pp=abs(a['predicted_center_pp']-t['full_wave']['frozen_score_median_pp']),
            official_national_copy_abs_error_pp=t['official_national']['center_mae_pp']))
    return cells


def readout(source,ledger,out):
    source,ledger,out=[Path(p).resolve() for p in (source,ledger,out)]
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored readout required')
    s=read_json(source/'summary.json');p=s['protocol'];cases=read_json(source/'cases_private.json')
    receipt=read_json(ledger/'run_receipt.json')
    if p['mechanism']!='v32_new2025_validation' or receipt['status']!='completed':
        raise ValueError('Completed registered new2025 batch required')
    arms,months,repeats=p['arms'],p['months'],p['generation_repeats']
    support=shared._common_person_months(cases,arms,repeats,'q9')
    r=summarize(cases,arms,months,repeats,support)
    # This identity is checked against the frozen weighted evaluator branch.
    for a in arms:
        w=s['arms'][a]['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells']
        for own,ref in [('center_mae_pp','q9_center_mae_pp'),('w1_pp','cross_section_w1_pp')]:
            if abs(r['metrics'][a][own]-w[ref])>1e-8:
                raise ValueError('Design-weighted evaluator disagreement')
    truth_dir=(ROOT/p['evaluation_truth']).parent
    t=read_json(truth_dir/'summary.json');bc=read_json(truth_dir/'cases_private.json')
    baselines=same_support_baselines(cases,bc,t['monthly'],arms[0])
    nc=national_cells(r,t['monthly'],arms[0])
    official={row['month']:row['official_national']['q9_headline_pp'] for row in t['monthly']}
    groups={}
    for b in ('below_2','2_to_below_4','4_to_below_8','8_or_above'):
        subset=[row for row in cases if band(row['real']['previous_q9_mean'])==b]
        gs={(row['month'],row['userid']) for row in subset}&support
        groups[b]=summarize(subset,arms,months,repeats,gs)
    result=dict(status='completed_new2025_design_weighted_readout',completed_at_utc=datetime.now(timezone.utc).isoformat(),
        new_api_calls=0,new_q9_fits=0,months=months,arms=arms,n_per_month=p['n_per_month'],
        person_months=r['person_months'],unique_persons=r['unique_persons'],readout=r,prior_groups=groups,
        q8_design_weighted={a:s['arms'][a]['auxiliary_survey_weighted']['q8'] for a in arms},
        baseline_comparison=baselines,national_comparison=dict(cells=nc,
            model_national_mae_pp=float(np.mean([c['model_national_abs_error_pp'] for c in nc])),
            model_full_wave_mae_pp=float(np.mean([c['model_full_wave_abs_error_pp'] for c in nc])),
            official_national_copy_mae_pp=float(np.mean([c['official_national_copy_abs_error_pp'] for c in nc]))),
        dispersion=analyze([row for row in cases if (row['month'],row['userid']) in support],official),
        coverage=s['coverage'],scorable_counts=s['scorable_counts'],accuracy_descriptive_only=s['accuracy_descriptive_only'],
        q9_postprocessing=s['q9_postprocessing'],runtime=receipt,
        configuration={k:p[k] for k in ('model','route','expected_provider','temperature','max_tokens',
            'thinking','allocation_seed','generation_repeats','max_workers','technical_max_workers')},
        quarantined_v1_fields=['baseline_comparison.model_national_mae_pp','baseline_comparison.national_comparison_cells',
            'baseline_comparison.model_same_support_center_rmse_pp'],
        correction_note='v1 derived national fields reconstructed a center from the equal-person branch plus weighted real center. Use this cached weighted readout; no calls, density fits, truths, prompts or primary weighting changed. Detected before new results were inspected.',
        limits=p['limits'],source_sha256={str(x.relative_to(ROOT)):sha(x) for x in (
            source/'summary.json',source/'cases_private.json',ledger/'run_receipt.json',Path(__file__))})
    result['leave_one_month_out']={str(m):{a:{k:float(np.mean([c['arms'][a][k] for c in r['cells'] if c['month']!=m]))
        for k in ('center_mae_pp','w1_pp','delta_w1_pp')} for a in [*arms,'carry']} for m in months}
    out.mkdir();dump(out/'summary.json',result)
    return dict(status=result['status'],person_months=r['person_months'],metrics=r['metrics'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();print(readout(a.source,a.ledger,a.out))
