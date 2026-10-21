"""Read scored price-menu replies using existing support and metric functions."""
from pathlib import Path
from time import perf_counter

import numpy as np

from . import cognition as shared
from .procurement_gap import band, average
from ..population_stratification import cell_key
from ..experiments.frozen_batch import ROOT, verify, read_json, dump, sha
from scripts.report_sce_information_exposure import cell_metrics


def summarize(cases, arms, months, repeats, support):
    cells = []
    for month in months:
        for repeat in repeats:
            rows = shared._cell_rows(cases,month,repeat,support)
            if not rows:
                continue
            y=np.array([r['real']['q9_mean'] for r in rows]); prev=np.array([r['real']['previous_q9_mean'] for r in rows])
            w=np.array([r['survey_weight'] for r in rows])
            values={'carry':prev, **{a:np.array([r['arms'][a]['mean'] for r in rows]) for a in arms}}
            if not all(np.isfinite(v).all() for v in (y,prev,w,*values.values())) or np.any(w<=0):
                raise ValueError('Common support must also have finite priors and positive weights')
            metrics={}
            for a,p in values.items():
                metrics[a]=cell_metrics(y,prev,p,w)
                metrics[a].update(model_mean_pp=float(np.average(p,weights=w)),
                    truth_mean_pp=float(np.average(y,weights=w)), prior_mean_pp=float(np.average(prev,weights=w)),
                    personal_bias_pp=float(np.average(p-y,weights=w)),
                    model_update_mean_pp=float(np.average(p-prev,weights=w)),
                    truth_update_mean_pp=float(np.average(y-prev,weights=w)))
            cells.append(dict(month=month,repeat=repeat,n=len(rows),
                ess=float(w.sum()**2/(w@w)),max_weight_share=float(w.max()/w.sum()),arms=metrics))
    names=['carry',*arms]
    aggregate={a:average([c['arms'][a] for c in cells]) for a in names} if cells else {}
    for a in aggregate:
        aggregate[a]['center_rmse_pp']=float(np.sqrt(np.mean([c['arms'][a]['center_bias_pp']**2 for c in cells])))
    used=[r for r in cases if (r['month'],r['userid']) in support]
    return dict(person_months=len({(r['month'],r['userid']) for r in used}),
        unique_persons=len({r['userid'] for r in used}), cells_used=len(cells), cells=cells,
        sparse_cells=[dict(month=c['month'],repeat=c['repeat'],n=c['n'],ess=c['ess'],max_weight_share=c['max_weight_share'])
                      for c in cells if c['n']<8 or c['ess']<5 or c['max_weight_share']>.25],
        metrics=aggregate)


