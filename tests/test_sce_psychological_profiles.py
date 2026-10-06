import unittest
import subprocess,sys
from pathlib import Path
import pandas as pd
from studies.sce_inflation_expectations.psychological_profiles import build_sidecars,candidate_text

class PsychologicalProfilesTest(unittest.TestCase):
 def setUp(self):
  self.p=pd.DataFrame({'date':[202105,202106,202105],'userid':[1,1,2],'Q1':[3,2,4], '_AGE_CAT':['Under 40']*3,'_EDU_CAT':['College']*3,'_HH_INC_CAT':['Under 50k','Under 50k',None],'_REGION_CAT':['West']*3})
  self.d=pd.DataFrame({'id':[10,20], 'happy':[1,3],'satfin':[1,3], 'donor_weight':[1.,1.], '_AGE_CAT':['Under 40']*2,'_EDU_CAT':['College']*2,'_HH_INC_CAT':['Under 50k']*2,'_REGION_CAT':['West','South']})
 def test_joint_row_stability_and_region_only_fallback(self):
  rows=build_sidecars(self.p,self.d,min_ess=2,source_hash='test')
  assigned=[r for r in rows if r['agent_id']=='sce_u1']
  self.assertEqual(assigned[0]['donor_local_id'],assigned[1]['donor_local_id'])
  self.assertEqual(assigned[0]['fallback_tier'],1)
  self.assertIn(assigned[0]['psychological_attributes'],[{'HAPPY':1,'SATFIN':1},{'HAPPY':3,'SATFIN':3}])
  missing=next(r for r in rows if r['agent_id']=='sce_u2');self.assertEqual(missing['support_status'],'unsupported')
 def test_order_and_role_do_not_change_assignment(self):
  a=build_sidecars(self.p,self.d,min_ess=2,source_hash='test')
  p=self.p.iloc[::-1].copy();p['population_role']='normal'
  b=build_sidecars(p,self.d.iloc[::-1],min_ess=2,source_hash='test')
  self.assertEqual(a,b)
 def test_cli_rejects_invalid_provenance_before_reading_files(self):
  root=Path(__file__).resolve().parents[1]
  r=subprocess.run([sys.executable,str(root/'scripts/build_sce_psychological_profiles.py'),'--profiles','missing.jsonl','--donors','missing.jsonl','--source-hash','a','--role-root','missing'],capture_output=True,text=True)
  self.assertEqual(r.returncode,2);self.assertIn('actual SHA-256',r.stderr)
 def test_preview_has_no_identifiers_or_targets(self):
  row=build_sidecars(self.p,self.d,min_ess=2,source_hash='test')[0]
  text=candidate_text(row)
  for forbidden in ['sce_u','Q9','Q8','donor','weight']:self.assertNotIn(forbidden,text)
  self.assertIn('financial position',text)
if __name__=='__main__':unittest.main()
