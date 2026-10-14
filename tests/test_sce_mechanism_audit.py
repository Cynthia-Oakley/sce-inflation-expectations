import unittest

import numpy as np
import pandas as pd

from studies.sce_inflation_expectations.evaluation.mechanism_audit import carry_gender_past_only, fit_month_wls


class MechanismAuditTest(unittest.TestCase):
    def test_absorption_equals_full_weighted_month_dummy_regression(self):
        rng=np.random.default_rng(731)
        n=90
        months=np.repeat(np.arange(3),30)
        persons=np.tile(np.arange(30),3)
        x=rng.normal(size=(n,2));w=rng.uniform(.2,3,n)
        y=1.3*x[:,0]-.7*x[:,1]+np.array([4,-3,2])[months]+rng.normal(size=n)
        result=fit_month_wls(y,x,w,months,persons,['a','b'])
        wn=w/np.bincount(months,weights=w)[months]*(n/3)
        full=np.column_stack([x,np.eye(3)[months]])
        expected=np.linalg.lstsq(full*np.sqrt(wn)[:,None],y*np.sqrt(wn),rcond=None)[0][:2]
        np.testing.assert_allclose([result['coefficients'][name]['estimate'] for name in ['a','b']],expected,rtol=0,atol=1e-12)
        self.assertEqual(result['persons'],30)
        self.assertEqual(result['rows'],90)

    def test_gender_is_not_backfilled_from_a_future_answer(self):
        frame=pd.DataFrame({'userid':[7,7,7,8],'date':[202001,202002,202003,202001],
                            'Q33':[np.nan,1,np.nan,2]})
        result=carry_gender_past_only(frame)
        self.assertTrue(pd.isna(result.iloc[0].gender))
        self.assertEqual(result.iloc[1].gender,'Female')
        self.assertEqual(result.iloc[2].gender_source_month,202002)


if __name__=='__main__':unittest.main()
