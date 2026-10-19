import numpy as np
import pandas as pd
import pytest

from studies.sce_inflation_expectations.evaluation.atus_roles import join_role_files, smoothed_role_probabilities, weighted_scores


def test_eh_join_excludes_other_household_people_and_rejects_duplicate_matches():
    eh=pd.DataFrame({'TUCASEID':['a'],'TULINENO':[1]})
    resp=eh.assign(TELFS=1,TRNUMHOU=2,TRCHILDNUM=0)
    cps=pd.DataFrame({'TUCASEID':['a','a'],'TULINENO':[1,2], 'PEEDUCA':[43,39],'HEFAMINC':[14,14],'GEREG':[1,1]})
    roster=pd.DataFrame({'TUCASEID':['a','a'],'TULINENO':[1,2],'TEAGE':[40,90],'TESEX':[1,2]})
    result=join_role_files(eh,resp,cps,roster)
    assert len(result)==1 and result.TEAGE.iloc[0]==40
    with pytest.raises(pd.errors.MergeError):
        join_role_files(eh,resp,pd.concat([cps,cps.iloc[:1]]),roster)


def test_sparse_cells_shrink_to_training_prior_and_weighted_scores():
    train=pd.DataFrame({'g':['seen','other'],'EUGROSHP2':[1,5],'EUFINLWGT':[1.,3.]})
    p,n=smoothed_role_probabilities(train,pd.DataFrame({'g':['missing','seen']}),['g'],alpha=20)
    base=np.array([.25,0,0,0,.75])
    assert np.allclose(p[0],base) and n.tolist()==[0,1]
    assert np.allclose(p[1],(np.array([1,0,0,0,0])+20*base)/21)
    q=np.array([[.8,.2],[.1,.9]])
    score=weighted_scores([0,1],q,[1,3])
    assert np.isclose(score['log_loss'],(-np.log(.8)-3*np.log(.9))/4)
    assert np.isclose(score['brier'],(.08+3*.02)/4)
