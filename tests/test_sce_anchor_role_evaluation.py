import unittest

import numpy as np
from scipy.stats import wasserstein_distance

from studies.sce_inflation_expectations.evaluation.anchor_role import compare_cases


def examples(shift):
    cases=[]
    for month in [202004,202105]:
        for repeat in [1,2]:
            for uid in range(6):
                actual=1+uid*.4
                cases.append({'month':month,'repeat':repeat,'userid':uid,'common':True,
                    'actual':actual,'previous':actual-.2,'original':actual+.7,'belief_start':actual+.7+shift,
                    'copy_previous':actual-.2,'history_anchor_half':actual-.1,'survey_weight':1,
                    'actual_iqr':3,'actual_zero_deflation':1,'previous_point':actual-.2,'actual_point':actual})
    return cases


class AnchorRoleEvaluationTest(unittest.TestCase):
    def test_identical_answers_have_zero_paired_contrast_and_intervals(self):
        result=compare_cases(examples(0),{'generation_repeats':[1,2]},draws=50)
        for value in result['belief_start_minus_original'].values():
            self.assertAlmostEqual(value['change_pp'],0,places=12)
            np.testing.assert_allclose(value['paired_person_within_month_ci95_pp'],[0,0],atol=1e-12)
        self.assertEqual(result['unique_common_person_months'],12)
        self.assertEqual(result['common_generation_rows'],24)
        self.assertEqual(result['distinct_people'],6)

    def test_distribution_change_agrees_with_independent_scipy_distance(self):
        cases=examples(-.3)
        result=compare_cases(cases,{'generation_repeats':[1,2]},draws=50)
        block=[r for r in cases if r['month']==202004 and r['repeat']==1]
        expected=wasserstein_distance([r['belief_start'] for r in block],[r['actual'] for r in block])-wasserstein_distance([r['original'] for r in block],[r['actual'] for r in block])
        self.assertAlmostEqual(result['belief_start_minus_original']['cross_section_w1_pp']['change_pp'],expected,places=12)


if __name__=='__main__':unittest.main()
