"""One-call recording: field preservation, stream interruption, identity and fees."""
import json
import pytest
from studies.sce_inflation_expectations.reports.terminal_live_v1 import demo


def protocol():
    return {'model':demo.MODEL,'expected_provider':'SiliconFlow','budget_cap_usd':.01,'reserved_usd':.004}


def answer():
    return {'point_pct':6,'q9':{f'bin{i}':v for i,v in enumerate([0,0,20,30,50,0,0,0,0,0],1)}}


def stream(raw=None,**metadata):
    text=json.dumps(answer()) if raw is None else raw
    for part in [text[:13],text[13:]]:
        yield dict(model=demo.MODEL,provider='SiliconFlow',id='gen-test',choices=[{'delta':{'content':part},'finish_reason':None}],**metadata)
    yield dict(model=demo.MODEL,provider='SiliconFlow',choices=[{'delta':{},'finish_reason':'stop'}],usage={'cost':.001})


def test_exact_content_and_usage_frame(tmp_path):
    received=[]
    r=demo.consume(stream(),protocol(),tmp_path,emit=received.append)
    assert ''.join(received)==json.dumps(answer())
    assert (tmp_path/'response_raw.txt').read_text()==json.dumps(answer())
    assert r['reported_cost_usd']==.001 and r['status']=='completed'


def test_interruption_keeps_partial_without_new_attempt(tmp_path):
    def fail():
        yield {'choices':[{'delta':{'content':'{"point_pct":'}}]}
        raise ConnectionError('offline injected connection break')
    with pytest.raises(ConnectionError):demo.consume(fail(),protocol(),tmp_path,emit=lambda _:None)
    assert (tmp_path/'response_partial.txt').read_text()=='{"point_pct":'
    assert len((tmp_path/'stream_private.jsonl').read_text().splitlines())==1


@pytest.mark.parametrize('bad',[
    {'error':{'code':500}},
    {'model':'other-model'},
    {'provider':'OtherProvider'},
])
def test_stream_error_or_wrong_route_rejected(tmp_path,bad):
    with pytest.raises(ValueError):demo.consume(iter([bad]),protocol(),tmp_path,emit=lambda _:None)
    assert len((tmp_path/'stream_private.jsonl').read_text().splitlines())==1


def test_valid_json_without_finish_is_not_complete(tmp_path):
    chunks=[{'choices':[{'delta':{'content':json.dumps(answer())}}]}]
    with pytest.raises(ValueError):demo.consume(chunks,protocol(),tmp_path,emit=lambda _:None)


def test_identity_not_inferred_when_metadata_missing(tmp_path):
    r=demo.consume([{'choices':[{'delta':{'content':json.dumps(answer())},'finish_reason':'stop'}]}],protocol(),tmp_path,emit=lambda _:None)
    assert r['status']=='completed_metadata_incomplete'
    assert r['returned_providers']==[] and r['spent_or_reserved_usd']==.004


def test_normalization_preserves_original(tmp_path):
    obj=answer();obj['q9']['bin5']=25
    raw=json.dumps(obj)
    r=demo.consume(stream(raw),protocol(),tmp_path,emit=lambda _:None)
    assert r['q9']['raw_sum']==75 and r['q9']['applied']
    assert (tmp_path/'response_raw.txt').read_text()==raw


@pytest.mark.parametrize('fee',[-1,float('inf'),.02])
def test_bad_reported_cost_rejected(tmp_path,fee):
    rows=list(stream());rows[-1]['usage']['cost']=fee
    with pytest.raises(ValueError):demo.consume(rows,protocol(),tmp_path,emit=lambda _:None)


def test_existing_attempt_refuses_before_client(tmp_path,monkeypatch):
    (tmp_path/'execution').mkdir()
    monkeypatch.setattr(demo,'show_input',lambda *a:None)
    monkeypatch.setattr(demo,'stage',lambda *a:None)
    monkeypatch.setattr('builtins.input',lambda _:'RUN')
    with pytest.raises(FileExistsError):demo.run_once(tmp_path,protocol(),{},False)


def test_terminal_controls_filtered():
    assert demo.safe('\x1b[2Jbad\x00\n')=='[2Jbad\n'


