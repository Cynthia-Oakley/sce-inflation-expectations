"""Prompt identity, leakage/time gates, three-arm estimands and budget consent."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from tests.test_sce_confidence_trial import ConfidenceTests
from studies.sce_inflation_expectations.confidence_experiment import build_messages as baseline_messages
from studies.sce_inflation_expectations.lifetime_experiment import SCHEMA, ARMS, validate_bundle, build_messages, LifetimeDecision
from studies.sce_inflation_expectations.lifetime_experience import insert_block, json_hash
from studies.sce_inflation_expectations.lifetime_episodes import render_cards
from studies.sce_inflation_expectations.lifetime_analysis import metrics, point_value
from studies.sce_inflation_expectations.lifetime_trial import execute


class LifetimeTrialTests(unittest.TestCase):
    def setUp(self):
        fixture = ConfidenceTests()
        fixture.setUp()
        self.person, self.ob = fixture.p, fixture.ob
        baseline = deepcopy(fixture.bundle)
        baseline['arm'] = 'national_confidence'
        self.card = {'era_id':'crisis','label':'Financial crisis','covered_start':'2008-01','covered_end':'2009-12',
            'n_months':24,'age_range_approximate':[12,13],'life_stages':['adolescence'],
            'landmarks':[{'month':'2008-07','cpi_yoy_pct':5.6},{'month':'2009-07','cpi_yoy_pct':-2.1}],
            'duration':{'threshold_pct':5.,'continuous_high_inflation_spell_around_peak':None},
            'context_facts':[{'id':'crisis','event_start':'2007-12-01','event_end':'2009-06-30','source_id':'fed','text':'A recession occurred.'}],
            'source_ids':['fed']}
        original = baseline_messages(self.ob,baseline)
        self.bundle = {'schema_version':SCHEMA,'arm':'original','baseline':baseline,'history_end':'2021-12',
            'start_age':6,'intro':'Historical twelve-month CPI changes.','research_line':'A_historical_reconstruction',
            'rows':{'private_id':{'cards':[],'baseline_messages_sha256':json_hash(original),'messages_sha256':json_hash(original)}}}

    def treatment(self):
        b = deepcopy(self.bundle)
        b['arm'] = 'age_matched_episodes'
        row = b['rows']['private_id']
        row['cards'] = [self.card]
        row['messages_sha256'] = json_hash(insert_block(baseline_messages(self.ob,b['baseline']),render_cards(row['cards'],b['intro'])))
        return b

    def test_original_unchanged_treatment_only_adds_history(self):
        base = build_messages(self.ob,self.bundle)
        treatment = self.treatment()
        validate_bundle(treatment,[self.person],'2022-03',self.bundle['baseline']['news']['as_of'])
        changed = build_messages(self.ob,treatment)
        block = render_cards(treatment['rows']['private_id']['cards'],treatment['intro'])
        self.assertEqual(changed[0]['content'].replace(block+'\n\n','',1),base[0]['content'])
        self.assertEqual(changed[1:],base[1:])
        self.assertNotIn('private_id',changed[0]['content'])

    def test_actual_old_input_or_generated_content_drift_rejected(self):
        b = self.treatment()
        b['rows']['private_id']['cards'][0]['label'] = 'Altered example'
        with self.assertRaisesRegex(ValueError,'frozen draft'):
            build_messages(self.ob,b)
        ob = deepcopy(self.ob)
        ob.local_physical['profile']['numeracy'] = 'Low'
        with self.assertRaisesRegex(ValueError,'profile binding|old P/E'):
            build_messages(ob,self.bundle)

    def test_future_landmark_context_and_answer_field_rejected(self):
        for kind in ('landmark','context','answer'):
            b = self.treatment()
            if kind == 'landmark':
                b['rows']['private_id']['cards'][0]['landmarks'][0]['month'] = '2023-01'
            elif kind == 'context':
                b['rows']['private_id']['cards'][0]['context_facts'][0]['event_end'] = '2022-12-31'
            else:
                b['rows']['private_id']['Q9_mean'] = 5.0
            with self.assertRaises(ValueError):
                validate_bundle(b,[self.person],'2022-03',self.bundle['baseline']['news']['as_of'])

    def test_wrong_roster_start_age_or_provider_prompt_rejected(self):
        b = deepcopy(self.bundle)
        b['rows']['another'] = b['rows'].pop('private_id')
        with self.assertRaises(ValueError): validate_bundle(b,[self.person],'2022-03',self.bundle['baseline']['news']['as_of'])
        b = deepcopy(self.bundle); b['start_age'] = 12
        with self.assertRaises(ValueError): validate_bundle(b,[self.person],'2022-03',self.bundle['baseline']['news']['as_of'])
        with self.assertRaisesRegex(ValueError,'provider/prompt'):
            LifetimeDecision(prompt_version='wrong',lifetime_bundle=self.bundle)

    def test_three_arm_common_sample_and_paired_error_differences(self):
        rows = [{'real':x,'original':x-1,'common_episodes':x-.5,'age_matched_episodes':x,
                 'weight':1.,'profile':{'age_group':'Under 40'}} for x in (2.,3.,4.)]
        rows.append({'real':100.,'original':0.,'common_episodes':0.,'age_matched_episodes':None,'profile':{'age_group':'Over 60'}})
        scores = metrics(rows,bootstrap=20)
        self.assertEqual(scores['n_common'],3)
        self.assertEqual(scores['arms']['original']['distribution_W1_pp'],1.)
        self.assertEqual(scores['contrasts']['age_matched_episodes_minus_original']['median_absolute_error_pp']['change_pp'],-1.)
        self.assertEqual(scores['contrasts']['age_matched_episodes_minus_common_episodes']['distribution_W1_pp']['change_pp'],-.5)

    def test_invalid_q9_does_not_mask_valid_q8_or_accept_error_placeholder(self):
        self.assertEqual(point_value({'validation_status':'invalid','point_pct':4.,'llm':{'error':'q9_sum_99.0'}}),4.)
        self.assertIsNone(point_value({'validation_status':'error','point_pct':0.,'llm':{'error':'Timeout'}}))
        self.assertIsNone(point_value({'validation_status':'invalid','point_pct':0.,'llm':{'error':'JSONDecodeError'}}))

    def test_no_approval_or_completed_trial_never_dispatches(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder/'trial_manifest.json').write_text(json.dumps({'status':'offline_prepared_not_authorized'}))
            with self.assertRaisesRegex(ValueError,'confirmation'):
                execute(folder,folder,'')
            (folder/'trial_manifest.json').write_text(json.dumps({'status':'completed_pending_analysis'}))
            with self.assertRaisesRegex(ValueError,'confirmation'):
                execute(folder,folder,'prior authorization')


if __name__ == '__main__':
    unittest.main()
