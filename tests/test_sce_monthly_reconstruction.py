from copy import deepcopy
import unittest

import numpy as np
import pandas as pd

from studies.sce_inflation_expectations.experiments.monthly_reconstruction_inputs import (
    PastScoreCache, choose_core, prior_grid_allocation, resolve_draw, stratified_bands,
)
from studies.sce_inflation_expectations.news_quantity import random_quantities
from studies.sce_inflation_expectations.evaluation.heterogeneous_news import allocate


def example_core():
    pop={'personas':[
        {'agent_id':'a','weight':999,'attributes':{'education_group':'college','employment_status':'employed'}},
        {'agent_id':'b','weight':1,'attributes':{'education_group':'college','employment_status':'employed'}},
        {'agent_id':'c','weight':1,'attributes':{'education_group':'high_school','employment_status':'retired'}},
    ]}
    sampling={'persons':[{'agent_id':a,'stable_priority':i,'inclusion_probability_core_k':.001}
                         for a,i in [('a',5),('b',1),('c',3)]]}
    entry={'persons':[{'agent_id':a,'survey_entry_status':'entrant' if a=='c' else 'returning'} for a in ['a','b','c']]}
    weights={'a':2.,'b':3.,'c':None}
    allocation={'college|attached':{'frame_n':2,'allocated_n':1},
                'high_school|not_attached':{'frame_n':1,'allocated_n':1}}
    return pop,sampling,entry,weights,allocation


class MonthlyReconstructionTests(unittest.TestCase):
    def test_actual_cell_probability_and_missing_weight_are_explicit(self):
        args=example_core(); original=deepcopy(args)
        rows,stats=choose_core(*args)
        self.assertEqual([r['persona']['agent_id'] for r in rows],['b','c'])
        self.assertEqual(rows[0]['inclusion_probability'],.5)
        self.assertEqual(rows[0]['analysis_weight'],6.)
        self.assertEqual(rows[0]['persona']['weight'],1.)
        self.assertIsNone(rows[1]['analysis_weight'])
        self.assertFalse(rows[1]['weight_valid'])
        self.assertEqual(stats['high_school|not_attached']['actual_inclusion_probability'],1.)
        self.assertEqual(args,original)

    def test_no_current_outcome_or_delivered_weight_changes_selection(self):
        args=example_core(); baseline,_=choose_core(*args)
        for p in args[0]['personas']:
            p['weight']=77777;p['attributes']['current_q9']=100000
        rows,_=choose_core(*args)
        self.assertEqual([r['persona']['agent_id'] for r in baseline],[r['persona']['agent_id'] for r in rows])
        self.assertEqual([r['analysis_weight'] for r in baseline],[r['analysis_weight'] for r in rows])

    def test_wrong_grid_frame_is_not_silently_used(self):
        args=example_core();args[-1]['college|attached']['frame_n']=3
        with self.assertRaises(ValueError):choose_core(*args)

    def test_unregistered_unknown_cell_is_not_imputed_to_a_known_cell(self):
        args=example_core();args[0]['personas'][-1]['attributes']['employment_status']='unknown'
        with self.assertRaises(ValueError):choose_core(*args)

    def test_finite_wave_census_has_zero_sampling_tolerance(self):
        rows=[]
        for i,x in enumerate([1.,2.,9.]):
            rows.append(dict(date=202504,userid=i,weight=1.,_EDU_CAT='College',employment='employed',_point=x,_center=x))
        allocation={'college|attached':{'frame_n':3,'allocated_n':3}}
        bands,info=stratified_bands(pd.DataFrame(rows),allocation,seed=5,draws=20)
        self.assertEqual(bands,{'q8':[2.,2.],'q9':[2.,2.]})
        self.assertEqual(info['q9']['past_reference']['median_pp'],2.)

    def test_finite_sampling_mismatch_is_rejected(self):
        rows=pd.DataFrame([dict(date=202504,userid=1,weight=1.,_EDU_CAT='College',employment='employed',_point=3.,_center=3.)])
        with self.assertRaises(ValueError):stratified_bands(rows,{'college|attached':{'frame_n':2,'allocated_n':1}},seed=5)

    def test_donor_does_not_create_own_history_or_a_real_previous_answer(self):
        row={'q8':3.,'q9_bins':[10.]*10,'synthetic_fields':['q8','q9'],'donor_period':202504,
             'own_observed':{},'older_own_memory':{},'matching':{}}
        past=pd.DataFrame([dict(userid=1,date=202504,_center=7.,survey_date='2025-04-12')])
        r=resolve_draw(row,past,99,202505)
        self.assertEqual(r['own_history_centers'],[])
        self.assertFalse(r['observed_previous_q9'])
        self.assertFalse(r['observed_previous_q8'])
        self.assertEqual(r['comparison_reference_day'],'2025-04-30')
        self.assertIn('not_actual_survey',r['comparison_day_source'])

    def test_real_history_remains_own_and_keeps_interview_reference(self):
        row={'q8':3.,'q9_bins':[10.]*10,'synthetic_fields':[],'donor_period':None,
             'own_observed':{'q8':{'source_period':202504},'q9':{'source_period':202504}},
             'older_own_memory':{},'matching':{}}
        past=pd.DataFrame([dict(userid=1,date=202503,_center=7.,survey_date='2025-03-12'),
                           dict(userid=1,date=202504,_center=3.,survey_date='2025-04-15')])
        r=resolve_draw(row,past,1,202505)
        self.assertEqual(len(r['own_history_centers']),2)
        self.assertTrue(r['observed_previous_q9'])
        self.assertEqual(r['comparison_reference_day'],'2025-04-15')

    def test_memoization_is_rejected_before_any_target_vector_is_scored(self):
        cache=PastScoreCache()
        with self.assertRaises(ValueError):cache.score(pd.DataFrame([dict(date=202505)]),202505)
        self.assertEqual(cache.new_fits,0)

    def test_generic_news_quota_preserves_old_96_rule(self):
        ids=[f'person{i}' for i in range(96)]
        self.assertEqual(random_quantities(ids,7),allocate(ids,np.full((96,6),1/6),7))

    def test_generic_news_quota_handles_512_and_full_frame_without_identity_loss(self):
        from collections import Counter
        for n in [1,95,512,1096]:
            ids=[f'person{i}' for i in range(n)]
            result=random_quantities(ids,7)
            self.assertEqual(set(result),set(ids))
            self.assertEqual(result,random_quantities(list(reversed(ids)),7))
            counts=Counter(result.values())
            for level,fraction in [(3,48/96),(8,28/96),(20,20/96)]:
                self.assertLess(abs(counts[level]-n*fraction),1+1e-12)

    def test_first_target_month_can_use_past_grid_outside_the_catalogue(self):
        prior=pd.DataFrame([{'_EDU_CAT':'College','employment':'employed','weight':1.} for _ in range(600)])
        result=prior_grid_allocation(prior)
        self.assertEqual(sum(x['allocated_n'] for x in result.values()),512)
        self.assertEqual(result['college|attached'],{'frame_n':600,'allocated_n':512})
        registered={'allocation':{'fixed':{'frame_n':1,'allocated_n':1}}}
        self.assertIs(prior_grid_allocation(prior,registered),registered['allocation'])
