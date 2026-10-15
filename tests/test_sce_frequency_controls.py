import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).resolve().parents[1]/'studies/sce_inflation_expectations/evaluation/frequency_controls.py'
spec=importlib.util.spec_from_file_location('frequency_controls',path)
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


class ControlAnalysisMathTest(unittest.TestCase):
    def test_generation_averaging_does_not_cancel_absolute_errors(self):
        self.assertEqual(module.average_absolute_error([0,4],2),2)

    def test_center_identity_uses_separate_medians(self):
        result=module.center_bridge([0,2,100],[0,3,4],[1,5,7],[2,3,9])
        self.assertEqual(result['q9_signed_error'],-3)
        self.assertEqual(result['q8_signed_error'],0)
        self.assertEqual(result['density_point_gap_error'],-3)
        self.assertEqual(module.quantile([1,2,3,4],.5),2)

    def test_variance_decomposition_with_unequal_group_sizes(self):
        result=module.variance_parts([0,2,4,4,4],['a','a','b','b','b'])
        self.assertAlmostEqual(result['between_month_variance']+result['within_month_variance'],result['total_variance'])
        self.assertAlmostEqual(result['between_month_share']+result['within_month_share'],1)


if __name__=='__main__':unittest.main()
