import unittest
from collections import Counter

from studies.sce_inflation_expectations.purchase_frequency_matching import (
    frequency_vector, normalize_attributes, FrequencyAssigner, CATEGORIES)
from studies.sce_inflation_expectations.frequency_price_inputs import parse_row


class PurchaseFrequencyTest(unittest.TestCase):
    def test_distinct_days_and_missing_day_are_not_transactions_or_zero(self):
        rows = [{'UCC': '330110', 'PUB_FLAG': '2', 'COST': '3', 'EXPNSQDY': '2', 'EXPN_QDY': 'D'},
                {'UCC': '330110', 'PUB_FLAG': '2', 'COST': '4', 'EXPNSQDY': '2', 'EXPN_QDY': 'D'}]
        mapping = {'330110': 'household_cleaning_paper'}
        result = frequency_vector(rows, mapping)
        self.assertEqual(result['household_cleaning_paper']['recorded_days_7d'], 1)
        rows.append({'UCC': '330110', 'PUB_FLAG': '2', 'COST': '4', 'EXPNSQDY': '', 'EXPN_QDY': ''})
        result = frequency_vector(rows, mapping)
        self.assertIsNone(result['household_cleaning_paper']['recorded_days_7d'])
        self.assertEqual(result['household_cleaning_paper']['status'], 'partial_support')

    def test_income_comes_from_diary_field_and_preserves_approximate_bands(self):
        row = {'FINCBEFM': '85000', 'AGE_REF': '60', 'EDUC_REF': '15', 'CUTENURE': '4', 'REGION': '3'}
        result = normalize_attributes(row)
        self.assertEqual(result['household_income_band'], '50k_to_100k')
        self.assertEqual(result['housing_tenure'], 'renter')
        self.assertEqual(result['age_group'], '40 to 60')

    def test_excluded_only_records_are_not_zero_frequency(self):
        rows = [{'UCC': '640110', 'PUB_FLAG': '1', 'COST': '5', 'EXPNSQDY': '2', 'EXPN_QDY': 'D'}]
        result = frequency_vector(rows, {'640110': 'personal_care_products'})
        self.assertEqual(result['personal_care_products']['status'], 'excluded_only')
        self.assertIsNone(result['personal_care_products']['recorded_days_7d'])

    def test_cu_first_draw_does_not_double_weight_two_week_household(self):
        def week(cu, n):
            return {'week_key': f'{cu}-{n}', 'week_number': n, 'weight': 1,
                    'categories': {k: {'recorded_days_7d': n} for k in CATEGORIES}}
        donors = [{'cu_key': 'a', 'weight': 1, 'attributes': {}, 'weeks': [week('a', 1), week('a', 2)]},
                  {'cu_key': 'b', 'weight': 1, 'attributes': {}, 'weeks': [week('b', 1)]}]
        assigner = FrequencyAssigner(donors, min_units=2, min_effective_units=1)
        counts = Counter(assigner.assign(str(i), {})['cu_key'] for i in range(1000))
        self.assertTrue(450 <= counts['a'] <= 550)  # Raw-week sampling would be about two thirds.
        for i in range(10):
            assigned = assigner.assign(str(i), {})
            self.assertEqual(len(set(assigned['recorded_days_7d'].values())), 1)
        self.assertEqual(assigner.assign('stable', {})['week_key'],
                         assigner.assign('stable', {'numeracy': 'low', 'employment_status': 'unemployed'})['week_key'])

    def test_table_two_annual_and_monthly_columns_are_distinct(self):
        row = parse_row('Housekeeping supplies1. . . . 0.877 1.7 0.7 -0.3 0.4 0.7', 'Housekeeping supplies')
        self.assertEqual(row['yoy_nsa_pct'], 1.7)
        self.assertEqual(row['mom_nsa_pct'], .7)
        with self.assertRaises(ValueError): parse_row('Housekeeping supplies1. . . 0.877 1.7 0.7', 'Housekeeping supplies')

    def test_week_specific_income_match_is_preserved_within_one_CU(self):
        def week(n, band):
            return {'week_key': str(n), 'week_number': n, 'weight': 1,
                    'attributes': {'household_income_band': band},
                    'categories': {k: {'recorded_days_7d': n} for k in CATEGORIES}}
        donor = {'cu_key': 'same-cu', 'weight': 1, 'attributes': {},
                 'weeks': [week(1, 'under_50k'), week(2, 'over_100k')]}
        assigner = FrequencyAssigner([donor], min_units=1, min_effective_units=1)
        low = assigner.assign('person', {'household_income_band': 'under_50k'})
        high = assigner.assign('person', {'household_income_band': 'over_100k'})
        self.assertEqual(low['week_number'], 1)
        self.assertEqual(high['week_number'], 2)
        self.assertEqual(low['pool_unique_units'], 1)


if __name__ == '__main__': unittest.main()
