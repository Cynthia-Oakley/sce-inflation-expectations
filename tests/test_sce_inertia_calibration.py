"""Independent arithmetic, release-day boundaries and dispersion semantics."""
import unittest
import numpy as np
from studies.sce_inflation_expectations.evaluation.inertia_calibration_diagnostic import blend, forecast_metrics, latest_public_release


class InertiaTests(unittest.TestCase):
    def test_fixed_weight_and_persistence_endpoints(self):
        self.assertEqual(blend(5., 3., .4), 4.2)
        self.assertEqual(blend(5., 3., 0.), 5.)
        self.assertEqual(blend(5., 3., 1.), 3.)
        for w in (-.1, 1.1, float('nan')):
            with self.assertRaises(ValueError): blend(5., 3., w)

    def test_known_error_moments(self):
        s = forecast_metrics([3., 7.], [4., 5.])
        self.assertEqual(s['mae_pp'], 1.5)
        self.assertAlmostEqual(s['rmse_pp'], np.sqrt(2.5))
        self.assertEqual(s['bias_pp'], .5)
        self.assertEqual(s['error_variance_pp_squared_ddof0'], 2.25)

    def test_publication_date_not_observation_period_controls_availability(self):
        releases = [{'reference_period': '2022-01', 'published_date': '2022-02-14', 'value_pp': 5.8},
                    {'reference_period': '2022-02', 'published_date': '2022-03-14', 'value_pp': 6.0}]
        self.assertEqual(latest_public_release(releases, '2022-03-10T23:59:59-05:00')['reference_period'], '2022-01')
        self.assertEqual(latest_public_release(releases, '2022-03-14T23:59:58-04:00')['reference_period'], '2022-01')
        self.assertEqual(latest_public_release(releases, '2022-03-14T23:59:59-04:00')['reference_period'], '2022-02')

    def test_aggregate_blend_is_not_personwise_belief_blending(self):
        prior, predicted = np.array([0., 0., 100.]), np.array([0., 100., 100.])
        aggregate = blend(float(np.median(predicted)), float(np.median(prior)), .4)
        personwise = np.median(.4 * prior + .6 * predicted)
        self.assertEqual(aggregate, 60.)
        # Choose asymmetric arrays to make the nonlinearity visible.
        prior, predicted = np.array([0., 100., 100.]), np.array([100., 0., 100.])
        self.assertEqual(blend(float(np.median(predicted)), float(np.median(prior)), .4), 100.)
        self.assertEqual(np.median(.4 * prior + .6 * predicted), 60.)

    def test_location_shift_keeps_people_variance_but_ensemble_reduces_generation_noise(self):
        values = np.array([1., 2., 5.])
        self.assertAlmostEqual(np.var(values), np.var(values + 3.2))
        self.assertAlmostEqual(np.var([blend(x, 3., .4) for x in values]), .36 * np.var(values))


if __name__ == '__main__':
    unittest.main()
