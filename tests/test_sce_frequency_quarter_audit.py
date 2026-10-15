import unittest
from unittest.mock import patch
import numpy as np

from studies.sce_inflation_expectations.evaluation.frequency_quarter_audit import (
    cu_first_probabilities, distribution, pool_for_profile, dictionary_checks,
)


class QuarterAuditMathTest(unittest.TestCase):
    def test_cu_then_week_probabilities_use_mean_cu_weight(self):
        rows=[{'cu_key':'a','weight':2},{'cu_key':'a','weight':4},{'cu_key':'b','weight':3}]
        p,n,effective=cu_first_probabilities(rows)
        np.testing.assert_allclose(p,[1/6,1/3,1/2])
        self.assertEqual(n,2);self.assertAlmostEqual(effective,2)

    def test_supported_zero_changes_distribution_without_becoming_missing(self):
        rows=[{'cu_key':'a','weight':1,'days':[0,0,0,0]},
              {'cu_key':'b','weight':1,'days':[2,4,6,2]}]
        d=distribution(rows)
        self.assertAlmostEqual(d['food_at_home']['mean_days'],1)
        self.assertAlmostEqual(d['food_at_home']['zero_share'],.5)
        self.assertAlmostEqual(sum(d['food_at_home']['day_probabilities']),1)

    def test_sparse_housing_fallback_preserves_income_age(self):
        attrs={'household_income_band':'under_50k','age_group':'Under 40'}
        rows=[{'cu_key':str(i),'weight':1,'days':[1,0,0,0],
               'attributes':{**attrs,'housing_tenure':'owner' if i<2 else 'renter'}} for i in range(26)]
        sub,p,receipt=pool_for_profile(rows,{**attrs,'housing_tenure':'owner'})
        self.assertEqual(receipt['matched_fields'],['household_income_band','age_group'])
        self.assertEqual(len(sub),26);self.assertAlmostEqual(sum(p),1)

    def test_official_dictionary_tuple_rows_are_read(self):
        codes=[('DIARY','FMLD','CUTENURE',str(i),'label',1998,1,None,None) for i in range(1,7)]
        with patch('studies.sce_inflation_expectations.evaluation.frequency_quarter_audit._xlsx_sheet_rows',
                   side_effect=[[],codes]):
            result=dictionary_checks('not_read')
        self.assertEqual(set(result['tenure_codes_2020']),set('123456'))


if __name__=='__main__':unittest.main()
