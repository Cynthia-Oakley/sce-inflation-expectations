"""Independent placement, sampling and input-isolation checks; no network."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('news_exposure_demo', ROOT / 'studies/sce_inflation_expectations/news_exposure_demo.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ExposureTests(unittest.TestCase):
    def row(self, identity, tags=()):
        return {'article_id': identity, 'routing_tags': list(tags), 'headline': 'Original ' + identity,
                'abstract': 'Saved original abstract.', 'snippet': 'Saved original abstract.', 'pub_date': '2021-04-01T12:00:00Z'}

    def test_general_front_page_requires_both_a_and_one(self):
        self.assertEqual(module.front_page_status({'print_section': 'A', 'print_page': '1'}), 'a1')
        self.assertEqual(module.front_page_status({'print_section': 'B', 'print_page': '1'}), 'other_recorded_page')
        self.assertEqual(module.front_page_status({'print_section': 'A', 'print_page': '4'}), 'other_recorded_page')
        self.assertEqual(module.front_page_status({'print_page': '1'}), 'unknown')
        self.assertEqual(module.front_page_status({}), 'unknown')

    def test_mixture_has_known_probabilities_and_positive_unrelated_probability(self):
        rows = [self.row('a', ['food']), self.row('b'), self.row('c')]
        uniform = module.probabilities(rows, {'food'}, 0., 2.)
        mixed = module.probabilities(rows, {'food'}, .3, 2.)
        self.assertAlmostEqual(uniform[0], 1 / 3)
        self.assertAlmostEqual(mixed[0], .7 / 3 + .3 * 2 / 4)
        self.assertAlmostEqual(mixed[1], .7 / 3 + .3 / 4)
        self.assertAlmostEqual(sum(mixed), 1.)
        self.assertGreater(mixed[1], 0.)

    def test_no_affinity_does_not_block_news(self):
        rows = [self.row('a'), self.row('b')]
        self.assertEqual(module.probabilities(rows, {'food'}, .6), [.5, .5])

    def test_order_invariant_reproducible_unique_draw(self):
        rows = [self.row(str(i), ['food'] if i % 2 else []) for i in range(20)]
        a, audit = module.draw_news(rows, 5, 'fixed seed', {'food'}, .3)
        b, _ = module.draw_news(list(reversed(rows)), 5, 'fixed seed', {'food'}, .3)
        self.assertEqual(a, b)
        self.assertEqual(len({r['article_id'] for r in a}), 5)
        self.assertEqual(len(audit), 5)
        with self.assertRaises(ValueError):
            module.draw_news([rows[0], rows[0]], 1, 'seed')

    def test_tags_avoid_waged_and_ambiguous_bare_gas(self):
        self.assertEqual(module.news_tags({'headline': 'A reporter waged a battle'}), [])
        self.assertEqual(module.news_tags({'headline': 'Natural gas utility rates increase'}), ['utilities'])
        self.assertEqual(module.news_tags({'headline': 'Gasoline prices increase'}), ['road_fuel'])
        self.assertEqual(module.news_tags({'headline': 'Wage growth rises'}), ['labor_income'])
        self.assertEqual(module.news_tags({'headline': 'Oil pipeline supply falls'}), ['road_fuel'])

    def test_front_page_is_not_refiltered_by_inflation_and_future_rows_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw_dir = root / 'data/raw/nyt_archive'
            raw_dir.mkdir(parents=True)
            inputs = root / 'prepared'
            inputs.mkdir()
            docs = []
            pool = []
            for identity, section, title in [('a', 'A', 'Political front-page story'), ('b', 'B', 'Grocery prices rise')]:
                doc = {'_id': identity, 'pub_date': '2021-05-01T12:00:00Z', 'print_section': section,
                       'print_page': '1', 'headline': {'main': title}, 'abstract': 'Original abstract', 'snippet': ''}
                docs.append(doc)
                pool.append({'canonical_source_id': identity, 'article_id': identity, 'headline': title,
                             'pub_date': doc['pub_date'], 'abstract': doc['abstract'], 'snippet': '',
                             'web_url': '', 'text_sha256': '', 'text_vintage_status': 'unverified'})
            (raw_dir / '2021-05.json').write_text(json.dumps({'response': {'docs': docs}}))
            (inputs / 'pool_202105.json').write_text(json.dumps(pool))
            info = {'target': '202105', 'months': ['2021-05'], 'cutoff_date': '2021-05-12', 'date_rule': 'legacy date'}
            labels = {'a': {'decision': 'exclude'}, 'b': {'decision': 'keep'}}
            with patch.object(module, 'ROOT', root):
                common, personal, _ = module.prepare_window(inputs, info, labels)
                self.assertEqual([r['article_id'] for r in common], ['a'])
                self.assertEqual([r['article_id'] for r in personal], ['b'])
                pool[0]['pub_date'] = '2021-05-13T00:00:00Z'
                (inputs / 'pool_202105.json').write_text(json.dumps(pool))
                with self.assertRaisesRegex(ValueError, 'future news'):
                    module.prepare_window(inputs, info, labels)

    def test_profile_answer_fields_rejected(self):
        profile = {'demo_id': 'demo', 'label_zh': '示例', 'housing_tenure': 'rent', 'employed': True,
                   'synthetic_spending_shares': {'food': .3, 'gasoline': .01, 'utilities': .02}}
        self.assertEqual(module.household_interests(profile), {'rental_housing', 'labor_income', 'food'})
        with self.assertRaises(ValueError):
            module.household_interests(dict(profile, q9_real_answer=5.))

    def test_renderer_does_not_send_labels_ids_or_selection_reason(self):
        row = self.row('a', ['food'])
        row.update(semantic_label={'decision': 'keep', 'reason_zh': 'SECRET REASON'}, text_sha256='SECRET HASH')
        output = module.render_news_input([row], [])
        self.assertIn(row['headline'], output)
        self.assertIn(row['abstract'], output)
        self.assertNotIn('SECRET', output)
        self.assertNotIn('routing_tags', output)
        row['snippet'] = 'Distinct saved source evidence.'
        self.assertIn(row['snippet'], module.render_news_input([row], []))

    def test_different_updates_remain(self):
        a, b = self.row('a'), self.row('b')
        b['headline'] = a['headline']
        self.assertEqual(len(module.exact_deduplicate([a, b])), 1)
        b['abstract'] = 'A different development.'
        self.assertEqual(len(module.exact_deduplicate([a, b])), 2)


if __name__ == '__main__':
    unittest.main()
