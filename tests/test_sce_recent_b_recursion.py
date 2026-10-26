from copy import deepcopy
import json

import pytest

from studies.sce_inflation_expectations.experiments import recent_b_recursion as mod
from studies.sce_inflation_expectations.experiments.frozen_batch import dump
from studies.sce_inflation_expectations.state_continuity_runtime import STATE_TOKEN,TIMING_TOKEN


def state():
    return dict(fields={'q8':dict(value=2.,source_period=202510,source_kind='synthetic_donor'),
                        'q9':dict(value=[10.]*10,source_period=202510,source_kind='synthetic_donor')},
                history_centers=[],comparison_reference_day='2025-10-31',
                comparison_day_source='synthetic_prior_reference_month_end')


def answer(q8=3.,q9=None,error=None):
    obj={'point_pct':q8,'q9':q9 if q9 is not None else {f'bin{i}':10. for i in range(1,11)}}
    return dict(raw_response_text=json.dumps(obj),finish_reason='stop',error=error)


@pytest.fixture(autouse=True)
def cheap_center(monkeypatch):
    import studies.sce_inflation_expectations.state_continuity_runtime as runtime
    monkeypatch.setattr(runtime,'density_center',lambda _:0.)


def test_repair_does_not_replace_successful_field_or_double_history():
    before=state();main=answer(q8=7.,q9={f'bin{i}':0 for i in range(1,11)})
    fix=answer(q8=99.)
    result=mod.transition(before,main,fix,['q9'],'202511','2025-11-13T23:59:59-05:00')
    assert result['fields']['q8']['value']==7
    assert result['fields']['q9']['value']==[10.]*10
    assert len(result['history_centers'])==1
    assert before==state()


def test_nonunit_q9_normalization_recorded_and_negative_q8_valid():
    result=mod.transition(state(),answer(q8=-2,q9={f'bin{i}':2 for i in range(1,11)}),None,[],
                          '202511','2025-11-13T23:59:59-05:00')
    assert result['fields']['q8']['value']==-2
    assert sum(result['fields']['q9']['value'])==100
    assert result['transition']['q9_proportional_normalization'] is True


def test_repeated_technical_failure_retains_same_households_prior():
    before=state();failed=answer(error='APIConnectionError')
    result=mod.transition(before,failed,failed,['q8','q9'],'202511','2025-11-13T23:59:59-05:00')
    assert result['fields']==before['fields']
    assert result['history_centers']==[]
    assert result['transition']['field_retained_as_explicit_fallback']=={'q8':True,'q9':True}


def test_future_state_is_rejected():
    before=state();before['fields']['q8']['source_period']=202511
    with pytest.raises(ValueError,match='forward'):
        mod.transition(before,answer(),None,[],'202511','2025-11-13T23:59:59-05:00')


def wave_setup(tmp_path,monkeypatch):
    monkeypatch.setattr(mod,'ROOT',tmp_path)
    pe=tmp_path/'PE';dest=pe/'202512';dest.mkdir(parents=True)
    contexts={a:dict(as_of='2025-12-18T23:59:59-05:00',common_news=[],personal_news=[],
                    food_published_at='2025-12-18T08:30:00-05:00',policy_published_at='2025-12-10T14:00:00-05:00')
              for a in ('a','b')}
    templates={a:[dict(role='user',content=TIMING_TOKEN+STATE_TOKEN)] for a in contexts}
    dump(dest/'timing_context_private.json',contexts);dump(dest/'templates_private.json',templates)
    previous={a:dict(agent_id=a,month='202511',state_after=mod.transition(state(),answer(q8=i),None,[],
        '202511','2025-11-13T23:59:59-05:00')) for a,i in [('a',4),('b',8)]}
    p=dict(PE='PE',max_prompt_bytes=100000,max_prompt_chars=100000,max_tokens=1024,
           price_input_per_mtok=.259,price_output_per_mtok=.8)
    folder=tmp_path/'run';folder.mkdir()
    return folder,p,previous


def test_later_prompt_uses_only_same_person_saved_model_state(tmp_path,monkeypatch):
    folder,p,previous=wave_setup(tmp_path,monkeypatch)
    wave,slots=mod.prepare_wave(folder,p,'202512',previous)
    rows=mod.read(wave/'frozen_messages/202512/prompts.json')['rows']
    assert '"point_pct": 4' in rows['a']['messages'][0]['content']
    assert '"point_pct": 8' in rows['b']['messages'][0]['content']
    assert 'your answer from an earlier step' in rows['a']['messages'][0]['content']
    _,again=mod.prepare_wave(folder,p,'202512',previous)
    assert slots==again
    changed=deepcopy(previous);changed['a']['state_after']['fields']['q8']['value']=100.
    with pytest.raises(ValueError,match='predecessor'):
        mod.prepare_wave(folder,p,'202512',changed)


@pytest.mark.parametrize('mode',['missing','swap','skip'])
def test_missing_swapped_or_skipped_predecessor_never_uses_new_donor(tmp_path,monkeypatch,mode):
    folder,p,previous=wave_setup(tmp_path,monkeypatch)
    if mode=='missing':del previous['b']
    if mode=='swap':previous['a']['agent_id']='b'
    if mode=='skip':previous['a']['month']='202510'
    with pytest.raises(ValueError,match='predecessor'):
        mod.prepare_wave(folder,p,'202512',previous)


def test_resume_refuses_changed_frozen_prompt(tmp_path,monkeypatch):
    folder,p,previous=wave_setup(tmp_path,monkeypatch)
    wave,_=mod.prepare_wave(folder,p,'202512',previous)
    (wave/'frozen_messages/202512/prompts.json').write_text('{}')
    with pytest.raises(ValueError,match='changed'):
        mod.prepare_wave(folder,p,'202512',previous)


def test_next_wave_cannot_read_prior_record_from_target_month(tmp_path,monkeypatch):
    folder,p,previous=wave_setup(tmp_path,monkeypatch)
    previous['a']['state_after']['fields']['q9']['source_period']=202512
    with pytest.raises(ValueError,match='earlier'):
        mod.prepare_wave(folder,p,'202512',previous)


def test_no_live_launch_without_recorded_exact_approval(tmp_path):
    # No default creation of authorization or reliance on an old batch's cap.
    with pytest.raises(FileNotFoundError):mod.launch(tmp_path,confirm=True)
    assert not (tmp_path/'package/authorization.json').exists()
