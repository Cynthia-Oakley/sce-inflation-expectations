import importlib.util
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

p=Path(__file__).resolve().parents[1]/'studies/sce_inflation_expectations/evaluation/coverage_age_audit.py'
spec=importlib.util.spec_from_file_location('coverage_age_audit',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


class CoverageAuditTest(unittest.TestCase):
    def test_household_excludes_nonrelatives_and_counts_children(self):
        r={f'Q45new_{i}':0 for i in range(1,10)}
        r.update(Q45new_1=1,Q45new_4=2,Q45new_8=3)
        v=m.family(r)
        self.assertEqual(v['members_including_self_excluding_nonrelatives'],4)
        self.assertEqual(v['children_under18'],2)
        self.assertEqual(v['nonrelatives_excluded'],3)

    def test_alone_flag_is_not_a_person_or_compatible_with_other_residents(self):
        r={f'Q45new_{i}':0 for i in range(1,10)};r['Q45new_9']=1
        self.assertEqual(m.family(r)['members_including_self_excluding_nonrelatives'],1)
        r['Q45new_1']=1;self.assertIsNone(m.family(r))

    def test_missing_is_not_zero(self):
        r={f'Q45new_{i}':0 for i in range(1,10)};r['Q45new_1']=1;del r['Q45new_8']
        self.assertIsNone(m.family(r));self.assertIsNone(m.integer('',1,11))

    def test_only_strictly_previous_month_features_are_used(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'links.json';path.write_text(json.dumps([{'month':202004,'userid':1,'agent_id':'a','profile':{'household_income_band':'50k_to_100k'}}]))
            rows=[{'userid':1,'date':202003,'Q47':6},{'userid':1,'date':202004,'Q47':9},{'userid':1,'date':202005,'Q47':11}]
            with patch.object(m,'LINK',path),patch.object(m,'SOURCES',[Path('fake')]),patch.object(m,'selected_rows',return_value=iter(rows)):
                private,summary=m.coverage()
        self.assertEqual(private[0]['features']['fine_income']['value'],6)
        self.assertEqual(private[0]['features']['fine_income']['source_month'],202003)
        self.assertEqual(summary['overall']['fine_income']['coarse_income_agrees'],1)


if __name__=='__main__':unittest.main()
