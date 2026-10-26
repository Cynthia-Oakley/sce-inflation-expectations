from copy import deepcopy
import json
from threading import Lock

import pytest

from studies.sce_inflation_expectations.experiments import recent_b_night as night
from studies.sce_inflation_expectations.experiments import monthly_main_resilient as robust
from test_sce_monthly_main_resilient import example,APIConnectionError,InternalServerError,UnauthorizedError
from test_sce_state_continuity_execution import reply


def setup(n=40):
    p,nodes,inputs,_,policy=example(n,workers=1)
    p['budget_cap_usd']=1.
    return p,nodes,inputs,policy


def test_technical_gate_distinguishes_format_and_transport():
    rows=[{'error':None,'finish_reason':'stop','technical_usable':True} for _ in range(30)]
    rows += [{'error':'APIConnectionError','finish_reason':None,'technical_usable':False} for _ in range(2)]
    assert night.gate_result(rows)['passed']
    assert not night.gate_result([])['passed']
    assert not night.gate_result([{'error':None,'finish_reason':'stop','technical_usable':False} for _ in range(32)])['passed']


def test_main_connection_failure_then_one_automatic_exact_prompt_repair(tmp_path):
    p,nodes,inputs,policy=setup();sent=[];lock=Lock();cooled=[]
    def send(messages):
        with lock:
            i=len(sent);sent.append(deepcopy(messages))
        if i==0:raise InternalServerError()
        return reply()
    main,rows=night.execute_main(p,nodes,inputs,tmp_path/'main',send,policy,engineering_only=True,cool=lambda *a:cooled.append(a[0]))
    assert main['status']=='completed' and len(rows)==40 and len(sent)==40 and cooled
    failed=next(r for r in rows if r.get('error'))
    rr,replies,targets=night.execute_repair(p,nodes,inputs,rows,tmp_path/'repair',send,policy,main['receipt'],engineering_only=True,cool=lambda *a:None)
    assert rr['status']=='completed' and len(replies)==1 and len(sent)==41
    assert replies[0]['messages']==failed['messages'] and replies[0]['prompt_sha256']==failed['prompt_sha256']
    merged=night.merge_fields(rows,replies,targets)
    assert len(merged)==40 and all(r['technical_usable'] for r in merged)
    assert rows[rows.index(failed)]['error']=='InternalServerError'
    assert main['receipt']['spent_or_reserved_usd']+rr['spent_or_reserved_usd']<=p['budget_cap_usd']


def test_q9_only_repair_keeps_original_good_q8_and_normalizes_probabilities(tmp_path):
    p,nodes,inputs,policy=setup();sent=[];lock=Lock()
    def send(messages):
        with lock:i=len(sent);sent.append(1)
        r=reply(point=9.)
        if i==0:r['raw_response_text']=json.dumps({'point_pct':9.,'q9':{'bin1':100}})
        if i>=40:r['raw_response_text']=json.dumps({'point_pct':99.,'q9':{f'bin{k}':100 for k in range(1,11)}})
        return r
    main,rows=night.execute_main(p,nodes,inputs,tmp_path/'main',send,policy,engineering_only=True,cool=lambda *a:None)
    failed=next(r for r in rows if not r['technical_usable'])
    assert night.technical_fields(failed)==['q9']
    rr,replies,targets=night.execute_repair(p,nodes,inputs,rows,tmp_path/'repair',send,policy,main['receipt'],engineering_only=True,cool=lambda *a:None)
    merged=night.merge_fields(rows,replies,targets)
    repaired=next(r for r in merged if r['reuse_key']==failed['reuse_key'])
    assert repaired['state_after']['fields']['q8']['value']==9.
    assert repaired['state_after']['fields']['q9']['value']==[10.]*10
    assert repaired['manual_repair']['accepted_fields']==['q9']
    assert repaired['state_after']['transition']['q9_proportional_normalization']


