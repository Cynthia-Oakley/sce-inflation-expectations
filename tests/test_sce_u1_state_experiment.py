"""U1 state/guided bundle checks: render drift, arm separation and no-spend gate."""
from copy import deepcopy
import unittest

from tests.test_sce_confidence_trial import ConfidenceTests
from studies.sce_inflation_expectations.confidence_experiment import build_messages as baseline_messages
from studies.sce_inflation_expectations.belief_state_preparation import render_state_block
from studies.sce_inflation_expectations.prior_belief_preparation import MARKER, add_prior
from studies.sce_inflation_expectations.prior_belief_experiment import message_hash
from studies.sce_inflation_expectations.u1_state_experiment import (
    SCHEMA, LINE, PROMPT_VERSION, validate_bundle, build_messages, U1StateDecision,
)
from studies.sce_inflation_expectations.u1_state_trial import _state_block, execute


def u1_messages(u0, block):
    before, after = u0[0]['content'].split(MARKER, 1)
    return [{'role': 'user', 'content': before + block + MARKER + after}]


class U1ExperimentTests(unittest.TestCase):
    def setUp(self):
        f = ConfidenceTests()
        f.setUp()
        self.person, self.ob = f.p, f.ob
        baseline = deepcopy(f.bundle)
        baseline['arm'] = 'national_confidence'
        self.baseline = baseline
        self.base = baseline_messages(self.ob, baseline)
        self.prior = {'source_month': 202202, 'point_pct': 4.5,
                      'q9': {f'bin{i}': 10. for i in range(1, 11)}}
        self.u0, _ = add_prior(self.base, self.prior, 202203)
        self.state = {'source_month': 202202, 'center': 4.5, 'low': 2.0, 'high': 7.0,
                      'anchor': 4.0, 'n_earlier_valid': 3}
        self.block = render_state_block(self.state, 202203, guidance=False)

    def bundle(self, arm='own_state', block=None):
        block = self.block if block is None else block
        messages = u1_messages(self.u0, block)
        return {'schema_version': SCHEMA, 'research_line': LINE, 'target_month': '2022-03',
            'as_of': self.baseline['news']['as_of'], 'arm': arm, 'baseline': self.baseline,
            'rows': {'private_id': {'prior': self.prior, 'state_block': block,
                'baseline_messages_sha256': message_hash(self.base),
                'prior_messages_sha256': message_hash(self.u0),
                'messages_sha256': message_hash(messages)}}}

    def test_state_block_inserted_and_full_chain_verified(self):
        bundle = self.bundle()
        validate_bundle(bundle, [self.person], '2022-03', bundle['as_of'])
        actual = build_messages(self.ob, bundle)
        self.assertEqual(actual, u1_messages(self.u0, self.block))
        text = actual[0]['content']
        self.assertIn('Your survey history', text)
        self.assertNotIn('One hypothesis', text)
        self.assertEqual(text.replace(self.block, '', 1), self.u0[0]['content'])
        self.assertNotIn('private_id', text)
        decision = U1StateDecision(prompt_version=PROMPT_VERSION, u1_bundle=bundle)
        self.assertEqual(decision.build_llm_messages(self.ob), actual)

    def test_guided_arm_carries_hypothesis_only_with_anchor(self):
        guided = render_state_block(self.state, 202203, guidance=True)
        self.assertIn('One hypothesis', guided)
        bundle = self.bundle(arm='own_state_guided', block=guided)
        validate_bundle(bundle, [self.person], '2022-03', bundle['as_of'])
        self.assertEqual(build_messages(self.ob, bundle), u1_messages(self.u0, guided))
        stateless = {**self.state, 'anchor': None}
        with self.assertRaises(ValueError):
            render_state_block(stateless, 202203, guidance=True)
        with self.assertRaisesRegex(ValueError, 'state-only arm'):
            validate_bundle(self.bundle(arm='own_state', block=guided), [self.person],
                            '2022-03', self.baseline['news']['as_of'])

    def test_state_block_drift_or_wrong_level_rejected(self):
        bundle = self.bundle()
        bundle['rows']['private_id']['state_block'] = self.block.replace('4.5', '9.9')
        with self.assertRaisesRegex(ValueError, 'frozen preparation'):
            build_messages(self.ob, bundle)
        bad = deepcopy(self.bundle())
        bad['rows']['private_id']['messages_sha256'] = bad['rows']['private_id']['prior_messages_sha256']
        with self.assertRaisesRegex(ValueError, 'must differ'):
            validate_bundle(bad, [self.person], '2022-03', bad['as_of'])
        bad = self.bundle(block=self.block + 'Question 1 (point estimate):')
        with self.assertRaisesRegex(ValueError, 'malformed state block'):
            validate_bundle(bad, [self.person], '2022-03', bad['as_of'])

    def test_changed_profile_or_prior_is_not_silently_used(self):
        ob = deepcopy(self.ob)
        ob.local_physical['profile']['numeracy'] = 'Low'
        with self.assertRaises(ValueError):
            build_messages(ob, self.bundle())
        bundle = self.bundle()
        bundle['rows']['private_id']['prior']['point_pct'] = 7.
        with self.assertRaises(ValueError):
            build_messages(self.ob, bundle)

    def test_state_block_extraction_round_trips(self):
        block = _state_block(u1_messages(self.u0, self.block), self.u0, self.state, 202203, 'own_state')
        self.assertEqual(block, self.block)
        guided = render_state_block(self.state, 202203, guidance=True)
        got = _state_block(u1_messages(self.u0, guided), self.u0,
                           {**self.state, 'guidance_active': True}, 202203, 'own_state_guided')
        self.assertEqual(guided, got)
        with self.assertRaises(ValueError):
            _state_block(u1_messages(self.u0, guided), self.u0,
                         {**self.state, 'guidance_active': False}, 202203, 'own_state_guided')

    def test_no_permission_stops_before_reading_plan(self):
        with self.assertRaisesRegex(ValueError, 'confirmation'):
            execute('.', '.', '')


if __name__ == '__main__':
    unittest.main()
