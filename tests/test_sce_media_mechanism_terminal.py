import hashlib
import json
from pathlib import Path
from threading import Lock

import pytest

from studies.sce_inflation_expectations.experiments import frozen_message_queue as q
from studies.sce_inflation_expectations.experiments import media_mechanism_terminal as terminal
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash


RAW=json.dumps({'point_pct':3.5,'q9':{f'bin{i}':10 for i in range(1,11)}})


def example(n=90):
    p={'model':'test','expected_provider':'test_provider','budget_cap_usd':5.}
    slots=[]
    for i in range(n):
        messages=[{'role':'user','content':str(i)}]
        slots.append(dict(key=str(i),month=202106,arm='Q0',repeat=1,agent_id=str(i),
            messages=messages,prompt_sha256=message_hash(messages),reserved_usd=.01))
    policy=dict(q.POLICY,initial_workers=1,max_workers=1,min_workers=1,
                healthy_segment_min_successes=2,scale_up_after_completed=2)
    return p,slots,policy


def reply(raw=RAW):
    return dict(returned_model='test',returned_provider='test_provider',raw_response_text=raw,
                finish_reason='stop',api_reported_cost_usd=.001)


def fake_error(name,status=None):
    exc=type(name,(Exception,),{})('Do not leak this body')
    exc.status_code=status
    return exc


@pytest.mark.parametrize('name,status',[('BadGatewayError',502),('RateLimitError',429),
                                      ('APIConnectionError',None),('APITimeoutError',None)])
def test_transient_errors_cool_and_never_resend_failed_request(tmp_path,name,status):
    p,slots,policy=example()
    sent=[];lock=Lock();cool=[]
    def send(messages):
        i=messages[0]['content']
        with lock:sent.append(i)
        if i=='35':raise fake_error(name,status)
        return reply()
    round_dir=tmp_path/'round_0001';round_dir.mkdir()
    r=q.run_segments(p,slots,tmp_path,round_dir,send,policy,cool=lambda *a:cool.append(a[0]))
    assert r['status']=='completed'
    assert len(sent)==len(set(sent))==90 and sent.count('35')==1
    assert cool==[30]
    intents,replies=q.archive(tmp_path)
    assert len(intents)==90 and len(replies)==90 and q.account(intents,replies)['usable']==89
    assert 'Do not leak' not in (round_dir/'segment_0002/calls_private.jsonl').read_text()


def test_hard_auth_error_drains_but_does_not_cool_or_continue(tmp_path):
    p,slots,policy=example();sent=[];cool=[]
    def send(messages):
        sent.append(messages[0]['content'])
        if messages[0]['content']=='35':raise fake_error('AuthenticationError',401)
        return reply()
    rd=tmp_path/'round_0001';rd.mkdir()
    r=q.run_segments(p,slots,tmp_path,rd,send,policy,cool=lambda *a:cool.append(1))
    assert r['status']=='stopped' and r['halt_reason']=='AuthenticationError'
    assert not cool and len(sent)==36


@pytest.mark.parametrize('changes',[{'returned_provider':'wrong'}, {'returned_model':'wrong'},
                                  {'api_reported_cost_usd':1.}, {'api_reported_cost_usd':-1.}])
def test_provider_and_charge_guards_are_hard_stops(tmp_path,changes):
    p,slots,_=example(3)
    r,_,rows=q.execute_segment(p,slots,tmp_path/'seg',lambda m:dict(reply(),**changes),
        workers=1,max_workers=1,scale_after=100)
    assert r['halt_reason'] and len(rows)==1


def test_inflight_and_unknown_reservations_cannot_reset_budget(tmp_path):
    p,slots,_=example(5);p['budget_cap_usd']=.019
    prior=[dict(key='old',prompt_sha256='oldhash',reserved_usd=.01)]
    r,intents,replies=q.execute_segment(p,slots,tmp_path/'seg',lambda m:reply(),workers=2,
        max_workers=2,scale_after=10,prior_intents=prior)
    assert not intents and not replies and r['halt_reason']=='Budget cap reached before dispatch'
    assert r['spent_or_reserved_usd']==.01 and r['unresolved']==1


