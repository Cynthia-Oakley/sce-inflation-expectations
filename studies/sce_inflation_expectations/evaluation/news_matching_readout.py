"""Cached news-mechanism diagnostics; shared metrics, no API or Q9 refitting."""
from copy import deepcopy
from pathlib import Path
from datetime import datetime,timezone
import numpy as np

from . import cognition as shared
from .price_background_readout import summarize
from .procurement_gap import band
from ..population_stratification import cell_key
from ..experiments.frozen_batch import ROOT,read_json,dump,sha

CONTRASTS=[('fixed_8','random_quantity'),('random_quantity','demographic_quantity'),
           ('random_quantity','random_quantity_uniform_topics')]


def runtime_chain(ledger):
    """Count actual new calls/fees across manual never-attempted continuations."""
    ledger=Path(ledger).resolve();parts=[];seen=set()
    while True:
        if ledger in seen:raise ValueError('Cyclic ledger provenance')
        seen.add(ledger);p=read_json(ledger/'protocol.json');r=read_json(ledger/'run_receipt.json')
        parts.append(dict(ledger=str(ledger.relative_to(ROOT)),receipt=r))
        previous=p.get('previous_call_ledger')
        if not previous:break
        ledger=(ROOT/previous).resolve()
        if not ledger.is_relative_to(ROOT/'outputs'):raise ValueError('Private ledger provenance required')
    total=deepcopy(parts[0]['receipt'])
    for key in ('new_calls','api_reported_new_cost_usd','seconds','automatic_retries'):
        total[key]=sum(part['receipt'][key] for part in parts)
    total.update(chunks=list(reversed(parts)),technical_gate_completed=any(
        bool(part['receipt'].get('technical_gate_completed')) for part in parts),
        aggregation='Sum new actual requests/reported fees/runtime across original and never-attempted continuation; final combined reserve already includes prior charges.')
    return total


def input_summary(trial):
    """First-stage allocation description; never uses answers or errors."""
    trial=Path(trial)
    allocation=read_json(trial/'allocations_private.json')
    links={(r['month'],r['agent_id']):r for r in read_json(trial/'evaluation_links_private.json')}
    monthly=[];groups=[]
    for month in sorted({r['month'] for r in allocation}):
        rows=[r for r in allocation if r['month']==month]
        w=np.array([links[month,r['agent_id']]['design_survey_weight'] for r in rows])
        rc=np.array([r['news_counts']['random_quantity'] for r in rows])
        mc=np.array([r['news_counts']['demographic_quantity'] for r in rows])
        expected=np.array([np.arange(1,7)@np.asarray(r['attention_probabilities']) for r in rows])
        monthly.append(dict(month=month,n=len(rows),
            same_person_news_count_changed_share=float(np.mean(rc!=mc)),
            design_weighted_changed_share=float(np.average(rc!=mc,weights=w)),
            random_weighted_news=float(np.average(rc,weights=w)),matched_weighted_news=float(np.average(mc,weights=w)),
            predicted_six_class_attention_score_min=float(expected.min()),
            predicted_six_class_attention_score_max=float(expected.max())))
        for dimension in ('education_group','age_group','household_income_band','region'):
            vals=[str(links[month,r['agent_id']]['profile'].get(dimension,'unknown')) for r in rows]
            for value in sorted(set(vals)):
                mask=np.array([v==value for v in vals]);gw=w[mask]
                groups.append(dict(month=month,dimension=dimension,group=value,n=int(mask.sum()),
                    ess=float(gw.sum()**2/(gw@gw)),random_weighted_news=float(np.average(rc[mask],weights=gw)),
                    matched_weighted_news=float(np.average(mc[mask],weights=gw))))
    return dict(scope='Input-only first-stage allocation; not effects on inflation expectations.',
        monthly=monthly,demographic_group_months=groups,news_quota_is_design_not_actual_readership=True)


def operational_view(cases,arms):
    """Project the previously registered fallback without touching originals."""
    result=deepcopy(cases)
    for row in result:
        real=row['real']
        for a in arms:
            v=row['arms'][a]
            if not shared.finite(v['mean']) or not shared.finite(v['iqr']):
                v.update(mean=real['previous_q9_mean'],iqr=real['previous_q9_iqr'],
                    zero_deflation=real['previous_q9_zero_deflation'],q9_bins=real['previous_q9_bins'])
            if not shared.finite(v['point']):v['point']=real['previous_q8_point']
    return result


