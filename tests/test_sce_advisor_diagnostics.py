import pytest
from studies.sce_inflation_expectations.evaluation.advisor_diagnostics import (
    variance_parts,point_from_raw,point_metrics,grid_key,q8_summary,cell)


def test_weighted_variance_identity_including_unknown():
    p=variance_parts([0,2,10,12],[1,1,1,1],['a','a','unknown','unknown'])
    assert p['total_variance_pp2']==pytest.approx(26)
    assert p['within_grid_variance_pp2']==pytest.approx(1)
    assert p['between_grid_variance_pp2']==pytest.approx(25)
    assert p['groups']['unknown']['weight_share']==.5


def test_unequal_weights_and_shift_do_not_change_variance():
    a=variance_parts([0,2],[1,3],['a','a']);b=variance_parts([10,12],[1,3],['a','a'])
    assert a['total_variance_pp2']==pytest.approx(.75)
    assert a['total_variance_pp2']==b['total_variance_pp2']
    with pytest.raises(ValueError):variance_parts([0,2],[1,-1],['a','a'])


def test_negative_point_and_change_legal_independent_of_bad_q9():
    assert point_from_raw('{"point_pct":-2,"q9":{"bin1":-5}}','direct',3)==-2
    assert point_from_raw('{"point_revision_pp":-5,"q9_revision_pp":{"bin1":-99}}','revision',3)==-2


def test_missing_previous_uses_absolute_never_zero_imputed_prior():
    assert point_from_raw('```json\n{"point_pct":4}\n```','revision',None)==4
    with pytest.raises(ValueError):point_from_raw('{"point_revision_pp":1}','revision',None)
    with pytest.raises(ValueError):point_from_raw('{"point_pct":4}','revision',3)
    with pytest.raises(ValueError):point_from_raw('{"point_pct":true}','direct',3)


def test_missing_group_not_silently_assigned():
    assert grid_key({'profile':{'age_group':'Under 40','education_group':'college'}})=='Under 40|college'
    assert grid_key({'profile':{'age_group':None,'education_group':'college'}})=='unclassified'


def test_group_median_not_average_of_points_and_survey_weights_matter():
    rows=[{'truth':0,'direct':0,'previous':0,'survey_weight':1},
          {'truth':100,'direct':20,'previous':100,'survey_weight':3}]
    r=point_metrics(rows,'direct',True)
    assert r['center_pp']==20
    assert r['truth_center_pp']==100
    assert r['center_mae_pp']==80
    assert r['personal_mae_pp']==60


def test_q8_support_does_not_require_q9_and_repeats_not_people():
    rows=[dict(month=202004,repeat=r,agent_id='x',truth=3,previous=2,direct=4,revision=3,
               survey_weight=1,old_q9_common=False) for r in [1,2]]
    s=q8_summary(rows)
    assert s['q8_only_common']['generation_rows']==2
    assert s['q8_only_common']['person_months']==1
    assert s['q8_only_common']['equal_people']['metrics']['revision']['center_mae_pp']==0
    assert s['old_q9_common']['generation_rows']==0


def test_even_n_empirical_median_uses_original_unit_weights():
    rows=[{'truth':i,'direct':i,'previous':i,'survey_weight':1} for i in range(24)]
    assert point_metrics(rows,'direct',False)['center_pp']==11


def test_generations_scored_before_average_and_sparse_support_suppressed():
    rows=[]
    for i in range(10):
        v=float(i)
        rows.append({'paired_eligible':True,'design_survey_weight':1,
          'truth_mean_pp':v,'prior_mean_pp':v,'truth_density_iqr_pp':2,
          'model_repeats':{'1':{'mean':v+1,'iqr':2},'2':{'mean':v-1,'iqr':2}}})
    c=cell(rows,202003)
    assert c['model_average_of_repeat_metrics']['q9_center_mae_pp']==pytest.approx(1)
    assert c['model_average_of_repeat_metrics']['centered_w1_pp']==pytest.approx(0)
    assert cell(rows[:9],202003)['suppressed']
    rows[0]['design_survey_weight']=100
    assert cell(rows,202003)['support']=='weak'
