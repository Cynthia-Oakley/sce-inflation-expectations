"""Offline inventory and preliminary budget; never starts labeling/simulation.

Candidate dates are selected for time coverage, not saved LLM performance.
No current outcome is used for respondent eligibility or any message.
"""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re

import pandas as pd

from .behavior_comparison import dump, sha
from ..coverage_preparation import build_news_pool, previous_month
from ..news_selection_trial import RecallRules, RULE_FILE

TARGETS = ('2021-05','2021-11','2022-03','2022-09','2023-03','2023-09','2024-03','2025-03')
OLD_U1 = {'2022-03','2022-09','2023-03','2024-03'}
PRICE_IN, PRICE_OUT = .30, 1.20


def scaled_budget(old_trial, planned_calls):
    actual=sum(job['estimated_cost_usd'] for job in old_trial['jobs'])
    ratio=planned_calls/old_trial['planned_answers']
    return dict(planned_calls=planned_calls, historical_cost_estimate_scaled_usd=actual*ratio,
                historical_byte_reservation_scaled_usd=old_trial['conservative_simulation_cost_bound_usd']*ratio,
                empirical_old_calls=old_trial['planned_answers'], empirical_old_cost_estimate_usd=actual,
                pricing_note='Peak cache-miss rates; estimate, not invoice or frozen new-prompt quote.')


