from copy import deepcopy

import pandas as pd
import pytest

from studies.sce_inflation_expectations.population.monthly_fine_grid import cell, prior_bands
from studies.sce_inflation_expectations.experiments.monthly_fine_inputs import choose


def frame():
    def a(edu, age):
        return {'education_group':edu,'numeracy':'high','age_group':age,'household_income_band':'under_50k'}
    people=[{'agent_id':str(i),'weight':1.,'attributes':a('college','Under 40')} for i in range(12)]
    people += [{'agent_id':'rare','weight':1.,'attributes':a('high_school','Over 60')},
               {'agent_id':'missing','weight':1.,'attributes':a('college','Under 40')}]
    return {'personas':people}, {'persons':[{'agent_id':p['agent_id'],'survey_entry_status':'returning'} for p in people]}, \
           {p['agent_id']:(None if p['agent_id']=='missing' else 1.+i) for i,p in enumerate(people)}, \
           {p['agent_id']:i for i,p in enumerate(people)}


def test_canonical_grid_matches_raw_and_delivered_fields():
    raw={'_EDU_CAT':'Some College','_NUM_CAT':'Low','_AGE_CAT':'40 to 60','_HH_INC_CAT':'50k to 100k'}
    delivered={'education_group':'some_college','numeracy':'low','age_group':'40 to 60','household_income_band':'50k_to_100k'}
    assert cell(raw)==cell(delivered)=='some_college|Low|40_60|50k_100k'
    assert cell({**delivered,'numeracy':None})=='unknown'


def test_real_probabilities_and_calibrated_masses_without_filling_missing_weight():
    p,e,w,identity=frame(); original=deepcopy(p)
    selected,plan,excluded=choose(p,e,w,budget=6,minimum=1,month=202206,identity=identity)
    assert excluded==['missing'] and p==original
    assert len(selected)==6 and all(r['persona']['weight']==1 for r in selected)
    for c,v in plan['cells'].items():
        rows=[r for r in selected if r['stratum']==c]
        assert sum(r['analysis_weight'] for r in rows)==pytest.approx(v['population_mass'])
        for r in rows:
            assert r['inclusion_probability']==v['selected_n']/v['frame_n']
            assert r['design_weight']==r['raw_survey_weight']/r['inclusion_probability']
    assert any(r['persona']['agent_id']=='rare' for r in selected)


def test_target_outcomes_and_source_demonstration_weights_do_not_select_people():
    p,e,w,identity=frame()
    expected,_,_=choose(p,e,w,budget=6,minimum=1,month=202206,identity=identity)
    for person in p['personas']:
        person['weight']=10000
        person['attributes']['current_q9_mean']=-10000
    actual,_,_=choose(p,e,w,budget=6,minimum=1,month=202206,identity=identity)
    assert [r['persona']['agent_id'] for r in expected]==[r['persona']['agent_id'] for r in actual]
    assert all('current_q9_mean' not in r['persona']['attributes'] for r in actual)


def test_past_census_exact_median_and_zero_width_tolerance():
    rows=pd.DataFrame([{'date':202205,'userid':i,'weight':1.,'_EDU_CAT':'College','_NUM_CAT':'High',
                       '_AGE_CAT':'Under 40','_HH_INC_CAT':'Under 50k','_point':v,'_center':v}
                      for i,v in enumerate([1.,2.,9.])])
    bands,refs,plan=prior_bands(rows,budget=3,minimum=1,seed=5,draws=8)
    assert bands=={'q8':[2.,2.],'q9':[2.,2.]}
    assert plan['budget']==3 and refs['q9']['past_reference']['median_pp']==2.
    with pytest.raises(ValueError):prior_bands(pd.concat([rows,rows]),budget=3,minimum=1,seed=5)
