#!/usr/bin/env python3
"""Evaluate original + resumed raw calls; missing API replies stay missing."""
import argparse
from collections import Counter
from pathlib import Path
from time import perf_counter
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.append(str(ROOT.parent/'socioverse2_repo'))
import studies
studies.__path__=[str(ROOT/'studies'),*studies.__path__]
from studies.sce_inflation_expectations.experiments.frozen_batch import verify,read_json,dump,sha
from studies.sce_inflation_expectations.evaluation import cognition as shared
from studies.sce_inflation_expectations.evaluation.frozen_trial import score_bins,paired_intervals
from studies.sce_inflation_expectations.model import validate_sce_bins
from studies.sce_inflation_expectations.q9_normalization import response_view,response_point


def evaluate(ledger,out):
    started=perf_counter();ledger,out=ledger.resolve(),out.resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored evaluation required')
    lp=read_json(ledger/'protocol.json');lm=read_json(ledger/'manifest.json')
    parent=ROOT/lp['call_ledger_parent'];manifest,protocol=verify(parent)
    if sha(ledger/'protocol.json')!=lm['protocol_sha256']:raise ValueError('Ledger protocol changed')
    for n,h in lm['source_sha256'].items():
        if sha(ROOT/n)!=h:raise ValueError('Ledger source changed: '+n)
    for n,h in lm['files_sha256'].items():
        if sha(ledger/n)!=h:raise ValueError('Ledger inputs changed')
    receipt=read_json(ledger/'run_receipt.json')
    if receipt['status']!='completed':raise ValueError('Finish all never-attempted slots before full evaluation')
    slots=read_json(ledger/'slots_private.json');existing=read_json(ledger/'existing_calls_private.json')
    calls={k:r['call'] for k,r in existing.items()}
    for line in (ledger/'new_calls_private.jsonl').read_text().splitlines():
        row=json.loads(line)
        if row['slot_key'] in calls:raise ValueError('A model slot was retried')
        calls[row['slot_key']]=row
    if len(calls)!=3456 or set(calls)!={s['slot_key'] for s in slots}:raise ValueError('Exact full call ledger required')
    arms=protocol['arms'];months=protocol['months'];repeats=protocol['generation_repeats']
    coverage={a:Counter() for a in arms};raw_coverage={a:Counter() for a in arms};normalization={a:Counter() for a in arms}
    actions={};normrows=[]
    for slot in slots:
        c=calls[slot['slot_key']];arm=slot['arm'];raw=c.get('raw_response_text') or ''
        raw_hash_ok=(hashlib.sha256(raw.encode()).hexdigest()==c['raw_response_sha256']
                     or bool(c.get('error') and c.get('raw_response_text') is None and c['raw_response_sha256'] is None))
        if (c['attempt_idx']!=0 or c['prompt_sha256']!=slot['prompt_sha256']
                or c['prompt_text']!=json.dumps(slot['messages'],ensure_ascii=False)
                or not raw_hash_ok
                or c['temperature']!=protocol['temperature'] or c['max_tokens']!=protocol['max_tokens']
                or c['extra_body']!=protocol['request_extra_body']):raise ValueError('Original input/reply/parameter mismatch')
        if not c.get('error') and (c.get('returned_model')!=protocol['model'] or c.get('returned_provider')!='DeepInfra'):
            raise ValueError('Model/provider mismatch')
        point=response_point(raw);view=None;usable=False;raw_bins=None;raw_ok=False
        try:
            obj=json.loads(raw);raw_bins=[obj['q9'][f'bin{i}'] for i in range(1,11)]
        except (ValueError,KeyError,TypeError):pass
        if not c.get('error') and c.get('finish_reason')=='stop':
            try:
                view=response_view(raw);usable=True;raw_ok=validate_sce_bins(view['raw_bins'])[0]
            except (ValueError,TypeError):pass
        raw_status='error' if c.get('error') else 'valid' if raw_ok else 'invalid'
        status='valid' if usable else 'error' if c.get('error') else 'invalid'
        raw_coverage[arm][raw_status]+=1;coverage[arm][status]+=1
        normalization[arm]['usable_after_postprocessing' if usable else 'unusable_after_postprocessing']+=1
        normalization[arm]['normalization_applied']+=bool(usable and view['applied'])
        bins=view['bins'] if usable else []
        score=score_bins(tuple(bins)) if usable else {'mean':None,'iqr':None,'zero_deflation':None}
        actions[slot['month'],slot['repeat'],slot['agent_id'],arm]={**score,'q9_bins':bins,
            'point':round(point,4) if point is not None else None,'validation_status':status,
            'raw_q9_bins':raw_bins,'raw_validation_status':raw_status,'normalization_applied':bool(usable and view['applied'])}
        normrows.append({'month':slot['month'],'repeat':slot['repeat'],'arm':arm,'agent_id':slot['agent_id'],
            'raw_response_sha256':c['raw_response_sha256'],'raw_bins':raw_bins,'derived_bins':bins if usable else None,
            'raw_sum':view['raw_sum'] if usable else None,'policy':protocol['q9_postprocessing'],
            'applied':bool(usable and view['applied']),'interface_error':bool(c.get('error'))})
    truth_file=ROOT/protocol['evaluation_truth']
    if sha(truth_file)!=manifest['source_sha256'][str(truth_file.relative_to(ROOT))]:raise ValueError('Frozen truth changed')
    truth={(r['month'],r['agent_id'],r['repeat']):r['real'] for r in read_json(truth_file)}
    cases=[]
    for link in read_json(parent/'evaluation_links_private.json'):
        for repeat in repeats:
            m,aid=link['month'],link['agent_id'];cases.append({**link,'repeat':repeat,'survey_weight':link['design_survey_weight'],
                'real':truth[m,aid,repeat],'arms':{a:actions[m,repeat,aid,a] for a in arms}})
    support9=shared._common_person_months(cases,arms,repeats,'q9');support8=shared._common_person_months(cases,arms,repeats,'q8')
    summaries={a:shared._summarize_arm(cases,a,months,repeats,support9,support8) for a in arms}
    expected=len(months)*protocol['n_per_month']*len(repeats)
    scorable={a:sum(shared.finite(r['arms'][a]['mean']) and shared.finite(r['arms'][a]['iqr']) for r in cases) for a in arms}
    valid=all(coverage[a]['valid']/expected>=.99 and scorable[a]/expected>=.99 for a in arms)
    result={'status':'completed_call_ledger_evaluation','protocol':protocol,'call_ledger_source':str(ledger.relative_to(ROOT)),
        'new_api_calls':0,'estimated_actual_cost_usd':receipt['combined_spent_or_reserved_usd'],
        'coverage':{a:dict(v) for a,v in coverage.items()},'common_q9_person_months':len(support9),'common_q8_person_months':len(support8),
        'scorable_counts':scorable,'arms':summaries,'primary_comparison':protocol['primary_comparison'],
        'paired_intervals':paired_intervals(cases,protocol['primary_comparison'],months,repeats,support9) if valid else None,
        'additional_paired_intervals':{f'{other}_minus_{base}':paired_intervals(cases,[base,other],months,repeats,support9)
            for base,other in protocol['additional_comparisons']} if valid else None,
        'accuracy_descriptive_only':not valid,'automatic_upgrade':False,
        'q9_postprocessing':{'policy':protocol['q9_postprocessing'],'counts_by_arm':{a:dict(v) for a,v in normalization.items()},
            'raw_runtime_coverage':{a:dict(v) for a,v in raw_coverage.items()},
            'coverage_semantics':'Original plus resumed raw call ledger. Failed calls stay missing; analysis uses normalized Q9.'},
        'evaluation_seconds':perf_counter()-started,
        'notes':['One attempt per original slot, including previously failed requests; no retries or invented decisions.',
            'Remaining requests use the same SCEOpenAILLM and frozen messages, outside the Core loop; schedule change documented.',
            'Proportional normalization is a user-authorized analysis policy; raw responses and failures unchanged.']}
    out.mkdir();dump(out/'summary.json',result);dump(out/'cases_private.json',cases);dump(out/'q9_normalization_private.json',normrows)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--ledger',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();r=evaluate(a.ledger,a.out);print({k:r[k] for k in ['status','common_q9_person_months','coverage','evaluation_seconds']})
