"""Known copying/update and contrast arithmetic, not model predictions."""
import unittest
from studies.sce_inflation_expectations.prior_belief_analysis import copying_and_updates, evaluate_rows


class PriorAnalysisTests(unittest.TestCase):
    def rows(self):
        return [{'real': x, 'no_prior': x-1, 'own_previous': x, 'permuted_previous': x+.5,
                 'own_prior': x-2, 'profile': {'age_group': 'Under 40'},
                 'raw_answers': {'own_previous': [10.]*10},
                 'supplied_priors': {'own_previous': [10.]*10}} for x in (2., 3., 4.)]

    def test_exact_copy_and_center_update_are_distinct(self):
        result = copying_and_updates(self.rows(), 'own_previous')
        self.assertEqual(result['supplied_prior_raw_copying']['exact_copy_n'], 3)
        self.assertEqual(result['update_MAE_pp'], 0.)
        self.assertEqual(result['mean_signed_update_pp'], 2.)
        self.assertEqual(result['update_sign_agreement'], 1.)

    def test_inverse_primary_contrast_and_same_sample_persistence(self):
        rows = self.rows() + [{'real': 99., 'no_prior': 0., 'own_previous': None, 'permuted_previous': 2.,
                              'own_prior': 99., 'profile': {'age_group': 'Under 40'}}]
        result = evaluate_rows(rows, bootstrap=20)
        self.assertEqual(result['n_common'], 3)
        self.assertEqual(result['prior_persistence_common_sample']['distribution_W1_pp'], 2.)
        c = result['contrasts']['own_previous_minus_permuted_previous']['median_absolute_error_pp']
        self.assertEqual(c['change_pp'], -.5)
        self.assertEqual(c['paired_person_bootstrap_95_interval_pp'], [-.5, -.5])


if __name__ == '__main__':
    unittest.main()
