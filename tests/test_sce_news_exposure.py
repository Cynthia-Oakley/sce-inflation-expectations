"""Input isolation and error gates for the news mechanism; no network."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from studies.sce_inflation_expectations.news_exposure import (
    SCHEMA, PROMPT_VERSION, NewsExposureDecision, build_messages, interests_for_profile, validate_bundle,
)
from studies.sce_inflation_expectations.news_exposure_demo import probabilities
from studies.sce_inflation_expectations.news_pool_preparation import partition_requests
from studies.sce_inflation_expectations.model import build_sce_messages_v2
from studies.sce_inflation_expectations.price_experience import profile_hash


class NewsExposureTests(unittest.TestCase):
    def setUp(self):
        self.profile = {'age_group': 'Under 40', 'region': 'South', 'state': 'TX',
                        'education_group': 'college', 'household_income_band': 'under_50k',
                        'housing_tenure': 'renter', 'employment_status': 'employed', 'numeracy': 'High'}
        self.shares = {'food': .3, 'gasoline': .1, 'shelter': .4, 'other': .2}
        self.persona = SimpleNamespace(agent_id='PRIVATE_ID_NOT_SENT', attributes=self.profile)
        def article(i, common):
            return {'article_id': f'SOURCE_ID_{i}', 'headline': f'Public news title {i}',
                    'abstract': f'Original abstract {i}.', 'snippet': f'Original abstract {i}.',
                    'pub_date': '2021-05-01T12:00:00Z', 'web_url': 'https://example.com/news',
                    'text_sha256': 'PRIVATE_AUDIT_HASH', 'text_vintage_status': 'unverified',
                    'print_section': 'A' if common else 'B', 'print_page': '1' if common else '2',
                    'placement': 'a1' if common else 'other_recorded_page', 'routing_tags': ['food'],
                    'semantic_label': None if common else {'decision': 'keep', 'reason_zh': 'SECRET_REASON'}}
        self.bundle = {'schema_version': SCHEMA, 'research_line': 'A_historical_reconstruction',
                       'target_month': '2021-05', 'as_of': '2021-05-12T23:59:59-04:00',
                       'arm': 'matched', 'mixing_weight': .5, 'affinity_boost': 2.,
                       'common_news': [article(i, True) for i in range(3)],
                       'rows': {self.persona.agent_id: {'profile_sha256': profile_hash(self.profile),
                                                      'spending_shares': self.shares,
                                                      'personal_news': [article(i, False) for i in range(3, 8)]}},
                       'source_sha256': {}, 'pool_status': 'partial_labels_offline_only'}
        self.ob = SimpleNamespace(agent_id=self.persona.agent_id,
                                  local_physical={'profile': dict(self.profile, weight=1)}, local_information={},
                                  macro_information={'target_month': '2021-05', 'as_of': self.bundle['as_of'],
                                                     'signals': [], 'events': [], 'broadcasts': []})

    def test_fifty_fifty_is_probability_mixture_not_quota(self):
        rows = [{'routing_tags': ['food']}, {'routing_tags': []}, {'routing_tags': []}]
        # .5*(1/3)+.5*(2/4)=5/12; unrelated .5/3+.5/4=7/24.
        actual = probabilities(rows, {'food'}, .5, 2)
        self.assertAlmostEqual(actual[0], 5/12)
        self.assertAlmostEqual(actual[1], 7/24)
        self.assertAlmostEqual(sum(actual), 1)

    def test_no_utility_share_or_missing_housing_invented(self):
        p = dict(self.profile, housing_tenure=None, employment_status='retired')
        self.assertEqual(interests_for_profile(p, self.shares), {'food', 'road_fuel'})

    def test_source_ids_labels_and_repeated_snippet_not_sent(self):
        text = build_messages(self.ob, self.bundle)[0]['content']
        for secret in ('PRIVATE_ID_NOT_SENT', 'SOURCE_ID_', 'PRIVATE_AUDIT_HASH', 'SECRET_REASON'):
            self.assertNotIn(secret, text)
        self.assertEqual(text.count('Original abstract 3.'), 1)
        marker = 'Question 1 (point estimate):'
        self.assertEqual(text.split(marker)[1], build_sce_messages_v2(self.ob)[0]['content'].split(marker)[1])

    def test_old_news_and_broadcast_cannot_leak_back(self):
        for key in ('events', 'broadcasts'):
            ob = deepcopy(self.ob)
            ob.macro_information[key] = [{'text': 'old news'}]
            with self.assertRaises(ValueError):
                build_messages(ob, self.bundle)

    def test_future_news_and_wrong_profile_rejected(self):
        b = deepcopy(self.bundle)
        b['common_news'][0]['pub_date'] = '2021-05-13T12:00:00Z'
        with self.assertRaises(ValueError):
            validate_bundle(b, [self.persona], '2021-05', b['as_of'])
        b = deepcopy(self.bundle)
        b['rows'][self.persona.agent_id]['profile_sha256'] = 'wrong'
        with self.assertRaises(ValueError):
            validate_bundle(b, [self.persona], '2021-05', b['as_of'])

    def test_real_simulation_cannot_use_partial_label_pool(self):
        with self.assertRaisesRegex(ValueError, 'complete candidate labels'):
            NewsExposureDecision(news_exposure_bundle=self.bundle, llm_kind='openai',
                                 prompt_version=PROMPT_VERSION, model='deepseek-flash', max_calls=1)

    def test_news_cannot_overlap_and_b1_not_common(self):
        b = deepcopy(self.bundle)
        b['common_news'][0]['print_section'] = 'B'
        with self.assertRaises(ValueError):
            validate_bundle(b, [self.persona], '2021-05', b['as_of'])
        b = deepcopy(self.bundle)
        b['rows'][self.persona.agent_id]['personal_news'][0]['article_id'] = b['common_news'][0]['article_id']
        with self.assertRaises(ValueError):
            validate_bundle(b, [self.persona], '2021-05', b['as_of'])

    def test_budget_parts_partition_without_losing_or_repeating_request(self):
        rows = [{'batch_id': i, 'request_usd_reservation': .11} for i in range(5)]
        parts = partition_requests(rows)
        self.assertEqual([[r['batch_id'] for r in p] for p in parts], [[0, 1], [2, 3], [4]])
        self.assertTrue(all(sum(r['request_usd_reservation'] for r in p) <= .25 for p in parts))


if __name__ == '__main__':
    unittest.main()
