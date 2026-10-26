"""Personal-cutoff boundaries and surgical changes to frozen Q3 messages."""
from copy import deepcopy

import pytest

from studies.sce_inflation_expectations.experiments.media_timing_inputs import (
    cutoff_for_response, status, timing_block, transform, policy_text, FOOD,
    BASKET, STATE, NEWS,
)
from studies.sce_inflation_expectations.news_exposure_demo import render_news_input


def fixture():
    common=[dict(headline='Public price report',pub_date='2021-05-18T12:00:00Z',abstract='Public summary',snippet='')]
    personal=[dict(headline='Local shopping report',pub_date='2021-06-01T12:00:00Z',abstract='',snippet='Source excerpt')]
    context=dict(as_of='2021-06-10T23:59:59-04:00',common_news=common,personal_news=personal,
                 policy_published_at='2021-04-28T14:00:00-04:00',food_published_at='2021-05-12T08:30:00-04:00')
    state=dict(comparison_reference_day='2021-05-20',comparison_day_source='own_observed_survey_day')
    policy=dict(published_at=context['policy_published_at'],facts=['First fact.','Second fact.','Third fact.'])
    food=FOOD+'\nPrice proxy remains unchanged.\n\n'
    text=('PERSONA UNCHANGED\nYou are answering a monthly survey in June 2021. '
          'You only know information that was publicly available by June 10, 2021.\n\n'+food+
          BASKET+'\nSYNTHETIC SHARES UNCHANGED\n\n'+render_news_input(common,personal)+'\n\n'+policy_text(policy)+
          timing_block(context,state)+STATE+'\nEARLIER BELIEF AND QUESTIONNAIRE UNCHANGED\n')
    return [{'role':'user','content':text}],context,state,food,policy


def test_previous_day_end_handles_month_boundary_and_dst():
    assert cutoff_for_response('2021-06-01',202106)=='2021-05-31T23:59:59-04:00'
    assert cutoff_for_response('2021-03-01',202103)=='2021-02-28T23:59:59-05:00'
    assert cutoff_for_response('2021-03-15',202103)=='2021-03-14T23:59:59-04:00'


def test_cross_month_completion_is_not_silently_clamped():
    with pytest.raises(ValueError):cutoff_for_response('2022-07-01',202206)


def test_same_reference_day_remains_uncertain_and_future_is_rejected():
    assert status('2021-05-31T08:00:00-04:00','2021-05-31','2021-05-31T23:59:59-04:00')=='same-day uncertain'
    with pytest.raises(ValueError):status('2021-06-01T08:00:00-04:00','2021-05-31','2021-05-31T23:59:59-04:00')
    with pytest.raises(ValueError):status('2021-05-30T08:00:00-04:00','2021-06-01','2021-05-31T23:59:59-04:00')


def test_identity_transform_reproduces_well_formed_prompt():
    m,c,s,f,p=fixture()
    assert transform(m,c,c,s,f,f,p,p,'','')==m


def test_identity_transform_preserves_extra_archived_timing_whitespace():
    m,c,s,f,p=fixture()
    m[0]['content']=m[0]['content'].replace(STATE,'\n\n'+STATE,1)
    assert transform(m,c,c,s,f,f,p,p,'','')==m


def test_only_wrong_general_timing_label_is_corrected():
    m,c,s,f,p=fixture();bad=deepcopy(m)
    bad[0]['content']=bad[0]['content'].replace('- General news, in the order listed above: earlier.',
                                             '- General news, in the order listed above: later.')
    assert transform(bad,c,c,s,f,f,p,p,'','')==m


def test_cutoff_news_change_preserves_prior_persona_basket_and_questions():
    m,c,s,f,p=fixture();new=deepcopy(c);new['as_of']='2021-06-08T23:59:59-04:00'
    new['personal_news']=[dict(headline='New dated report',pub_date='2021-06-07T12:00:00Z',abstract='New summary',snippet='')]
    updated=transform(m,c,new,s,f,f,p,p,'','')[0]['content']
    assert updated.startswith('PERSONA UNCHANGED\n')
    assert 'by June 8, 2021.' in updated
    assert updated[updated.index(STATE):]==m[0]['content'][m[0]['content'].index(STATE):]
    assert updated[updated.index(BASKET):updated.index(NEWS)]==m[0]['content'][m[0]['content'].index(BASKET):m[0]['content'].index(NEWS)]
    assert 'New dated report' in updated and 'Local shopping report' not in updated


def test_no_new_future_fact_or_prior_reference_survives_timing_render():
    m,c,s,f,p=fixture();new=deepcopy(c);new['as_of']='2021-05-31T23:59:59-04:00'
    with pytest.raises(ValueError):transform(m,c,new,s,f,f,p,p,'','')
