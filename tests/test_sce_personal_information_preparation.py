import numpy as np
import pandas as pd

from studies.sce_inflation_expectations.personal_information_preparation import (
    composition, past_state, conditional_roles, draw_role, balanced_permutation,
)


def roster(prefix='Q45new', *, child=0, other=0, roommate=0):
    values = [1,0,0,child,0,0,other,roommate]
    return {**{f'{prefix}_{i}':v for i,v in enumerate(values,1)},f'{prefix}_9':0}


def test_whole_residence_is_not_family_and_unknown_children_are_not_absent():
    r = composition(roster(roommate=2),'Q45new')
    assert r['whole_residence_size']==4 and r['family_size_excluding_nonrelatives']==2
    assert r['children_group']=='missing'
    assert composition(roster(child=1,other=2),'Q45new')['children_group']=='with_children'
    assert composition(roster(),'Q45new')['children_group']=='no_children'


def test_future_rows_excluded_and_invalid_updates_do_not_resurrect_old_roster():
    previous = roster(); previous['Q32']=38
    history = [(202001,previous),(202002,{'D1':2}),(202003,roster(child=4))]
    r = past_state(history,202003)
    assert not r['available'] and r['source_month']==202002
    assert r['invalidations']==['reported_change_without_complete_D2']
    r = past_state([(202001,previous),(202002,{'D1':1})],202003)
    assert r['available'] and r['record_age_months']==2
    assert r['nonrelative_count_currently_confirmed'] is False
    assert not past_state([(202001,previous),(202002,{'D3':1})],202003)['available']


def test_missing_target_dimension_is_marginalized_and_stable_draw_repeats():
    train = pd.DataFrame({'age_group':['young','young','old'],
        'children_group':['with_children','no_children','no_children'],
        'EUFINLWGT':[1.,3.,1.],'role':[1,3,2]})
    target = pd.DataFrame({'age_group':['young'],'children_group':['missing']})
    p,s = conditional_roles(train,target,'role',3,['age_group','children_group'])
    base = np.array([1,1,3])/5
    expected = 2/22*np.array([1,0,3])/4+20/22*base
    assert np.allclose(p[0],expected) and s[0]['n']==2
    assert s[0]['observed_dimensions']==['age_group']
    assert draw_role(p[0],'fixed_person',42)==draw_role(p[0],'fixed_person',42)


def test_balanced_shuffling_preserves_counts_and_design_weighted_quantity():
    x=np.tile([3,8,20],32);w=np.linspace(1,3,len(x))
    perm,receipt=balanced_permutation(x,w,np.random.default_rng(42))
    assert sorted(x)==sorted(x[perm]) and not np.array_equal(x,x[perm])
    assert abs(np.average(x[perm],weights=w)/np.average(x,weights=w)-1)<=.01
    assert receipt['relative_weighted_quantity_difference']<=.01
