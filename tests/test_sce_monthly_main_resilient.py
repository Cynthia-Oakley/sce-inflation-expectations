from copy import deepcopy
import json
from pathlib import Path

import pytest

from studies.sce_inflation_expectations.experiments import monthly_main_resilient as robust
from test_sce_state_continuity_execution import fixture,reply


class InternalServerError(Exception):
    status_code=502


class UnauthorizedError(Exception):
    status_code=401


class APIConnectionError(Exception):
    pass


def example(n=12,workers=1):
    p,nodes,inputs=fixture()
    proto=next(r for r in nodes if r['arm']=='observed_history')
    nodes=[dict(proto,repeat=i+1,logical_reuse_key=f'key-{i}') for i in range(n)]
    p.update(months=['202505'],planned_calls=n,budget_mode='spent_plus_inflight_reservation',budget_cap_usd=40.)
    initial=inputs['202505','a'][1]
    old=[dict(reuse_key=nodes[0]['logical_reuse_key'],nodes=[nodes[0]],state_after=initial,
              error=None,api_reported_cost_usd=.0001,request_reservation_usd=.003)]
    policy=deepcopy(robust.POLICY)
    policy.update(initial_workers=workers,max_workers=workers,min_workers=1,cooldown_seconds=[1,2,3,4,5])
    return p,nodes,inputs,old,policy


def test_single_502_cools_then_finishes_without_retry(tmp_path):
    p,nodes,inputs,old,policy=example(5);calls=[];cooled=[]
    def send(messages):
        calls.append(messages)
        if len(calls)==1:raise InternalServerError('provider body must not be logged')
        return reply()
    result=robust.execute_segments(p,nodes,inputs,old,tmp_path/'calls',send,policy,
        cool=lambda delay,path,details:cooled.append(delay),engineering_only=True)
    rows=robust.base.lines(tmp_path/'calls/calls_private.jsonl')
    assert result['status']=='completed' and result['attempts']==4 and len(calls)==4
    assert result['recovery_cycles']==1 and cooled==[1]
    assert len({r['reuse_key'] for r in rows})==4
    assert old[0]['reuse_key'] not in {r['reuse_key'] for r in rows}
    assert result['automatic_retries']==0 and result['reported_cost_usd']==pytest.approx(.0004)
    assert result['spent_or_reserved_usd']>result['reported_cost_usd']
    assert 'provider body must not be logged' not in (tmp_path/'calls/calls_private.jsonl').read_text()


def test_persistent_connection_outage_has_bounded_recoveries(tmp_path):
    p,nodes,inputs,old,policy=example(40)
    policy['max_unhealthy_recoveries']=2;cooled=[];sent=[]
    def send(messages):sent.append(1);raise APIConnectionError()
    result=robust.execute_segments(p,nodes,inputs,old,tmp_path/'calls',send,policy,
        cool=lambda delay,path,details:cooled.append(delay),engineering_only=True)
    assert result['status']=='stopped_no_retry' and result['recovery_cycles']==2
    assert len(cooled)==2 and result['attempts']==9 and len(sent)==9
    assert 'bounded recovery' in result['halt_reason']
    rows=robust.base.lines(tmp_path/'calls/calls_private.jsonl')
    assert len({r['reuse_key'] for r in rows})==9


def test_recovery_reduces_concurrency(tmp_path):
    p,nodes,inputs,old,policy=example(40,workers=4)
    policy['max_unhealthy_recoveries']=2;limits=[]
    def send(messages):raise InternalServerError()
    robust.execute_segments(p,nodes,inputs,old,tmp_path/'calls',send,policy,
        cool=lambda delay,path,details:limits.append(details['workers']),engineering_only=True)
    assert limits==[2,1]


def test_authentication_error_still_stops_immediately(tmp_path):
    p,nodes,inputs,old,policy=example()
    def send(messages):raise UnauthorizedError()
    def no_cool(*a):pytest.fail('Authentication errors must not recover')
    result=robust.execute_segments(p,nodes,inputs,old,tmp_path/'calls',send,policy,cool=no_cool,engineering_only=True)
    assert result['attempts']==1 and result['recovery_cycles']==0
    assert result['halt_reason']=='UnauthorizedError' and result['status']=='stopped_no_retry'


def test_provider_mismatch_on_final_slot_is_not_reported_complete(tmp_path):
    p,nodes,inputs,old,policy=example(2)
    result=robust.execute_segments(p,nodes,inputs,old,tmp_path/'calls',lambda m:reply(provider='wrong'),policy,
        cool=lambda *a:pytest.fail('Must stop'),engineering_only=True)
    assert result['attempts']==1 and result['status']=='stopped_no_retry'
    assert result['halt_reason']=='Locked model/provider mismatch'


def test_budget_guard_is_never_recovered_or_reset(tmp_path):
    p,nodes,inputs,old,policy=example();p['budget_cap_usd']=.00011
    result=robust.execute_segments(p,nodes,inputs,old,tmp_path/'calls',lambda m:pytest.fail('No budget'),policy,
        cool=lambda *a:pytest.fail('Budget cannot recover'),engineering_only=True)
    assert result['attempts']==0 and result['recovery_cycles']==0
    assert result['spent_or_reserved_usd']==.0001 and 'budget' in result['halt_reason']


def test_retry_after_longer_than_total_cooling_cap_stops_safely(tmp_path):
    p,nodes,inputs,old,policy=example()
    def send(messages):
        exc=InternalServerError();exc.response=type('Response',(),{'headers':{'Retry-After':'9999'}})()
        raise exc
    result=robust.execute_segments(p,nodes,inputs,old,tmp_path/'calls',send,policy,
        cool=lambda *a:pytest.fail('Cannot wait beyond cap'),engineering_only=True)
    assert result['attempts']==1 and result['halt_reason']=='Total cooldown time cap reached'


def test_current_request_metadata_does_not_enter_flat_input_replay(tmp_path):
    p,nodes,inputs,old,policy=example(3);before=deepcopy(old)
    result=robust.execute_segments(p,nodes,inputs,old,tmp_path/'calls',lambda m:reply(),policy,
        cool=lambda *a:None,engineering_only=True)
    assert old==before and result['attempts']==2
    for line in (tmp_path/'calls/dispatch_private.jsonl').read_text().splitlines():
        assert json.loads(line)['reuse_key']!=old[0]['reuse_key']


def test_progress_aggregation_never_mutates_or_double_counts_old_months(tmp_path):
    old=tmp_path/'old';new=tmp_path/'new/segment_0001';old.mkdir();new.mkdir(parents=True)
    for folder in (old,new):
        (folder/'dispatch_private.jsonl').write_text(json.dumps(dict(reserved_usd=.003))+'\n')
        (folder/'calls_private.jsonl').write_text(json.dumps(dict(month='202505',error=None,
            technical_usable=True,api_reported_cost_usd=.0001,request_reservation_usd=.003))+'\n')
    observer=robust.Progress(old);trackers={}
    first=robust.poll_segments(observer,trackers,new.parent)
    second=robust.poll_segments(observer,trackers,new.parent)
    assert first['completed_by_month']=={'202505':2}
    assert second['completed_by_month']=={'202505':2}
    assert observer.months=={'202505':1} and second['completed']==2


def test_transient_classification_is_narrow():
    assert robust.recoverable(dict(error='InternalServerError',error_http_status=502),robust.POLICY)
    assert not robust.recoverable(dict(error='InternalServerError',error_http_status=501),robust.POLICY)
    assert not robust.recoverable(dict(error='AuthenticationError',error_http_status=401),robust.POLICY)
