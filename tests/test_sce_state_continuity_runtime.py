from copy import deepcopy
import json
import unittest

from studies.sce_inflation_expectations.state_continuity_runtime import (
    STATE_TOKEN, TIMING_TOKEN, advance_state, initialize_state, render_messages, render_state,
)


def state():
    return initialize_state({
        'fields': {'q8': {'value': 3., 'source_period': 202504, 'source_kind': 'own_observed'},
                   'q9': {'value': [10.] * 10, 'source_period': 202504, 'source_kind': 'own_observed'}},
        'own_history_centers': [{'source_period': 202503, 'center': 2.}, {'source_period': 202504, 'center': 3.}],
        'comparison_reference_day': '2025-04-15', 'comparison_day_source': 'own_observed_survey_day'})


class ContinuityRuntimeTests(unittest.TestCase):
    def test_q9_update_survives_invalid_q8_and_is_proportionally_normalized(self):
        initial = state(); old = deepcopy(initial)
        raw = json.dumps({'point_pct': 'bad', 'q9': {f'bin{i}': 5 for i in range(1, 11)}})
        updated = advance_state(initial, raw, '202505', '2025-05-13T23:59:59-04:00')
        self.assertEqual(updated['fields']['q8'], initial['fields']['q8'])
        self.assertAlmostEqual(sum(updated['fields']['q9']['value']), 100)
        self.assertEqual(updated['fields']['q9']['source_period'], 202505)
        self.assertTrue(updated['transition']['q9_proportional_normalization'])
        self.assertEqual(initial, old)

    def test_q8_survives_invalid_q9_and_failed_probability_state_is_retained(self):
        initial = state()
        raw = json.dumps({'point_pct': -2., 'q9': {f'bin{i}': 0 for i in range(1, 11)}})
        updated = advance_state(initial, raw, '202505', '2025-05-13T23:59:59-04:00')
        self.assertEqual(updated['fields']['q8']['value'], -2.)
        self.assertEqual(updated['fields']['q9'], initial['fields']['q9'])
        self.assertTrue(updated['transition']['field_retained_as_explicit_fallback']['q9'])
        self.assertEqual(updated['history_centers'], initial['history_centers'])

    def test_recursive_summary_appends_model_only_and_rejects_duplicate_transition(self):
        initial = state()
        raw = json.dumps({'point_pct': 5., 'q9': {f'bin{i}': 10 for i in range(1, 11)}})
        updated = advance_state(initial, raw, '202505', '2025-05-13T23:59:59-04:00')
        self.assertEqual([r['source_period'] for r in updated['history_centers']], [202503, 202504, 202505])
        with self.assertRaises(ValueError):
            advance_state(updated, raw, '202505', '2025-05-13T23:59:59-04:00')

    def test_only_two_state_insertions_change_and_synthetic_is_not_called_observed(self):
        initial = state(); initial['fields']['q9']['source_kind'] = 'synthetic_donor'
        template = [{'role': 'user', 'content': 'FIXED PRICE/NEWS\n' + TIMING_TOKEN + '\n' + STATE_TOKEN + '\nFIXED QUESTIONS'}]
        context = dict(as_of='2025-05-13T23:59:59-04:00', common_news=[], personal_news=[],
                       policy_published_at='2025-05-07T14:00:00-04:00', food_published_at='2025-05-13T08:30:00-04:00')
        text = render_messages(template, initial, '202505', context)[0]['content']
        self.assertTrue(text.startswith('FIXED PRICE/NEWS\n'))
        self.assertTrue(text.endswith('\nFIXED QUESTIONS'))
        self.assertIn('not your actual survey answer', text)
        self.assertNotIn(STATE_TOKEN, text)
        self.assertEqual(template[0]['content'].count(STATE_TOKEN), 1)

    def test_future_history_cannot_be_rendered(self):
        initial = state(); initial['history_centers'].append({'source_period': 202505, 'center': 99.})
        with self.assertRaises(ValueError): render_state(initial, '202505')
