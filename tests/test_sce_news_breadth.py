from copy import deepcopy

import numpy as np
import pytest

from studies.sce_inflation_expectations.experiments.news_breadth import (
    TAGS, balance_receipt, balanced_shuffle, select_views,
)
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash


def test_balance_receipt_uses_each_persons_actual_view_and_design_weights():
    # Hand-computable example: reference weighted count=9/4, candidate=11/4.
    left=np.array([[3,30,100,*([1]*len(TAGS))],[2,20,90,*([0]*len(TAGS))]],float)
    right=left[::-1]
    r=balance_receipt(left,right,np.array([1.,3.]))
    assert r['weighted_mean_news_reference']==2.25
    assert r['weighted_mean_news_candidate']==2.75
    assert r['weighted_count_relative_gap']==pytest.approx(2/9)
    # Topic share is a ratio of weighted article counts, not a mean of ratios.
    assert r['topic_share_absolute_gaps'][TAGS[0]]==pytest.approx(3/11-1/9)


def test_shuffled_assignment_is_reproducible_equal_quantity_and_not_identical():
    levels=(3,8,20); labels=np.array([3,3,8,20])
    cube=np.zeros((4,3,3+len(TAGS)))
    for j,n in enumerate(levels):
        cube[:,j,:3]=[n,n*100,500+n*100]
        cube[:,j,3:]=n/2
    a,receipt=balanced_shuffle(labels,cube,np.ones(4),42)
    b,_=balanced_shuffle(labels,cube,np.ones(4),42)
    assert np.array_equal(a,b) and not np.array_equal(a,labels)
    assert sorted(a)==sorted(labels)
    assert receipt['weighted_count_relative_gap']==0
    assert max(receipt['topic_share_absolute_gaps'].values())==0


def test_whole_prompt_selection_keeps_prior_and_rejects_other_changes():
    by_level={}
    for n in (3,8,20):
        text=('Persona\nRecent official statistics:\nFixed statistics\n\n'
            f'General news you encountered:\n{n} articles\nPublic policy news brief (today):\nSame policy\n'
            'Your earlier survey response (last month):\nPrior and questionnaire unchanged')
        messages=[{'role':'user','content':text}]
        by_level[n]={'a':{'messages':messages,'prompt_sha256':message_hash(messages)}}
    got=select_views(by_level,{'a':3})
    assert got['a']==by_level[3]['a']
    got['a']['messages'][0]['content']='Changed copy'
    assert by_level[3]['a']['messages'][0]['content']!='Changed copy'
    bad=deepcopy(by_level)
    bad[3]['a']['messages'][0]['content']=bad[3]['a']['messages'][0]['content'].replace('Prior and','Different prior and')
    bad[3]['a']['prompt_sha256']=message_hash(bad[3]['a']['messages'])
    with pytest.raises(ValueError,match='prior/questionnaire'):
        select_views(bad,{'a':3})
