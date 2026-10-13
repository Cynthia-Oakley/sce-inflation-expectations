"""Actual render drift, historical-source boundary and no-spend gate checks."""
from copy import deepcopy
import unittest
from unittest.mock import patch

from tests.test_sce_confidence_trial import ConfidenceTests
from studies.sce_inflation_expectations.confidence_experiment import build_messages as baseline_messages
from studies.sce_inflation_expectations.prior_belief_preparation import add_prior
from studies.sce_inflation_expectations.prior_belief_experiment import (
    SCHEMA, LINE, PROMPT_VERSION, message_hash, validate_bundle, build_messages, PriorBeliefDecision,
)
from studies.sce_inflation_expectations.prior_belief_trial import extract_prior, request_bound, execute


class PriorExperimentTests(unittest.TestCase):
    def setUp(self):
        f = ConfidenceTests()
        f.setUp()
        self.person, self.ob = f.p, f.ob
        baseline = deepcopy(f.bundle)
        baseline['arm'] = 'national_confidence'
        self.base = baseline_messages(self.ob, baseline)
        self.prior = {'source_month': 202202, 'point_pct': 4.5,
                      'q9': {f'bin{i}': 10. for i in range(1, 11)}}
        self.messages, self.block = add_prior(self.base, self.prior, 202203)
        self.bundle = {'schema_version': SCHEMA, 'research_line': LINE, 'target_month': '2022-03',
            'as_of': baseline['news']['as_of'], 'arm': 'own_previous', 'baseline': baseline,
            'rows': {'private_id': {'prior': self.prior, 'baseline_messages_sha256': message_hash(self.base),
                                    'messages_sha256': message_hash(self.messages)}}}

    def test_same_question_and_pe_preserved_through_actual_provider(self):
        validate_bundle(self.bundle, [self.person], '2022-03', self.bundle['as_of'])
        actual = build_messages(self.ob, self.bundle)
        self.assertEqual(actual, self.messages)
        self.assertEqual(actual[0]['content'].replace(self.block, '', 1), self.base[0]['content'])
        decision = PriorBeliefDecision(prompt_version=PROMPT_VERSION, prior_bundle=self.bundle)
        self.assertEqual(decision.build_llm_messages(self.ob), actual)
        self.assertNotIn('private_id', actual[0]['content'])

    def test_current_prior_extra_answer_and_probability_drift_rejected(self):
        for change in ('current', 'answer', 'probability'):
            b = deepcopy(self.bundle)
            prior = b['rows']['private_id']['prior']
            if change == 'current':
                prior['source_month'] = 202203
            elif change == 'answer':
                prior['Q9_mean'] = 4.
            else:
                prior['q9']['bin1'] = 11.
            with self.assertRaises(ValueError):
                validate_bundle(b, [self.person], '2022-03', self.bundle['as_of'])

    def test_changed_real_profile_or_prior_is_not_silently_used(self):
        ob = deepcopy(self.ob)
        ob.local_physical['profile']['numeracy'] = 'Low'
        with self.assertRaises(ValueError):
            build_messages(ob, self.bundle)
        b = deepcopy(self.bundle)
        b['rows']['private_id']['prior']['point_pct'] = 7.
        with self.assertRaisesRegex(ValueError, 'frozen preparation'):
            build_messages(self.ob, b)

    def test_no_prior_is_exact_original_and_extraction_round_trips(self):
        self.assertEqual(extract_prior(self.messages, self.base, 'own_previous', '202203'), self.prior)
        b = deepcopy(self.bundle)
        b['arm'] = 'no_prior'
        row = b['rows']['private_id']
        row['prior'], row['messages_sha256'] = None, row['baseline_messages_sha256']
        validate_bundle(b, [self.person], '2022-03', b['as_of'])
        self.assertEqual(build_messages(self.ob, b), self.base)

    def test_no_permission_stops_before_dispatch_and_cost_covers_bytes(self):
        with patch('studies.sce_inflation_expectations.prior_belief_trial.engine_execute') as dispatch:
            with self.assertRaisesRegex(ValueError, 'confirmation'):
                execute('.', '.', '')
            dispatch.assert_not_called()
        decision = PriorBeliefDecision(prompt_version=PROMPT_VERSION, prior_bundle=self.bundle,
                                       price_input_per_mtok=.30, price_output_per_mtok=1.20)
        self.assertAlmostEqual(request_bound(self.messages), decision._request_cost_bound(
            __import__('json').dumps(self.messages, ensure_ascii=False)))


if __name__ == '__main__':
    unittest.main()
