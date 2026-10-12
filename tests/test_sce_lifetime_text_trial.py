"""Qualitative conversion must delete numeric anchors without future outcomes."""
from copy import deepcopy
import unittest

from tests.test_sce_lifetime_trial import LifetimeTrialTests as Fixture
from studies.sce_inflation_expectations.lifetime_text_experiment import render_text_cards, build_messages, validate_bundle, TEXT_INTRO, SCHEMA, ARMS
from studies.sce_inflation_expectations.lifetime_episodes import render_cards
from studies.sce_inflation_expectations.confidence_experiment import build_messages as baseline_messages
from studies.sce_inflation_expectations.lifetime_experience import insert_block,json_hash
from studies.sce_inflation_expectations.lifetime_analysis import metrics


class LifetimeTextTests(unittest.TestCase):
    def setUp(self):
        self.f=Fixture();self.f.setUp()

    def bundle(self,arm):
        b=self.f.treatment();b['schema_version']=SCHEMA;b['arm']=arm
        base=baseline_messages(self.f.ob,b['baseline']);row=b['rows']['private_id']
        if arm=='text_history':b['intro']=TEXT_INTRO;text=render_text_cards(row['cards'])
        elif arm=='numeric_history':text=render_cards(row['cards'],b['intro'])
        else:row['cards']=[];text=None
        row['messages_sha256']=json_hash(base if text is None else insert_block(base,text))
        return b

    def test_preserves_era_trend_not_cpi_percent_or_month_points(self):
        c=deepcopy(self.f.card);c['context_facts'].append({'id':'pce_goal_2012','text':'The goal was 2%.','event_start':'2012-01','event_end':'2012-01','source_id':'fed'})
        text=render_text_cards([c])
        self.assertIn('Financial crisis',text);self.assertIn('Inflation eased',text)
        self.assertNotIn('%',text);self.assertNotIn('2008-07',text);self.assertNotIn('5.6',text)
        self.assertNotIn('roughly ages',text)

    def test_changed_magnitudes_same_direction_do_not_change_qualitative_text(self):
        c=deepcopy(self.f.card);d=deepcopy(c);d['landmarks'][0]['cpi_yoy_pct']=25.;d['landmarks'][1]['cpi_yoy_pct']=-20.
        self.assertEqual(render_text_cards([c]),render_text_cards([d]))
        self.assertNotEqual(render_cards([c],TEXT_INTRO),render_cards([d],TEXT_INTRO))

    def test_censored_episode_not_asserted_short_or_finished(self):
        c=deepcopy(self.f.card);c['duration']['continuous_high_inflation_spell_around_peak']={'start':'2008-07','end':'2008-12','known_months':6,'left_censored':False,'right_censored':True}
        text=render_text_cards([c]);self.assertIn('still continuing',text);self.assertNotIn('short-lived',text)
        c['duration']['continuous_high_inflation_spell_around_peak']['right_censored']=False
        c['duration']['continuous_high_inflation_spell_around_peak']['left_censored']=True
        text=render_text_cards([c]);self.assertIn('full duration is not observed',text);self.assertNotIn('short-lived',text)

    def test_questionnaire_and_old_environment_identical_all_three_arms(self):
        base=baseline_messages(self.f.ob,self.f.bundle['baseline'])
        for arm in ARMS:
            b=self.bundle(arm);validate_bundle(b,[self.f.person],'2022-03',self.f.bundle['baseline']['news']['as_of'])
            out=build_messages(self.f.ob,b)
            if arm!='original':
                text=render_text_cards(b['rows']['private_id']['cards']) if arm=='text_history' else render_cards(b['rows']['private_id']['cards'],b['intro'])
                out[0]['content']=out[0]['content'].replace(text+'\n\n','',1)
            self.assertEqual(out,base)

    def test_future_or_new_answer_fields_rejected(self):
        b=self.bundle('text_history');b['rows']['private_id']['cards'][0]['covered_end']='2023-12'
        with self.assertRaises(ValueError):validate_bundle(b,[self.f.person],'2022-03',self.f.bundle['baseline']['news']['as_of'])
        b=self.bundle('text_history');b['rows']['private_id']['Q8']=5.
        with self.assertRaises(ValueError):validate_bundle(b,[self.f.person],'2022-03',self.f.bundle['baseline']['news']['as_of'])

    def test_generic_analysis_compares_text_against_numeric_on_same_people(self):
        rows=[{'real':x,'original':x-1.,'numeric_history':x-2.,'text_history':x,'weight':1.,'profile':{'age_group':'Under 40'}} for x in (2.,3.,4.)]
        s=metrics(rows,bootstrap=20,arms=ARMS)
        self.assertEqual(s['n_common'],3)
        self.assertEqual(s['contrasts']['text_history_minus_numeric_history']['distribution_W1_pp']['change_pp'],-2.)
        self.assertEqual(s['contrasts']['text_history_minus_original']['median_absolute_error_pp']['change_pp'],-1.)


if __name__=='__main__':unittest.main()
