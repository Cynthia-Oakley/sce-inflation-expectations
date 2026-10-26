from datetime import datetime,timezone,timedelta
import json

import pytest

from studies.sce_inflation_expectations.experiments import monthly_main_console as console


def sample():
    return dict(at_utc=datetime.now(timezone.utc).isoformat(),phase='generation_or_initial_validation',
        completed=2048,planned_calls=41984,new_attempts=1024,technically_usable=2000,errors=48,
        dispatched_without_local_result=0,api_reported_cost_usd=1.3918,unknown_fee_reservation_usd=.1646)


def test_progress_is_cumulative_and_stale_is_visible():
    data=sample();value=console.progress_line(data)
    assert '2,048/41,984' in value and '本次 1,024' in value and '失败 48' in value
    data['at_utc']=(datetime.now(timezone.utc)-timedelta(seconds=90)).isoformat()
    assert '超过60秒未更新' in console.progress_line(data)


def test_watch_is_read_only_and_reports_a_stop(tmp_path,monkeypatch,capsys):
    (tmp_path/'progress.json').write_text(json.dumps(sample()))
    (tmp_path/'worker_receipt.json').write_text(json.dumps(dict(status='generation_stopped_no_evaluation',receipt=dict(halt_reason='APIConnectionError'))))
    def forbidden(*a,**k):raise AssertionError('Watcher must not launch or authorize')
    monkeypatch.setattr(console.subprocess,'Popen',forbidden)
    monkeypatch.setattr(console.resume,'authorize',forbidden)
    value=console.watch(tmp_path)
    assert value['status']=='generation_stopped_no_evaluation'
    assert 'APIConnectionError' in capsys.readouterr().out


def test_ctrl_c_only_detaches_observer(tmp_path,monkeypatch):
    def interrupt(seconds):raise KeyboardInterrupt
    monkeypatch.setattr(console.time,'sleep',interrupt)
    assert console.watch(tmp_path)['status']=='observer_detached_worker_unchanged'
    assert not list(tmp_path.iterdir())


def test_run_requires_human_flag_before_any_checks(tmp_path,monkeypatch):
    monkeypatch.setattr(console.resume,'checked',lambda *a,**k:pytest.fail('Should reject first'))
    with pytest.raises(ValueError,match='confirm-continuation'):console.run(tmp_path)


def test_existing_launch_cannot_be_repeated(tmp_path,monkeypatch):
    package=tmp_path/'package';package.mkdir()
    (package/'resume.json').write_text(json.dumps(dict(prior_attempts=2048,new_requests=39936,prior_spent_or_reserved_usd=1.5564)))
    (tmp_path/'launch_lock.json').write_text('{}')
    monkeypatch.setattr(console.resume,'checked',lambda *a,**k:(dict(paths=dict(package=str(package))),dict(budget_cap_usd=40),{}))
    with pytest.raises(ValueError,match='already launched'):console.run(tmp_path,confirm_continuation=True)
