import unittest

from studies.sce_inflation_expectations.evaluation.purchase_frequency import compare


class FrequencyEvaluationTest(unittest.TestCase):
    def test_equal_arms_have_zero_paired_contrasts_and_correct_baseline_errors(self):
        rows = []
        for repeat in [1, 2]:
            for i, previous in enumerate([2.0, 4.0]):
                actual = previous + 1.0
                rows.append({'month': 202105, 'repeat': repeat, 'userid': i,
                             'actual': actual, 'previous': previous, 'actual_iqr': 2.0,
                             'actual_zero_deflation': 1.0, 'actual_point': actual,
                             'previous_point': previous, 'survey_weight': 1.0,
                             'frequency_data': actual, 'frequency_rule': actual,
                             'frequency_data_point': actual, 'frequency_rule_point': actual,
                             'copy_previous': previous, 'history_anchor_half': previous,
                             'reused_C': actual, 'reused_C_point': actual, 'common': True})
        result = compare(rows, {'generation_repeats': [1, 2]}, draws=50)
        self.assertEqual(result['common_generation_rows'], 4)
        self.assertEqual(result['unique_common_person_months'], 2)
        for value in result['frequency_rule_minus_data'].values():
            self.assertEqual(value['change_pp'], 0)
            self.assertEqual(value['paired_person_within_month_ci95_pp'], [0, 0])
        baseline = result['results']['copy_previous']['aggregate']
        for key in ['sample_center_mae_pp', 'cross_section_w1_pp', 'delta_w1_pp']:
            self.assertEqual(baseline[key], 1.0)


if __name__ == '__main__':
    unittest.main()