@pytest.mark.parametrize('late',['news','food'])
def test_no_future_environment(late):
    d=dict(cutoff='2021-06-12T23:59:59-04:00',news_count=1,common_count=1,personal_count=0,
        news=[{'headline':'Example','published_at':'2021-06-10T08:30:00-04:00'}],
        food_published='2021-06-10T08:30:00-04:00',messages=[{'content':'Example'}])
    if late=='news':d['news'][0]['published_at']='2021-06-13T01:00:00-04:00'
    else:d['food_published']='2021-06-13T01:00:00-04:00'
    with pytest.raises(ValueError):demo.validate_visibility(d)


def archive(tmp_path,dirname='execution'):
    folder=tmp_path/dirname
    result=demo.consume(stream(),protocol(),folder,emit=lambda _:None)
    result['seconds']=23.4
    demo.dump(folder/'receipt.json',result)
    return folder


def test_same_entry_defaults_to_free_replay(tmp_path,monkeypatch):
    folder=archive(tmp_path);seen=[]
    monkeypatch.setattr('builtins.input',lambda _:'')
    monkeypatch.setattr(demo,'playback',lambda *a:seen.append(a[-1]) or {'status':'archived_playback_complete','new_api_calls':0})
    monkeypatch.setattr(demo,'run_once',lambda *a:pytest.fail('Default recording must never call model'))
    assert demo.run(tmp_path,protocol(),{},False)['new_api_calls']==0
    assert demo.run(tmp_path,protocol(),{},False)['new_api_calls']==0
    assert seen==[folder,folder]


def test_manual_new_take_preserves_old_bytes(tmp_path,monkeypatch):
    folder=archive(tmp_path)
    before={x.name:x.read_bytes() for x in folder.iterdir()}
    monkeypatch.setattr('builtins.input',lambda _:'2')
    seen=[]
    def fake_run(bundle,p,d,pause,new_folder):
        seen.append(new_folder)
        assert new_folder.parent==tmp_path/'executions' and not new_folder.exists()
        return {'status':'offline_test_only'}
    monkeypatch.setattr(demo,'run_once',fake_run)
    demo.run(tmp_path,protocol(),{},False)
    demo.run(tmp_path,protocol(),{},False)
    assert seen[0]!=seen[1]
    assert before=={x.name:x.read_bytes() for x in folder.iterdir()}


def test_playback_discloses_mode_and_does_not_change_archive(tmp_path,monkeypatch,capsys):
    folder=archive(tmp_path);before={x.name:x.read_bytes() for x in folder.iterdir()}
    monkeypatch.setattr(demo,'show_input',lambda *a:None)
    r=demo.playback(tmp_path,protocol(),{},False,delay=0)
    shown=capsys.readouterr().out
    assert '本次API调用0' in shown and '不是再次现场调用' in shown
    assert r['new_api_calls']==0 and json.dumps(answer()) in shown
    assert before=={x.name:x.read_bytes() for x in folder.iterdir()}


def test_replay_prefers_latest_complete_and_ignores_incomplete(tmp_path):
    first=archive(tmp_path)
    second=archive(tmp_path,'executions/take_001')
    (tmp_path/'executions/take_002').mkdir()
    assert demo.completed_takes(tmp_path)==[first,second]


def test_corrupt_archived_content_not_replayed(tmp_path):
    folder=archive(tmp_path)
    changed=answer();changed['point_pct']=7
    (folder/'response_raw.txt').write_text(json.dumps(changed))
    with pytest.raises(ValueError):demo.completed_takes(tmp_path)


def test_parallel_live_run_is_locked(tmp_path):
    with demo.live_lock(tmp_path):
        with pytest.raises(RuntimeError):
            with demo.live_lock(tmp_path):pytest.fail('Two paid dispatches must not overlap')


def test_exit_menu_does_not_dispatch(tmp_path,monkeypatch):
    archive(tmp_path)
    monkeypatch.setattr('builtins.input',lambda _:'q')
    monkeypatch.setattr(demo,'run_once',lambda *a:pytest.fail('Exit must not call model'))
    assert demo.run(tmp_path,protocol(),{},False) is None


def test_new_call_still_requires_run_confirmation(tmp_path,monkeypatch):
    monkeypatch.setattr(demo,'show_input',lambda *a:None)
    monkeypatch.setattr(demo,'stage',lambda *a:None)
    monkeypatch.setattr('builtins.input',lambda _:'')
    folder=tmp_path/'executions/take_new'
    assert demo.run_once(tmp_path,protocol(),{},False,folder) is None
    assert not folder.exists()
