from copy import deepcopy
import unittest

import pandas as pd

from studies.sce_inflation_expectations.experiments.state_continuity_inputs import (
    BINS, draw_legal_donor, resolve_person,
)


def record(month, uid=1, point=3., bins=None, tenure=1):
    return dict(date=month, userid=uid, Q8v2part2=point, tenure=tenure,
                survey_date=f'{month // 100}-{month % 100:02}-15',
                _AGE_CAT='Under 40', _EDU_CAT='College', _HH_INC_CAT='Under 50k',
                **dict(zip(BINS, [10.] * 10 if bins is None else bins)))


def declared(valid=True):
    return dict(source_kind='donor_initial', source_period=202403,
                q8_q9={'q8_point_pct': 4., 'q9_bins': [10.] * 10 if valid else [None] * 10},
                donor={'donor_period': 202403})


class ContinuityInputsTests(unittest.TestCase):
    def test_partial_prior_fields_recover_independently_from_strict_past(self):
        past = pd.DataFrame([record(202503), record(202504, point=7., bins=[None] * 10, tenure=2)])
        before = past.copy(deep=True)
        row = resolve_person(past, 1, 'person-a', {}, declared(), '202505', 'test')
        self.assertEqual(row['fields']['q8']['value'], 7.)
        self.assertEqual(row['fields']['q8']['source_period'], 202504)
        self.assertEqual(row['fields']['q9']['source_period'], 202503)
        self.assertEqual(row['fields']['q9']['source_kind'], 'own_observed')
        pd.testing.assert_frame_equal(past, before)

    def test_valid_delivered_joint_donor_kept_and_not_called_own_history(self):
        past = pd.DataFrame([record(202404)])
        d = declared(); original = deepcopy(d)
        row = resolve_person(past, 99, 'entrant', {}, d, '202505', 'test')
        self.assertEqual(row['fields']['q8']['value'], 4.)
        self.assertEqual(row['fields']['q9']['value'], [10.] * 10)
        self.assertEqual(row['fields']['q9']['source_kind'], 'synthetic_donor')
        self.assertEqual(row['own_history_centers'], [])
        self.assertIn('not_actual_survey', row['comparison_day_source'])
        self.assertEqual(d, original)

    def test_invalid_joint_donor_is_replaced_from_past_valid_pairs(self):
        past = pd.DataFrame([record(202404), record(202403, uid=7, bins=[None] * 10)])
        row = resolve_person(past, 99, 'entrant', {}, declared(False), '202505', 'test')
        self.assertEqual(row['fields']['q9']['source_period'], 202404)
        self.assertEqual(row['fields']['q8']['value'], 3.)
        self.assertEqual(row['donor']['eligible_pool_n'], 1)

    def test_current_or_future_rows_are_rejected_before_resolution_or_matching(self):
        past = pd.DataFrame([record(202505)])
        with self.assertRaises(ValueError):
            resolve_person(past, 1, 'a', {}, declared(), '202505', 'test')
        with self.assertRaises(ValueError):
            draw_legal_donor(past, {}, '202505', 'a', 'test')

    def test_no_eligible_donor_fails_instead_of_fabricating_probabilities(self):
        past = pd.DataFrame([record(202404, bins=[None] * 10)])
        with self.assertRaises(ValueError):
            resolve_person(past, 99, 'a', {}, declared(False), '202505', 'test')
