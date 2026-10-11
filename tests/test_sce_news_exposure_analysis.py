import unittest

from studies.sce_inflation_expectations.news_exposure_analysis import describe, metrics


class TestNewsEvaluation(unittest.TestCase):
    def rows(self):
        return [dict(real=x, shared=5., random=x+1., matched=x,
                     evaluation_weight=10. if x == 7 else 1.,
                     profile={'housing_tenure': 'renter', 'numeracy': 'High'}) for x in (1., 3., 5., 7.)]

    def test_center_distribution_and_width_are_distinct(self):
        out = metrics(self.rows(), bootstrap=20)
        self.assertEqual(out['real']['median_pp'], 3.)
        self.assertEqual(out['arms']['random']['median_absolute_error_pp'], 1.)
        self.assertEqual(out['arms']['matched']['distribution_W1_pp'], 0.)
        self.assertEqual(out['arms']['random']['distribution_W1_pp'], 1.)
        self.assertEqual(out['arms']['shared']['IQR_absolute_gap_pp'], 3.)
        self.assertEqual(out['matched_minus_random']['distribution_W1_pp']['change_pp'], -1.)
        self.assertEqual(out['arms']['matched']['survey_weighted_auxiliary']['real']['weighted_median_pp'], 7.)
        self.assertIn('High', out['arms']['matched']['groups']['numeracy'])

    def test_every_arm_uses_same_common_cases(self):
        rows = self.rows()
        rows[0]['matched'] = None
        out = metrics(rows, bootstrap=20)
        self.assertEqual(out['n_common'], 3)
        self.assertEqual(out['n_excluded'], 1)
        self.assertTrue(all(a['distribution']['n'] == 3 for a in out['arms'].values()))
        self.assertIsNone(out['arms']['matched']['groups']['housing_tenure']['renter']['median_absolute_error_pp'])

    def test_point_uses_existing_interpolated_contract(self):
        self.assertEqual(describe([1., 3., 5., 7.], point=True)['median_pp'], 4.)
        self.assertEqual(describe([1., 3., 5., 7.])['median_pp'], 3.)

    def test_empty_does_not_create_success(self):
        out = metrics([], bootstrap=20)
        self.assertEqual(out['n_common'], 0)
        self.assertIsNone(out['arms']['matched']['median_absolute_error_pp'])
        self.assertEqual(out['matched_minus_random'], {})

    def test_missing_group_remains_unknown(self):
        rows = self.rows()
        rows[0]['profile']['housing_tenure'] = None
        out = metrics(rows, bootstrap=20)
        self.assertIn('unknown', out['arms']['matched']['groups']['housing_tenure'])


if __name__ == '__main__':
    unittest.main()