def report(trial, evaluation, out):
    started=perf_counter(); trial,evaluation,out=[Path(p).resolve() for p in (trial,evaluation,out)]
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored readout required')
    manifest,protocol=verify(trial); scored=read_json(evaluation/'summary.json')
    if protocol['mechanism']!='price_background_qwen' or scored['protocol']!=protocol:
        raise ValueError('Completed matching price-background evaluation required')
    cases=read_json(evaluation/'cases_private.json')
    arms,months,repeats=protocol['arms'],protocol['months'],protocol['generation_repeats']
    support=shared._common_person_months(cases,arms,repeats,'q9')
    result=summarize(cases,arms,months,repeats,support)
    if result['cells_used']!=len(months)*len(repeats):
        raise ValueError('No complete common support across all registered cells')
    checked=0
    for arm in arms:
        ref=scored['arms'][arm]['auxiliary_survey_weighted']['q9']['aggregate_equal_month_repeat_cells']
        for key,refkey in [('center_mae_pp','q9_center_mae_pp'),('personal_mae_pp','individual_density_mean_mae_pp'),('w1_pp','cross_section_w1_pp')]:
            if abs(result['metrics'][arm][key]-ref[refkey])>1e-8:
                raise ValueError('Existing evaluator disagreement: '+arm+'/'+key)
            checked+=1
    monthly={str(m):summarize([r for r in cases if r['month']==m],arms,[m],repeats,support) for m in months}
    groups={}
    def label(row,dimension):
        if dimension=='prior':return band(row['real']['previous_q9_mean'])
        if dimension=='six_cell':return cell_key(row['profile'])
        return str(row['profile'].get(dimension,'unknown'))
    for dimension in ('prior','numeracy','six_cell','age_group','region'):
        groups[dimension]={}
        for value in sorted({label(r,dimension) for r in cases if (r['month'],r['userid']) in support}):
            subset=[r for r in cases if label(r,dimension)==value]
            group_support={(r['month'],r['userid']) for r in subset}&support
            groups[dimension][value]=summarize(subset,arms,months,repeats,group_support)
    intervals=(scored.get('paired_intervals') or {}).get('intervals') or {}
    w1_ci=intervals.get('cross_section_w1_pp')
    base,treat=arms
    signal=bool(not scored['accuracy_descriptive_only'] and w1_ci and w1_ci[1]<0
                and result['metrics'][treat]['delta_w1_pp']<=result['metrics'][base]['delta_w1_pp'])
    differences={k:result['metrics'][treat][k]-result['metrics'][base][k]
                 if shared.finite(result['metrics'][treat][k]) and shared.finite(result['metrics'][base][k]) else None
                 for k in result['metrics'][base]}
    result.update(status='completed_price_background_readout',new_api_calls=0,scorer_calls=0,
        source_evaluation=str(evaluation.relative_to(ROOT)),protocol_sha256=manifest['protocol_sha256'],
        arms=arms,months=months,repeats=repeats,monthly=monthly,groups=groups,
        coverage=scored['coverage'],scorable_counts=scored['scorable_counts'],
        q9_postprocessing=scored['q9_postprocessing'],q8={a:scored['arms'][a]['auxiliary_survey_weighted']['q8'] for a in arms},
        main_metric_crosschecks=checked,paired_intervals=scored['paired_intervals'],
        treatment_minus_control=differences,development_signal_passed=signal,automatic_default_upgrade=False,
        leave_one_month_out={str(m):{k:float(np.mean([c['arms'][treat][k]-c['arms'][base][k] for c in result['cells'] if c['month']!=m]))
                                   for k in ('center_mae_pp','w1_pp','delta_w1_pp')} for m in months},
        estimated_actual_cost_usd=scored['estimated_actual_cost_usd'],
        limits=['Fixed six previously examined months; no independent time validation or effect beyond this sampled support.',
                'All group results are descriptive; sparse groups explicitly flagged, no truth-based input allocation.',
                'ESS is per person within each month/repeat, never pooled as if repetitions were more people.',
                'Primary Q9 center is the across-person weighted median of individual fitted density means.',
                'Q8 has its own support; raw validity and normalized usability remain distinct.'],
        source_sha256={str((evaluation/n).relative_to(ROOT)):sha(evaluation/n) for n in ('summary.json','cases_private.json')},
        readout_source_sha256=sha(Path(__file__)),seconds=perf_counter()-started)
    out.mkdir(parents=True); dump(out/'summary.json',result)
    return result


def support_sensitivity(evaluation, out):
    """Selection sensitivity on cached normalized scores; never refit raw Q9."""
    evaluation,out=Path(evaluation).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh ignored sensitivity output required')
    scored=read_json(evaluation/'summary.json');protocol=scored['protocol']
    if protocol['mechanism']!='price_background_qwen':raise ValueError('Matching price-background evaluation required')
    cases=read_json(evaluation/'cases_private.json');arms=protocol['arms']
    months,repeats=protocol['months'],protocol['generation_repeats']
    support=shared._common_person_months(cases,arms,repeats,'q9')
    raw_support={(m,u) for m,u in support if all(
        r['arms'][a]['raw_validation_status']=='valid'
        for r in cases if (r['month'],r['userid'])==(m,u) for a in arms)}
    result=dict(raw_valid_support=summarize(cases,arms,months,repeats,raw_support),
        generation={str(rep):summarize(cases,arms,months,[rep],support) for rep in repeats},
        all_usable_person_months=len(support),new_api_calls=0,scorer_calls=0,
        interpretation='Raw-valid SUPPORT restriction using the same normalized scores. Different sample; not a causal normalization-effect estimate.',
        source_sha256={str((evaluation/n).relative_to(ROOT)):sha(evaluation/n) for n in ('summary.json','cases_private.json')})
    out.mkdir(parents=True);dump(out/'summary.json',result);return result
