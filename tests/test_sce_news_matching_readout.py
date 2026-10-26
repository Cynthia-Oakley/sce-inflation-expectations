from copy import deepcopy
import pytest

from studies.sce_inflation_expectations.evaluation.news_matching_readout import operational_view,summary,contrast


def test_operational_view_preserves_original_and_q8_independently():
    row=dict(real=dict(previous_q9_mean=3.,previous_q9_iqr=2.,previous_q9_zero_deflation=1.,
        previous_q9_bins=[0,0,0,100,0,0,0,0,0,0],previous_q8_point=5.),
        arms={'a':dict(mean=None,iqr=None,zero_deflation=None,q9_bins=[],point=7.)})
    original=deepcopy(row);out=operational_view([row],['a'])[0]
    assert row==original
    assert out['arms']['a']['mean']==3. and out['arms']['a']['point']==7.
    assert out['arms']['a']['q9_bins']==row['real']['previous_q9_bins']


def test_readout_uses_design_weights_for_median_not_unweighted_people():
    cases=[]
    for rep in (1,2):
        for uid,y,p,w in [(1,1.,1.,1.),(2,10.,20.,9.)]:
            cases.append(dict(month=202504,repeat=rep,userid=uid,survey_weight=w,
                real=dict(q9_mean=y,previous_q9_mean=y),arms={'a':dict(mean=p)}))
    result=summary(cases,['a'],[202504],[1,2],{(202504,1),(202504,2)})
    assert result['metrics']['a']['center_mae_pp']==10.
    assert result['metrics']['a']['w1_pp']==pytest.approx(9.)
    assert result['unique_persons']==2 and result['person_months']==2
    assert len(result['sparse_cells'])==2


def test_one_large_month_gain_cannot_pass_five_of_eight_screen():
    cells=[]
    for m in range(8):
        for rep in (1,2):
            base=dict(center_mae_pp=.2,w1_pp=2.,delta_w1_pp=1.)
            cand=dict(center_mae_pp=.2,w1_pp=0. if m==0 else 2.1,delta_w1_pp=1.)
            cells.append(dict(month=m,repeat=rep,arms={'base':base,'candidate':cand}))
    b=dict(center_mae_pp=.2,center_rmse_pp=.2,w1_pp=2.,delta_w1_pp=1.,across_person_iqr_pp=3.,personal_mae_pp=1.)
    c={**b,'w1_pp':1.8375}
    readout=dict(cells=cells,metrics={'base':b,'candidate':c})
    result=contrast(readout,readout,'base','candidate',True)
    assert result['screen_checks']['fixed_roster_mean_w1_lower']
    assert not result['screen_checks']['w1_nonworse_in_at_least_five_months']
    assert not result['development_screen_passed']


def test_missing_previous_q8_does_not_drop_current_q8_or_q9():
    import json
    from studies.sce_inflation_expectations.evaluation.news_matching_export import finish_operational
    cases=[]
    for rep in (1,2):
        for uid,priorpoint in [(1,None),(2,3.)]:
            real=dict(q9_mean=4.,q9_iqr=2.,q9_zero_deflation=1.,q8_point=4.,q9_bins=[0,0,0,100,0,0,0,0,0,0],
                previous_q9_mean=3.,previous_q9_iqr=1.,previous_q9_zero_deflation=1.,previous_q8_point=priorpoint,
                previous_q9_bins=[0,0,0,0,100,0,0,0,0,0])
            cases.append(dict(month=202504,repeat=rep,userid=uid,survey_weight=1.,real=real,
                arms={'a':dict(mean=4.,iqr=2.,zero_deflation=1.,q9_bins=real['q9_bins'],point=4.)}))
    original=deepcopy(cases)
    out=finish_operational(cases,dict(arms=['a'],months=[202504]))
    assert out['common_q9_person_months']==2 and out['common_q8_person_months']==2
    assert out['q8_baseline_comparable_person_months']==1
    assert out['primary_arms']['a']['q8']['aggregate_equal_month_repeat_cells']['q8_center_mae_pp']==0.
    json.dumps(out,allow_nan=False)
    assert cases==original
