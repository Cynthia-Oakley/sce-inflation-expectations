"""Verify immutable classifier replies and summarize stratified news trial."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs',type=Path,required=True)
    parser.add_argument('--labels',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    plan=json.loads((args.inputs/'summary.json').read_text())
    state=json.loads((args.labels/'state.json').read_text())
    assert state['status']=='completed','Label trial incomplete'
    assert state['input_request_file_sha256']==plan['request_file_sha256']==sha(args.inputs/'requests_prepared.jsonl')
    requests={r['batch_id']:r for r in (json.loads(line) for line in (args.inputs/'requests_prepared.jsonl').read_text().splitlines())}
    spec=importlib.util.spec_from_file_location('news_label_analysis_validator',Path(__file__).with_name('news_label_trial.py'))
    validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
    calls=validator.prior_call_chain(args.labels)
    assert len(calls)==len(requests) and {c['batch_id'] for _,c in calls}==set(requests)
    verified,repairs,returned_models={},[],Counter()
    prompt_tokens=completion_tokens=0
    exact_snapshot_cost=0.
    for source_directory,call in calls:
        number=call['batch_id'];row=requests[number]
        path=source_directory/f'response_{number:03d}.json'
        assert sha(path)==call['response_sha256']
        reply=json.loads(path.read_bytes());choice=reply['choices'][0]
        assert choice['finish_reason']=='stop'
        inputs=validator.guarded_payload(row)
        labels,fixes=validator.validate_with_evidence_shortening(choice['message']['content'],inputs)
        repairs.extend(dict(batch_id=number,**fix) for fix in fixes)
        for label in labels:
            assert label['article_id'] not in verified
            verified[label['article_id']]=label
        returned_models[reply['model']]+=1
        usage=reply['usage'];prompt_tokens+=usage['prompt_tokens'];completion_tokens+=usage['completion_tokens']
        # This run was dispatched Sunday UTC: all requests qualify for off-peak.
        # This is a published-rate usage estimate, not an account invoice.
        from datetime import datetime
        assert datetime.fromisoformat(call['started_at_utc']).weekday()==6
        hit=usage.get('prompt_cache_hit_tokens',0)
        miss=usage.get('prompt_cache_miss_tokens',usage['prompt_tokens']-hit)
        assert hit+miss==usage['prompt_tokens']
        exact_snapshot_cost+=(hit*.003+miss*.15+usage['completion_tokens']*.60)/1e6
    stored={r['label']['article_id']:r['label'] for r in (json.loads(line) for line in (args.labels/'labels.jsonl').read_text().splitlines())}
    assert stored==verified
    assert len(verified)==plan['unique_articles_to_label']==state['articles_valid']
    assert prompt_tokens==state['prompt_tokens'] and completion_tokens==state['completion_tokens']
    assert abs((prompt_tokens*.30+completion_tokens*1.20)/1e6-state['spent_or_reserved_upper_usd'])<1e-10
    assert state['spent_or_reserved_upper_usd']<=.25
    for path,expected in plan['source_sha256'].items():assert sha(ROOT/path)==expected
    protected=json.loads((ROOT/'docs/sources/sol_handoff_protected_files_20261010.json').read_bytes())['files_sha256']
    assert all(sha(ROOT/p)==h for p,h in protected.items())
    windows=[];all_public=[]
    for info in plan['windows']:
        target=info['target']
        pool=json.loads((args.inputs/f'pool_{target}.json').read_text())
        sample=json.loads((args.inputs/f'sample_{target}.json').read_text())
        pool_by_id={r['article_id']:r for r in pool}
        assert len(pool_by_id)==len(pool)
        assert len({r['article_id'] for r in sample})==len(sample)
        assert all(r==pool_by_id[r['article_id']] for r in sample)
        strata={}
        estimates={k:Counter() for k in ('new_rule','old_rule')}
        old_final_counts=Counter();old_final_topics=Counter()
        main_examples=[];miss_examples=[];old_excluded=[]
        new_sample_counts=Counter()
        for name,design in info['strata'].items():
            rows=[r for r in sample if r['stratum']==name]
            pop=[r for r in pool if r['stratum']==name]
            assert len(rows)==design['sample'] and len(pop)==design['population']
            decisions=Counter(verified[r['article_id']]['decision'] for r in rows)
            strata[name]=dict(design,decision_counts=dict(decisions))
            weight=len(pop)/len(rows) if rows else 0
            for r in rows:
                label=verified[r['article_id']]
                for method,yes in (('new_rule',bool(r['new_hits'])),('old_rule',r['old_tier'] is not None)):
                    if yes:estimates[method][label['decision']]+=weight
                if r['new_hits']:new_sample_counts[label['decision']]+=1
                if r['old_final']:
                    old_final_counts[label['decision']]+=1
                    if label['decision']=='keep':old_final_topics.update(label['topics'])
                public={k:r[k] for k in ('article_id','event_id','headline','web_url','pub_date','stratum')}
                public.update(target=target,decision=label['decision'],topics=label['topics'],scope=label['scope'],
                              claim_type=label['claim_type'],reason_zh=label['reason_zh'],
                              new_recalled=bool(r['new_hits']),old_final=r['old_final'])
                all_public.append(public)
                if label['decision']=='keep' and r['stratum']=='new_only':main_examples.append(public)
                if label['decision']=='keep' and not r['new_hits']:miss_examples.append(public)
                if label['decision'] in {'exclude','uncertain'} and r['old_final']:old_excluded.append(public)
        candidate_estimates={}
        for method,key in (('new_rule','new_rule_candidates'),('old_rule','old_rule_candidates')):
            count=info['counts'][key]
            assert abs(sum(estimates[method].values())-count)<1e-7
            candidate_estimates[method]={'candidate_population':count,
                'estimated_label_counts':dict(estimates[method]),
                'estimated_keep_fraction':estimates[method]['keep']/count,
                'estimated_keep_or_background_fraction':(estimates[method]['keep']+estimates[method]['background'])/count}
        windows.append(dict(info,stratified_model_labels=strata,
            old_final_exact_model_labels=dict(old_final_counts),old_final_keep_topics=dict(old_final_topics),
            new_candidate_sample_model_labels=dict(new_sample_counts),candidate_model_estimates=candidate_estimates,
            new_only_keep_examples=main_examples,still_not_recalled_keep_examples=miss_examples,
            old_final_exclude_or_uncertain_examples=old_excluded))
    args.out.mkdir(parents=True,exist_ok=False)
    summary={'checked_on':'2026-10-11','preparation_run_id':plan['run_id'],'classification_run_id':state['run_id'],
        'windows':windows,'unique_articles_labeled':len(verified),'unique_label_counts':dict(Counter(r['decision'] for r in verified.values())),
        'total_paid_requests':len(calls),'same_prompt_retries':0,
        'quote_shortening_count':sum(r['kind']=='offline_verbatim_quote_shortening' for r in repairs),
        'verbatim_echo_removal_count':sum(r['kind']=='offline_remove_verbatim_input_echo' for r in repairs),
        'returned_models':dict(returned_models),'prompt_tokens':prompt_tokens,'completion_tokens':completion_tokens,
        'peak_uncached_cost_upper_usd':state['spent_or_reserved_upper_usd'],
        'published_offpeak_cache_aware_cost_estimate_usd':exact_snapshot_cost,'budget_cap_usd':.25,
        'billing_note':'Token/rate estimate, not an account bill; Sunday off-peak prices verified from official docs on 2026-10-11.',
        'pricing_url':plan['pricing_url'],'raw_json_schema_and_verbatim_evidence':'pass after recorded quote shortening',
        'all_requests_revalidated_from_raw_response':True,'protected_files_unchanged':len(protected),
        'new_simulation_calls':0,'historical_text_vintage':'unverified_archive_snapshot',
        'interpretation':'Funnel is observed counts. Semantic labels and weighted rates are model suggestions, not human accuracy or true recall. Rare missed topics sampled at n15 have high uncertainty. Independent September shares standards but a different window length, so raw counts are not directly comparable.'}
    dump(args.out/'summary.json',summary)
    dump(args.out/'labels_public.json',all_public)
    dump(args.out/'quote_shortening_audit.json',repairs)
    dump(args.out/'acceptance.json',{'all_requests_revalidated':True,'sources_unchanged':True,
        'protected_unchanged':len(protected),'no_retries':True,'within_cap':True,
        'source_sha256':plan['source_sha256'],'requests_sha256':plan['request_file_sha256'],
        'state_sha256':sha(args.labels/'state.json'),'summary_sha256':sha(args.out/'summary.json'),
        'analysis_module_sha256':sha(Path(__file__))})
    print(json.dumps({k:summary[k] for k in ('unique_articles_labeled','unique_label_counts','total_paid_requests','quote_shortening_count','peak_uncached_cost_upper_usd','published_offpeak_cache_aware_cost_estimate_usd')},ensure_ascii=False))


if __name__=='__main__':main()
