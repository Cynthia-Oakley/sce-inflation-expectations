"""The exception must never turn new auth errors into automatic retries."""
from copy import deepcopy
from studies.sce_inflation_expectations.experiments import weekly_key_limit_resume as resume


def old_reply():
    return dict(key='weekly|w20260710|synthetic',error='PermissionDeniedError',error_http_status=403,
                started_at_utc='2026-10-26T18:10:29+00:00',fatal=True)


def test_exact_old_reply_only_is_recoverable():
    row=old_reply();allowed=dict(key=row['key'],record_sha256=resume.record_hash(row))
    policy={'recoverable_statuses':[429,500]}
    with resume.exact_historical_exception(allowed):
        assert resume.weekly.transport.recoverable(row,policy)
        future=deepcopy(row);future['started_at_utc']='2026-10-27T02:00:00+00:00'
        assert not resume.weekly.transport.recoverable(future,policy)
        repair=deepcopy(row);repair['key']='repair1|'+row['key']
        assert not resume.weekly.transport.recoverable(repair,policy)
        auth=deepcopy(row);auth['error_http_status']=401
        assert not resume.weekly.transport.recoverable(auth,policy)


def test_exception_restores_original_handler():
    row=old_reply();original=resume.weekly.transport.recoverable
    try:
        with resume.exact_historical_exception(dict(key=row['key'],record_sha256=resume.record_hash(row))):
            raise RuntimeError('test interruption')
    except RuntimeError:pass
    assert resume.weekly.transport.recoverable is original


def test_archived_403_continues_untouched_slots_and_repairs_only_once(monkeypatch,tmp_path):
    from test_sce_full_a_personal_terminal import _slots,_protocol,_policy,_install_materializer,_sender_result
    from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
    from studies.sce_inflation_expectations.experiments import full_a_personal_terminal as t
    slots,messages=_slots(60);_install_materializer(monkeypatch,messages)
    p=_protocol(60);policy=_policy();policy.update(initial_workers=1,max_workers=1)
    failed=slots[32]['key'];digest=message_hash(messages[failed]);sent=[]
    class PermissionDeniedError(Exception):status_code=403
    def before_limit_increase(prompt):
        sent.append(message_hash(prompt))
        if message_hash(prompt)==digest:raise PermissionDeniedError('synthetic key budget')
        return _sender_result()
    stopped=t.run_main_segments(p,slots,tmp_path,before_limit_increase,policy,cool=lambda *_:None)
    assert stopped['halt_reason']=='hard_provider_or_account_error'
    intents,replies=resume.queue.archive(tmp_path/'main')
    assert len(intents)==33
    old=next(r for r in replies if r.get('error_http_status')==403)
    allowed=dict(key=old['key'],record_sha256=resume.record_hash(old))
    sealed_bytes={f:f.read_bytes() for f in (tmp_path/'main').rglob('*') if f.is_file()}
    def healthy(prompt):sent.append(message_hash(prompt));return _sender_result()
    with resume.exact_historical_exception(allowed):
        result=t.run_main_segments(p,slots,tmp_path,healthy,policy,cool=lambda *_:None)
        assert result['status']=='completed'
        ii,rr=resume.queue.archive(tmp_path/'main')
        repair,ri,_,targets=t.run_repair_segments(p,slots,tmp_path,ii,rr,healthy,policy,cool=lambda *_:None)
        assert repair['status']=='completed' and len(ri)==1 and set(targets)=={failed}
        count=len(sent)
        t.run_main_segments(p,slots,tmp_path,healthy,policy,cool=lambda *_:None)
        t.run_repair_segments(p,slots,tmp_path,ii,rr,healthy,policy,cool=lambda *_:None)
        assert len(sent)==count==61
    assert all(f.read_bytes()==data for f,data in sealed_bytes.items())
    assert sent.count(digest)==2
