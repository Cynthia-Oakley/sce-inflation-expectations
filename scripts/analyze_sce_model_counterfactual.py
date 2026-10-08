#!/usr/bin/env python3
"""Analyze completed model probes offline, with true answers only in this script."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from studies.sce_inflation_expectations.model import parse_sce_response
from studies.sce_inflation_expectations.household_state_analysis import density,distribution
from studies.sce_inflation_expectations.model_comparison_analysis import comparison_metrics
from studies.sce_inflation_expectations.model_followup import MODEL_LABELS
from studies.sce_inflation_expectations.scoring.sce_q9_frozen import provenance


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read_lines(path):return [json.loads(line) for line in path.read_text().splitlines() if line]


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--inputs',type=Path,required=True)
    ap.add_argument('--run',type=Path,action='append',required=True)
    ap.add_argument('--truth',type=Path,default=ROOT/'data/evaluation/dev_full_20261005T045330Z_947a818f/truth.json')
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    sources=[args.inputs/'summary.json',args.inputs/'requests_prepared.jsonl',args.inputs/'deepseek_reference_private.jsonl',args.truth]
    prep=json.loads((args.inputs/'summary.json').read_text());refs=read_lines(args.inputs/'deepseek_reference_private.jsonl')
    requests={ (r['case_id'],r['payload']['model']):r for r in read_lines(args.inputs/'requests_prepared.jsonl') }
    calls={};runs=[];audit_counts={}
    for folder in args.run:
        run=json.loads((folder/'run_summary.json').read_text())
        if run['status']=='running':raise ValueError('run not finalized')
        executed_requests=folder/'requests_prepared.jsonl'
        if run['input_sha256']!=sha(executed_requests):raise ValueError('run snapshot inputs differ')
        sources.append(executed_requests)
        for request in read_lines(executed_requests):
            key=(request['case_id'],request['payload']['model'])
            if key[1] not in MODEL_LABELS:raise ValueError('unregistered model identity')
            messages=request['payload']['messages']
            if hashlib.sha256(json.dumps(messages,ensure_ascii=False).encode()).hexdigest()!=prep['case_prompt_hashes'][key[0]]:
                raise ValueError('run messages differ from original frozen reference')
            if key in requests and request!=requests[key]:raise ValueError('conflicting model/case input')
            requests[key]=request
        runs.append(run);sources.append(folder/'run_summary.json')
        path=folder/'llm_calls.jsonl'
        if path.exists():
            sources.append(path)
            for call in read_lines(path):
                counts=audit_counts.setdefault(call['requested_model'],Counter())
                counts['attempts']+=1
                counts['http_200']+=call.get('http_status')==200
                if call.get('error'):counts[call['error']]+=1
                if call.get('error') or 'answer' not in call:continue
                key=(call['case_id'],call['requested_model'])
                if key in calls:raise ValueError('duplicate successful model/case')
                request=requests[key];messages=request['payload']['messages']
                if hashlib.sha256(json.dumps(messages,ensure_ascii=False).encode()).hexdigest()!=prep['case_prompt_hashes'][key[0]]:
                    raise ValueError('reference messages changed')
                from studies.sce_inflation_expectations.model_counterfactual import guarded_payload
                payload=guarded_payload(request)
                if hashlib.sha256(json.dumps(payload,ensure_ascii=False,sort_keys=True).encode()).hexdigest()!=call['payload_sha256']:
                    raise ValueError('executed payload hash differs')
                calls[key]=call
    completed=sorted({model for _,model in calls if sum(m==model for _,m in calls)==40})
    if not completed:raise ValueError('no full 40-case model')
    def month_key(value):
        text=str(value)
        return f'{text[:4]}-{text[4:]}' if len(text)==6 and text.isdigit() else text
    truth={(month_key(r['date']),f"sce_u{int(r['userid'])}"):r for r in json.loads(args.truth.read_text())['per_person']}
    labels={model:MODEL_LABELS[model] for model in completed}
    arms=['deepseek_reference',*[labels[m] for m in completed]]
    scorer=provenance()
    if not scorer['live_matches_pinned']:raise ValueError('frozen scorer sources changed')
    result={'run_ids':[r['run_id'] for r in runs],'completed_models':completed,'months':{},
            'model_completion':{model:{'target_cases':40,'valid_unique_cases':sum(m==model for _,m in calls),
                'complete_for_effect_comparison':model in completed,'attempt_audit':dict(counts)} for model,counts in audit_counts.items()},
            'costs':{r['run_id']:r.get('new_charged_or_reserved_usd',r['total_charged_or_reserved_usd']) for r in runs},'scorer':scorer,
            'estimand':'equal-weight exact matched 20-case development sample per month; not national headline',
            'prompt_version':prep['prompt_version'],'temperature':.5,'new_calls_in_analysis':0,
            'limitations':['A development months only, not blind B prediction','2021 is potentially in every model training window',
                          'one generation per model/case; model, provider, quantization and random variation not separately identified',
                          'same approximate Q9 scorer applied to real and model bins; no official headline reconstruction',
                          'Qwen absent if its locked route failed preflight; no provider substitution']}
    person_rows=[]
    for month in ['2021-05','2021-06']:
        selected=[r for r in refs if r['case_id'].startswith(month)]
        people={r['agent_id']:r for r in json.loads((args.inputs/month/'population.json').read_text())['personas']}
        q9rows=[];q8rows=[];statuses=Counter();uncertainty={arm:[] for arm in ['real',*arms]};profiles={}
        raw_patterns={arm:Counter() for arm in arms}
        for ref in selected:
            case=ref['case_id'];person=truth[(month,ref['source_agent_id'])]
            baseline,error=parse_sce_response(ref['reference_response'])
            if error:raise ValueError('invalid recorded baseline')
            answers={'deepseek_reference':baseline,**{labels[m]:calls[(case,m)]['answer'] for m in completed}}
            for arm,answer in answers.items():raw_patterns[arm].update([tuple(answer['bins'])])
            fits={'real':density([person.get(f'Q9_bin{i}') for i in range(1,11)]),
                  **{arm:density(a['bins']) for arm,a in answers.items()}}
            statuses.update(f'{arm}:{f["status"]}' for arm,f in fits.items())
            q9row={'case_id':case,**{arm:f['mean'] for arm,f in fits.items()}}
            q8row={'case_id':case,'real':person.get('Q8v2part2'),**{arm:a['point_pct'] for arm,a in answers.items()}}
            q9rows.append(q9row);q8rows.append(q8row)
            profiles[case]=people[ref['source_agent_id']]['attributes']
            if all(q9row[k] is not None for k in ['real',*arms]):
                for arm,f in fits.items():
                    if f['iqr'] is not None:uncertainty[arm].append(f['iqr'])
            person_rows.append({'month':month,'case_id':case,'Q9':q9row,'Q8':q8row,
                                'profile':people[ref['source_agent_id']]['attributes'],
                                'individual_uncertainty_iqr':{arm:f['iqr'] for arm,f in fits.items()}})
        groups={}
        for field in ['age_group','education_group','household_income_band','numeracy','employment_status']:
            groups[field]={}
            for value in sorted({str(p.get(field,'unknown')) for p in profiles.values()}):
                subset=[r for r in q9rows if str(profiles[r['case_id']].get(field,'unknown'))==value]
                common=[r for r in subset if all(type(r[k]) in (int,float) for k in ['real',*arms])]
                # Tiny groups are not displayed with true/model estimates.
                groups[field][value]={'n_selected':len(subset),'n_common':len(common),'sparse_below_five':len(common)<5}
                if len(common)>=5:
                    groups[field][value]['Q9']=comparison_metrics(subset,arms)
        result['months'][month]={'Q9':comparison_metrics(q9rows,arms),'Q8_secondary':comparison_metrics(q8rows,arms),
                                 'fitting_status_counts':dict(statuses),
                                 'individual_uncertainty_iqr':{arm:distribution(vals) for arm,vals in uncertainty.items()},
                                 'raw_probability_patterns':{arm:{'n':sum(counts.values()),'unique_vectors':len(counts),
                                     'most_frequent_vector':list(counts.most_common(1)[0][0]),
                                     'most_frequent_count':counts.most_common(1)[0][1]} for arm,counts in raw_patterns.items()},
                                 'profile_group_diagnostics':groups}
    sources += [Path(__file__).resolve(),ROOT/'studies/sce_inflation_expectations/model_comparison_analysis.py',
                ROOT/'studies/sce_inflation_expectations/model_followup.py',
                ROOT/'studies/sce_inflation_expectations/household_state_analysis.py',
                ROOT/'studies/sce_inflation_expectations/scoring/sce_q9_frozen.py']
    result['source_hashes']={str(p):sha(p) for p in sources}
    (args.out/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    (args.out/'paired_evaluation_private.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in person_rows))
    snapshot=args.out/'scorer_snapshot';snapshot.mkdir()
    for name in ['sce_q9.py','sce_q9_frozen.py','beta_fit_kernel.py']:
        (snapshot/name).write_bytes((ROOT/'studies/sce_inflation_expectations/scoring'/name).read_bytes())
    print(json.dumps({m:{'n':r['Q9']['n_common'],'arms':r['Q9']['arms']} for m,r in result['months'].items()},ensure_ascii=False))


if __name__=='__main__':main()
