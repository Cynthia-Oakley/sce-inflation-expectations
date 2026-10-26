from copy import deepcopy
import json
from pathlib import Path

import pytest

from studies.sce_inflation_expectations.experiments import monthly_main_continuation as resume
from studies.sce_inflation_expectations.experiments.state_continuity_execution import execute, node_key
from test_sce_state_continuity_execution import fixture, reply


def audit_fixture():
    nodes=[dict(month='202501',agent_id=str(i),repeat=1,arm='monthly_reconstruction',
                dependency=None,logical_reuse_key=str(i)) for i in range(5)]
    rows=[dict(reuse_key=str(i),nodes=[nodes[i]],prompt_sha256='p'+str(i),
               error='APIConnectionError' if i==1 else None) for i in range(2)]
    intents=[dict(reuse_key=r['reuse_key'],prompt_sha256=r['prompt_sha256']) for r in rows]
    return nodes,rows,intents,[n for r in rows for n in r['nodes']]


def test_never_resubmit_old_success_or_failure():
    args=audit_fixture();before=deepcopy(args)
    assert resume.audit_attempts(*args)==['2','3','4']
    assert args==before


def test_unresolved_dispatch_is_not_never_attempted():
    nodes,rows,intents,positions=audit_fixture()
    intents.append(dict(reuse_key='2',prompt_sha256='p2'))
    with pytest.raises(ValueError,match='Unresolved'):
        resume.audit_attempts(nodes,rows,intents,positions)


def test_duplicate_or_mismatched_position_is_rejected():
    nodes,rows,intents,positions=audit_fixture()
    with pytest.raises(ValueError,match='Position ledger'):
        resume.audit_attempts(nodes,rows,intents,positions+[positions[0]])
    rows[0]['nodes'][0]=dict(rows[0]['nodes'][0],agent_id='wrong')
    with pytest.raises(ValueError):resume.audit_attempts(nodes,rows,intents,positions)


def test_prompt_hash_drift_is_rejected():
    nodes,rows,intents,positions=audit_fixture();intents[0]['prompt_sha256']='changed'
    with pytest.raises(ValueError,match='prompt'):
        resume.audit_attempts(nodes,rows,intents,positions)


def test_existing_queue_continues_without_sending_previous_slots(tmp_path):
    p,nodes,inputs=fixture()
    # Independent months, two unique slots per month; keep old successes AND errors.
    nodes=[n for n in nodes if n['arm']=='observed_history']
    p.update(planned_calls=4,budget_mode='spent_plus_inflight_reservation')
    originals=[]
    for n in nodes[:2]:
        state=inputs[n['month'],n['agent_id']][1]
        originals.append(dict(reuse_key=n['logical_reuse_key'],nodes=[n],state_after=state,
              api_reported_cost_usd=.0001 if len(originals)==0 else None,
              request_reservation_usd=.001,error=None if len(originals)==0 else 'APIConnectionError'))
    seen=[]
    result=execute(p,nodes,inputs,tmp_path/'new',lambda messages:(seen.append(messages) or reply()),
                   completed_calls=originals,engineering_only=True)
    assert result['status']=='completed' and result['attempts']==2 and len(seen)==2
    assert result['existing_attempts_retained']==2
    assert result['spent_or_reserved_usd']==pytest.approx(.0013)
    emitted=resume.lines(tmp_path/'new/calls_private.jsonl')
    assert not {r['reuse_key'] for r in emitted}&{r['reuse_key'] for r in originals}


def test_merge_preserves_bytes_and_counts_charges_once(tmp_path,monkeypatch):
    monkeypatch.setattr(resume,'ROOT',tmp_path)
    paths={k:str(tmp_path/k) for k in ('previous_calls','calls','combined','package')}
    for k in ('previous_calls','calls','package'):Path(paths[k]).mkdir()
    old,new=Path(paths['previous_calls']),Path(paths['calls'])
    for name in resume.LEDGERS:
        (old/name).write_bytes(b'{"old":true}\n');(new/name).write_bytes(b'{"new":true}\n')
    resume.dump(old/'receipt.json',dict(attempts=2,completed_calls=2,seconds=3,peak_in_flight=2))
    resume.dump(old/'technical_gate.json',dict(passed=True))
    resume.dump(Path(paths['package'])/'resume.json',{})
    receipt=dict(attempts=3,completed_calls=3,seconds=4,peak_in_flight=1,status='completed',
                 reported_cost_usd=.4,spent_or_reserved_usd=.5)
    result=resume.merge(paths,receipt,'original-protocol')
    assert result['attempts']==5 and result['seconds']==7 and result['peak_in_flight']==2
    assert result['reported_cost_usd']==.4 and result['spent_or_reserved_usd']==.5
    assert result['protocol_sha256']=='original-protocol'
    for name in resume.LEDGERS:
        assert (Path(paths['combined'])/name).read_bytes()==(old/name).read_bytes()+(new/name).read_bytes()
        assert (old/name).read_bytes()==b'{"old":true}\n'
    with pytest.raises(FileExistsError):resume.merge(paths,receipt,'original-protocol')


def test_combined_progress_counts_old_failures_without_inflight(tmp_path):
    old,new=tmp_path/'old',tmp_path/'new';old.mkdir();new.mkdir()
    def row(error,cost):return dict(month='202501',request_reservation_usd=.02,
                        error=error,technical_usable=not error,api_reported_cost_usd=cost)
    for folder,value in [(old,row('APIConnectionError',None)),(new,row(None,.001))]:
        (folder/'dispatch_private.jsonl').write_text(json.dumps(dict(reserved_usd=.02))+'\n')
        (folder/'calls_private.jsonl').write_text(json.dumps(value)+'\n')
    result=resume.combined_progress(resume.Progress(old),resume.Progress(new))
    assert result['completed']==2 and result['previous_attempts']==1 and result['new_attempts']==1
    assert result['errors']==1 and result['dispatched_without_local_result']==0
    assert result['api_reported_cost_usd']==.001 and result['unknown_fee_reservation_usd']==.02


def test_launch_job_is_one_shot_not_a_login_or_retry_job(tmp_path,monkeypatch):
    folder=tmp_path/'supervisor';folder.mkdir();package=tmp_path/'package';package.mkdir()
    config=dict(python='python',paths=dict(package=str(package)),budget_cap_usd=40)
    monkeypatch.setattr(resume,'checked',lambda folder:(config,{},{}))
    monkeypatch.setenv('OPENROUTER_API_KEY','unit-test-only')
    monkeypatch.setattr(resume.sys,'platform','darwin')
    invoked=[]
    def fake_run(command,**kwargs):
        invoked.append(command)
        return type('Result',(),dict(returncode=0))()
    monkeypatch.setattr(resume.subprocess,'run',fake_run)
    assert resume.start(folder)['status']=='launched_check_progress'
    import plistlib
    job=plistlib.loads((folder/'one_shot_launchd.plist').read_bytes())
    assert job['KeepAlive'] is False and job['RunAtLoad'] is True
    assert 'StartInterval' not in job and 'StartCalendarInterval' not in job
    assert 'unit-test-only' not in str(job)
    with pytest.raises(FileExistsError):resume.start(folder)
    assert len(invoked)==1
