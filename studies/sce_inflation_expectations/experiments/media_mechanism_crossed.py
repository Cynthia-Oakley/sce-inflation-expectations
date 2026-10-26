"""Offline draft for two missing cells of the media mechanism comparisons.

Do not mutate the frozen V3 registry or start a paid sender. Existing four arms
must reconstruct byte-for-byte before any candidate draft is accepted.
"""
from collections import Counter
import json
import math
from pathlib import Path

from .frozen_batch import ROOT, dump, read_json, sha, verify
from .media_mechanism_v3 import ARM_CONFIG, draw_personal, four_tier_levels
from .media_mechanism_v3_preparation import load_nyt_pool, load_supplemental_run, apply_label_overrides
from .media_mechanism_trial import ASSEMBLY, change_rendered_news, latest_cpi_release_day, select_salient_common
from . import frozen_message_queue as queue
from ..news_exposure import interests_for_profile
from ..prior_belief_experiment import message_hash

CONFIG={
    'X_CA':dict(four_tiers=True,alarming_boost=2.,cpi_boost=1.5,fox_share=0.),
    'X_3C':dict(four_tiers=False,alarming_boost=1.,cpi_boost=1.5,fox_share=0.),
}


def build_arm(month,ids,pool,base,common,config):
    as_of=base['environment']['provider_args']['targets'][0]['as_of']
    common_ids={r['article_id'] for r in common}
    personal_pool=[r for r in pool if r['article_id'] not in common_ids]
    profiles={p['agent_id']:p['attributes'] for p in base['population']['personas']}
    tiers=four_tier_levels(ids,month)
    rows,contexts={},{}
    for aid in ids:
        count=tiers[aid] if config['four_tiers'] else base['news_quantity_frame_private'][aid]
        interests=interests_for_profile(profiles[aid],base['baskets_private'][aid]['spending_shares'])
        news=draw_personal(personal_pool,[],count-3,f'20261025|{month}|{aid}',interests,
            alarming_boost=config['alarming_boost'],cpi_boost=config['cpi_boost'],fox_share=0.)
        messages=change_rendered_news(base['initial_previews_private'][aid]['messages'],
            base['timing_context_private'][aid]['common_news'],base['timing_context_private'][aid]['personal_news'],
            common,news,base['initial_states_private'][aid]['comparison_reference_day'],as_of)
        rows[aid]={'messages':messages,'prompt_sha256':message_hash(messages)}
        contexts[aid]={'news_count':count,'article_ids':[r['article_id'] for r in news],
            'alarming_articles':sum(r['semantic_label']['tone']=='alarming' for r in news),
            **config}
    return rows,contexts