def test_failed_repair_is_not_retried_or_disguised_as_success(tmp_path):
    p,nodes,inputs,policy=setup()
    main,rows=night.execute_main(p,nodes,inputs,tmp_path/'main',lambda m:reply(),policy,engineering_only=True,cool=lambda *a:None)
    broken=deepcopy(rows[0]);broken['error']='APIConnectionError'
    broken['state_after']=deepcopy(broken['state_before'])
    broken['state_after']['transition']={'field_updated_from_model':{'q8':False,'q9':False},'field_retained_as_explicit_fallback':{'q8':True,'q9':True},'q9_proportional_normalization':False}
    rows[0]=broken;counter=[]
    def fail(m):counter.append(1);raise APIConnectionError()
    rr,replies,targets=night.execute_repair(p,nodes,inputs,rows,tmp_path/'repair',fail,policy,main['receipt'],engineering_only=True,cool=lambda *a:None)
    assert len(counter)==len(replies)==1
    merged=night.merge_fields(rows,replies,targets)
    assert not next(r for r in merged if r['reuse_key']==broken['reuse_key'])['technical_usable']


def test_auth_error_stops_without_recovery_or_retry(tmp_path):
    p,nodes,inputs,policy=setup();called=[];cool=[]
    def fail(m):called.append(1);raise UnauthorizedError()
    main,rows=night.execute_main(p,nodes,inputs,tmp_path/'main',fail,policy,engineering_only=True,cool=lambda *a:cool.append(1))
    assert main['status']=='stopped_before_main' and len(called)<=8 and not cool
    with pytest.raises(ValueError,match='Hard failures'):night.technical_fields(rows[0])


def test_valid_output_density_fitting_failure_is_not_a_requery_criterion():
    r={'error':None,'finish_reason':'stop','state_after':{'transition':{'field_updated_from_model':{'q8':True,'q9':True}}},'scorer_status':'candidate_exception'}
    assert night.technical_fields(r)==[]


def test_no_budget_remains_no_repair_calls(tmp_path):
    p,nodes,inputs,policy=setup();called=[]
    r={'reuse_key':nodes[0]['logical_reuse_key'],'error':'APIConnectionError'}
    rr,replies,_=night.execute_repair(p,nodes,inputs,[r],tmp_path/'repair',lambda m:called.append(1),policy,{'spent_or_reserved_usd':p['budget_cap_usd']},engineering_only=True)
    assert not called and replies==[] and rr['status']=='skipped_budget'


def test_progress_is_incremental_and_does_not_count_composed_ledgers(tmp_path):
    stage=tmp_path/'main_stages/gate/segment_0001';stage.mkdir(parents=True)
    row={'month':'202511','request_reservation_usd':.001,'error':None,'technical_usable':True,'api_reported_cost_usd':.0001}
    (stage/'calls_private.jsonl').write_text(json.dumps(row)+'\n')
    (stage/'dispatch_private.jsonl').write_text(json.dumps({'reserved_usd':.001})+'\n')
    (stage.parent/'calls_private.jsonl').write_text(json.dumps(row)+'\n')
    trackers={};p={'planned_calls':5632}
    first=night.progress_snapshot(tmp_path,p,trackers);second=night.progress_snapshot(tmp_path,p,trackers)
    assert first['physical_completed']==second['physical_completed']==1
    assert first['in_flight']==0 and second['reported_cost_usd']==.0001


def test_overlay_refuses_changed_prompt_or_extra_repair_scope():
    with pytest.raises(ValueError,match='scope'):
        night.merge_fields([], [{'reuse_key':'other'}], {})


def test_run_without_explicit_confirmation_does_not_create_authorization_or_sender(tmp_path,monkeypatch):
    monkeypatch.setattr(night,'checked',lambda *a,**k:({}, {}, {}))
    monkeypatch.setattr(night,'live_sender',lambda *a:pytest.fail('No live sender before authorization'))
    with pytest.raises(ValueError,match='confirm-scope-and-budget'):
        night.run(tmp_path,confirm=False)
    assert not list(tmp_path.iterdir())
