import unittest
from types import SimpleNamespace
from unittest.mock import patch

from studies.sce_inflation_expectations.purchase_frequency_runtime import transform, PurchaseFrequencyDecision
from studies.sce_inflation_expectations.purchase_frequency_matching import CATEGORIES, render_frequency
from studies.sce_inflation_expectations.model import SCEDecision


class FrequencyRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.messages = [{'role': 'user', 'content': 'Unchanged original context\nQuestion 1 (point estimate):\nUnchanged questionnaire'}]
        self.frequency = dict.fromkeys(CATEGORIES, 2)
        self.prices = {'published_at': '2021-11-10T08:30:00-05:00', 'reference_period': '2021-10',
                       'categories': {k: {'category_label': k, 'yoy_nsa_pct': 5.4, 'mom_nsa_pct': 1.1} for k in CATEGORIES}}

    def test_no_mechanical_forecast_prohibition_and_only_rule_changes(self):
        neutral = transform(self.messages, 'frequency_data', self.prices, self.frequency)
        active = transform(self.messages, 'frequency_rule', self.prices, self.frequency)
        self.assertNotIn('Do not mechanically', active[0]['content'])
        self.assertNotIn('Do not mechanically', neutral[0]['content'])
        data = render_frequency({'recorded_days_7d': self.frequency}, active_rule=False)
        rule = render_frequency({'recorded_days_7d': self.frequency}, active_rule=True)
        self.assertEqual(active[0]['content'].replace(rule, data, 1), neutral[0]['content'])
        self.assertEqual(self.messages[0]['content'], 'Unchanged original context\nQuestion 1 (point estimate):\nUnchanged questionnaire')

    def test_missing_day_value_rejected_before_call(self):
        with self.assertRaises(ValueError):
            transform(self.messages, 'frequency_rule', self.prices, {**self.frequency, 'food_at_home': None})

    def test_provider_error_stops_without_retry(self):
        decision = object.__new__(PurchaseFrequencyDecision)
        decision.bundle = {'arm': 'frequency_data', 'messages_sha256': {'anon': 'hash'}}
        decision.audit_dir = None
        action = SimpleNamespace(payload={'validation_status': 'error'})
        with patch.object(SCEDecision, '_decide_openai_one', return_value=action) as call:
            with self.assertRaisesRegex(RuntimeError, 'without retry'):
                decision._decide_openai_one(SimpleNamespace(agent_id='anon'))
            self.assertEqual(call.call_count, 1)


if __name__ == '__main__':
    unittest.main()