def summary(cases,arms,months,repeats,support):
    result=summarize(cases,arms,months,repeats,support)
    result['sparse_cells']=[{k:c[k] for k in ('month','repeat','n','ess','max_weight_share')}
        for c in result['cells'] if c['n']<10 or c['ess']<10]
    result['sparse_rule']='Per month/repeat N<10 or ESS<10; repeats never add independent people.'
    return result


def contrast(readout,available,base,candidate,coverage_ok):
    cells=readout['cells'];months=sorted({c['month'] for c in cells})
    differences={k:readout['metrics'][candidate][k]-readout['metrics'][base][k]
        for k in ('center_mae_pp','center_rmse_pp','w1_pp','delta_w1_pp','across_person_iqr_pp','personal_mae_pp')}
    monthly={str(m):{k:float(np.mean([c['arms'][candidate][k]-c['arms'][base][k] for c in cells if c['month']==m]))
        for k in ('center_mae_pp','w1_pp','delta_w1_pp')} for m in months}
    repeats={str(r):{k:float(np.mean([c['arms'][candidate][k]-c['arms'][base][k] for c in cells if c['repeat']==r]))
        for k in ('center_mae_pp','w1_pp','delta_w1_pp')} for r in (1,2)}
    common_gap=available['metrics'][candidate]['w1_pp']-available['metrics'][base]['w1_pp']
    checks=dict(available_coverage_at_least_95pct=bool(coverage_ok),fixed_roster_mean_w1_lower=differences['w1_pp']<0,
        w1_nonworse_in_at_least_five_months=sum(v['w1_pp']<=0 for v in monthly.values())>=5,
        both_generations_mean_w1_nonworse=all(v['w1_pp']<=0 for v in repeats.values()),
        center_mae_cost_at_most_005pp=differences['center_mae_pp']<=.05,
        actual_common_support_w1_not_reversed=common_gap<=0)
    return dict(base=base,candidate=candidate,candidate_minus_base=differences,monthly=monthly,generation=repeats,
        actual_common_support_w1_difference_pp=common_gap,screen_checks=checks,
        development_screen_passed=all(checks.values()),automatic_upgrade=False,
        leave_one_month_out={str(m):{k:float(np.mean([c['arms'][candidate][k]-c['arms'][base][k]
            for c in cells if c['month']!=m])) for k in ('center_mae_pp','w1_pp','delta_w1_pp')} for m in months})


