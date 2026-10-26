from copy import deepcopy
import json
import numpy as np
import pytest

from studies.sce_inflation_expectations.experiments.news_matching import allocate_quantity,change_news
from studies.sce_inflation_expectations.experiments.news_matching_ledger import reusable_call,expand_aliases
from studies.sce_inflation_expectations.experiments.staged_rosters import job_n
from studies.sce_inflation_expectations.news_exposure_demo import render_news_input


def news(aid,date='2025-03-03T12:00:00Z',common=False):
    return dict(article_id=aid,headline='Story '+aid,abstract='Summary',snippet='Summary',
        pub_date=date,web_url='https://example.invalid/'+aid,text_sha256='x',text_vintage_status='unknown',
        print_section='A' if common else 'B',print_page='1' if common else '2',
        placement='a1' if common else 'other_recorded_page',routing_tags=[],semantic_label={'decision':'keep'})


def test_quota_scaling_and_person_order_invariance():
    ids=[str(i) for i in range(192)];prob=np.full((192,6),1/6)
    a=allocate_quantity(ids,prob,7)
    assert {v:list(a.values()).count(v) for v in (3,8,20)}=={3:96,8:56,20:40}
    assert a==allocate_quantity(ids[::-1],prob,7)
    assert set(a.values())=={3,8,20}


@pytest.mark.parametrize('n',[0,95,97])
def test_invalid_roster_rejected(n):
    with pytest.raises(ValueError):allocate_quantity(list(range(n)),np.full((n,6),1/6),1)


def example():
    common=[news('common',common=True)];old=[news('old')]
    text=('Persona and unchanged prices\n'+render_news_input(common,old)+'\n\nPublic policy news brief (March): no change\n\n'
        'Publication timing for the same information above:\n- General news, in the order listed above: later.\n'
        '- Other news, in the order listed above: later.\n\nYour earlier survey response (2025-02):\nPRIOR\nQUESTIONS')
    return [dict(role='user',content=text)],common,old


def test_change_news_keeps_prior_and_policy_and_reindexes_time():
    messages,common,old=example();original=deepcopy(messages)
    updated=change_news(messages,common,old,[news('new','2025-02-10T12:00:00Z')],'2025-02-15','2025-03-10T23:59:59-04:00')
    assert messages==original
    assert '- Other news, in the order listed above: earlier.' in updated[0]['content']
    assert 'Story old' not in updated[0]['content'] and 'Story new' in updated[0]['content']
    assert updated[0]['content'].endswith('PRIOR\nQUESTIONS')
    assert change_news(messages,common,old,old,'2025-02-15','2025-03-10T23:59:59-04:00')==messages


def test_change_rejects_future_or_mismatched_old_story():
    messages,common,old=example()
    with pytest.raises(ValueError):change_news(messages,common,old,[news('future','2026-01-01T12:00:00Z')],'2025-02-15','2025-03-10T23:59:59-04:00')
    with pytest.raises(ValueError):change_news(messages,common,[news('wrong')],[],'2025-02-15','2025-03-10T23:59:59-04:00')


def test_empty_personal_pool_retains_common_and_empty_timing():
    messages,common,old=example()
    updated=change_news(messages,common,old,[],'2025-02-15','2025-03-10T23:59:59-04:00')[0]['content']
    assert 'Story common' in updated and 'Story old' not in updated
    assert '- Other news, in the order listed above: .' in updated


def test_aliases_reference_original_call_and_reject_cycles():
    calls={'canonical':{'raw_response_text':'unchanged','error':'Timeout'}}
    assert expand_aliases(calls,{'alias':'canonical'})['alias'] is calls['canonical']
    assert 'alias' not in calls
    with pytest.raises(ValueError):expand_aliases(calls,{'alias':'missing'})
    with pytest.raises(ValueError):expand_aliases(calls,{'a':'b','b':'a'})


def test_reuse_requires_exact_input_and_params_including_failed_attempts():
    p=dict(model='m',route='r',temperature=.5,max_tokens=1024,request_extra_body={},expected_provider='test')
    s=dict(month=202504,agent_id='anonymous',repeat=1,prompt_sha256='h',messages=[dict(role='user',content='abc')])
    c=dict(month=s['month'],agent_id=s['agent_id'],repeat=1,attempt_idx=0,prompt_sha256='h',
        prompt_text=json.dumps(s['messages'],ensure_ascii=False),temperature=.5,max_tokens=1024,extra_body={},error='ConnectionError')
    assert reusable_call(s,c,p,p)
    assert not reusable_call(s,{**c,'prompt_text':'changed'},p,p)
    assert not reusable_call(s,c,p,{**p,'route':'different'})
    assert not reusable_call(s,{**c,'attempt_idx':1},p,p)


def test_registered_variable_rosters_do_not_change_old_protocols():
    p=dict(mechanism='v32_news_matching',months=[202009,202504],n_by_month={'202009':96,'202504':192})
    assert job_n(p,dict(month=202009))==96
    assert job_n(p,dict(month=202504))==192
    assert job_n(dict(n_per_month=48),{})==48
    with pytest.raises(ValueError):job_n({**p,'mechanism':'old'},dict(month=202009))


def test_fixed_roster_fallback_keeps_humans_and_valid_q8_independently():
    from scripts.evaluate_sce_news_matching import fixed_roster
    real=dict(q9_mean=4.,q9_iqr=2.,q9_zero_deflation=1.,q8_point=5.,q9_bins=[0,0,0,100,0,0,0,0,0,0],
        previous_q9_mean=3.,previous_q9_iqr=1.,previous_q9_zero_deflation=1.,
        previous_q8_point=2.,previous_q9_bins=[0,0,0,0,100,0,0,0,0,0])
    rows=[dict(month=202504,repeat=r,userid=1,survey_weight=2.,real=deepcopy(real),
        arms={'a':dict(mean=None,iqr=None,zero_deflation=None,point=7.)}) for r in (1,2)]
    original=deepcopy(rows)
    result=fixed_roster(rows,dict(arms=['a'],months=[202504]))
    assert rows==original
    assert result['fallback_counts']=={'a':2}
    assert result['common_q9_person_months']==1
    a=result['primary_arms']['a']
    assert a['q9']['aggregate_equal_month_repeat_cells']['q9_center_mae_pp']==1.
    # Successful Q8 stays7; it must not be replaced by the prior2 because Q9 failed.
    assert a['q8']['aggregate_equal_month_repeat_cells']['q8_center_mae_pp']==2.
