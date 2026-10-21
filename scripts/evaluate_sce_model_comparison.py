#!/usr/bin/env python3
"""Score new model once, then combine cached exact-message Qwen controls."""
import argparse
from collections import Counter
from copy import deepcopy
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from scripts.evaluate_sce_call_ledger import evaluate as score_calls
from studies.sce_inflation_expectations.experiments.frozen_batch import verify,read_json,dump,sha
from studies.sce_inflation_expectations.evaluation import cognition as shared
from studies.sce_inflation_expectations.evaluation.frozen_trial import paired_intervals
from studies.sce_inflation_expectations.evaluation.price_background_readout import summarize


def merge_cached_controls(new_cases, archived_cases, months, repeats):
    controls={(r['month'],r['repeat'],r['agent_id']):r for r in archived_cases if r['month'] in months}
    result=[]
    for r in new_cases:
        old=controls[r['month'],r['repeat'],r['agent_id']]
        if (r['real']!=old['real'] or r['profile']!=old['profile']
                or abs(r['design_survey_weight']-old['design_survey_weight'])>1e-12):
            raise ValueError('Same targets, P and weights required for cached comparison')
        row=deepcopy(r);row['arms']['qwen_cached']=deepcopy(old['arms']['food_background']);result.append(row)
    expected=len(months)*96*len(repeats)
    if len(result)!=expected or len({(r['month'],r['repeat'],r['agent_id']) for r in result})!=expected:
        raise ValueError('Complete unique comparison cases required')
    return result


def evaluate(ledger,out):
    ledger,out=ledger.resolve(),out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh evaluation required')
    parent=ROOT/read_json(ledger/'protocol.json')['call_ledger_parent'];m,p=verify(parent)
    if p['mechanism']!='v32_same_input':raise ValueError('Registered V3.2 comparison required')
    scored_dir=out.with_name(out.name+'_new_model_scores')
    score_calls(ledger,scored_dir)
    scored=read_json(scored_dir/'summary.json')
    cache=ROOT/p['source_evaluation']/'cases_private.json'
    if sha(cache)!=m['source_sha256'][str(cache.relative_to(ROOT))]:raise ValueError('Cached controls changed')
    cases=merge_cached_controls(read_json(scored_dir/'cases_private.json'),read_json(cache),p['months'],p['generation_repeats'])
    arms=p['comparison_arms'];months=p['months'];repeats=p['generation_repeats']
    s9=shared._common_person_months(cases,arms,repeats,'q9');s8=shared._common_person_months(cases,arms,repeats,'q8')
    summaries={a:shared._summarize_arm(cases,a,months,repeats,s9,s8) for a in arms}
    readout=summarize(cases,arms,months,repeats,s9)
    groups={}
    from studies.sce_inflation_expectations.evaluation.procurement_gap import band
    for group in sorted({band(r['real']['previous_q9_mean']) for r in cases}):
        subset=[r for r in cases if band(r['real']['previous_q9_mean'])==group]
        groups[group]=summarize(subset,arms,months,repeats,s9)
    result=dict(status='completed_exact_message_model_comparison',protocol=dict(p,arms=arms),
        generated_protocol=p,new_api_calls=0,new_generated_responses=p['planned_calls'],reused_control_responses=768,
        coverage={a:dict(Counter(r['arms'][a]['validation_status'] for r in cases)) for a in arms},
        common_q9_person_months=len(s9),common_q8_person_months=len(s8),arms=summaries,readout=readout,
        prior_groups=groups,paired_intervals=paired_intervals(cases,arms,months,repeats,s9) if s9 else None,
        estimated_actual_cost_usd=scored['estimated_actual_cost_usd'],automatic_upgrade=False,
        q9_postprocessing=scored['q9_postprocessing'],comparison_kind='New model versus archived exact-message controls',
        source_sha256={str((scored_dir/n).relative_to(ROOT)):sha(scored_dir/n) for n in ('summary.json','cases_private.json')})
    out.mkdir();dump(out/'summary.json',result);dump(out/'cases_private.json',cases)
    return dict(status=result['status'],common_q9_person_months=len(s9),metrics=readout['metrics'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();print(evaluate(args.ledger,args.out))
