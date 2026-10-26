"""Truth and past-only baselines AFTER cohort selection; never prompt inputs."""
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import load_workbook

from .behavior_comparison import score, finite, previous_month
from .metrics import quantile, wasserstein1, headline_errors

ROOT=Path(__file__).resolve().parents[3]
FRAME=ROOT/'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
CHART=ROOT/'data/raw/sce_micro_refresh_20261021/chart.xlsx'


def sha(path):
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def row_score(row):
    return score(tuple(float(row[f'Q9_bin{i}']) for i in range(1,11)))


def public_bins(row):
    """Retain missing target bins as null, never repair or resample the person."""
    return [float(row[f'Q9_bin{i}']) if finite(row[f'Q9_bin{i}']) else None for i in range(1,11)]


def baseline_metrics(rows, field):
    usable=[r for r in rows if finite(r['real']['q9_mean']) and finite(r[field])]
    y=np.array([r['real']['q9_mean'] for r in usable]);x=np.array([r[field] for r in usable])
    w=np.array([r['design_survey_weight'] for r in usable])
    return dict(person_months=len(usable),truth_center_pp=quantile(y,w,.5),predicted_center_pp=quantile(x,w,.5),
        center_bias_pp=quantile(x,w,.5)-quantile(y,w,.5),
        center_mae_pp=abs(quantile(x,w,.5)-quantile(y,w,.5)),
        w1_pp=wasserstein1(x,w,y,w),personal_mae_pp=float(np.average(abs(x-y),weights=w)),
        across_person_iqr_pp=quantile(x,w,.75)-quantile(x,w,.25),
        human_iqr_pp=quantile(y,w,.75)-quantile(y,w,.25))


def run(population,out):
    population,out=Path(population).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh isolated evaluation directory required')
    m=json.loads((population/'manifest.json').read_text())
    if m['current_target_answers_read'] or m['status']!='population_and_past_only_not_live_trial':
        raise ValueError('Outcome-blind selected population must be frozen first')
    # The population candidates are data inputs. Do not use its old live-run
    # verifier: no paid trial exists, and unrelated news helpers may have changed.
    for name,h in m['prepared_file_sha256'].items():
        if sha(population/name)!=h:raise ValueError('Frozen population/past data changed')
    if sha(FRAME)!=m['source_sha256'][str(FRAME.relative_to(ROOT))]:raise ValueError('Raw reference changed')
    links=json.loads((population/'evaluation_links_private.json').read_text())
    months=m['months'];all_months=sorted(set(months)|{previous_month(x) for x in months})
    cols=['date','userid','weight','Q8v2part2','Q9_mean',*[f'Q9_bin{i}' for i in range(1,11)]]
    frame=pd.read_parquet(FRAME,columns=cols,filters=[('date','in',all_months)])
    lookup={(int(r['date']),int(r['userid'])):r for r in frame.to_dict('records')}
    wb=load_workbook(CHART,read_only=True,data_only=True)
    chart={int(r[0]):list(r) for r in wb['Inflation expectations'].iter_rows(min_row=5,values_only=True)
           if isinstance(r[0],(float,int))};wb.close()
    out.mkdir(parents=True);private=[];monthly=[]
    for month in months:
        past=json.loads((population/str(month)/'past_private.json').read_text());rows=[]
        for link in [r for r in links if r['month']==month]:
            raw=lookup[month,link['userid']];before=lookup[previous_month(month),link['userid']]
            now,old=row_score(raw),row_score(before)
            bins=public_bins(raw)
            prior_bins=public_bins(before)
            point=float(raw['Q8v2part2']) if pd.notna(raw['Q8v2part2']) and np.isfinite(raw['Q8v2part2']) else None
            anchor=past[link['agent_id']]['state']['anchor']
            row={**link,'real':dict(q9_mean=now['mean'],q9_iqr=now['iqr'],q9_bins=bins,
                q9_zero_deflation=now['zero_deflation'],q8_point=point if point is not None and abs(point)<=100 else None,
                q8_outside_100=bool(point is not None and abs(point)>100),weight=link['survey_weight'],
                previous_q9_mean=old['mean'],previous_q9_bins=prior_bins),
                'carry':old['mean'],'history_anchor_half':.5*old['mean']+.5*anchor if finite(anchor) else old['mean']}
            rows.append(row);private.append(row)
        full=[]
        for raw in frame[frame.date.eq(month)].to_dict('records'):
            w=raw['weight']
            if not finite(w) or w<=0:continue
            s=row_score(raw)
            if finite(s['mean']):full.append((s['mean'],float(w)))
        full_center=quantile([x for x,w in full],[w for x,w in full],.5)
        official=float(chart[month][1]);national_previous=float(chart[previous_month(month)][1])
        nested={r['agent_id']:r for r in json.loads((population/str(month)/'nested96_private.json').read_text())}
        secondary=[dict(r,design_survey_weight=nested[r['agent_id']]['design_survey_weight']) for r in rows if r['agent_id'] in nested]
        monthly.append(dict(month=month,selected_n=len(rows),q9_valid_n=sum(finite(r['real']['q9_mean']) for r in rows),
            q8_valid_n=sum(finite(r['real']['q8_point']) for r in rows),
            same_person_baselines={a:baseline_metrics(rows,a) for a in ('carry','history_anchor_half')},
            nested96_baselines={a:baseline_metrics(secondary,a) for a in ('carry','history_anchor_half')},
            full_wave=dict(n_scorable=len(full),frozen_score_median_pp=full_center),
            official_national=dict(q9_headline_pp=official,q8_point_headline_pp=float(chart[month][7]),
                copy_previous_headline_pp=national_previous,center_mae_pp=abs(official-national_previous)),
            truth_levels_note='Same-person fitted density median, full-wave fitted density median and published national headline are distinct.'))
        print(f'Truth/baseline {month}: selected {len(rows)}, scorable {monthly[-1]["q9_valid_n"]}',flush=True)
    truth=[]
    for r in private:
        for repeat in (1,2):truth.append(dict(month=r['month'],agent_id=r['agent_id'],repeat=repeat,real=r['real']))
    from ..scoring.sce_q9_frozen import provenance
    summary=dict(status='new2025_truth_and_baselines_frozen_no_model_outputs',months=months,new_api_calls=0,
        prepared_at_utc=datetime.now(timezone.utc).isoformat(),monthly=monthly,
        national_copy_errors=headline_errors([x['official_national']['copy_previous_headline_pp'] for x in monthly],
            [x['official_national']['q9_headline_pp'] for x in monthly]),
        individual_copy_equal_month_metrics={k:float(np.mean([x['same_person_baselines']['carry'][k] for x in monthly]))
            for k in ('center_mae_pp','w1_pp','personal_mae_pp','across_person_iqr_pp')},
        scorer_provenance=provenance(),input_isolation='Evaluation-only directory; no inputs or prompts import this module/output',
        source_sha256={str(p.relative_to(ROOT)):sha(p) for p in (FRAME,CHART,population/'manifest.json',Path(__file__))},
        limits=['Truth is extracted from actual SCE data, never synthesized or tuned.',
            'Frozen score is the existing project approximation; official published headline is evaluated separately.',
            'Population selection precedes current outcome reads; invalid target answers stay in the selected roster.',
            'This is a conditional returner reconstruction sample, not all national households.',
            'No combination coefficients fitted on these new target answers.'])
    for name,value in [('summary.json',summary),('cases_private.json',private),('truth_private.json',truth)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return summary
