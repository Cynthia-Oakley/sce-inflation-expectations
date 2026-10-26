import numpy as np
import pandas as pd
import pytest

from studies.sce_inflation_expectations.experiments.recent_b_priors import (
    balance_joint_draw, month_age, next_month, options_from_old_pool, prior_bands,
)
from studies.sce_inflation_expectations.population.entry_initialization import calibrate,draw


def old_pool():
    rows=[]
    for i in range(8):
        bins=[0.,0.,0.,0.,0.,0.,100.,0.,0.,0.]
        rows.append({'userid':i,'date':202408,'tenure':2,'weight':1.,
                     '_AGE_CAT':'Under 40','_EDU_CAT':'College','_HH_INC_CAT':'Under 50k',
                     '_point':100.+i,'_center':float(i), '_bins_valid':True,'_age_months':1,
                     **{f'Q9_bin{j}':v for j,v in enumerate(bins,1)}})
    return pd.DataFrame(rows)


def selected():
    return [{'persona':{'agent_id':'proxy_a','attributes':dict(age_group='Under 40',education_group='college',household_income_band='under_50k')},'analysis_weight':2.}]


def test_old_source_dates_are_not_target_previous_month_and_both_fields_synthetic():
    options=options_from_old_pool(old_pool(),selected(),source_max_month=202408)
    r=draw(options,'202511',20261024)[0]
    assert r['donor_period']==202408
    assert r['synthetic_fields']==['q8','q9'] and r['own_observed']=={}
    assert month_age(202511,r['donor_period'])==15
    assert 'not recent' in r['matching']['window_semantics']


def test_old_pool_guard_rejects_a_newer_observation():
    frame=old_pool();frame.loc[0,'date']=202510
    with pytest.raises(ValueError,match='Current/future'):
        options_from_old_pool(frame,selected(),source_max_month=202408)


def test_q9_anchor_never_becomes_a_q8_target_and_joint_draw_is_preserved():
    options=options_from_old_pool(old_pool(),selected(),source_max_month=202408)
    bands=prior_bands(options,3.)
    assert bands['q9']==[2.95,3.05] and bands['q8']==[99.,108.]
    result=calibrate(options,bands,max_ratio=4.)
    row=draw(options,'202511',20261024)[0]
    assert row['q8']==row['q9']+100
    assert row['q9_bins']==old_pool().iloc[0][[f'Q9_bin{i}' for i in range(1,11)]].tolist()
    assert result['min_probability_ratio']>=.25-1e-9
    assert result['max_probability_ratio']<=4+1e-9


def test_source_window_calendar_arithmetic():
    assert next_month(202412)==202501 and next_month(202408)==202409
    assert month_age('202609',202408)==25


def test_finite_assignment_keeps_weights_and_intact_joint_donors():
    # Independent synthetic assignments all start too low. The known-past
    # median constraint can be satisfied using each SAME donor pool.
    p=selected()*4
    for i,r in enumerate(p):
        p[i]={'persona':{**r['persona'],'agent_id':f'proxy_{i}'},'analysis_weight':1.}
    options=options_from_old_pool(old_pool(),p,source_max_month=202408)
    rows=draw(options,'202511',20261024)
    for r in rows:r.update(q8=100.,q9=0.,donor_period=202408)
    before=[r.copy() for r in rows]
    result,meta=balance_joint_draw(options,rows,[2.95,3.05],month='202511',seed=20261024)
    assert rows==before and [r['weight'] for r in result]==[1.]*4
    assert meta['status']=='finite_assignment_band_met' and meta['realized_median_pp']==3.
    assert all(r['q8']==r['q9']+100 for r in result)
    assert all(r['donor_period']==202408 for r in result)
    assert not meta['new_marginal_probability_ratio_bound_claimed']


def test_finite_assignment_reports_unreachable_band_without_numeric_clipping():
    options=options_from_old_pool(old_pool(),selected(),source_max_month=202408)
    rows=draw(options,'202511',20261024)
    result,meta=balance_joint_draw(options,rows,[20.,21.],month='202511',seed=20261024)
    assert result==rows and meta['status']=='finite_assignment_infeasible'
