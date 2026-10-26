from copy import deepcopy
import unittest

import numpy as np
import pandas as pd

from studies.sce_inflation_expectations.population.entry_initialization import (
    EntryConfig, build_options, calibrate, donor_candidates, draw, score_past,
)


def record(uid, month=202504, tenure=1, point=3., center=3., **extra):
    return dict(userid=uid, date=month, tenure=tenure, weight=1.,
                Q8v2part2=point, _point=point, _center=center, _bins_valid=True,
                _age_months=2025 * 12 + 4 - (month // 100 * 12 + month % 100 - 1),
                _AGE_CAT='Under 40', _EDU_CAT='College', _HH_INC_CAT='Under 50k',
                **{f'Q9_bin{i}': 100. if i == 6 else 0. for i in range(1, 11)}, **extra)


PROFILE = {'age_group': 'Under 40', 'education_group': 'college', 'household_income_band': 'under_50k'}


def recipient(uid=99, weight=1.):
    return dict(agent_id=f'person{uid}', userid=uid, profile=PROFILE, weight=weight, donor_type='entrant')


def small_options(probabilities=(.6, .4), fixed=False):
    p = np.array(probabilities)
    return {'agent_id': 'a', 'weight': 1., 'q8': np.array([-1., 1.]),
            'q9': np.array([-1., 1.]), 'p0': p, 'p': p.copy()}


class RecentEntryTests(unittest.TestCase):
    def test_past_guard_rejects_before_scoring(self):
        with self.assertRaises(ValueError):
            score_past(pd.DataFrame([record(1, month=202505)]), 202505)

    def test_sparse_exact_cell_relaxes_demographics_before_time(self):
        rows = [record(i) for i in range(8)]
        for r in rows[1:]:
            r['_EDU_CAT'] = 'High School'
        rows += [record(50+i, month=202503) for i in range(20)]
        pool, p, meta = donor_candidates(pd.DataFrame(rows), 202505, PROFILE)
        self.assertEqual(meta['window_months'], 1)
        self.assertEqual(meta['matched_columns'], ['_AGE_CAT', '_HH_INC_CAT'])
        self.assertEqual(len(pool), 8)
        np.testing.assert_allclose(p, np.full(8, 1/8))

    def test_three_month_fallback_is_explicit_and_never_crosses_years(self):
        frame = pd.DataFrame([record(i, month=202503) for i in range(8)] + [record(500, month=202101)])
        _, _, meta = donor_candidates(frame, 202505, PROFILE)
        self.assertEqual(meta['window_months'], 3)
        self.assertEqual(meta['max_age_months'], 2)
        with self.assertRaises(ValueError):
            donor_candidates(frame.loc[frame.userid.eq(500)], 202505, PROFILE)

    def test_survey_weights_enter_draw_once(self):
        rows = [record(i) for i in range(8)]
        rows[0]['weight'] = 2.
        _, p, _ = donor_candidates(pd.DataFrame(rows), 202505, PROFILE)
        self.assertAlmostEqual(p[0], 2/9)
        self.assertAlmostEqual(sum(p), 1.)

    def test_recent_own_partial_field_is_immutable_joint_donor_for_missing(self):
        rows = [record(i, point=float(i), center=float(i)) for i in range(1, 9)]
        own = record(99, tenure=2, point=12.)
        own['_bins_valid'] = False
        frame = pd.DataFrame(rows + [own]); original = frame.copy(deep=True)
        options = build_options(frame, [recipient()], 202505)
        output = draw(options, 202505, 7)
        self.assertEqual(output[0]['q8'], 12.)
        self.assertEqual(output[0]['weight'], 1.)
        self.assertEqual(output[0]['synthetic_fields'], ['q9'])
        self.assertEqual(output[0]['own_observed']['q8']['source_period'], 202504)
        pd.testing.assert_frame_equal(frame, original)

    def test_stale_own_record_keeps_date_as_memory_not_lag_one(self):
        frame = pd.DataFrame([record(i) for i in range(8)] + [record(99, month=202101, tenure=2)])
        o = build_options(frame, [recipient()], 202505)[0]
        self.assertEqual(o['synthetic_fields'], ['q8', 'q9'])
        self.assertEqual(o['older_own_memory']['q8']['source_period'], 202101)
        self.assertFalse(o['fixed'])

    def test_joint_draw_and_seed_are_reproducible(self):
        frame = pd.DataFrame([record(i, point=float(i), center=float(i + 20)) for i in range(8)])
        options = build_options(frame, [recipient()], 202505)
        a = draw(options, 202505, 7); b = draw(options, 202505, 7)
        self.assertEqual(a, b)
        self.assertEqual(a[0]['q9'] - a[0]['q8'], 20.)
        self.assertEqual(a[0]['q8'], a[0]['donor_userid_private'])

    def test_missing_recipient_weight_is_not_silently_filled(self):
        frame = pd.DataFrame([record(i) for i in range(8)])
        person = recipient(); person['weight'] = None
        options = build_options(frame, [person], 202505)
        row = draw(options, 202505, 7)[0]
        self.assertIsNone(row['weight'])
        self.assertEqual(row['synthetic_fields'], ['q8', 'q9'])

    def test_calibration_reduces_past_cdf_violation_with_ratio_cap(self):
        options = [small_options()]; before = deepcopy(options)
        result = calibrate(options, {'q8': [1., 1.], 'q9': [1., 1.]})
        self.assertLess(result['max_cdf_violation_after'], 1e-5)
        self.assertLess(result['max_cdf_violation_after'], result['max_cdf_violation_before'])
        self.assertGreaterEqual(result['min_probability_ratio'], .25)
        self.assertLessEqual(result['max_probability_ratio'], 4.)
        np.testing.assert_array_equal(options[0]['q8'], before[0]['q8'])
        self.assertEqual(options[0]['weight'], before[0]['weight'])

    def test_infeasible_fixed_real_mass_is_disclosed_not_changed(self):
        o = small_options((1., 0.))
        o['q8'] = np.array([-1.]); o['q9'] = np.array([-1.])
        o['p0'] = np.array([1.]); o['p'] = np.array([1.])
        result = calibrate([o], {'q8': [1., 1.], 'q9': [1., 1.]})
        self.assertEqual(result['status'], 'soft_constraint_unmet')
        self.assertEqual(result['max_cdf_violation_after'], .5)
        np.testing.assert_array_equal(o['q8'], [-1.])

    def test_ties_in_median_band_do_not_force_adjustment(self):
        o = small_options((.9, .1)); o['q8'] = np.zeros(2); o['q9'] = np.zeros(2)
        result = calibrate([o], {'q8': [0., 0.], 'q9': [0., 0.]})
        self.assertEqual(result['status'], 'already_in_band')
        np.testing.assert_allclose(o['p'], [.9, .1])