def test_crash_unknown_intent_is_preserved_and_only_unsent_slots_continue(tmp_path):
    p,slots,policy=example(40)
    rd=tmp_path/'round_0001';seg=rd/'segment_0001';seg.mkdir(parents=True)
    intents=[{k:s[k] for k in ('key','prompt_sha256','reserved_usd')} for s in slots[:32]]
    (seg/'dispatch_private.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in intents))
    rows=[dict(reply(),key=s['key'],prompt_sha256=s['prompt_sha256']) for s in slots[1:32]]
    # A torn raw reply is not a usable completion, and is not overwritten.
    (seg/'calls_private.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows)+'{"key":')
    new=tmp_path/'round_0002';new.mkdir();sent=[]
    r=q.run_segments(p,slots,tmp_path,new,lambda m:(sent.append(m[0]['content']) or reply()),policy)
    assert r['status']=='completed' and r['unresolved']==1
    assert set(sent)==set(str(i) for i in range(32,40))
    assert r['spent_or_reserved_usd']==pytest.approx(.049)
    assert (seg/'calls_private.jsonl').read_text().endswith('{"key":')


def test_unknown_intent_cannot_be_explicitly_requeried(tmp_path):
    p,slots,_=example(1)
    with pytest.raises(ValueError,match='must not be resent'):
        q.execute_segment(p,slots,tmp_path/'seg',lambda m:reply(),workers=1,max_workers=1,
            scale_after=1,prior_intents=[{k:slots[0][k] for k in ('key','prompt_sha256','reserved_usd')}])


def test_cooldown_and_retry_after_are_bounded(tmp_path):
    p,slots,policy=example(200);policy=dict(policy,max_total_cooldown_seconds=10)
    def send(messages):
        if int(messages[0]['content'])>=35:raise fake_error('RateLimitError',429)
        return reply()
    rd=tmp_path/'round_0001';rd.mkdir();cool=[]
    r=q.run_segments(p,slots,tmp_path,rd,send,policy,cool=lambda *a:cool.append(a[0]))
    assert r['halt_reason']=='Cooldown cap reached' and not cool


def test_valid_retry_after_is_respected_without_resending(tmp_path):
    p,slots,policy=example();cool=[]
    def send(messages):
        if messages[0]['content']=='35':
            exc=fake_error('RateLimitError',429)
            exc.response=type('Response',(),{'headers':{'Retry-After':'75'}})()
            raise exc
        return reply()
    rd=tmp_path/'round_0001';rd.mkdir()
    r=q.run_segments(p,slots,tmp_path,rd,send,policy,cool=lambda *a:cool.append(a[0]))
    assert r['status']=='completed' and cool==[75]


def test_cumulative_hard_failure_wins_over_transient_error(tmp_path):
    p,slots,policy=example(40)
    def send(messages):
        i=int(messages[0]['content'])
        if i==0:raise fake_error('BadGatewayError',502)
        if i==1:raise fake_error('PermissionDeniedError',403)
        return reply()
    rd=tmp_path/'round_0001';rd.mkdir();cool=[]
    r=q.run_segments(p,slots,tmp_path,rd,send,policy,cool=lambda *a:cool.append(1))
    assert r['status']=='stopped' and not cool


def test_gate_is_format_based_and_never_reads_truth(tmp_path):
    p,slots,policy=example(40)
    rd=tmp_path/'round_0001';rd.mkdir();sent=[]
    r=q.run_segments(p,slots,tmp_path,rd,lambda m:(sent.append(1) or reply('{}')),policy)
    assert r['halt_reason']=='Technical format gate not passed' and len(sent)==32


def test_sum_normalization_does_not_change_raw_reply():
    raw=json.dumps({'point_pct':3,'q9':{f'bin{i}':20 for i in range(1,11)}})
    row=dict(reply(raw))
    assert q.fields(row)=={'q8':True,'q9':True}
    assert row['raw_response_text']==raw


def test_terminal_without_explicit_confirmation_does_not_load_key_or_start(tmp_path):
    with pytest.raises(ValueError,match='confirm-scope-and-budget'):
        terminal.run(tmp_path)
    assert not list(tmp_path.iterdir())


def test_frozen_slots_preserve_original_messages_and_repeats(tmp_path):
    messages=[{'role':'user','content':'Exact\nunchanged 中文'}]
    month=tmp_path/'202106';month.mkdir()
    (month/'prompts_Q0.json').write_text(json.dumps({'rows':{'a':{
        'messages':messages,'prompt_sha256':message_hash(messages)}}}))
    m={'jobs':[{'month':202106,'arm':'Q0','repeat':i} for i in (1,2)]}
    p={'planned_calls':2,'price_input_per_mtok':.259,'price_output_per_mtok':.8,'max_tokens':1024}
    slots=terminal.slots_for(tmp_path,m,p)
    assert len(slots)==2 and {r['repeat'] for r in slots}=={1,2}
    assert all(r['messages']==messages for r in slots)


def test_baseline_uses_real_previous_response_not_current_target(monkeypatch):
    from studies.sce_inflation_expectations.evaluation import media_mechanism_terminal as e
    monkeypatch.setattr(e,'score',lambda b:dict(mean=50.,iqr=2.,zero_deflation=0.))
    bins=[0]*9+[100]
    out=e.previous_action(dict(previous_q9_mean=5.,previous_q9_bins=bins,previous_q8_point=4.,q9_mean=99.))
    assert out['mean']==5. and out['point']==4. and out['q9_bins']==bins


def test_failed_model_reply_remains_missing_without_prior_imputation():
    from studies.sce_inflation_expectations.evaluation import media_mechanism_terminal as e
    out=e.model_action(dict(reply(),error='APIConnectionError'))
    assert out['mean'] is None and out['point'] is None and out['validation_status']=='invalid'


def test_immutable_segment_hash_is_checked_on_recovery(tmp_path):
    p,slots,_=example(1)
    segment=tmp_path/'round_0001/segment_0001'
    q.execute_segment(p,slots,segment,lambda m:reply(),workers=1,max_workers=1,scale_after=1)
    with (segment/'calls_private.jsonl').open('a') as f:f.write('\n')
    with pytest.raises(ValueError,match='Immutable segment'):
        q.archive(tmp_path)


def test_engineering_run_is_marked_non_research(tmp_path):
    p,slots,_=example(1)
    r,_,rows=q.execute_segment(p,slots,tmp_path/'s',lambda m:reply(),workers=1,
        max_workers=1,scale_after=1,engineering_only=True)
    assert r['actual_model_results'] is False and rows[0]['actual_model_results'] is False


def test_second_terminal_launch_is_blocked_by_process_lock(tmp_path,monkeypatch):
    import os
    import fcntl
    p,_,_=example()
    p.update(destination='https://example.invalid',route='fixed',planned_calls=90)
    (tmp_path/'config.json').write_text('{}')
    c={'estimated_cost_usd':1.}
    monkeypatch.setattr(terminal,'checked',lambda *a,**k:(c,p))
    monkeypatch.setenv('OPENROUTER_API_KEY','test-only-never-sent')
    fd=os.open(tmp_path/'execution.lock',os.O_CREAT|os.O_RDWR,0o600)
    fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
    try:
        with pytest.raises(BlockingIOError):terminal.run(tmp_path,confirm=True)
        assert not (tmp_path/'authorization.json').exists()
    finally:os.close(fd)


def test_offline_evaluation_writes_baseline_a82_and_strata_on_same_support(monkeypatch):
    from tempfile import TemporaryDirectory
    from functools import lru_cache
    from studies.sce_inflation_expectations.evaluation import media_mechanism_terminal as e
    root=terminal.ROOT
    with TemporaryDirectory(dir=root/'outputs') as d:
        folder=Path(d);package=folder/'package';package.mkdir()
        p={'months':[202106],'arms':['Q0','Q1'],'generation_repeats':[1,2],
           'planned_calls':8,'model':'test','expected_provider':'test_provider'}
        monkeypatch.setattr(e,'checked',lambda f:({'package':str(package)},p))
        monkeypatch.setattr(e,'score',lru_cache(None)(lambda b:dict(mean=3.,iqr=2.,zero_deflation=0.)))
        real=dict(q9_mean=3.,q9_iqr=2.,q9_zero_deflation=0.,q9_bins=[10]*10,
                  q8_point=3.,previous_q9_mean=5.,previous_q9_bins=[10]*10,previous_q8_point=4.)
        links=[dict(month=202106,agent_id=a,userid=i,profile={},stratum='s',
                    survey_weight=w,design_survey_weight=w) for i,(a,w) in enumerate((('a',1.),('b',2.)))]
        truth=[dict(month=202106,agent_id=a,repeat=r,real=real) for a in ('a','b') for r in (1,2)]
        (package/'evaluation_truth').mkdir()
        (package/'evaluation_truth/cases_private.json').write_text(json.dumps(truth))
        (package/'evaluation_links_private.json').write_text(json.dumps(links))
        (package/'manifest.json').write_text('{}')
        (package/'protocol.json').write_text(json.dumps(p))
        reference=[dict(link,repeat=1,real=real,arms={'monthly_reconstruction':dict(
            mean=3.,iqr=2.,zero_deflation=0.,q9_bins=[10]*10,point=3.)}) for link in links]
        (package/'a82_reference_private.json').write_text(json.dumps(reference))
        (package/'202106').mkdir()
        (package/'202106/contexts_private.json').write_text(json.dumps({a:{aid:{'news_count':4,'sources':[]}
            for aid in ('a','b')} for a in ('Q0','Q1')}))
        slots=[];intents=[];rows=[]
        for a in ('Q0','Q1'):
            for r in (1,2):
                for aid in ('a','b'):
                    key=f'202106|{a}|{r}|{aid}'
                    slots.append(dict(key=key,prompt_sha256='hash'))
                    intents.append(dict(key=key,prompt_sha256='hash',reserved_usd=.01))
                    rows.append(dict(reply(),key=key,prompt_sha256='hash',actual_model_results=True,
                                     raw_response_sha256=hashlib.sha256(RAW.encode()).hexdigest()))
        monkeypatch.setattr(e,'slots_for',lambda *args:slots)
        seg=folder/'round_0001/segment_0001';seg.mkdir(parents=True)
        (seg/'dispatch_private.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in intents))
        (seg/'calls_private.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
        result=e.evaluate(folder,folder/'evaluation')
        summary=json.loads((folder/'evaluation/summary.json').read_text())
        comp=json.loads((folder/'evaluation/comparison/summary.json').read_text())
        assert result['persistence_baseline_included'] is True
        assert summary['persistence_same_support']['q9_person_months']==2
        base=summary['persistence_same_support']['arms']['copy_previous']['auxiliary_survey_weighted']['q9']
        assert base['aggregate_equal_month_repeat_cells']['q9_center_mae_pp']==2.
        assert comp['A82_original_single_generation']['q9']['expected_cells']==1
        assert 'stratified_descriptive' in comp
        assert 'copy_previous' in (folder/'evaluation/RESULTS.md').read_text()
