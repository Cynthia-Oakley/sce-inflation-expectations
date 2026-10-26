"""Past-only cohort/news preparation and isolated truth for new 2025 months.

No API client. New full-period entrants/recursive synthetic cohorts are separate.
"""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd

from .frozen_batch import ROOT, dump, read_json, sha

MONTHS = (202504, 202506, 202508, 202510)
N = 192
SEED = 20261021
FRAME = ROOT/'outputs/sce_prior_preparation_20261013_v4/labeled_reference_private.parquet'
COVERAGE = ROOT/'outputs/sce_fullperiod_data_20261021_v1/coverage.json'


def fresh(out):
    out=Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):raise ValueError('Fresh ignored output required')
    return out


def cutoffs():
    return {int(r['target_month'].replace('-','')):r['as_of'] for r in read_json(COVERAGE)['months']}


def prepare_news(out):
    from ..coverage_preparation import build_news_pool
    from ..news_selection_trial import RULE_FILE, RecallRules
    from ..news_pool_preparation import FIELDS, partition_requests
    from ..news_extension_label_preparation import freeze_requests
    out=fresh(out)
    known=set();sources={str(COVERAGE.relative_to(ROOT)):sha(COVERAGE),
        str(RULE_FILE.relative_to(ROOT)):sha(RULE_FILE),str(Path(__file__).relative_to(ROOT)):sha(__file__)}
    labels=sorted((ROOT/'outputs').rglob('labels.jsonl'))
    for path in labels:
        sources[str(path.relative_to(ROOT))]=sha(path)
        for line in path.read_text().splitlines():
            if line.strip():
                row=json.loads(line);known.add(row.get('label',row)['article_id'])
    rules=RecallRules(read_json(RULE_FILE));pending={};inventory=[];co=cutoffs()
    out.mkdir(parents=True)
    for month in MONTHS:
        target=f'{month//100}-{month%100:02}'
        rows,counts,hashes=build_news_pool(ROOT,target,co[month],rules);sources.update(hashes)
        chosen=[r for r in rows if r['new_hits']]
        missing=[r for r in chosen if r['article_id'] not in known]
        for row in missing:
            public={k:row[k] for k in FIELDS}
            if row['article_id'] in pending and pending[row['article_id']]!=public:
                raise ValueError('Conflicting cross-window article')
            pending[row['article_id']]=public
        inventory.append(dict(target_month=target,as_of=co[month],coarse_candidates=len(chosen),
                              new_labels_needed=len(missing),reused_labels=len(chosen)-len(missing)))
    prompt=ROOT/'docs/literature/sce/news_selection/llm_label_prompt_v1_2.md'
    system=re.search(r'```text\n(.*?)\n```',prompt.read_text(),re.S).group(1)
    sources[str(prompt.relative_to(ROOT))]=sha(prompt)
    articles=[pending[k] for k in sorted(pending)];drafts=[]
    for i in range(0,len(articles),8):
        subset=articles[i:i+8]
        messages=[dict(role='system',content=system),dict(role='user',content=json.dumps({'articles':subset},ensure_ascii=False))]
        payload=dict(model='deepseek-flash',temperature=0,max_tokens=2400,
            response_format={'type':'json_object'},thinking={'type':'disabled'},messages=messages)
        drafts.append(dict(batch_id=len(drafts)+1,article_ids=[r['article_id'] for r in subset],
                           payload=payload,input_byte_reservation=len(json.dumps(messages,ensure_ascii=False).encode())+512))
    dump(out/'pending_public_articles.json',articles)
    (out/'news_requests_draft.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in drafts))
    # Preserve today's unrelated user/Kimi edits. The 10-10 wrapper rejects them
    # against its historical snapshot; do not change that wrapper or old manifest.
    protected=ROOT/'docs/sources/sol_handoff_protected_files_20261010.json'
    current_protected={name:sha(ROOT/name) for name in read_json(protected)['files_sha256']}
    sources.update(current_protected)
    for name in ('news_extension_label_preparation.py','news_pool_preparation.py','news_selection_trial.py','news_label_trial.py'):
        path=ROOT/'studies/sce_inflation_expectations'/name;sources[str(path.relative_to(ROOT))]=sha(path)
    requests,prompt_sha=freeze_requests(drafts,articles)
    frozen=out/'frozen_requests';frozen.mkdir();parts=[]
    for i,subset in enumerate(partition_requests(requests,.25),1):
        folder=frozen/f'part_{i:02d}';folder.mkdir()
        rows=[dict(r,batch_id=j+1) for j,r in enumerate(subset)]
        path=folder/'requests_prepared.jsonl'
        path.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
        reservation=sum(r['request_usd_reservation'] for r in rows)
        part=dict(status='offline_prepared_new_budget_required',unique_articles_to_label=sum(len(r['article_ids']) for r in rows),
            batches=len(rows),request_file_sha256=sha(path),source_sha256=sources,system_prompt_sha256=prompt_sha,
            preparation_module_sha256=sha(ROOT/'studies/sce_inflation_expectations/news_selection_trial.py'),
            proposed_budget_usd=.25,total_usd_reservation_no_retries=reservation,retry_policy='none',
            protected_snapshot_note='Current preparation-time contents pinned; historical 10-10 registry unchanged',
            new_project_api_calls=0)
        dump(folder/'summary.json',part)
        parts.append(dict(part=i,folder=str(folder.relative_to(ROOT)),articles=part['unique_articles_to_label'],
            batches=len(rows),reservation_usd=reservation,package_cap_usd=.25))
    result=dict(status='prepared_not_authorized_not_run',unique_new_articles=len(articles),new_batches=len(requests),
        total_reservation_usd=sum(r['request_usd_reservation'] for r in requests),proposed_total_cap_usd=len(parts)*.25,
        parts=parts,target_months=list(MONTHS),destination='https://api.deepseek.com/v1/chat/completions',
        requested_model='deepseek-flash',temperature=0,max_output_tokens=2400,retry_policy='none',new_api_calls=0)
    dump(frozen/'summary.json',result)
    dump(out/'summary.json',dict(status='offline_news_gap_deduplicated_against_all_caches',months=inventory,
        unique_pending_articles=len(articles),label_files_reused=len(labels),known_unique_labels=len(known),
        source_sha256=sources,new_api_calls=0,pricing_verified_on='2026-10-21',
        pricing_url='https://api-docs.deepseek.com/quick_start/pricing/'))
    return result


def prepare_population(out):
    from socioverse.schemas import PopulationBundle
    from ..expanded_state_inputs import profiles
    from ..monthly_population import build_monthly_population
    from ..reference_population_preparation import sample_strata, anonymous_id, stratum
    from ..prior_belief_preparation import eligible_previous,month_offset,prior_record
    from ..belief_state_preparation import compute_person_state
    from ..evaluation.behavior_comparison import score
    out=fresh(out)
    metadata=pd.read_parquet(FRAME,columns=['date','userid','panel_status','tenure_valid',
        'timeline_consistent','raw_prior_valid','survey_date'])
    prof,hashes=profiles();sources={str(FRAME.relative_to(ROOT)):sha(FRAME),
        str(COVERAGE.relative_to(ROOT)):sha(COVERAGE),**hashes,
        str(Path(__file__).relative_to(ROOT)):sha(__file__)}
    co=cutoffs();bins=[f'Q9_bin{i}' for i in range(1,11)]
    out.mkdir(parents=True);links=[];inventory=[]
    for month in MONTHS:
        dest=out/str(month);dest.mkdir()
        current=metadata[metadata.date.eq(month)]
        previous=metadata[metadata.date.eq(month_offset(month,-1))].set_index('userid',drop=False)
        candidates=[int(r['userid']) for r in current.to_dict('records') if r['userid'] in previous.index
                    and eligible_previous(r,previous.loc[r['userid']],month,datetime.fromisoformat(co[month]).date())]
        prior=pd.read_parquet(FRAME,columns=['date','userid',*bins],filters=[('date','==',month_offset(month,-1)),
            ('userid','in',candidates)]).set_index('userid')
        eligible=[uid for uid in candidates if score(tuple(float(prior.loc[uid,b]) for b in bins))['status']=='ok']
        weights=prof[prof.date.eq(month)].set_index('userid')['weight'].to_dict()
        eligible=[uid for uid in eligible if uid in weights and pd.notna(weights[uid])
                  and math.isfinite(float(weights[uid])) and float(weights[uid])>0]
        population,_=build_monthly_population(prof[prof.userid.isin(eligible)],month,n=None,seed=SEED)
        ids,pi,design=sample_strata(population['personas'],month,n=N,seed=SEED)
        picked=[p for p in population['personas'] if p['agent_id'] in ids]
        # A second, outcome-blind stratified stage gives a 96-person nested check.
        ids96,pi96,_=sample_strata(picked,month,n=96,seed=SEED+1)
        uids=[int(p['agent_id'].removeprefix('sce_u')) for p in picked]
        history=pd.read_parquet(FRAME,columns=['date','userid','Q8v2part2',*bins],
            filters=[('date','<',month),('userid','in',uids)])
        if history.date.ge(month).any():raise ValueError('Current answers cannot enter history')
        previous_rows=history[history.date.eq(month_offset(month,-1))].set_index('userid')
        past={};newpeople=[];nested=[]
        for person in picked:
            old=person['agent_id'];uid=int(old.removeprefix('sce_u'));aid=anonymous_id(uid)
            state=compute_person_state(history[history.userid.eq(uid)],uid,month)
            if state is None:raise ValueError('Frozen selection prior no longer scorable; do not resample')
            past[aid]={'prior':prior_record(previous_rows.loc[uid]),'state':state}
            link=dict(month=month,agent_id=aid,userid=uid,profile=person['attributes'],
                stratum=stratum(person['attributes']),survey_weight=float(weights[uid]),
                inclusion_probability=pi[old],design_survey_weight=float(weights[uid])/pi[old])
            links.append(link)
            if old in ids96:nested.append(dict(agent_id=aid,inclusion_probability=pi[old]*pi96[old],
                design_survey_weight=float(weights[uid])/(pi[old]*pi96[old])))
            person.update(agent_id=aid,weight=1.,group_key=None,init_state={});newpeople.append(person)
        population.update(personas=newpeople,materialized_count=N);PopulationBundle.model_validate(population)
        dump(dest/'population.json',population);dump(dest/'past_private.json',past)
        dump(dest/'sampling_private.json',design);dump(dest/'nested96_private.json',nested)
        dump(dest/'eligible_ids_private.json',eligible)
        w=np.array([r['design_survey_weight'] for r in links if r['month']==month])
        inventory.append(dict(month=month,as_of=co[month],n=N,eligible_n=len(eligible),
            weight_ess=float(w.sum()**2/(w@w)),nested_n=96,current_targets_used=False))
        print(f'Population {month}: {N} selected from {len(eligible)}; no current answers read',flush=True)
    dump(out/'evaluation_links_private.json',links);dump(out/'coverage.json',inventory)
    result=dict(status='population_and_past_only_not_live_trial',months=list(MONTHS),n_per_month=N,
        source_sha256=sources,prepared_file_sha256={str(p.relative_to(out)):sha(p) for p in out.rglob('*.json')},
        new_api_calls=0,current_target_answers_read=False,sampling_seed=SEED,
        mechanisms_unchanged=True,remaining=['Current-month truth is separate','Food/news prompts not assembled',
            'Budget authorization and engine dry-runs required before calls'])
    dump(out/'manifest.json',result)
    return result