def prepare(parent,completed_run,out):
    parent,completed_run,out=Path(parent).resolve(),Path(completed_run).resolve(),Path(out).resolve()
    if out.exists() or not out.is_relative_to(ROOT/'outputs'):
        raise ValueError('Fresh draft directory required')
    manifest,p=verify(parent)
    if p['mechanism']!='v32_news_mechanism_v3':raise ValueError('Frozen V3 parent required')
    labels_dir=ROOT/'outputs/sce_news_mechanism_labels_20261025_v1'
    review_file=ROOT/'outputs/sce_news_mechanism_label_audit_20261025_v1/review.json'
    labels=apply_label_overrides(load_supplemental_run(labels_dir),read_json(review_file)['overrides'])
    _,old_replies=queue.archive(completed_run)
    successes,failures={},set()
    for row in old_replies:
        k=(row['month'],row['agent_id'],row['repeat'],row['prompt_sha256'])
        if row['technical_usable']:successes.setdefault(k,row['key'])
        else:failures.add(k)
    out.mkdir(parents=True)
    reconstructed=0;positions=[];unique={};reused=held=0;new_maxbytes=0;guesses=bound=0.
    for month in p['months']:
        ids=sorted(read_json(parent/str(month)/'prompts_Q0.json')['rows'])
        names=('initial_previews_private','timing_context_private','initial_states_private',
               'news_quantity_frame_private','baskets_private','population','environment')
        base={name:read_json(ROOT/ASSEMBLY/str(month)/(name+'.json')) for name in names}
        pool=load_nyt_pool(ROOT,month,labels)
        common=select_salient_common(pool,latest_cpi_release_day(ROOT,month))
        # Same source pools, reviewed tags, random stream and non-news blocks.
        for arm in ('R0','Q0','Q1','Q3'):
            expected=read_json(parent/str(month)/f'prompts_{arm}.json')['rows']
            rows,_=build_arm(month,ids,pool,base,common,ARM_CONFIG[arm])
            if rows!=expected:raise ValueError('Existing frozen arm did not reconstruct: '+str((month,arm)))
            reconstructed+=len(rows)
        dest=out/str(month);dest.mkdir()
        for arm,config in CONFIG.items():
            rows,contexts=build_arm(month,ids,pool,base,common,config)
            dump(dest/f'prompts_{arm}.json',{'month':month,'arm':arm,'rows':rows})
            dump(dest/f'contexts_{arm}_private.json',contexts)
            for aid,row in rows.items():
                size=len(json.dumps(row['messages'],ensure_ascii=False).encode())
                for repeat in (1,2):
                    k=(month,aid,repeat,row['prompt_sha256'])
                    record={'month':month,'arm':arm,'agent_id':aid,'repeat':repeat,'prompt_sha256':row['prompt_sha256']}
                    if k in successes:
                        record.update(status='reuse_exact_success',source_key=successes[k]);reused+=1
                    elif k in failures:
                        record['status']='hold_old_attempted_failure_do_not_automatically_resend';held+=1
                    else:
                        reuse_key='|'.join(map(str,k))
                        record.update(status='new_request' if k not in unique else 'reuse_same_new_prompt',new_request_key=reuse_key)
                        if k not in unique:
                            unique[k]=record
                            guesses+=(size/4*.259+300*.8)/1e6
                            bound+=((size+1024)*.259+1024*.8)/1e6
                            new_maxbytes=max(new_maxbytes,size)
                    positions.append(record)
    summary={'status':'offline_input_draft_not_execution_ready','new_api_calls':0,'target_answers_read':False,
        'parent':str(parent.relative_to(ROOT)),'completed_run':str(completed_run.relative_to(ROOT)),
        'months':p['months'],'n_per_month':96,'repeats':[1,2],
        'new_arms':CONFIG,'logical_new_arm_positions':2688,
        'reconstructed_original_prompt_rows':reconstructed,
        'existing_control_arms':['R0','Q0','Q1','Q3'],'existing_control_attempts':5376,
        'exact_success_positions_reused':reused,'held_old_failure_positions':held,
        'unique_new_requests_if_approved':len(unique),'maximum_prompt_utf8_bytes':new_maxbytes,
        'estimated_new_cost_usd':guesses,'conservative_new_reservation_usd':bound,
        'suggested_budget_cap_usd':max(1,math.ceil(bound)),
        'factorial_alarm':{'quantity':'four_tiers','cells':[['Q0','Q1'],['Q3','X_CA']],
            'loss_interaction':'L(X_CA)-L(Q3)-L(Q1)+L(Q0)'},
        'factorial_quantity':{'alarm_boost':1.,'cells':[['R0','X_3C'],['Q0','Q3']],
            'loss_interaction':'[L(Q3)-L(Q0)]-[L(X_3C)-L(R0)]'},
        'pre_run_gaps':['Official Core offline checks for new messages; versioned live execution/evaluation adapter with exact response reuse.',
                        'Freeze cumulative budget, receiver/scope authorization and tolerance policy before any send.'],
        'limits':['Two linked 2x2 designs, not a complete 2x2x2 design; three-way interaction unidentified.',
                  'These seven inspected months are exploratory; no independent validation claim.',
                  'Joint boost multiplies unnormalized weighted-half scores by 3 for qualifying articles, not exposure probability by 3.',
                  'Old transport/output failures are held, not silently resent.']}
    dump(out/'positions_private.json',positions);dump(out/'summary.json',summary)
    dump(out/'manifest.json',{'parent_manifest_sha256':sha(parent/'manifest.json'),
        'parent_protocol_sha256':sha(parent/'protocol.json'),'source_sha256':{str(Path(__file__).relative_to(ROOT)):sha(__file__)},
        'new_api_calls':0,'files_sha256':{str(f.relative_to(out)):sha(f) for f in out.rglob('*.json')}})
    return summary