def run(root: Path,out: Path, candidate_months=TARGETS):
    if len(candidate_months)!=8 or len(set(candidate_months))!=8:
        raise ValueError('Eight distinct candidate months required')
    if out.exists(): raise FileExistsError('Use a fresh ignored output directory')
    out.mkdir(parents=True)
    sources={}
    def read(path):
        p=root/path;sources[path]=sha(p);return json.loads(p.read_text())
    env=read('outputs/sce_e_extension_2020_2025_verified_20261007/environment_candidate.json')
    targets={t['target_month']:(i,t) for i,t in enumerate(env['provider_args']['targets'])}
    refpath='outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
    ref_receipt=read('outputs/sce_prior_preparation_20261013_v4/summary.json')
    sources[refpath]=sha(root/refpath)
    if sources[refpath]!=ref_receipt['output_file_sha256']['labeled_reference_private.parquet']:
        raise ValueError('Profile/history cache changed')
    f=pd.read_parquet(root/refpath)
    labels_receipt=read('outputs/sce_multiperiod_news_label_analysis_20261011_v1/summary.json')
    known=set()
    for path,h in labels_receipt['source_sha256'].items():
        if not path.endswith('labels.jsonl'):continue
        sources[path]=sha(root/path)
        if sources[path]!=h:raise ValueError('Prior label receipt changed')
        for line in (root/path).read_text().splitlines():known.add(json.loads(line)['label']['article_id'])
    rule_path=str(RULE_FILE.relative_to(root));rules=RecallRules(read(rule_path))
    windows=[];pending={}
    for target in candidate_months:
        i,t=targets[target];cutoff=datetime.fromisoformat(t['as_of'])
        month=int(target.replace('-',''));prev=int(previous_month(target).replace('-',''))
        current=f[f.date==month]
        earlier=f[f.date==prev][['userid','raw_prior_valid','timeline_consistent','tenure_valid','survey_date']]
        pair=current[['userid','panel_status']].merge(earlier,on='userid',how='inner',validate='one_to_one')
        eligible=(pair.panel_status.eq('adjacent_returner') & pair.raw_prior_valid & pair.timeline_consistent & pair.tenure_valid
                  & pair.survey_date.notna() & (pair.survey_date.dt.date<cutoff.date()))
        records,counts,news_sources=build_news_pool(root,target,t['as_of'],rules)
        sources.update(news_sources)
        candidates=[r for r in records if r['new_hits']]
        for r in candidates:
            if r['article_id'] not in known:
                public={k:r[k] for k in ('article_id','headline','abstract','snippet','source','section_name','news_desk')}
                if r['article_id'] in pending and pending[r['article_id']]!=public:
                    raise ValueError('Conflicting source text')
                pending[r['article_id']]=public
        signals=env['provider_args']['signals_by_step'][str(i)]
        future=unknown=0
        for signal in signals:
            stamp=signal.get('published_at')
            try:
                published=datetime.fromisoformat(stamp.replace('Z','+00:00'))
                if published.tzinfo is None:raise ValueError('No timezone')
                future+=published>cutoff
            except (ValueError,TypeError,AttributeError):unknown+=1
        windows.append(dict(target_month=target,as_of=t['as_of'],full_wave_n=len(current),
            adjacent_raw_prior_eligible_n=int(eligible.sum()),entry_n=int(current.panel_status.eq('entry_tenure_1').sum()),
            core_history_cache_available=True,full_new_population_materialized=False,
            signal_records=len(signals),future_signal_records=int(future),undated_signal_records=unknown,
            archive_docs_in_window=counts.get('docs_in_window',0),coarse_news_candidates=len(candidates),
            known_label_records=sum(r['article_id'] in known for r in candidates),
            pending_label_memberships=sum(r['article_id'] not in known for r in candidates),
            already_used_for_U1=target in OLD_U1,
            note='Inventory only; historical text/gasoline vintages and new confidence/policy assignments still require assembly checks.'))
    prompt_path='docs/literature/sce/news_selection/llm_label_prompt_v1_2.md'
    prompt_source=(root/prompt_path).read_text();sources[prompt_path]=sha(root/prompt_path)
    prompt=re.search(r'```text\n(.*?)\n```',prompt_source,re.S).group(1)
    articles=[pending[k] for k in sorted(pending)]
    requests=[]
    for offset in range(0,len(articles),8):
        part=articles[offset:offset+8]
        messages=[dict(role='system',content=prompt),dict(role='user',content=json.dumps({'articles':part},ensure_ascii=False))]
        reserve=len(json.dumps(messages,ensure_ascii=False).encode())+512
        requests.append(dict(batch_id=len(requests)+1,article_ids=[r['article_id'] for r in part],
            payload=dict(model='deepseek-flash',temperature=0,max_tokens=2400,response_format={'type':'json_object'},
                         thinking={'type':'disabled'},messages=messages),
            input_token_reservation=reserve,request_usd_reservation=(reserve*PRICE_IN+2400*PRICE_OUT)/1e6))
    (out/'pending_public_articles.json').write_text(json.dumps(articles,ensure_ascii=False,indent=2)+'\n')
    (out/'news_label_requests_draft.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in requests))
    old=read('outputs/sce_u1_trial_20261014_v2/trial_manifest.json')
    costs=scaled_budget(old,8*96*2*2)
    result=dict(status='candidate_inventory_only_not_execution_package',candidate_months=list(candidate_months),
        n_per_month=96,arms=2,generation_repeats=2,simulation_budget=costs,
        draft_model=dict(endpoint='https://api.deepseek.com',requested_alias='deepseek-flash',
            published_version='DeepSeek-V4.1-Flash',temperature=.5,thinking='disabled',max_tokens=1024,
            retries=0,pricing_verified_date='2026-10-14',pricing_source='https://api-docs.deepseek.com/quick_start/pricing/',
            peak_input_cache_miss_per_million=PRICE_IN,peak_output_per_million=PRICE_OUT),
        windows=windows,unique_pending_articles=len(articles),news_label_batches=len(requests),
        news_label_reservation_usd=sum(r['request_usd_reservation'] for r in requests),
        source_sha256=sources,new_api_calls=0,new_cost_usd=0,
        remaining=['Choose and register the specific update rule and development/evaluation split.',
                   'Materialize all eight 96-person populations from profile-only selection and evaluate representativeness.',
                   'Finish new-date CE/confidence/policy and accepted news libraries; do not silently reuse wrong-month inputs.',
                   'Generate actual prompts, perform dry runs, recalculate job and total caps, obtain scoped new-call authorization.'],
        limits=['SCE counts are history-cache inventory, not final frozen-score eligibility or selected populations.',
                'Four extra dates have not been used for U1 but are not a wholly blind project test.',
                'Same total method information need not mean identical LLM-visible information; describe architecture contrast.',
                'Model alias does not pin immutable weights or a training cutoff.',
                'This remains A returner-conditional diagnostic; no B prediction or nationwide headline claim.'])
    dump(out/'summary.json',result)
    dump(out/'manifest.json',dict(files_sha256={p.name:sha(p) for p in out.iterdir() if p.is_file()},
        implementation_sha256=sha(Path(__file__)),new_api_calls=0))
    return result
