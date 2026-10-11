"""Independent news-boundary and label-isolation examples; no network."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name,ROOT/'studies/sce_inflation_expectations'/f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


recall = load('news_selection_trial')
labeler = load('news_label_trial')


class NewsTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = recall.RecallRules(json.loads(recall.RULE_FILE.read_text()))

    def hits(self,title,**extra):
        return self.rules.classify(dict(headline={'main':title},**extra))

    def test_word_boundary_avoids_waged_and_wager(self):
        self.assertFalse(self.hits('A reporter waged a legal battle over a wager'))
        self.assertTrue(self.hits('Workers seek higher wages'))

    def test_price_changes_both_directions_and_near_limit(self):
        self.assertTrue(self.hits('Stores increase prices'))
        self.assertTrue(self.hits('Prices increased'))
        self.assertTrue(self.hits('Prices one two three four increased'))
        self.assertFalse(self.hits('Prices one two three four five increased'))

    def test_food_supply_without_inflation_keyword(self):
        self.assertTrue(self.hits('Beef factories shuttered after malware attack'))

    def test_no_synthetic_cross_field_proximity(self):
        self.assertFalse(self.hits('Beef',abstract='Production stopped'))

    def test_hyphen_normalization_and_economic_section(self):
        self.assertTrue(self.hits('Supply-chain pressure continues'))
        self.assertTrue(self.hits('Company reports quarterly results',section_name='Business Day'))
        self.assertFalse(self.hits('A summer recipe',section_name='Food'))

    def test_id_and_evidence_isolation(self):
        inputs=[{'article_id':'a','headline':'Beef plants stopped production','abstract':'','snippet':''},
                {'article_id':'b','headline':'A sports match','abstract':'','snippet':''}]
        labels=[{'article_id':i['article_id'],'decision':'keep','topics':['supply_costs'],
                 'scope':'us_unspecified','claim_type':'fact','reason_zh':'格式测试',
                 'evidence_snippet':i['headline']} for i in inputs]
        self.assertEqual(len(labeler.validate_labels(json.dumps({'labels':labels}),inputs)),2)
        wrong=copy.deepcopy(labels);wrong[1]['article_id']='a'
        with self.assertRaises(ValueError):labeler.validate_labels(json.dumps({'labels':wrong}),inputs)
        wrong=copy.deepcopy(labels);wrong[1]['evidence_snippet']=labels[0]['evidence_snippet']
        with self.assertRaises(ValueError):labeler.validate_labels(json.dumps({'labels':wrong}),inputs)

    def test_only_verified_long_quote_can_be_shortened(self):
        quote='one two three four five six seven eight nine ten eleven twelve thirteen'
        inputs=[{'article_id':'a','headline':quote,'abstract':'','snippet':''}]
        label={'article_id':'a','decision':'exclude','topics':[],'scope':'unspecified',
               'claim_type':'unclear','reason_zh':'测试','evidence_snippet':quote}
        labels,repairs=labeler.validate_with_evidence_shortening(json.dumps({'labels':[label]}),inputs)
        self.assertEqual(labels[0]['evidence_snippet'],'one two three four five six seven eight nine ten eleven twelve')
        self.assertEqual(labels[0]['decision'],'exclude')
        self.assertEqual(len(repairs),1)
        label['evidence_snippet']='invented '+quote
        with self.assertRaises(ValueError):labeler.validate_with_evidence_shortening(json.dumps({'labels':[label]}),inputs)

    def test_only_exact_input_echo_can_be_removed(self):
        source={'article_id':'a','headline':'Beef plant closes','abstract':'','snippet':'','source':'demo','section_name':'','news_desk':''}
        row={'article_id':'a','decision':'keep','topics':['supply_costs'],'scope':'us_unspecified',
             'claim_type':'fact','reason_zh':'供给','evidence_snippet':'Beef plant closes','headline':source['headline']}
        labels,repairs=labeler.validate_with_evidence_shortening(json.dumps({'labels':[row]}),[source])
        self.assertNotIn('headline',labels[0]);self.assertEqual(len(repairs),1)
        row['headline']='invented'
        with self.assertRaises(ValueError):labeler.validate_with_evidence_shortening(json.dumps({'labels':[row]}),[source])

    def test_ellipsis_recovery_requires_ordered_fragments_in_one_article(self):
        source={'article_id':'a','headline':'','abstract':'Beef plants, after repairs, were coming back online.','snippet':''}
        row={'article_id':'a','decision':'keep','topics':['supply_costs'],'scope':'us_unspecified',
             'claim_type':'fact','reason_zh':'供给','evidence_snippet':'Beef plants ... were coming back online'}
        labels,repairs=labeler.validate_with_evidence_shortening(json.dumps({'labels':[row]}),[source])
        self.assertEqual(labels[0]['decision'],'keep')
        self.assertEqual(labels[0]['evidence_snippet'],'were coming back online')
        self.assertEqual(repairs[0]['kind'],'offline_extract_verified_continuous_quote')
        row['evidence_snippet']='were coming back online ... Beef plants'
        with self.assertRaises(ValueError):labeler.validate_with_evidence_shortening(json.dumps({'labels':[row]}),[source])

    def test_minor_quote_difference_only_clips_literal_source_fragment(self):
        source={'article_id':'a','headline':'','abstract':'Its vaccine generated revenue in the first quarter.','snippet':''}
        row={'article_id':'a','decision':'keep','topics':['other_economic'],'scope':'us_national',
             'claim_type':'fact','reason_zh':'原分类不变','evidence_snippet':'The vaccine generated revenue in the first quarter'}
        labels,repairs=labeler.validate_with_evidence_shortening(json.dumps({'labels':[row]}),[source])
        self.assertIn(labels[0]['evidence_snippet'],source['abstract'])
        self.assertEqual(labels[0]['decision'],row['decision'])
        self.assertEqual(labels[0]['reason_zh'],row['reason_zh'])
        row['evidence_snippet']='Invented unrelated price increase'
        with self.assertRaises(ValueError):labeler.validate_with_evidence_shortening(json.dumps({'labels':[row]}),[source])

    def test_identity_recovery_requires_one_character_and_unique_article_quote(self):
        source={'article_id':'abcde','headline':'A unique source title','abstract':'','snippet':''}
        row={'article_id':'abccde','decision':'background','topics':['other_economic'],'scope':'unspecified',
             'claim_type':'unclear','reason_zh':'原分类','evidence_snippet':source['headline']}
        labels,repairs=labeler.validate_with_evidence_shortening(json.dumps({'labels':[row]}),[source])
        self.assertEqual(labels[0]['article_id'],'abcde')
        self.assertEqual(labels[0]['decision'],'background')
        self.assertEqual(repairs[0]['kind'],'offline_identity_recovery_by_unique_literal_quote')
        row['article_id']='unrelated-id'
        with self.assertRaises(ValueError):labeler.validate_with_evidence_shortening(json.dumps({'labels':[row]}),[source])
        row['article_id']='abccde';row['evidence_snippet']='No matching source quote'
        with self.assertRaises(ValueError):labeler.validate_with_evidence_shortening(json.dumps({'labels':[row]}),[source])


if __name__=='__main__':
    unittest.main()
