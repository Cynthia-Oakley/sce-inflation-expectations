import unittest
import numpy as np
import pandas as pd
from studies.sce_inflation_expectations.household_state_audit import weighted_quantile, classify_numeracy, gss_income, gss_education, audit_support

class HouseholdAuditTest(unittest.TestCase):
 def test_quantile_modes_and_invalid_weights(self):
  self.assertEqual(weighted_quantile([0,10],[1,3]),10)
  self.assertAlmostEqual(weighted_quantile([0,0,10],[1,2,1],interpolate=True),2.5)
  self.assertEqual(weighted_quantile([float('nan'),4,9],[1,2,0]),4)
 def test_numeracy_five_original_questions_and_missing(self):
  d=pd.DataFrame({'QNUM1':[150,150,150,None],'QNUM2':[242,242,242,242], 'QNUM3':[10,10,10,10],'QNUM5':[100,100,0,100],'QNUM6':[5,0,0,5], 'QNUM8':[1,1,1,1]})
  c,valid=classify_numeracy(d)
  self.assertEqual(c[:3].tolist(),['High','High','Low']);self.assertFalse(valid.iloc[3]);self.assertTrue(pd.isna(c.iloc[3]))
 def test_income_boundary_not_midpoint_imputed(self):
  self.assertEqual(gss_income(18),'Under 50k');self.assertEqual(gss_income(19),'50k to 100k');self.assertIsNone(gss_income(22));self.assertEqual(gss_income(23),'Over 100k')
 def test_education_some_college_without_degree(self):
  self.assertEqual(gss_education(1,14),'Some College');self.assertEqual(gss_education(1,12),'High School');self.assertEqual(gss_education(3,16),'College')
 def test_support_missing_pool_and_effective_n(self):
  t=pd.DataFrame({'a':['x','y'],'weight':[1.,3.]});d=pd.DataFrame({'a':['x','x'],'donor_weight':[1.,3.]})
  r=audit_support(t,d,['a']);self.assertEqual(r['target_zero_support_n'],1);self.assertAlmostEqual(r['cells'][0]['donor_ess'],1.6)
if __name__=='__main__':unittest.main()
