"""Boundary examples for declared publication-lag proxy construction."""
from datetime import date

import pandas as pd
import pytest

from studies.sce_inflation_expectations.experiments.recent_b_rolling_preflight import (
    eligible_history, inferred_available_date, select_source_wave, make_people,
)


def test_nine_month_rule_is_month_end_based_and_handles_calendar_lengths():
    assert inferred_available_date(202501)==date(2025,10,31)
    assert inferred_available_date(202502)==date(2025,11,28)
    assert inferred_available_date(202405)==date(2025,2,28)
    assert inferred_available_date(202402)==date(2024,11,29)


def test_november_cutoff_does_not_assume_february_already_published():
    assert select_source_wave([202412,202501,202502,202503],
        '2025-11-13T23:59:59-05:00','202511')==202501


def test_current_target_and_not_yet_eligible_waves_are_excluded():
    assert select_source_wave([202501,202502,202511,202609],
        '2025-11-13T23:59:59-05:00','202511')==202501
    with pytest.raises(ValueError,match='No source wave'):
        select_source_wave([202502],'2025-11-13T23:59:59-05:00','202511')
    with pytest.raises(ValueError,match='Timezone'):
        select_source_wave([202501],'2025-11-13T23:59:59','202511')


def test_same_day_inferred_availability_is_conservatively_withheld():
    assert select_source_wave([202412,202501],'2025-10-31T23:59:59-04:00','202511')==202412


def test_latest_local_month_caps_coverage_without_fabricating_later_records():
    assert select_source_wave([202509,202510],'2026-09-11T23:59:59-04:00','202609')==202510


def test_newer_profile_records_cannot_change_earlier_eligible_projection():
    f=pd.DataFrame({'date':[202501,202502],'userid':[1,1],'income':[1,2]})
    first=eligible_history(f,202501)
    changed=f.copy();changed.loc[changed.date==202502,'income']=999
    pd.testing.assert_frame_equal(first,eligible_history(changed,202501))
    assert first.income.tolist()==[1]


def profile_row(month,job=None):
    d={'date':month,'userid':1,'weight':2.,'Q43':None,'D3':None,
       '_AGE_CAT':'Under 40','_EDU_CAT':'College','_HH_INC_CAT':'Under 50k',
       '_REGION_CAT':'Northeast','_STATE':'NY','_NUM_CAT':'High'}
    for i in range(1,11):d[f'Q10_{i}']=None if job is None else int(i==job)
    return d


def test_employment_carries_only_earlier_own_observation():
    f=pd.DataFrame([profile_row(202412,1),profile_row(202501),profile_row(202502,3)])
    people,weights,provenance=make_people(f,202501)
    assert people[0]['attributes']['employment_status']=='employed'
    assert provenance[people[0]['agent_id']]['employment_observed_month']==202412
    assert weights[people[0]['agent_id']]==2.
    assert 'init_state' not in people[0]


def test_missing_survey_weight_is_not_replaced_by_persona_default():
    r=profile_row(202501,1);r['weight']=None
    people,weights,_=make_people(pd.DataFrame([r]),202501)
    assert weights[people[0]['agent_id']] is None


def test_freeze_binds_the_actual_preparation_paths(tmp_path,monkeypatch):
    import json
    from studies.sce_inflation_expectations.experiments import recent_b_night as night
    monkeypatch.setattr(night,'ROOT',tmp_path)
    prior=tmp_path/'outputs/priors_v3';prior.mkdir(parents=True)
    (prior/'summary.json').write_text(json.dumps({'population_preflight':'outputs/population_v3'}))
    s={'population_preflight':'outputs/population_v3','prior_source':'outputs/priors_v3'}
    assert night.preparation_sources(s)==s
    with pytest.raises(ValueError,match='differ'):
        night.preparation_sources(dict(s,population_preflight='outputs/wrong_population'))
    with pytest.raises(ValueError,match='ignored'):
        night.preparation_sources(dict(s,population_preflight='../outside'))


def test_read_only_review_never_creates_authorization_or_sender(tmp_path,monkeypatch):
    from studies.sce_inflation_expectations.experiments import recent_b_night as night
    p={'months':['202511'],'n_per_month':512,'planned_calls':512,'maximum_physical_api_attempts':1024,
       'model':'test_no_live_model','route':'fixture','temperature':.5,'budget_cap_usd':8,
       'estimated_main_cost_usd':.3,'population_source_waves':{'202511':'202501'},
       'micro_availability_basis':'fixture_rule'}
    monkeypatch.setattr(night,'checked',lambda *a,**k:({'package':str(tmp_path/'package')},p,{}))
    monkeypatch.setattr(night,'live_sender',lambda *a:pytest.fail('No sender during review'))
    result=night.review(tmp_path)
    assert not result['authorization_exists'] and result['new_api_calls']==0
    assert list(tmp_path.iterdir())==[]


def test_prior_selection_rebases_recency_to_each_source_wave(tmp_path,monkeypatch):
    import json
    from pathlib import Path
    from studies.sce_inflation_expectations.experiments import recent_b_priors as priors
    code_snapshot=tmp_path/'recent_b_priors.py';code_snapshot.write_text(Path(priors.__file__).read_text())
    monkeypatch.setattr(priors,'__file__',str(code_snapshot))
    monkeypatch.setattr(priors,'ROOT',tmp_path)
    source=tmp_path/'outputs/source';source.mkdir(parents=True)
    def write(name,value):(source/name).write_text(json.dumps(value))
    write('summary.json',{'status':'offline_rolling_proxy_P_under_declared_release_lag_assumption',
                         'source_sha256':{},'source_snapshot_reference_max':'202502',
                         'source_public_known_by_utc':None,'availability_basis':'test_assumption'})
    write('monthly_input_plan.json',[{'month':'202511','old_population_reference_period':'202501',
         'availability_basis':'test_assumption','historical_byte_vintage_verified':False,
         'last_public_national_anchor':{'reference_period':'2025-10','value_pp':3.}}])
    write('selected_proxy_population_private.json',{'202511':[{'persona':{
        'agent_id':'proxy_test','attributes':{'age_group':'Under 40','education_group':'college',
                                              'household_income_band':'under_50k'}},'analysis_weight':1.}]})
    bins=[0.]*10;bins[3]=100.
    records=[{'date':m,'userid':100*m+i,'tenure':2,'weight':1.,'Q8v2part2':point,
              '_AGE_CAT':'Under 40','_EDU_CAT':'College','_HH_INC_CAT':'Under 50k',
              **{f'Q9_bin{j+1}':v for j,v in enumerate(bins)}}
             for m,point in [(202501,3.),(202502,99.)] for i in range(6)]
    pd.DataFrame(records).to_parquet(source/'old_joint_donor_pool_private.parquet',index=False)
    cache=tmp_path/'cache.json';cache.write_text(json.dumps([{'bins':bins,'score':{'mean':3.}}]))
    monkeypatch.setattr(priors,'CACHE',cache)
    output=tmp_path/'outputs/prior';result=priors.prepare(source,output)
    states=json.loads((output/'202511_initial_states_private.json').read_text())
    r=states['proxy_test']
    assert r['observed_donor_reference_period']=='202501' and r['q8_point_pct']==3.
    assert not r['historical_byte_vintage_verified'] and result['new_api_calls']==0
