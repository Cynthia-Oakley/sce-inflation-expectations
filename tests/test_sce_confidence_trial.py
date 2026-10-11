"""Confidence-only intervention, policy time and evaluation isolation gates."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from studies.sce_inflation_expectations.confidence_experiment import SCHEMA, ARMS, build_messages, validate_bundle
from studies.sce_inflation_expectations.news_exposure import SCHEMA as NEWS_SCHEMA
from studies.sce_inflation_expectations.belief_trial_preparation import confidence_block
from studies.sce_inflation_expectations.price_experience import profile_hash
from studies.sce_inflation_expectations.confidence_analysis import paired_metrics


class ConfidenceTests(unittest.TestCase):
    def setUp(self):
        profile = {'age_group': 'Under 40', 'region': 'South', 'state': 'TX',
                   'education_group': 'college', 'household_income_band': 'under_50k',
                   'housing_tenure': 'renter', 'employment_status': 'employed', 'numeracy': 'High'}
        self.p = SimpleNamespace(agent_id='private_id', attributes=profile)
        cutoff = '2022-03-10T23:59:59-05:00'
        def article(i):
            common = i < 3
            return {'article_id': str(i), 'headline': f'Example headline {i}', 'abstract': 'A public fact.',
                'snippet': 'A public fact.', 'pub_date': '2022-03-01T12:00:00Z', 'web_url': 'https://example.com',
                'text_sha256': 'a'*64, 'text_vintage_status': 'unverified',
                'print_section': 'A' if common else 'B', 'print_page': '1' if common else '2',
                'placement': 'a1' if common else 'other_recorded_page', 'routing_tags': ['food'],
                'semantic_label': None if common else {'decision': 'keep'}}
        news = {'schema_version': NEWS_SCHEMA, 'research_line': 'A_historical_reconstruction',
            'target_month': '2022-03', 'as_of': cutoff, 'arm': 'matched', 'mixing_weight': .5, 'affinity_boost': 2.,
            'common_news': [article(i) for i in range(3)],
            'rows': {'private_id': {'profile_sha256': profile_hash(profile), 'spending_shares': {'food': .3, 'gasoline': .1, 'shelter': .4, 'other': .2}, 'personal_news': [article(i) for i in range(3, 8)]}},
            'source_sha256': {}, 'pool_status': 'complete_coarse_candidate_labels'}
        self.bundle = {'schema_version': SCHEMA, 'arm': ARMS[0], 'news': news, 'labels': {'private_id': 'great_deal'},
            'wave_id': 'prior_wave', 'policy': {'published_at': '2022-01-26T14:00:00-05:00',
                'source_url': 'https://www.federalreserve.gov/example', 'source_sha256': 'b'*64,
                'facts': ['A past rate action.', 'A past assessment.', 'A past policy intention.']}}
        self.ob = SimpleNamespace(agent_id='private_id', local_physical={'profile': profile}, local_information={},
            macro_information={'target_month': '2022-03', 'as_of': cutoff, 'signals': [], 'events': [], 'broadcasts': []})

    def test_only_confidence_sentence_differs(self):
        base = build_messages(self.ob, self.bundle)[0]['content']
        changed = deepcopy(self.bundle)
        changed['arm'] = ARMS[1]
        value = build_messages(self.ob, changed)[0]['content']
        expected = base.replace('Question 1 (point estimate):', confidence_block('great_deal') + 'Question 1 (point estimate):', 1)
        self.assertEqual(value, expected)
        self.assertEqual(value.count('A past rate action.'), 1)
        self.assertNotIn('private_id', value)

    def test_dont_know_is_identical_not_invented_distrust(self):
        base = build_messages(self.ob, self.bundle)
        changed = deepcopy(self.bundle)
        changed['arm'] = ARMS[1]
        changed['labels']['private_id'] = 'dont_know_or_refused'
        self.assertEqual(base, build_messages(self.ob, changed))

    def test_future_policy_rejected(self):
        changed = deepcopy(self.bundle)
        changed['policy']['published_at'] = '2022-03-16T14:00:00-04:00'
        with self.assertRaises(ValueError):
            validate_bundle(changed, [self.p], '2022-03', self.bundle['news']['as_of'])

    def test_answer_field_or_missing_label_rejected(self):
        for mutate in ('Q9_mean', 'missing_label'):
            changed = deepcopy(self.bundle)
            if mutate == 'Q9_mean':
                changed['policy']['Q9_mean'] = 4.5
            else:
                changed['labels'] = {}
            with self.assertRaises(ValueError):
                validate_bundle(changed, [self.p], '2022-03', self.bundle['news']['as_of'])

    def test_paired_evaluation_uses_common_people_and_correct_W1(self):
        rows = [{'real': r, ARMS[0]: r-1, ARMS[1]: r, 'weight': 1., 'profile': {}, 'answer_date_group': 'before_cutoff'} for r in (2., 3., 4.)]
        rows.append({'real': 100., ARMS[0]: 0., ARMS[1]: None, 'weight': 1., 'profile': {}})
        result = paired_metrics(rows, bootstrap=30)
        self.assertEqual(result['n_common'], 3)
        self.assertEqual(result['arms'][ARMS[0]]['distribution_W1_pp'], 1)
        self.assertEqual(result['arms'][ARMS[1]]['median_absolute_error_pp'], 0)
        self.assertEqual(result['confidence_minus_no_confidence']['median_absolute_error_pp']['change_pp'], -1)


if __name__ == '__main__':
    unittest.main()
