import unittest
from studies.sce_inflation_expectations.information_update_runtime import (
    publication_status, displayed_signals, transform, TIME_ROLE_BLOCK)
from studies.sce_inflation_expectations.behavior_prompt_blocks import ANCHOR_BLOCK
from studies.sce_inflation_expectations.evaluation.information_update import compare


class InformationUpdateTest(unittest.TestCase):
    def test_release_day_uses_new_york_and_keeps_same_day_ambiguous(self):
        cutoff = '2021-11-10T23:59:59-05:00'
        # 01:00 UTC is still the previous calendar day in New York.
        self.assertEqual(publication_status('2021-10-13T01:00:00Z', '2021-10-13', cutoff), 'earlier')
        self.assertEqual(publication_status('2021-10-13T08:30:00-04:00', '2021-10-13', cutoff), 'same-day uncertain')
        self.assertEqual(publication_status('2021-11-10T08:30:00-05:00', '2021-10-13', cutoff), 'later')
        with self.assertRaises(ValueError): publication_status('2021-11-11T08:30:00-05:00', '2021-10-13', cutoff)
        with self.assertRaises(ValueError): publication_status('2021-11-10T08:30:00', '2021-10-13', cutoff)

    def test_no_hidden_gasoline_yoy_value_added_to_time_index(self):
        rows = [{'signal_id': 'eia_gasoline_retail_regular_mean_2021_10', 'role': 'latest_release'},
                {'signal_id': 'eia_gasoline_retail_regular_yoy_2021_10', 'role': 'latest_release'}]
        self.assertEqual([r['signal_id'] for r in displayed_signals(rows)], [rows[0]['signal_id']])

    def test_transform_preserves_questionnaire_and_existing_facts(self):
        original = [{'role': 'user', 'content': 'Prices 6.2%.\nYour earlier survey response (2021-10):\n5%.\n' + ANCHOR_BLOCK + 'Question 1 (point estimate): unchanged.'}]
        index = 'Publication timing for the same information above:\nmetadata\n\n'
        for arm in ['new_wording', 'dated_information']:
            result = transform(original, arm, index)[0]['content']
            recovered = result.replace(TIME_ROLE_BLOCK, ANCHOR_BLOCK).replace(index, '')
            self.assertEqual(recovered, original[0]['content'])
            self.assertEqual(result.count('Prices 6.2%.'), 1)

    def test_primary_contrast_uses_new_B_C_not_old_A_value(self):
        rows = []
        for month in [202004, 202105]:
            for repeat in [1, 2]:
                for uid in range(6):
                    actual = 1 + uid * .4
                    rows.append({'month': month, 'repeat': repeat, 'userid': uid, 'common': True,
                                 'actual': actual, 'previous': actual - .2, 'reused_A': 100 + uid,
                                 'new_wording': actual + .7, 'dated_information': actual + .7,
                                 'copy_previous': actual - .2, 'history_anchor_half': actual - .1,
                                 'survey_weight': 1, 'actual_iqr': 3, 'actual_zero_deflation': 1,
                                 'previous_point': actual - .2, 'actual_point': actual})
        result = compare(rows, {'generation_repeats': [1, 2]}, draws=30)
        for value in result['primary_dated_minus_wording'].values():
            self.assertAlmostEqual(value['change_pp'], 0)
            self.assertEqual(value['paired_person_within_month_ci95_pp'], [0, 0])
        self.assertEqual(result['common_generation_rows'], 24)
        self.assertEqual(result['unique_common_person_months'], 12)


if __name__ == '__main__': unittest.main()
