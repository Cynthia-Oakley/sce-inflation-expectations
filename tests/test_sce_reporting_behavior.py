import numpy as np
import pandas as pd

from studies.sce_inflation_expectations.reporting_behavior.analysis import (
    classify,prepare,history_probabilities,loss_rows,fit_tables,predictions,
    cluster_interval,block_interval,
)


def fixture():
    rows=[]
    for person in (1,2):
        for date,prob in [(201701,[10,90]),(201702,[5,95]),(202201,[1,99])]:
            r={'userid':person,'date':date,'weight':1.,'Q9_iqr':2.,'Q9_mean':3.,
               '_AGE_CAT':'Under 40','_EDU_CAT':'College','_NUM_CAT':'High'}
            r.update({f'Q9_bin{k+1}':float(v) for k,v in enumerate(prob+[0]*8)})
            rows.append(r)
    return pd.DataFrame(rows)


def protocol():
    return {'train':[201701,201912],'table_min_rows':1,'table_min_persons':1,
            'table_prior_mass':20,'personal_prior_mass':3}


def test_grid_labels_and_invalid_sum():
    valid,labels=classify([[10,90]+[0]*8,[5,95]+[0]*8,[1,99]+[0]*8,[1,98]+[0]*8])
    assert labels.tolist()==[2,1,0,0]
    assert valid.tolist()==[True,True,True,False]


def test_history_strictly_excludes_current_answer_and_has_calendar_gap():
    d,_=prepare(fixture())
    assert d.past_n.tolist()==[0,1,2,0,1,2]
    assert d[['past_count_0','past_count_1','past_count_2']].iloc[:3].values.tolist()==[[0,0,0],[0,0,1],[0,1,1]]
    assert d.gap_months.iloc[2]==59


def test_personal_shrinkage_has_independent_expected_value():
    p=history_probabilities([[.2,.3,.5]],[[0,0,2]],3)
    np.testing.assert_allclose(p,[[.12,.18,.7]])


def test_brier_perfect_uniform_and_wrong():
    assert loss_rows([0],[[1,0,0]])[0]==0
    np.testing.assert_allclose(loss_rows([0],[[1/3]*3]),[1/3])
    assert loss_rows([0],[[0,1,0]])[0]==1


def test_target_and_future_answers_do_not_change_earlier_prediction():
    f=fixture()
    # Add third class to TRAIN only to satisfy support.
    f.loc[0,'Q9_bin1']=1.;f.loc[0,'Q9_bin2']=99.
    d,_=prepare(f); tables=fit_tables(d,protocol()); p=predictions(d,tables,protocol())
    altered=f.copy()
    altered.loc[altered.date==202201,'Q9_bin1']=50.
    altered.loc[altered.date==202201,'Q9_bin2']=50.
    other,_=prepare(altered); tables2=fit_tables(other,protocol()); q=predictions(other,tables2,protocol())
    assert tables==tables2
    for name in p:
        np.testing.assert_allclose(p[name],q[name])


def test_bootstrap_keeps_constant_paired_difference():
    d=pd.DataFrame({'userid':[1,1,2,2],'date':[202201,202202,202201,202202],'weight':[1.,2.,3.,4.]})
    a=cluster_interval(d,np.full(4,-.1),repetitions=20)
    np.testing.assert_allclose(a['interval_95'],[-.1,-.1])
    b=block_interval([-.1]*8,repetitions=20,block=3)
    np.testing.assert_allclose(b['interval_95'],[-.1,-.1])
