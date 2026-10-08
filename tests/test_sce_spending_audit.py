import numpy as np
import pandas as pd
import pytest
from studies.sce_inflation_expectations.spending_audit import SHARES,valid_baskets,join_core,historical_baskets,centered,ridge_predict,shuffled_baskets


def row(uid,month,shares):return {'userid':uid,'date':month,**dict(zip(SHARES,shares))}


def test_missing_zero_bad_sum_are_distinct():
 d=pd.DataFrame([row(1,202104,[100]+[0]*8),row(2,202104,[None]+[0]*8),row(3,202104,[90]+[0]*8),row(4,202104,[-1,101]+[0]*7)])
 v,c=valid_baskets(d)
 assert v.tolist()==[True,False,False,False]
 assert c=={'incomplete_n':1,'complete_out_of_range_n':1,'complete_in_range_bad_sum_n':1}


def test_past_basket_selection_no_future_and_age_limit():
 s=pd.DataFrame([row(1,202012,[100]+[0]*8),row(1,202104,[50,50]+[0]*7),row(1,202108,[60,40]+[0]*7),row(2,202012,[100]+[0]*8)])
 t=pd.DataFrame({'userid':[1,1,2],'date':[202105,202106,202105]})
 h=historical_baskets(s,t)
 assert h.date_basket.tolist()==[202104,202104] and h.basket_age_months.tolist()==[1,2]
 assert h.qsp5_1.tolist()==[50,50]
 with pytest.raises(ValueError):join_core(pd.concat([s,s.iloc[:1]]),t)


def test_centering_and_ridge_independent_known_solution():
 assert np.allclose(centered([1,3,10,14],[1,1,2,2],[1,3,1,1]),[-1.5,.5,-2,2])
 # Zero penalty recovers a known linear function and keeps train-only scaling.
 p=ridge_predict(np.array([[0.],[1.],[2.]]),[2,5,8],[1,1,1],np.array([[3.],[4.]]),alpha=0)
 assert np.allclose(p,[11,14])


def test_shuffle_preserves_complete_vectors_per_month():
 s=pd.DataFrame([row(i,m,[i,100-i]+[0]*7) for m in [202104,202108] for i in range(1,6)])
 q=shuffled_baskets(s)
 for m in [202104,202108]:
  assert sorted(map(tuple,s[s.date==m][SHARES].to_numpy()))==sorted(map(tuple,q[q.date==m][SHARES].to_numpy()))
 pd.testing.assert_frame_equal(q,shuffled_baskets(s))
