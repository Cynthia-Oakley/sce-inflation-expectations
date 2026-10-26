#!/usr/bin/env python3
"""Existing call-ledger evaluator plus same-support baselines and dispersion."""
from pathlib import Path
import argparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
import numpy as np

from scripts.evaluate_sce_call_ledger import evaluate as base_evaluate
from studies.sce_inflation_expectations.experiments.frozen_batch import read_json,dump
from studies.sce_inflation_expectations.evaluation import cognition as shared
from studies.sce_inflation_expectations.evaluation.post2025_baselines import baseline_metrics
from studies.sce_inflation_expectations.evaluation.model_dispersion import analyze


def same_support_baselines(cases, baseline_cases, monthly_truth, arm):
    support=shared._common_person_months(cases,[arm],[1,2],'q9')
    cells=[]
    for month in sorted({r['month'] for r in cases}):
        rows=[r for r in baseline_cases if r['month']==month and (month,r['userid']) in support]
        if not rows:
            raise ValueError('Every month requires common model/human/baseline support')
        cells.append(dict(month=month,baselines={a:baseline_metrics(rows,a) for a in ('carry','history_anchor_half')}))
    equal={a:{k:float(np.mean([c['baselines'][a][k] for c in cells]))
              for k in ('center_mae_pp','w1_pp','personal_mae_pp','across_person_iqr_pp')}
           for a in ('carry','history_anchor_half')}
    for a in equal:
        equal[a]['center_rmse_pp']=float(np.sqrt(np.mean([c['baselines'][a]['center_mae_pp']**2 for c in cells])))
    national={r['month']:r for r in monthly_truth}
    return dict(common_person_months=len(support),monthly=cells,equal_month_metrics=equal,
        official_national_copy_mae_pp=float(np.mean([national[c['month']]['official_national']['center_mae_pp'] for c in cells])),
        scope='Same final common people for individual baselines; official national copy is a separate population/metric.',
        history_anchor_weight_fixed=.5,weights_fitted_on_new_targets=False)


def evaluate(ledger,out):
    ledger,out=Path(ledger).resolve(),Path(out).resolve()
    protocol=read_json(ledger/'protocol.json')
    if protocol['mechanism']!='v32_new2025_validation':
        raise ValueError('This extension only evaluates the registered new2025 batch')
    result=base_evaluate(ledger,out)
    cases=read_json(out/'cases_private.json')
    truth_dir=(ROOT/protocol['evaluation_truth']).parent
    baseline_cases=read_json(truth_dir/'cases_private.json')
    truth=read_json(truth_dir/'summary.json')
    extension=same_support_baselines(cases,baseline_cases,truth['monthly'],'deepseek_v32')
    official={r['month']:r['official_national']['q9_headline_pp'] for r in truth['monthly']}
    dispersion=analyze(cases,official)
    monthly_lookup={r['month']:r for r in truth['monthly']}
    national_cells=[]
    q9cells=result['arms']['deepseek_v32']['q9']['cells']
    for cell in q9cells:
        month=cell['month'];real_center=next(c['baselines']['carry']['truth_center_pp'] for c in extension['monthly'] if c['month']==month)
        predicted=real_center+cell['q9_center_bias_pp'];row=monthly_lookup[month]
        national_cells.append(dict(month=month,repeat=cell['repeat'],model_center_pp=predicted,
            national_headline_pp=official[month],model_national_abs_error_pp=abs(predicted-official[month]),
            copy_national_abs_error_pp=row['official_national']['center_mae_pp'],
            full_wave_frozen_score_center_pp=row['full_wave']['frozen_score_median_pp'],
            selected_real_center_pp=real_center))
    extension.update(national_comparison_cells=national_cells,
        model_national_mae_pp=float(np.mean([r['model_national_abs_error_pp'] for r in national_cells])),
        model_same_support_center_rmse_pp=float(np.sqrt(np.mean([r['q9_center_mae_pp']**2 for r in q9cells]))))
    dump(out/'baseline_comparison.json',extension);dump(out/'dispersion.json',dispersion)
    result.update(baseline_comparison=extension,dispersion=dispersion)
    dump(out/'summary.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=evaluate(a.ledger,a.out);print(r['status'],r['common_q9_person_months'])