def readout(evaluation,ledger,out):
    evaluation,ledger,out=map(lambda p:Path(p).resolve(),(evaluation,ledger,out))
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh private readout required')
    s=read_json(evaluation/'summary.json');cases=read_json(evaluation/'cases_private.json')
    p=s['protocol'];runtime=runtime_chain(ledger)
    if p['mechanism']!='v32_news_matching' or runtime['status']!='completed':raise ValueError('Completed news batch required')
    arms,months,repeats=p['arms'],p['months'],p['generation_repeats']
    support=shared._common_person_months(cases,arms,repeats,'q9')
    available=summary(cases,arms,months,repeats,support)
    op_cases=operational_view(cases,arms);fixed_support=shared._common_person_months(op_cases,arms,repeats,'q9')
    fixed=summary(op_cases,arms,months,repeats,fixed_support)
    crosschecks=0
    for a in arms:
        for own,ref in [('center_mae_pp','q9_center_mae_pp'),('w1_pp','cross_section_w1_pp'),
                        ('across_person_iqr_pp','cross_person_iqr_pp'),('delta_w1_pp','delta_w1_pp')]:
            for result,expected in ((available,s['arms'][a]['auxiliary_survey_weighted']),
                (fixed,s['fixed_roster_operational']['primary_arms'][a])):
                if abs(result['metrics'][a][own]-expected['q9']['aggregate_equal_month_repeat_cells'][ref])>1e-8:
                    raise ValueError('Frozen weighted evaluator mismatch: '+a+'/'+own)
                crosschecks+=1
    lp=read_json(ledger/'protocol.json')
    groups={};allocation=read_json(ROOT/lp['call_ledger_parent']/'allocations_private.json')
    level={(r['month'],r['agent_id']):r['news_counts']['random_quantity'] for r in allocation}
    def label(r,dimension):
        if dimension=='prior':return band(r['real']['previous_q9_mean'])
        if dimension=='six_cell':return cell_key(r['profile'])
        if dimension=='news_count':return str(level[r['month'],r['agent_id']])
        return str(r['profile'].get(dimension,'unknown'))
    for dimension in ('prior','six_cell','age_group','household_income_band','region','news_count'):
        groups[dimension]={}
        for value in sorted({label(r,dimension) for r in op_cases if (r['month'],r['userid']) in fixed_support}):
            rows=[r for r in op_cases if label(r,dimension)==value]
            gs={(r['month'],r['userid']) for r in rows}&fixed_support
            groups[dimension][value]=summary(rows,arms,months,repeats,gs)
    pairs={f'{cand}_minus_{base}':summary(cases,[base,cand],months,repeats,
        shared._common_person_months(cases,[base,cand],repeats,'q9')) for base,cand in CONTRASTS}
    epochs={str(name):summary([r for r in op_cases if r['month'] in mm],arms,mm,repeats,fixed_support)
        for name,mm in [('earlier_four',[202009,202109,202206,202503]),('later2025_four',[202504,202506,202508,202510])]}
    result=dict(status='completed_news_matching_cached_readout',new_api_calls=0,new_q9_fits=0,
        completed_at_utc=datetime.now(timezone.utc).isoformat(),months=months,arms=arms,
        n_by_month=p['n_by_month'],actual_available=available,fixed_roster_operational=fixed,
        actual_pair_support=pairs,epochs=epochs,groups=groups,input_allocation=input_summary(ROOT/lp['call_ledger_parent']),
        comparisons=[contrast(fixed,available,b,c,not s['accuracy_descriptive_only']) for b,c in CONTRASTS],
        weighted_metric_crosschecks=crosschecks,coverage=s['coverage'],scorable_counts=s['scorable_counts'],
        fallback_counts=s['fixed_roster_operational']['fallback_counts'],q9_postprocessing=s['q9_postprocessing'],
        actual_q8={a:s['arms'][a]['auxiliary_survey_weighted']['q8'] for a in arms},
        fixed_q8={a:s['fixed_roster_operational']['primary_arms'][a]['q8'] for a in arms},
        baseline_comparable_q8=s['fixed_roster_operational']['q8_baseline_supported_models'],
        baseline_comparable_q8_person_months=s['fixed_roster_operational']['q8_baseline_comparable_person_months'],
        carry_q8=s['fixed_roster_operational']['same_support_carry']['q8'],
        actual_q9_density={a:s['arms'][a]['auxiliary_survey_weighted']['q9'] for a in arms},
        paired_intervals_actual_support=s['paired_intervals'],additional_intervals_actual_support=s['additional_paired_intervals'],
        runtime=runtime,dispatch_budget_usd=read_json(ledger/'protocol.json')['budget_cap_usd'],
        reuse=read_json(ledger/'preparation_receipt.json'),accuracy_descriptive_only=s['accuracy_descriptive_only'],
        configuration={k:p[k] for k in ('model','route','temperature','max_tokens','thinking','allocation_seed','generation_repeats')},
        limits=p['limits']+['Fixed-roster results include separately counted previous-answer fallbacks; they are not pure model responses.',
            'Conditional groups are descriptive; calendar months and demographic cells are not new randomized experiments.',
            'Only actually run combinations can be selected; demographic quantity plus uniform themes has not been run.',
            'Development screening is not a multiplicity-adjusted confirmatory claim or a final default upgrade.'],
        source_sha256={str(f.relative_to(ROOT)):sha(f) for f in [evaluation/'summary.json',evaluation/'cases_private.json',
            ledger/'run_receipt.json',ledger/'protocol.json',Path(__file__)]})
    out.mkdir(parents=True);dump(out/'summary.json',result)
    return dict(status=result['status'],metrics=fixed['metrics'],comparisons=result['comparisons'])
