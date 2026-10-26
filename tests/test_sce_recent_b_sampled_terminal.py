from copy import deepcopy
import json
from pathlib import Path

import pytest

from studies.sce_inflation_expectations.experiments import recent_b_sampled_terminal as mod
from studies.sce_inflation_expectations.experiments import full_a_personal_terminal as transport
from studies.sce_inflation_expectations.experiments import frozen_message_queue as queue
from studies.sce_inflation_expectations.experiments.frozen_batch import dump
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash


def reply(point=3., valid=True):
    return dict(raw_response_text=json.dumps(dict(point_pct=point,q9={f'bin{i}':10. if valid else 0. for i in range(1,11)})),
        returned_model='deepseek/deepseek-v3.2',returned_provider='SiliconFlow',finish_reason='stop',api_reported_cost_usd=.0001,
        error=None)


def initial():
    return dict(fields={'q8':dict(value=2.,source_period=202510,source_kind='synthetic_donor'),
                         'q9':dict(value=[10.]*10,source_period=202510,source_kind='synthetic_donor')},
                history_centers=[],comparison_reference_day='2025-10-31')


def setup(tmp_path,n=80):
    folder=tmp_path/'run';folder.mkdir();inp=tmp_path/'inputs';(inp/'202511').mkdir(parents=True)
    rows={};slots=[]
    for i in range(n):
        aid=str(i);messages=[dict(role='user',content=aid)];digest=message_hash(messages)
        rows[aid]=dict(messages=messages,prompt_sha256=digest)
        slots.append(dict(key=f'test|{i}',month='202511',agent_id=aid,arm='recent_b',repeat=1,prompt_sha256=digest,reserved_usd=.005))
    dump(inp/'202511/prompts.json',dict(month='202511',rows=rows))
    p=dict(model='deepseek/deepseek-v3.2',expected_provider='SiliconFlow',budget_cap_usd=2.,
        input_package_path=str(inp),technical_gate={'minimum_format_ratio':.95})
    policy=transport._policy();policy.update(initial_workers=2,max_workers=4,batch_slots=n,
        repair_initial_workers=2,repair_max_workers=4)
    return folder,slots,p,policy


def test_successful_original_field_survives_repair():
    before=initial();old=reply(point=7.,valid=False);fix=reply(point=99.)
    after=mod.merge_state(before,old,fix,['q9'],'202511')
    assert before==initial()
    assert after['fields']['q8']['value']==7.
    assert after['fields']['q9']['value']==[10.]*10
    assert all(after['transition']['field_updated_from_model'].values())


def test_unnormalized_probabilities_and_final_failure_fallback():
    main=reply();obj=json.loads(main['raw_response_text']);obj['q9']={f'bin{i}':2 for i in range(1,11)};main['raw_response_text']=json.dumps(obj)
    after=mod.merge_state(initial(),main,None,[],'202511')
    assert sum(after['fields']['q9']['value'])==100
    assert after['transition']['q9_proportional_normalization']
    failed={**main,'error':'APIConnectionError'}
    after=mod.merge_state(initial(),failed,failed,['q8','q9'],'202511')
    assert after['fields']==initial()['fields']
    assert not any(after['transition']['field_updated_from_model'].values())


def test_temporary_failure_is_repaired_once_and_repeat_invocation_sends_nothing(tmp_path):
    folder,slots,p,policy=setup(tmp_path);calls={}
    def send(messages):
        aid=messages[0]['content'];calls[aid]=calls.get(aid,0)+1
        if aid=='40' and calls[aid]==1:return {**reply(),'error':'APIConnectionError','error_http_status':None}
        return reply()
    result=transport.run_main_segments(p,slots,folder,send,policy,cool=lambda *_:None,engineering_only=True)
    mi,mr=queue.archive(folder/'main');assert result['status']=='completed' and len(mi)==80
    result,ri,rr,targets=transport.run_repair_segments(p,slots,folder,mi,mr,send,policy,cool=lambda *_:None,engineering_only=True)
    assert result['status']=='completed' and len(ri)==1 and calls['40']==2
    assert all(n==1 for aid,n in calls.items() if aid!='40')
    transport.run_main_segments(p,slots,folder,send,policy,cool=lambda *_:None,engineering_only=True)
    transport.run_repair_segments(p,slots,folder,mi,mr,send,policy,cool=lambda *_:None,engineering_only=True)
    assert sum(calls.values())==81


def test_429_cools_and_only_continues_never_sent_positions(tmp_path):
    folder,slots,p,policy=setup(tmp_path);seen=[];cool=[]
    def send(messages):
        aid=messages[0]['content'];seen.append(aid)
        return {**reply(),'error':'RateLimitError','error_http_status':429} if aid=='40' else reply()
    result=transport.run_main_segments(p,slots,folder,send,policy,cool=lambda seconds,*_:cool.append(seconds),engineering_only=True)
    assert result['status']=='completed' and len(seen)==len(set(seen))==80
    assert cool and cool[0]>=30


def test_provider_mismatch_stops_without_automatic_repair(tmp_path):
    folder,slots,p,policy=setup(tmp_path)
    result=transport.run_main_segments(p,slots,folder,lambda _:dict(reply(),returned_provider='Other'),policy,cool=lambda *_:None,engineering_only=True)
    assert result['status']!='completed'
    assert any(r['error']=='Locked model/provider mismatch' for r in queue.archive(folder/'main')[1])
    assert not (folder/'repair').exists()


def test_budget_guard_includes_inflight_reservations(tmp_path):
    folder,slots,p,policy=setup(tmp_path);p['budget_cap_usd']=.02
    result=transport.run_main_segments(p,slots,folder,lambda _:reply(),policy,cool=lambda *_:None,engineering_only=True)
    intents,replies=queue.archive(folder/'main')
    assert len(intents)<80 and result['status']!='completed'
    assert queue.account(intents,replies)['spent_or_reserved_usd']<=.02


def test_unknown_crash_intent_is_not_replayed(tmp_path):
    folder,slots,p,policy=setup(tmp_path,n=33);segment=folder/'main/round_0001/segment_0001';segment.mkdir(parents=True)
    intents=[];replies=[]
    for slot in slots:
        intents.append({k:slot[k] for k in ('key','prompt_sha256','reserved_usd')})
        if len(intents)<33:replies.append({**slot,**reply(),'actual_model_results':False})
    for name,rows in [('dispatch_private.jsonl',intents),('calls_private.jsonl',replies)]:
        (segment/name).write_text(''.join(json.dumps(r)+'\n' for r in rows))
    result=transport.run_main_segments(p,slots,folder,lambda _:pytest.fail('Unknown intent was replayed'),policy,cool=lambda *_:None,engineering_only=True)
    assert result['status']=='stopped_unresolved_unknown_intents' and result['unresolved']==1
